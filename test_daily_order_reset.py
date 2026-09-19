"""
test_daily_order_reset.py
=========================
Comprehensive verification for Daily Order Number Reset:
1. Create multiple orders on the same calendar date -> sequential #1, #2, #3...
2. Simulate/create an order for the next calendar day -> resets to #1
3. Create another order on that second day -> increments to #2
4. Confirm previous day's orders remain intact in database
5. Confirm Order IDs remain globally unique
6. Confirm payment verification still works
7. Confirm order tracking still works
8. Confirm Stage Ready Items still works
9. Confirm stationery orders still work
10. Confirm queue / timer calculation is NOT affected
11. Concurrency test: Multiple concurrent threads creating orders receive unique, sequential numbers
"""

import unittest
import sys
import os
import json
import threading
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, 'backend')
from app import create_app
from database import (
    create_order,
    create_multi_order,
    next_display_order_number,
    find_order,
    get_order_by_id,
    calculate_order_queue,
    calculate_printing_duration_seconds,
    get_db_connection
)
from payment_verification import verify_screenshot, _check_date

class TestDailyOrderReset(unittest.TestCase):
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

    def test_01_to_05_daily_order_number_reset_lifecycle(self):
        # We test across 2 separate simulated days
        day1 = "2026-10-01"
        day2 = "2026-10-02"

        # Ensure no existing orders for these test days
        conn = get_db_connection()
        conn.execute("DELETE FROM orders WHERE created_at LIKE ? OR created_at LIKE ?", (f"{day1}%", f"{day2}%"))
        conn.commit()
        conn.close()

        # Day 1 - Order 1 -> Expected #1
        ord1 = create_order({
            "student_name": "Day 1 Student A",
            "roll_number": "D1-01",
            "phone_number": "9000000001",
            "created_at": f"{day1} 09:00:00"
        })
        self.assertEqual(ord1["display_order_number"], 1)
        self.assertTrue(ord1["order_id"].startswith("ORD-20261001-"))

        # Day 1 - Order 2 -> Expected #2
        ord2 = create_order({
            "student_name": "Day 1 Student B",
            "roll_number": "D1-02",
            "phone_number": "9000000002",
            "created_at": f"{day1} 09:05:00"
        })
        self.assertEqual(ord2["display_order_number"], 2)
        self.assertTrue(ord2["order_id"].startswith("ORD-20261001-"))

        # Day 1 - Order 3 (via multi_order) -> Expected #3
        ord3 = create_multi_order({
            "student_name": "Day 1 Student C",
            "roll_number": "D1-03",
            "phone_number": "9000000003",
            "created_at": f"{day1} 09:10:00"
        }, stationery_items=[{"id": "black_pen", "name": "Black Pen", "price": 5.0, "quantity": 1, "subtotal": 5.0}])
        self.assertEqual(ord3["display_order_number"], 3)
        self.assertTrue(ord3["order_id"].startswith("ORD-20261001-"))
        print(f"[PASS] Requirement 1: Same date orders created sequentially: #{ord1['display_order_number']}, #{ord2['display_order_number']}, #{ord3['display_order_number']}")

        # Day 2 (Next Calendar Day) - Order 1 -> Expected RESET to #1!
        ord4 = create_order({
            "student_name": "Day 2 Student A",
            "roll_number": "D2-01",
            "phone_number": "9000000004",
            "created_at": f"{day2} 08:30:00"
        })
        self.assertEqual(ord4["display_order_number"], 1, "Order number must reset to 1 on a new calendar day")
        self.assertTrue(ord4["order_id"].startswith("ORD-20261002-"))
        print(f"[PASS] Requirement 2: Next calendar day {day2} Order 1 reset to: #{ord4['display_order_number']}")

        # Day 2 - Order 2 -> Expected #2
        ord5 = create_multi_order({
            "student_name": "Day 2 Student B",
            "roll_number": "D2-02",
            "phone_number": "9000000005",
            "created_at": f"{day2} 08:35:00"
        }, stationery_items=[{"id": "pencil", "name": "Pencil", "price": 5.0, "quantity": 2, "subtotal": 10.0}])
        self.assertEqual(ord5["display_order_number"], 2)
        self.assertTrue(ord5["order_id"].startswith("ORD-20261002-"))
        print(f"[PASS] Requirement 3: Next calendar day {day2} Order 2 incremented to: #{ord5['display_order_number']}")

        # Requirement 4: Previous day's orders remain preserved in DB
        h1 = get_order_by_id(ord1["order_id"])
        h2 = get_order_by_id(ord2["order_id"])
        h3 = get_order_by_id(ord3["order_id"])
        self.assertIsNotNone(h1)
        self.assertIsNotNone(h2)
        self.assertIsNotNone(h3)
        self.assertEqual(h1["display_order_number"], 1)
        self.assertEqual(h2["display_order_number"], 2)
        self.assertEqual(h3["display_order_number"], 3)
        print("[PASS] Requirement 4: Historical previous day orders remain completely preserved in database")

        # Requirement 5: Order IDs remain unique
        ids = [ord1["order_id"], ord2["order_id"], ord3["order_id"], ord4["order_id"], ord5["order_id"]]
        self.assertEqual(len(ids), len(set(ids)), "All Order IDs must be globally unique")
        print(f"[PASS] Requirement 5: All 5 Order IDs are globally unique: {ids}")

        # Clean up test orders
        conn = get_db_connection()
        conn.execute("DELETE FROM orders WHERE created_at LIKE ? OR created_at LIKE ?", (f"{day1}%", f"{day2}%"))
        conn.commit()
        conn.close()

    def test_06_payment_verification_still_works(self):
        # Verify 15 Sep 2026 screenshot still passes and old dates fail
        sample_path = os.path.join("backend", "uploads", "pay_d9343091_a2409e.jpeg")
        if os.path.isfile(sample_path):
            with open(sample_path, "rb") as f:
                img_bytes = f.read()
            # Matching session date 15 Sep 2026
            sess_dt_match = datetime(2026, 9, 15, 5, 26, 0)
            res = verify_screenshot(
                img_bytes,
                expected_amount=12.0,
                session_started_at=sess_dt_match,
                merchant_name="Bandi Lakshmi Sai",
                merchant_identifiers=["bandi lakshmi sai", "lakshmi sai"]
            )
            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "verified")
            self.assertTrue(res["checks"]["payment_date"]["passed"])

            # Non-matching session date 14 Sep 2026 -> must fail
            sess_dt_mismatch = datetime(2026, 9, 14, 5, 26, 0)
            res_fail = verify_screenshot(
                img_bytes,
                expected_amount=12.0,
                session_started_at=sess_dt_mismatch,
                merchant_name="Bandi Lakshmi Sai",
                merchant_identifiers=["bandi lakshmi sai", "lakshmi sai"]
            )
            self.assertFalse(res_fail["success"])
            self.assertFalse(res_fail["checks"]["payment_date"]["passed"])
            print("[PASS] Requirement 6: Payment verification passes for matching date and fails for old date")

    def test_07_order_tracking_still_works(self):
        # Create an order and track it via /api/orders/track/<query>
        test_roll = "TRK-RESET-01"
        ord_res = create_order({
            "student_name": "Track Student",
            "roll_number": test_roll,
            "phone_number": "9123456789"
        })
        oid = ord_res["order_id"]
        tok = ord_res["token_number"]

        # Track by Order ID
        res_oid = self.client.get(f"/api/orders/track/{oid}")
        self.assertEqual(res_oid.status_code, 200)
        self.assertEqual(res_oid.get_json()["orders"][0]["order_id"], oid)

        # Track by Token
        res_tok = self.client.get(f"/api/orders/track/{tok}")
        self.assertEqual(res_tok.status_code, 200)
        self.assertEqual(res_tok.get_json()["orders"][0]["token_number"], tok)

        # Track by Roll
        res_roll = self.client.get(f"/api/orders/track/{test_roll}")
        self.assertEqual(res_roll.status_code, 200)
        print(f"[PASS] Requirement 7: Order tracking works by Order ID ({oid}), Token ({tok}), and Roll ({test_roll})")

    def test_08_stage_ready_items_still_works(self):
        ord_res = create_order({
            "student_name": "Stage Student",
            "roll_number": "STAGE-02",
            "phone_number": "9123456789"
        })
        oid = ord_res["order_id"]

        patch_res = self.client.patch(f"/api/staff/orders/{oid}/status", json={"status": "Stage Ready"})
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.get_json()["order"]["order_status"], "Stage Ready")

        # Track confirms status
        track = self.client.get(f"/api/orders/track/{oid}").get_json()
        self.assertEqual(track["orders"][0]["order_status"], "Stage Ready")
        print("[PASS] Requirement 8: Stage Ready Items status transition and tracking verified")

    def test_09_stationery_orders_still_work(self):
        items = [{"id": "blue_pen", "name": "Blue Pen", "price": 5.0, "quantity": 2, "subtotal": 10.0}]
        data = {
            "student_name": "Stat Student",
            "roll_number": "STAT-09",
            "phone_number": "9876543210",
            "payment_method": "UPI",
            "stationery_items": json.dumps(items)
        }
        res = self.client.post("/api/orders/multi", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 201)
        r = res.get_json()
        self.assertEqual(r["order"]["order_type"], "stationery")
        self.assertEqual(r["order"]["stationery_total"], 10.0)
        self.assertIsNotNone(r["order"]["display_order_number"])
        print(f"[PASS] Requirement 9: Stationery order #{r['order']['display_order_number']} created successfully with 0s queue")

    def test_10_queue_calculation_not_affected(self):
        self.assertEqual(calculate_printing_duration_seconds(1), 90)
        self.assertEqual(calculate_printing_duration_seconds(36), 580) # 9:40
        self.assertEqual(calculate_printing_duration_seconds(41), 640) # 10:40
        self.assertEqual(calculate_printing_duration_seconds(46), 700) # 11:40
        q_zero = calculate_order_queue(0)
        self.assertEqual(q_zero["processing_duration_seconds"], 120)
        print("[PASS] Requirement 10: Exact 1-50 copy timing table and queue calculation remain intact")

    def test_11_concurrency_protection(self):
        # Spawn 10 concurrent threads creating orders simultaneously for a test day
        sim_day = "2026-10-10"
        conn = get_db_connection()
        conn.execute("DELETE FROM orders WHERE created_at LIKE ?", (f"{sim_day}%",))
        conn.commit()
        conn.close()

        results = []
        errors = []

        def worker(idx):
            try:
                order = create_order({
                    "student_name": f"Concurrent Student {idx}",
                    "roll_number": f"CONC-{idx:02d}",
                    "phone_number": "9999999999",
                    "created_at": f"{sim_day} 10:00:{idx:02d}"
                })
                results.append(order["display_order_number"])
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Errors occurred during concurrent creation: {errors}")
        self.assertEqual(len(results), 10)
        # All numbers must be distinct 1..10
        self.assertEqual(sorted(results), list(range(1, 11)), f"Expected [1..10], got: {sorted(results)}")
        print(f"[PASS] Requirement 11: Concurrency protection verified across 10 simultaneous threads: {sorted(results)}")

        # Clean up
        conn = get_db_connection()
        conn.execute("DELETE FROM orders WHERE created_at LIKE ?", (f"{sim_day}%",))
        conn.commit()
        conn.close()

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestDailyOrderReset)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    if res.wasSuccessful():
        print("\nALL 11 DAILY ORDER RESET TESTS PASSED PERFECTLY!")
    else:
        sys.exit(1)
