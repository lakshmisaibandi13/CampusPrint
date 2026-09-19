"""
test_stationery_features.py — Verification of Stationery, Smart Queue & Tracking
"""
import unittest, json, io, sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from app import create_app
from config import Config
from database import (
    calculate_printing_duration_seconds,
    calculate_order_queue,
    get_db_connection,
    _serialize_order
)

def _make_pdf(num_pages: int) -> bytes:
    try:
        import pymupdf
        doc = pymupdf.open()
        for _ in range(num_pages):
            doc.new_page()
        return doc.tobytes()
    except Exception:
        return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF\n"

class TestStationeryAndQueue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def test_01_stationery_catalog(self):
        res = self.client.get("/api/stationery")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        items = data["items"]
        self.assertEqual(len(items), 13)
        price_map = {it["id"]: it["price"] for it in items}
        self.assertEqual(price_map["black_pen"], 5)
        self.assertEqual(price_map["blue_pen"], 5)
        self.assertEqual(price_map["red_pen"], 5)
        self.assertEqual(price_map["pencil"], 5)
        self.assertEqual(price_map["eraser"], 5)
        self.assertEqual(price_map["sharpener"], 3)
        self.assertEqual(price_map["plain_small_notebook"], 20)
        self.assertEqual(price_map["plain_long_notebook"], 50)
        self.assertEqual(price_map["ruled_long_notebook"], 50)
        self.assertEqual(price_map["assignment_booklet"], 15)
        self.assertEqual(price_map["record_book"], 90)
        self.assertEqual(price_map["record_paper"], 1)
        self.assertEqual(price_map["a4_sheet"], 1)
        print("[PASS] test_01  stationery catalog returns all 13 items with exact prices")

    def test_02_printing_duration_table(self):
        # 1-5 pages: 90s (1m 30s)
        self.assertEqual(calculate_printing_duration_seconds(1), 90)
        self.assertEqual(calculate_printing_duration_seconds(5), 90)
        # 6-10 pages: 180s (3m)
        self.assertEqual(calculate_printing_duration_seconds(6), 180)
        self.assertEqual(calculate_printing_duration_seconds(10), 180)
        # 11-15 pages: 240s (4m)
        self.assertEqual(calculate_printing_duration_seconds(15), 240)
        # 16-20 pages: 360s (6m)
        self.assertEqual(calculate_printing_duration_seconds(20), 360)
        # 21-25 pages: 420s (7m)
        self.assertEqual(calculate_printing_duration_seconds(25), 420)
        # 26-30 pages: 480s (8m)
        self.assertEqual(calculate_printing_duration_seconds(30), 480)
        # 31-35 pages: 540s (9m)
        self.assertEqual(calculate_printing_duration_seconds(35), 540)
        # 36-40 pages: 580s (9m 40s)
        self.assertEqual(calculate_printing_duration_seconds(40), 580)
        # 41-45 pages: 640s (10m 40s)
        self.assertEqual(calculate_printing_duration_seconds(45), 640)
        # 46-50 pages: 700s (11m 40s)
        self.assertEqual(calculate_printing_duration_seconds(50), 700)
        # Stationery only (0 pages): 0s
        self.assertEqual(calculate_printing_duration_seconds(0), 0)
        print("[PASS] test_02  printing duration table matches specification exactly")

    def test_03_stationery_only_order(self):
        stationery_payload = [
            {"id": "black_pen", "name": "Black Pen", "price": 5, "quantity": 2, "subtotal": 10},
            {"id": "record_book", "name": "Record Book", "price": 90, "quantity": 1, "subtotal": 90},
        ]
        data = {
            "student_name": "Stationery Student",
            "roll_number": "ST-99",
            "phone_number": "9876543210",
            "payment_method": "UPI",
            "stationery_items": json.dumps(stationery_payload)
        }
        res = self.client.post("/api/orders/multi", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 201)
        resp = res.get_json()
        self.assertTrue(resp["success"])
        order = resp["order"]
        self.assertEqual(order["order_type"], "stationery")
        self.assertEqual(order["total_price"], 100.0)
        self.assertEqual(order["stationery_total"], 100.0)
        self.assertEqual(order["printing_total"], 0.0)
        self.assertEqual(order["processing_duration_seconds"], 0)
        self.assertIsNotNone(order["display_order_number"])
        self.assertTrue(len(resp["stationery_items"]) == 2)
        print(f"[PASS] test_03  stationery-only order created  #{order['display_order_number']}  total=Rs {order['total_price']}")

    def test_04_mixed_order(self):
        pdf_bytes = _make_pdf(4)
        stationery_payload = [
            {"id": "blue_pen", "name": "Blue Pen", "price": 5, "quantity": 3, "subtotal": 15},
            {"id": "plain_small_notebook", "name": "Plain Small Notebook", "price": 20, "quantity": 1, "subtotal": 20}
        ]
        # 4 pages * 2 (BW) * 1 copy = 8 printing. Stationery = 15 + 20 = 35. Grand Total = 43.
        data = {
            "student_name": "Mixed Student",
            "roll_number": "MX-101",
            "phone_number": "9123456780",
            "payment_method": "UPI",
            "stationery_items": json.dumps(stationery_payload),
            "document_0": (io.BytesIO(pdf_bytes), "sample_notes.pdf"),
            "copies_0": "1",
            "color_mode_0": "bw",
            "side_mode_0": "single"
        }
        res = self.client.post("/api/orders/multi", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 201)
        resp = res.get_json()
        self.assertTrue(resp["success"])
        order = resp["order"]
        self.assertEqual(order["order_type"], "mixed")
        self.assertEqual(order["printing_total"], 8.0)
        self.assertEqual(order["stationery_total"], 35.0)
        self.assertEqual(order["total_price"], 43.0)
        self.assertEqual(order["print_pages_total"], 4)
        self.assertEqual(order["processing_duration_seconds"], 90)
        self.assertIsNotNone(order["readable_collection_time"])
        print(f"[PASS] test_04  mixed order created  #{order['display_order_number']}  print=Rs {order['printing_total']}  stationery=Rs {order['stationery_total']}  total=Rs {order['total_price']}")

    def test_05_track_order_endpoint(self):
        # Track previous order MX-101
        res = self.client.get("/api/orders/track/MX-101")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        orders = data["orders"]
        self.assertGreaterEqual(len(orders), 1)
        matched = orders[0]
        self.assertEqual(matched["roll_number"], "MX-101")
        self.assertEqual(matched["order_type"], "mixed")
        self.assertIn("stationery_items", matched)
        self.assertEqual(len(matched["stationery_items"]), 2)
        print(f"[PASS] test_05  tracking returns enriched mixed order with stationery items & collection time")

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestStationeryAndQueue)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    if res.wasSuccessful():
        print("\nALL STATIONERY & QUEUE TESTS PASSED!")
    else:
        sys.exit(1)
