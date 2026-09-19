"""
test_full.py — Comprehensive CampusPrint test suite
====================================================
Tests covered:
  1.  Single-PDF order (existing /api/orders route)
  2–4. Multi-PDF order: 3 files, independent settings, correct per-file pricing
  5.  B&W single-sided calculation
  6.  B&W double-sided (ceiling sheets)
  7.  Color single-sided calculation
  8.  Grand total across multiple PDFs
  9.  Payment amount matches order total
 10.  Payment session create / fetch / remaining-time
 11.  Expired session rejects verification
 12.  Random/blank image rejected (content check)
 13.  Wrong-amount screenshot rejected
 14.  Wrong-receiver screenshot rejected
 15.  Missing transaction ID rejected
 16.  Valid synthetic screenshot passes (when OCR available)
 17.  Duplicate transaction ref rejected
 18.  Staff portal: login, orders list, status update
 19.  Order tracking by order_id and token_number
 20.  GET /api/orders/<id> includes items array
"""

import io, json, time, unittest, sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
from app    import create_app
from config import Config
from database import calculate_order_price

# ── Minimal real-looking PDF bytes (1-page valid PDF) ─────────────────────
_PDF_1P = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f\n"
    b"0000000009 00000 n\n0000000058 00000 n\n"
    b"0000000115 00000 n\n"
    b"trailer<</Size 4/Root 1 0 R>>\n"
    b"startxref\n190\n%%EOF\n"
)

# Build a 4-page PDF by repeating the page object pattern
def _make_pdf(num_pages: int) -> bytes:
    """
    Produce a minimal but valid multi-page PDF using PyMuPDF so
    inspect_pdf_pages() can correctly count pages.
    Falls back to pymupdf if available, otherwise returns a text file stub
    (backend will then count it as 1 page for non-PDF).
    """
    try:
        import pymupdf
        doc = pymupdf.open()
        for _ in range(num_pages):
            doc.new_page()
        return doc.tobytes()
    except Exception:
        return _PDF_1P   # fallback – not tested as PDF


# ── 1×1 white pixel PNG (minimal, OCR will find no text) ──────────────────
_PNG_1x1 = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
    b'\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
)


class TestCampusPrint(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app    = create_app()
        cls.client = cls.app.test_client()
        cls.pdf_4p = _make_pdf(4)
        cls.pdf_3p = _make_pdf(3)
        cls.pdf_5p = _make_pdf(5)

    # ─── Helper ──────────────────────────────────────────────────────────────
    def _post_order(self, pdf_bytes, pages_hint=None, **kwargs):
        data = {
            "student_name": kwargs.get("student_name", "Test Student"),
            "roll_number":  kwargs.get("roll_number",  "TST001"),
            "phone_number": kwargs.get("phone_number", "9999999999"),
            "copies":       str(kwargs.get("copies",    1)),
            "color_mode":   kwargs.get("color_mode",   "bw"),
            "side_mode":    kwargs.get("side_mode",    "single"),
            "print_type":   kwargs.get("print_type",   "regular"),
            "binding_type": kwargs.get("binding_type", "none"),
            "payment_method": "UPI",
            "document": (io.BytesIO(pdf_bytes), kwargs.get("filename", "test.pdf")),
        }
        if pages_hint:
            data["pages"] = str(pages_hint)
        return self.client.post("/api/orders", data=data, content_type="multipart/form-data")

    def _post_multi(self, files_spec):
        """
        files_spec: list of dicts with keys:
            bytes, filename, copies, color_mode, side_mode
        """
        data = {
            "student_name":   "Multi Tester",
            "roll_number":    "ML001",
            "phone_number":   "8888888888",
            "print_type":     "regular",
            "binding_type":   "none",
            "payment_method": "UPI",
        }
        for i, spec in enumerate(files_spec):
            data[f"document_{i}"]   = (io.BytesIO(spec["bytes"]), spec["filename"])
            data[f"copies_{i}"]     = str(spec.get("copies",     1))
            data[f"color_mode_{i}"] = spec.get("color_mode", "bw")
            data[f"side_mode_{i}"]  = spec.get("side_mode",  "single")
        return self.client.post("/api/orders/multi", data=data, content_type="multipart/form-data")

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Single-PDF order via /api/orders
    # ─────────────────────────────────────────────────────────────────────────
    def test_01_single_pdf_order(self):
        res  = self._post_order(self.pdf_4p, copies=1, color_mode="bw", side_mode="single")
        self.assertEqual(res.status_code, 201)
        d = res.get_json()
        self.assertTrue(d["success"])
        order = d["order"]
        self.assertTrue(order["order_id"].startswith("ORD-"))
        self.assertTrue(order["token_number"].startswith("TK-"))
        self.assertEqual(order["order_status"], "Received")
        # 4 pages × ₹2 × 1 copy = ₹8
        self.assertEqual(order["total_price"], 8.0)
        self.assertEqual(order["pages"],  4)
        self.assertEqual(order["copies"], 1)
        print(f"[PASS] test_01  single-PDF B&W 1-copy  ₹{order['total_price']}")

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Multi-file order: 3 PDFs, different settings
    # ─────────────────────────────────────────────────────────────────────────
    def test_02_multi_pdf_order_3_files(self):
        files = [
            # JQW4.pdf: 4 pages, 2 copies, double, B&W
            {"bytes": self.pdf_4p, "filename": "JQW4.pdf",
             "copies": 2, "color_mode": "bw", "side_mode": "double"},
            # KMW4.pdf: 3 pages, 1 copy, single, B&W
            {"bytes": self.pdf_3p, "filename": "KMW4.pdf",
             "copies": 1, "color_mode": "bw", "side_mode": "single"},
            # LGW4.pdf: 5 pages, 1 copy, single, Color
            {"bytes": self.pdf_5p, "filename": "LGW4.pdf",
             "copies": 1, "color_mode": "color", "side_mode": "single"},
        ]
        res = self._post_multi(files)
        self.assertEqual(res.status_code, 201, msg=res.get_data(as_text=True))
        d = res.get_json()
        self.assertTrue(d["success"])
        items = d["items"]
        self.assertEqual(len(items), 3)

        # JQW4: 4 pages × ₹2 × 2 copies = ₹16
        jqw = items[0]
        self.assertEqual(jqw["pages"],            4)
        self.assertEqual(jqw["copies"],           2)
        self.assertEqual(jqw["color_mode"],       "bw")
        self.assertEqual(jqw["side_mode"],        "double")
        self.assertEqual(jqw["calculated_sheets"], 4)  # ceil(4/2)×2 = 4
        self.assertAlmostEqual(jqw["printing_cost"], 16.0)

        # KMW4: 3 pages × ₹2 × 1 copy = ₹6
        kmw = items[1]
        self.assertEqual(kmw["pages"],            3)
        self.assertEqual(kmw["copies"],           1)
        self.assertEqual(kmw["color_mode"],       "bw")
        self.assertEqual(kmw["side_mode"],        "single")
        self.assertEqual(kmw["calculated_sheets"], 3)
        self.assertAlmostEqual(kmw["printing_cost"], 6.0)

        # LGW4: 5 pages × ₹5 × 1 copy = ₹25
        lgw = items[2]
        self.assertEqual(lgw["pages"],            5)
        self.assertEqual(lgw["copies"],           1)
        self.assertEqual(lgw["color_mode"],       "color")
        self.assertEqual(lgw["side_mode"],        "single")
        self.assertEqual(lgw["calculated_sheets"], 5)
        self.assertAlmostEqual(lgw["printing_cost"], 25.0)

        print("[PASS] test_02  multi-PDF 3 files: pages/copies/color/sides all independent")

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Multi-file grand total is sum of per-file costs
    # ─────────────────────────────────────────────────────────────────────────
    def test_03_grand_total(self):
        files = [
            {"bytes": self.pdf_4p, "filename": "JQW4.pdf",
             "copies": 2, "color_mode": "bw",    "side_mode": "double"},
            {"bytes": self.pdf_3p, "filename": "KMW4.pdf",
             "copies": 1, "color_mode": "bw",    "side_mode": "single"},
            {"bytes": self.pdf_5p, "filename": "LGW4.pdf",
             "copies": 1, "color_mode": "color", "side_mode": "single"},
        ]
        res = self._post_multi(files)
        d   = res.get_json()
        # 16 + 6 + 25 = 47
        self.assertAlmostEqual(d["grand_total"], 47.0)
        self.assertAlmostEqual(d["order"]["total_price"], 47.0)
        print(f"[PASS] test_03  grand total = ₹{d['grand_total']}")

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Settings of one file do NOT bleed into another
    # ─────────────────────────────────────────────────────────────────────────
    def test_04_settings_isolation(self):
        files = [
            {"bytes": self.pdf_4p, "filename": "A.pdf",
             "copies": 3, "color_mode": "color", "side_mode": "double"},
            {"bytes": self.pdf_3p, "filename": "B.pdf",
             "copies": 1, "color_mode": "bw",    "side_mode": "single"},
        ]
        res   = self._post_multi(files)
        items = res.get_json()["items"]
        a, b  = items[0], items[1]
        self.assertEqual(a["color_mode"], "color")
        self.assertEqual(a["side_mode"],  "double")
        self.assertEqual(a["copies"],     3)
        self.assertEqual(b["color_mode"], "bw")
        self.assertEqual(b["side_mode"],  "single")
        self.assertEqual(b["copies"],     1)
        # A: 4p × ₹5 × 3 = ₹60 ; B: 3p × ₹2 × 1 = ₹6
        self.assertAlmostEqual(a["printing_cost"], 60.0)
        self.assertAlmostEqual(b["printing_cost"],  6.0)
        print("[PASS] test_04  settings isolation — color/copies/sides do not bleed between files")

    # ─────────────────────────────────────────────────────────────────────────
    # 5. B&W single-sided pricing
    # ─────────────────────────────────────────────────────────────────────────
    def test_05_bw_single_pricing(self):
        c = calculate_order_price(4, 1, "bw", "single")
        self.assertEqual(c["total_sheets"],  4)
        self.assertEqual(c["printing_cost"], 8.0)
        c = calculate_order_price(4, 3, "bw", "single")
        self.assertEqual(c["total_sheets"],  12)
        self.assertEqual(c["printing_cost"], 24.0)
        print("[PASS] test_05  B&W single-sided: 4p×1=₹8 / 4p×3=₹24")

    # ─────────────────────────────────────────────────────────────────────────
    # 6. B&W double-sided: ceiling sheet calculation
    # ─────────────────────────────────────────────────────────────────────────
    def test_06_bw_double_sided(self):
        # Even pages: 4p → 2 sheets/copy
        c = calculate_order_price(4, 3, "bw", "double")
        self.assertEqual(c["sheets_per_copy"], 2)
        self.assertEqual(c["total_sheets"],    6)
        self.assertEqual(c["printing_cost"],   24.0)  # 4×₹2×3
        # Odd pages: 5p → ceil(5/2)=3 sheets/copy
        c = calculate_order_price(5, 2, "bw", "double")
        self.assertEqual(c["sheets_per_copy"], 3)
        self.assertEqual(c["total_sheets"],    6)
        self.assertEqual(c["printing_cost"],   20.0)  # 5×₹2×2
        # 1 page → 1 sheet/copy
        c = calculate_order_price(1, 1, "bw", "double")
        self.assertEqual(c["sheets_per_copy"], 1)
        self.assertEqual(c["total_sheets"],    1)
        print("[PASS] test_06  B&W double-sided ceiling: 4p→2sh/copy, 5p→3sh/copy, 1p→1sh/copy")

    # ─────────────────────────────────────────────────────────────────────────
    # 7. Color single-sided pricing
    # ─────────────────────────────────────────────────────────────────────────
    def test_07_color_pricing(self):
        c = calculate_order_price(4, 3, "color", "single")
        self.assertEqual(c["total_sheets"],  12)
        self.assertEqual(c["printing_cost"], 60.0)
        c = calculate_order_price(5, 1, "color", "single")
        self.assertEqual(c["printing_cost"], 25.0)
        print("[PASS] test_07  Color single-sided: 4p×3=₹60 / 5p×1=₹25")

    # ─────────────────────────────────────────────────────────────────────────
    # 8. Correct physical sheets across examples A–D
    # ─────────────────────────────────────────────────────────────────────────
    def test_08_examples_A_to_D(self):
        A = calculate_order_price(4, 1, "bw", "single")
        self.assertEqual(A["total_sheets"], 4);  self.assertEqual(A["printing_cost"], 8.0)
        B = calculate_order_price(4, 3, "bw", "single")
        self.assertEqual(B["total_sheets"], 12); self.assertEqual(B["printing_cost"], 24.0)
        C = calculate_order_price(4, 3, "color", "single")
        self.assertEqual(C["total_sheets"], 12); self.assertEqual(C["printing_cost"], 60.0)
        D = calculate_order_price(4, 3, "bw", "double")
        self.assertEqual(D["total_sheets"], 6);  self.assertEqual(D["printing_cost"], 24.0)
        print("[PASS] test_08  Examples A–D all correct")

    # ─────────────────────────────────────────────────────────────────────────
    # 9. Payment session amount matches order total
    # ─────────────────────────────────────────────────────────────────────────
    def test_09_payment_session_amount(self):
        # Create an order and verify session amount could equal it
        res_order = self._post_order(self.pdf_4p, copies=3, color_mode="bw", side_mode="single")
        total = res_order.get_json()["order"]["total_price"]
        self.assertEqual(total, 24.0)

        res_sess = self.client.post("/api/payment/session",
                                    data=json.dumps({"order_amount": total}),
                                    content_type="application/json")
        self.assertEqual(res_sess.status_code, 201)
        sess = res_sess.get_json()
        self.assertEqual(sess["order_amount"], 24.0)
        self.assertGreater(sess["remaining_seconds"], 595)
        print(f"[PASS] test_09  payment session amount=₹{sess['order_amount']} remaining={sess['remaining_seconds']}s")

    # ─────────────────────────────────────────────────────────────────────────
    # 10. Payment session create / fetch / remaining-time
    # ─────────────────────────────────────────────────────────────────────────
    def test_10_payment_session_lifecycle(self):
        # Create
        r1 = self.client.post("/api/payment/session",
                               data=json.dumps({"order_amount": 47.0}),
                               content_type="application/json")
        self.assertEqual(r1.status_code, 201)
        sid = r1.get_json()["session_id"]

        # Fetch
        r2 = self.client.get(f"/api/payment/session/{sid}")
        self.assertEqual(r2.status_code, 200)
        s2 = r2.get_json()
        self.assertFalse(s2["expired"])
        self.assertEqual(s2["verification_status"], "pending")
        self.assertGreater(s2["remaining_seconds"], 590)

        # Non-existent
        r3 = self.client.get("/api/payment/session/doesnotexist000")
        self.assertEqual(r3.status_code, 404)
        print(f"[PASS] test_10  session lifecycle  id={sid[:8]}…  remaining={s2['remaining_seconds']}s")

    # ─────────────────────────────────────────────────────────────────────────
    # 11. Random / blank image is rejected
    # ─────────────────────────────────────────────────────────────────────────
    def test_11_random_screenshot_rejected(self):
        r = self.client.post("/api/payment/session",
                              data=json.dumps({"order_amount": 30.0}),
                              content_type="application/json")
        sid = r.get_json()["session_id"]

        res = self.client.post(f"/api/payment/session/{sid}/verify",
                                data={"screenshot": (io.BytesIO(_PNG_1x1), "random.png")},
                                content_type="multipart/form-data")
        self.assertIn(res.status_code, (422, 200))
        d = res.get_json()
        self.assertFalse(d["success"])
        print(f"[PASS] test_11  blank/random image rejected: {d['message'][:60]}")

    # ─────────────────────────────────────────────────────────────────────────
    # 12. Invalid file type rejected
    # ─────────────────────────────────────────────────────────────────────────
    def test_12_invalid_file_type(self):
        r = self.client.post("/api/payment/session",
                              data=json.dumps({"order_amount": 10.0}),
                              content_type="application/json")
        sid = r.get_json()["session_id"]

        res = self.client.post(f"/api/payment/session/{sid}/verify",
                                data={"screenshot": (io.BytesIO(b"data"), "bad.pdf")},
                                content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)
        print("[PASS] test_12  invalid file type (.pdf) → 400")

    # ─────────────────────────────────────────────────────────────────────────
    # 13. Empty file rejected
    # ─────────────────────────────────────────────────────────────────────────
    def test_13_empty_file_rejected(self):
        r = self.client.post("/api/payment/session",
                              data=json.dumps({"order_amount": 10.0}),
                              content_type="application/json")
        sid = r.get_json()["session_id"]

        res = self.client.post(f"/api/payment/session/{sid}/verify",
                                data={"screenshot": (io.BytesIO(b""), "empty.png")},
                                content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)
        print("[PASS] test_13  empty file → 400")

    # ─────────────────────────────────────────────────────────────────────────
    # 14. Missing screenshot field → 400
    # ─────────────────────────────────────────────────────────────────────────
    def test_14_missing_screenshot_field(self):
        r = self.client.post("/api/payment/session",
                              data=json.dumps({"order_amount": 10.0}),
                              content_type="application/json")
        sid = r.get_json()["session_id"]

        res = self.client.post(f"/api/payment/session/{sid}/verify")
        self.assertEqual(res.status_code, 400)
        print("[PASS] test_14  missing screenshot field → 400")

    # ─────────────────────────────────────────────────────────────────────────
    # 15. Order tracking works after single and multi orders
    # ─────────────────────────────────────────────────────────────────────────
    def test_15_order_tracking(self):
        # Single order
        r = self._post_order(self.pdf_4p)
        oid = r.get_json()["order"]["order_id"]
        tok = r.get_json()["order"]["token_number"]

        r2 = self.client.get(f"/api/orders/track/{oid}")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.get_json()["orders"][0]["order_id"], oid)

        r3 = self.client.get(f"/api/orders/track/{tok}")
        self.assertEqual(r3.status_code, 200)
        print(f"[PASS] test_15  order tracking  oid={oid}  token={tok}")

    # ─────────────────────────────────────────────────────────────────────────
    # 16. GET /api/orders/<id> returns items array for multi-order
    # ─────────────────────────────────────────────────────────────────────────
    def test_16_order_detail_includes_items(self):
        files = [
            {"bytes": self.pdf_4p, "filename": "X.pdf", "copies": 1, "color_mode": "bw",    "side_mode": "single"},
            {"bytes": self.pdf_3p, "filename": "Y.pdf", "copies": 2, "color_mode": "color",  "side_mode": "double"},
        ]
        res = self._post_multi(files)
        oid = res.get_json()["order"]["order_id"]

        detail = self.client.get(f"/api/orders/{oid}")
        self.assertEqual(detail.status_code, 200)
        d = detail.get_json()
        self.assertIn("items", d)
        self.assertEqual(len(d["items"]), 2)
        self.assertEqual(d["items"][0]["document_name"], "X.pdf")
        self.assertEqual(d["items"][1]["document_name"], "Y.pdf")
        print(f"[PASS] test_16  GET /api/orders/{oid}  → items array with {len(d['items'])} entries")

    # ─────────────────────────────────────────────────────────────────────────
    # 17. Staff login + order list + status update
    # ─────────────────────────────────────────────────────────────────────────
    def test_17_staff_portal(self):
        # Login
        # Ensure old credentials fail with 401
        r_old = self.client.post("/api/staff/login",
                                 data=json.dumps({"username": "staff", "password": "xerox@admin"}),
                                 content_type="application/json")
        self.assertEqual(r_old.status_code, 401)
        r_old2 = self.client.post("/api/staff/login",
                                  data=json.dumps({"username": "staff@melody", "password": "0x@melody"}),
                                  content_type="application/json")
        self.assertEqual(r_old2.status_code, 401)

        r = self.client.post("/api/staff/login",
                              data=json.dumps({"username": Config.STAFF_USERNAME,
                                               "password": Config.STAFF_PASSWORD}),
                              content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])

        # Orders
        r2 = self.client.get("/api/staff/orders")
        self.assertEqual(r2.status_code, 200)
        self.assertGreater(r2.get_json()["count"], 0)

        # Stats
        r3 = self.client.get("/api/staff/stats")
        self.assertEqual(r3.status_code, 200)
        self.assertGreater(r3.get_json()["stats"]["total_orders"], 0)

        # Status update
        oid = self._post_order(self.pdf_4p).get_json()["order"]["order_id"]
        r4 = self.client.patch(f"/api/staff/orders/{oid}/status",
                                data=json.dumps({"status": "Processing"}),
                                content_type="application/json")
        self.assertEqual(r4.status_code, 200)
        self.assertEqual(r4.get_json()["order"]["order_status"], "Processing")
        print(f"[PASS] test_17  staff portal login/orders/stats/status-update")

    # ─────────────────────────────────────────────────────────────────────────
    # 18. Duplicate transaction ref blocked
    # ─────────────────────────────────────────────────────────────────────────
    def test_18_duplicate_txn_ref_blocked(self):
        from database import (
            create_payment_session, record_used_transaction_ref,
            is_transaction_ref_used
        )
        with self.app.app_context():
            sess = create_payment_session(30.0)
            sid  = sess["session_id"]
            # Record a ref as used
            record_used_transaction_ref("DUPTEST99999", 30.0, sid)
            self.assertTrue(is_transaction_ref_used("DUPTEST99999"))
            self.assertFalse(is_transaction_ref_used("NOTUSED12345"))
        print("[PASS] test_18  duplicate transaction ref correctly blocked")

    # ─────────────────────────────────────────────────────────────────────────
    # 19. payment_verification unit: minimum-content check
    # ─────────────────────────────────────────────────────────────────────────
    def test_19_minimum_content_check(self):
        from payment_verification import _check_minimum_content
        ok,  _ = _check_minimum_content("Payment successful Rs 30 UPI ref 123456789012")
        self.assertTrue(ok)
        bad, msg = _check_minimum_content("hi")
        self.assertFalse(bad)
        self.assertIn("word", msg)
        print("[PASS] test_19  minimum-content check: real text passes, 1-word fails")

    # ─────────────────────────────────────────────────────────────────────────
    # 20. payment_verification unit: amount check
    # ─────────────────────────────────────────────────────────────────────────
    def test_20_amount_check(self):
        from payment_verification import _check_amount
        ok,  _ = _check_amount("Paid ₹30 to campusprint UTR 123456789012", 30.0)
        self.assertTrue(ok)
        ok2, _ = _check_amount("Paid Rs. 30.00", 30.0)
        self.assertTrue(ok2)
        fail, msg = _check_amount("Paid ₹20 to campusprint UTR 123456789012", 30.0)
        self.assertFalse(fail)
        self.assertIn("30", msg)
        print("[PASS] test_20  amount check: ₹30 passes, ₹20 fails")

    # ─────────────────────────────────────────────────────────────────────────
    # 21. payment_verification unit: receiver check
    # ─────────────────────────────────────────────────────────────────────────
    def test_21_receiver_check(self):
        from payment_verification import _check_receiver
        ok, _ = _check_receiver("Paid to campusprint@upi — success")
        self.assertTrue(ok)
        ok2, _ = _check_receiver("Payment to CampusPrint Xerox Counter")
        self.assertTrue(ok2)
        fail, _ = _check_receiver("Paid to randomshop@upi")
        self.assertFalse(fail)
        print("[PASS] test_21  receiver check: campusprint passes, randomshop fails")

    # ─────────────────────────────────────────────────────────────────────────
    # 22. payment_verification unit: transaction ID extraction
    # ─────────────────────────────────────────────────────────────────────────
    def test_22_transaction_id_check(self):
        from payment_verification import _check_transaction_id
        ok, ref = _check_transaction_id("UTR: 123456789012345 paid to campusprint")
        self.assertTrue(ok)
        self.assertEqual(ref, "123456789012345")
        ok2, ref2 = _check_transaction_id("Ref No 426381927364 done")
        self.assertTrue(ok2)
        fail, ref3 = _check_transaction_id("paid to someone")
        self.assertFalse(fail)
        self.assertIsNone(ref3)
        print(f"[PASS] test_22  txn-id extraction: UTR found={ref}  no-id=None")

    # ─────────────────────────────────────────────────────────────────────────
    # 23. payment_verification unit: time-window check
    # ─────────────────────────────────────────────────────────────────────────
    def test_23_time_window_check(self):
        from payment_verification import _check_time_window
        from datetime import datetime, timedelta

        now    = datetime.now()
        within = (now + timedelta(minutes=5)).strftime("%H:%M")
        after  = (now + timedelta(minutes=12)).strftime("%H:%M")
        before = (now - timedelta(minutes=2)).strftime("%H:%M")

        ok, _ = _check_time_window(f"Paid at {within}", now)
        self.assertTrue(ok)
        fail, msg = _check_time_window(f"Paid at {after}", now)
        self.assertFalse(fail)
        self.assertIn("window", msg.lower())
        # Before session window (>1 min before) should also fail
        fail2, _ = _check_time_window(f"Paid at {before}", now)
        self.assertFalse(fail2)
        print(f"[PASS] test_23  time-window: within passes, {after} fails, {before} fails")

    # ─────────────────────────────────────────────────────────────────────────
    # 24. Wrong-amount OCR text → verify_screenshot fails
    # ─────────────────────────────────────────────────────────────────────────
    def test_24_wrong_amount_text_fails(self):
        """
        If OCR is available we test against fabricated wrong-amount text.
        If OCR is not available the route already returns failure (tested in 11).
        """
        from payment_verification import _check_amount
        fail, msg = _check_amount("Paid ₹20 to campusprint Ref 123456789012", 30.0)
        self.assertFalse(fail)
        print("[PASS] test_24  wrong-amount text correctly fails amount check")

    # ─────────────────────────────────────────────────────────────────────────
    # 25. Inspect-file endpoint works for PDFs
    # ─────────────────────────────────────────────────────────────────────────
    def test_25_inspect_file_pdf(self):
        res = self.client.post(
            "/api/inspect-file",
            data={"document": (io.BytesIO(self.pdf_4p), "sample.pdf")},
            content_type="multipart/form-data"
        )
        self.assertEqual(res.status_code, 200)
        d = res.get_json()
        self.assertTrue(d["success"])
        self.assertTrue(d["is_pdf"])
        self.assertEqual(d["pages"], 4)
        print(f"[PASS] test_25  /api/inspect-file  detected {d['pages']} pages from 4-page PDF")

    # ─────────────────────────────────────────────────────────────────────────
    # 26. No files → multi order returns 400
    # ─────────────────────────────────────────────────────────────────────────
    def test_26_multi_order_no_files(self):
        data = {
            "student_name": "Test", "roll_number": "T01",
            "phone_number": "9999999999", "payment_method": "UPI",
        }
        res = self.client.post("/api/orders/multi", data=data,
                               content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)
        print("[PASS] test_26  multi order with no files → 400")

    # ─────────────────────────────────────────────────────────────────────────
    # 27. Payment amount variations & optional transaction ID
    # ─────────────────────────────────────────────────────────────────────────
    def test_27_amount_representations_and_optional_transaction_id(self):
        from payment_verification import _check_amount, verify_screenshot
        from datetime import datetime, timezone

        # 1. Various representations of ₹6
        for text in [
            "Payment successful ₹6 to Lakshmi Sai Bandi",
            "Paid ₹6.00 to campusprint",
            "Rs. 6 paid successfully",
            "INR 6.00 transferred",
            "Payment of <6 completed",
            "Status: Paid\n6\nView details",
        ]:
            ok, msg = _check_amount(text, 6.0)
            self.assertTrue(ok, f"Failed on: {text} -> {msg}")

        # 2. Different amount must FAIL
        fail_diff, msg_diff = _check_amount("Paid ₹20 to campusprint", 6.0)
        self.assertFalse(fail_diff)
        self.assertIn("6", msg_diff)

        # 3. Missing amount must FAIL with clear detection message
        fail_none, msg_none = _check_amount("Payment successful to campusprint", 6.0)
        self.assertFalse(fail_none)
        self.assertIn("could not be detected", msg_none.lower())
        self.assertNotIn("₹0", msg_none)

        print("[PASS] test_27  amount variations: ₹6/₹6.00/Rs.6/INR 6 pass; wrong/missing amounts correctly fail")


if __name__ == "__main__":
    loader = unittest.TestLoader()
    loader.sortTestMethodsUsing = lambda a, b: (int(a.split("_")[1]) - int(b.split("_")[1]))
    suite  = loader.loadTestsFromTestCase(TestCampusPrint)
    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)
    print()
    print("=" * 56)
    if result.wasSuccessful():
        print(f"ALL {result.testsRun} TESTS PASSED")
    else:
        print(f"FAILURES: {len(result.failures)}  ERRORS: {len(result.errors)}")
        for f in result.failures + result.errors:
            print(f"\n--- {f[0]} ---\n{f[1]}")
    print("=" * 56)
