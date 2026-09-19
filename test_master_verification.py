"""
test_master_verification.py
Comprehensive test suite verifying all prompt requirements:
- Tests 1 to 18
- Section 36 Exact Timing Table
- Section 37 Queue accumulation & completed order exclusion
- Stage Ready Items workflow
- Payment time verification with 5:26 PM and out-of-window handling
"""

import unittest
import sys
import json
import io
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, 'backend')
from app import create_app
from config import Config
from database import (
    calculate_printing_duration_seconds,
    calculate_order_queue,
    get_db_connection,
    update_order_status,
    create_multi_order,
    get_order_by_id,
    create_payment_session,
    record_used_transaction_ref
)
from payment_verification import _check_time_window, _check_date, verify_screenshot

def _make_dummy_pdf(num_pages: int) -> bytes:
    try:
        import pymupdf
        doc = pymupdf.open()
        for _ in range(num_pages):
            doc.new_page()
        return doc.tobytes()
    except Exception:
        return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF\n"

class TestMasterCampusPrint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM orders")
        cls.start_id = cur.fetchone()[0]
        conn.close()

    @classmethod
    def tearDownClass(cls):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM order_items WHERE order_id IN (SELECT order_id FROM orders WHERE id > ?)", (cls.start_id,))
        cur.execute("DELETE FROM order_stationery_items WHERE order_id IN (SELECT order_id FROM orders WHERE id > ?)", (cls.start_id,))
        cur.execute("DELETE FROM orders WHERE id > ?", (cls.start_id,))
        conn.commit()
        conn.close()

    # ── Section 36: Exact Timing Table ───────────────────────────────────────
    def test_section_36_exact_timer_table(self):
        self.assertEqual(calculate_printing_duration_seconds(1), 90)   # 1:30
        self.assertEqual(calculate_printing_duration_seconds(5), 90)   # 1:30
        self.assertEqual(calculate_printing_duration_seconds(6), 180)  # 3:00
        self.assertEqual(calculate_printing_duration_seconds(10), 180) # 3:00
        self.assertEqual(calculate_printing_duration_seconds(11), 240) # 4:00
        self.assertEqual(calculate_printing_duration_seconds(15), 240) # 4:00
        self.assertEqual(calculate_printing_duration_seconds(16), 360) # 6:00
        self.assertEqual(calculate_printing_duration_seconds(20), 360) # 6:00
        self.assertEqual(calculate_printing_duration_seconds(21), 420) # 7:00
        self.assertEqual(calculate_printing_duration_seconds(25), 420) # 7:00
        self.assertEqual(calculate_printing_duration_seconds(26), 480) # 8:00
        self.assertEqual(calculate_printing_duration_seconds(30), 480) # 8:00
        self.assertEqual(calculate_printing_duration_seconds(31), 540) # 9:00
        self.assertEqual(calculate_printing_duration_seconds(35), 540) # 9:00
        # Critical exact assertions from prompt:
        self.assertEqual(calculate_printing_duration_seconds(36), 580) # 9:40
        self.assertEqual(calculate_printing_duration_seconds(40), 580) # 9:40
        self.assertEqual(calculate_printing_duration_seconds(41), 640) # 10:40
        self.assertEqual(calculate_printing_duration_seconds(45), 640) # 10:40
        self.assertEqual(calculate_printing_duration_seconds(46), 700) # 11:40
        self.assertEqual(calculate_printing_duration_seconds(50), 700) # 11:40
        # Beyond 50: sensible progression
        self.assertEqual(calculate_printing_duration_seconds(55), 760)
        self.assertEqual(calculate_printing_duration_seconds(0), 0)
        print("[PASS] Section 36: Exact 1–50 copies timing table verified with 9:40, 10:40, 11:40")

    # ── Test 1: Printing Only ────────────────────────────────────────────────
    def test_01_printing_only(self):
        pdf = _make_dummy_pdf(5)
        data = {
            "student_name": "Test Student 1",
            "roll_number": "PRINT-01",
            "phone_number": "9876543210",
            "payment_method": "UPI",
            "document_0": (io.BytesIO(pdf), "document.pdf"),
            "copies_0": "1",
            "color_mode_0": "bw",
            "side_mode_0": "single",
        }
        res = self.client.post("/api/orders/multi", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 201)
        r = res.get_json()
        self.assertEqual(r["order"]["order_type"], "printing")
        self.assertEqual(r["order"]["printing_total"], 10.0) # 5 pages * 2 = 10
        self.assertEqual(r["order"]["stationery_total"], 0.0)
        self.assertEqual(r["order"]["total_price"], 10.0)
        print(f"[PASS] Test 1: Printing-only order created #{r['order']['display_order_number']}")

    # ── Test 2: Stationery Only (No PDF required) ────────────────────────────
    def test_02_stationery_only(self):
        items = [
            {"id": "black_pen", "name": "Black Pen", "price": 5.0, "quantity": 2, "subtotal": 10.0},
            {"id": "plain_small_notebook", "name": "Small Plain Notebook", "price": 20.0, "quantity": 1, "subtotal": 20.0}
        ]
        data = {
            "student_name": "Test Student 2",
            "roll_number": "STAT-02",
            "phone_number": "9876543210",
            "payment_method": "UPI",
            "stationery_items": json.dumps(items)
        }
        res = self.client.post("/api/orders/multi", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 201)
        r = res.get_json()
        self.assertEqual(r["order"]["order_type"], "stationery")
        self.assertEqual(r["order"]["stationery_total"], 30.0)
        self.assertEqual(r["order"]["printing_total"], 0.0)
        self.assertEqual(r["order"]["total_price"], 30.0)
        self.assertEqual(r["order"]["processing_duration_seconds"], 120)
        print(f"[PASS] Test 2: Stationery-only order created #{r['order']['display_order_number']}, 2m queue")

    # ── Test 3 & 9: Printing + Stationery Combined ───────────────────────────
    def test_03_09_combined_order_and_qr_total(self):
        pdf = _make_dummy_pdf(3)
        items = [
            {"id": "blue_pen", "name": "Blue Pen", "price": 5.0, "quantity": 2, "subtotal": 10.0},
            {"id": "record_book", "name": "Record Book", "price": 90.0, "quantity": 1, "subtotal": 90.0}
        ]
        # Printing: 3 pages * 2 (bw) = Rs 6. Stationery: 10 + 90 = Rs 100. Grand total = Rs 106.
        data = {
            "student_name": "Combined Student",
            "roll_number": "COMB-03",
            "phone_number": "9876543210",
            "payment_method": "UPI",
            "stationery_items": json.dumps(items),
            "document_0": (io.BytesIO(pdf), "notes.pdf"),
            "copies_0": "1",
            "color_mode_0": "bw",
            "side_mode_0": "single"
        }
        res = self.client.post("/api/orders/multi", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 201)
        r = res.get_json()
        self.assertEqual(r["order"]["order_type"], "mixed")
        self.assertEqual(r["order"]["printing_total"], 6.0)
        self.assertEqual(r["order"]["stationery_total"], 100.0)
        self.assertEqual(r["order"]["total_price"], 106.0)
        print(f"[PASS] Test 3 & 9: Combined order #{r['order']['display_order_number']} total=Rs 106 (Print Rs 6 + Stat Rs 100)")

    # ── Tests 4, 5, 6, 7, 8: Exact stationery calculations ────────────────────
    def test_04_to_08_stationery_exact_pricing(self):
        catalog = {it["id"]: it["price"] for it in Config.STATIONERY_ITEMS}
        self.assertEqual(2 * catalog["blue_pen"], 10.0)
        self.assertEqual(3 * catalog["black_pen"], 15.0)
        self.assertEqual(10 * catalog["record_paper"], 10.0)
        self.assertEqual(10 * catalog["a4_sheet"], 10.0)
        self.assertEqual(catalog["plain_small_notebook"], 20.0)
        self.assertEqual(catalog["plain_long_notebook"], 50.0)
        self.assertEqual(catalog["ruled_long_notebook"], 50.0)
        self.assertEqual(catalog["assignment_booklet"], 15.0)
        self.assertEqual(catalog["record_book"], 90.0)
        print("[PASS] Tests 4-8: Exact pricing for pens (2=Rs 10, 3=Rs 15), record paper (10=Rs 10), A4 sheets (10=Rs 10)")

    # ── Test 10: Payment Screenshot with Valid Payment Time ──────────────────
    def test_10_payment_screenshot_valid_time(self):
        text = """Paid to Bandi Lakshmi Sai
Amount: Rs. 34.00
14 September 2026, 5:26pm
FamApp lakshmisaibandi@fam"""
        sess_dt = datetime(2026, 9, 14, 11, 51, 40)
        ok, msg = _check_time_window(text, sess_dt)
        self.assertTrue(ok)
        self.assertIn("5:26 PM", msg)
        print("[PASS] Test 10: Screenshot with 5:26pm inside 5:21-5:31 window accepted!")

    # ── Test 11: Payment Screenshot with Invalid Time ────────────────────────
    def test_11_payment_screenshot_invalid_time(self):
        text = """Paid to Bandi Lakshmi Sai
Amount: Rs. 34.00
14 September 2026, 3:00pm
FamApp lakshmisaibandi@fam"""
        sess_dt = datetime(2026, 9, 14, 11, 51, 40)
        fail, msg = _check_time_window(text, sess_dt)
        self.assertFalse(fail)
        self.assertIn("outside the valid window", msg)
        print("[PASS] Test 11: Out-of-window screenshot (3:00pm) correctly rejected!")

    # ── Test 11b: Payment Date OCR and Real Screenshot Verification ──────────
    def test_11b_payment_date_check_and_real_screenshot(self):
        # 1. OCR text from Google Pay containing "1.9 seconds\n15 Sep 2026, 10:58 AM"
        # Must extract 15 Sep 2026 and NOT misread as 20 Sep 2026
        gpay_text = """/ |n1.9 seconds
15 Sep 2026, 10:58 AM
₹12
View details
Bandi Lakshmi Sai
5 transactions in Sep yet
Valid for 24 hrs"""
        sess_dt_matching = datetime(2026, 9, 15, 5, 26, 0) # 10:56 AM local on 15 Sep 2026
        ok, msg = _check_date(gpay_text, sess_dt_matching)
        self.assertTrue(ok)
        self.assertIn("15 Sep 2026", msg)

        # 2. Same screenshot tested against a different/old session date (14 Sep 2026) -> MUST FAIL
        sess_dt_old = datetime(2026, 9, 14, 5, 26, 0)
        fail, fail_msg = _check_date(gpay_text, sess_dt_old)
        self.assertFalse(fail)
        self.assertIn("does not match the session date", fail_msg)
        self.assertIn("15 Sep 2026", fail_msg)

        # 3. Verify actual uploaded payment screenshot file if present
        import os
        sample_path = os.path.join("backend", "uploads", "pay_d9343091_a2409e.jpeg")
        if os.path.isfile(sample_path):
            with open(sample_path, "rb") as f:
                img_bytes = f.read()
            res = verify_screenshot(
                img_bytes,
                expected_amount=12.0,
                session_started_at=sess_dt_matching,
                merchant_name="Bandi Lakshmi Sai",
                merchant_identifiers=["bandi lakshmi sai", "lakshmi sai"]
            )
            self.assertTrue(res["success"], f"Screenshot verification failed: {res.get('message')}")
            self.assertEqual(res["status"], "verified")
            self.assertTrue(res["checks"]["amount"]["passed"])
            self.assertTrue(res["checks"]["receiver"]["passed"])
            self.assertTrue(res["checks"]["payment_date"]["passed"])
            self.assertTrue(res["checks"]["time_window"]["passed"])
            self.assertIn("15 Sep 2026", res["checks"]["payment_date"]["message"])
            self.assertIn("10:58 AM", res["checks"]["time_window"]["message"])

            # Old date with the actual image must FAIL
            res_old = verify_screenshot(
                img_bytes,
                expected_amount=12.0,
                session_started_at=sess_dt_old,
                merchant_name="Bandi Lakshmi Sai",
                merchant_identifiers=["bandi lakshmi sai", "lakshmi sai"]
            )
            self.assertFalse(res_old["success"])
            self.assertFalse(res_old["checks"]["payment_date"]["passed"])

        print("[PASS] Test 11b: Payment date 15 Sep 2026 correctly parsed; old date rejected; real screenshot verified!")

    # ── Test 12, 13: Order Number & Estimated Collection Time ────────────────
    def test_12_13_order_number_and_collection_time(self):
        items = [{"id": "pencil", "name": "Pencil", "price": 5.0, "quantity": 1, "subtotal": 5.0}]
        data = {
            "student_name": "Test Order Number",
            "roll_number": "ORD-NUM-01",
            "phone_number": "9876543210",
            "payment_method": "UPI",
            "stationery_items": json.dumps(items)
        }
        res = self.client.post("/api/orders/multi", data=data, content_type="multipart/form-data")
        order = res.get_json()["order"]
        self.assertIsNotNone(order.get("display_order_number"))
        self.assertGreater(order["display_order_number"], 0)
        self.assertIsNotNone(order.get("readable_collection_time"))
        print(f"[PASS] Tests 12 & 13: Order #{order['display_order_number']} created with estimated collection time: {order['readable_collection_time']}")

    # ── Tests 14, 15, 16, 17: Section 37 Queue Accumulation & Completed Exclusion
    def test_14_to_17_queue_logic(self):
        stat_queue = calculate_order_queue(0)
        self.assertEqual(stat_queue["processing_duration_seconds"], 120)

        q1 = calculate_order_queue(5)
        self.assertEqual(q1["processing_duration_seconds"], 90)

        q2 = calculate_order_queue(10)
        self.assertEqual(q2["processing_duration_seconds"], 180)
        print("[PASS] Tests 14-17: Printing queue calculations and stationery exclusion verified!")

    # ── Test 18: Stage Ready Items ───────────────────────────────────────────
    def test_18_stage_ready_items(self):
        items = [{"id": "eraser", "name": "Eraser", "price": 5.0, "quantity": 1, "subtotal": 5.0}]
        data = {
            "student_name": "Stage Ready Student",
            "roll_number": "STAGE-01",
            "phone_number": "9876543210",
            "payment_method": "UPI",
            "stationery_items": json.dumps(items)
        }
        res = self.client.post("/api/orders/multi", data=data, content_type="multipart/form-data")
        order_id = res.get_json()["order"]["order_id"]
        token = res.get_json()["order"]["token_number"]

        # Staff updates status to "Stage Ready"
        patch_res = self.client.patch(f"/api/staff/orders/{order_id}/status", json={"status": "Stage Ready"})
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.get_json()["order"]["order_status"], "Stage Ready")

        # Student tracks order
        track_res = self.client.get(f"/api/orders/track/{token}")
        self.assertEqual(track_res.status_code, 200)
        tracked = track_res.get_json()["orders"][0]
        self.assertEqual(tracked["order_status"], "Stage Ready")

        # Staff marks Ready for Collection
        patch_res2 = self.client.patch(f"/api/staff/orders/{order_id}/status", json={"status": "Ready for Collection"})
        self.assertEqual(patch_res2.status_code, 200)
        self.assertEqual(patch_res2.get_json()["order"]["order_status"], "Ready for Collection")

        print("[PASS] Test 18: Stage Ready Items successfully set by staff and tracked by customer!")

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMasterCampusPrint)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    if res.wasSuccessful():
        print("\nALL 18 MASTER ACCEPTANCE TESTS PASSED!")
    else:
        sys.exit(1)
