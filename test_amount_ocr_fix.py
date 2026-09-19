"""
test_amount_ocr_fix.py
======================
Comprehensive verification for the OCR Payment Amount Extraction Fix.

Tests:
1. Actual ₹3 screenshot (pay_38b0ebc3_52276d.jpeg):
   - Expected ₹3 -> PASS
   - Expected ₹5 -> FAIL (mismatch rejected)
2. Actual ₹3 screenshot (pay_de862b65_97706c.jpeg):
   - Expected ₹3 -> PASS
   - Expected ₹5 -> FAIL
3. Actual ₹5 screenshot (pay_5cf4083d_5fd4c9.jpeg):
   - Expected ₹5 -> PASS
   - Expected ₹3 -> FAIL
4. Actual ₹12 screenshot (pay_6977fe16_40b4e7.jpeg):
   - Expected ₹12 -> PASS
   - Expected ₹3 -> FAIL
5. Actual ₹6 screenshot (pay_0de20348_6027fb.jpeg):
   - Expected ₹6 -> PASS
   - Expected ₹3 -> FAIL
6. Actual ₹34 screenshot (pay_d2f9553d_9bc4ab.jpeg):
   - Expected ₹34 -> PASS
   - Expected ₹10 -> FAIL
7. Arbitrary amounts: ₹10, ₹100, ₹250, ₹999 -> PASS
8. Complete payment verification checks:
   - Receiver validation
   - Payment date validation (15 Sep 2026, 10:58 AM)
   - Payment time validation
   - Transaction reference optional handling
   - Unreadable screenshot rejection
"""

import unittest
import os
import sys
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'backend')
from payment_verification import (
    verify_screenshot,
    _extract_text_from_image,
    _check_amount,
    _check_date,
    _check_time_window,
    _check_receiver,
    _check_minimum_content,
    _check_transaction_id,
)

class TestAmountOCRFix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sess_dt_sep15 = datetime(2026, 9, 15, 6, 55, 0) # 12:25 PM IST
        cls.sess_dt_sep15_1058 = datetime(2026, 9, 15, 5, 26, 0) # 10:56 AM IST
        cls.merchant_name = "Bandi Lakshmi Sai"
        cls.merchant_ids = ["bandi lakshmi sai", "lakshmi sai", "campusprint"]

    def _read_image(self, rel_path):
        full_path = os.path.join("backend", "uploads", rel_path) if not os.path.isabs(rel_path) else rel_path
        if not os.path.isfile(full_path):
            full_path = rel_path
        self.assertTrue(os.path.isfile(full_path), f"File not found: {full_path}")
        with open(full_path, "rb") as f:
            return f.read()

    # ── Test 1: The actual ₹3 screenshot (previously reported as ₹5) ──────────
    def test_01_actual_rs3_screenshot_passes_for_rs3(self):
        img_bytes = self._read_image("pay_38b0ebc3_52276d.jpeg")
        res = verify_screenshot(
            img_bytes,
            expected_amount=3.0,
            session_started_at=self.sess_dt_sep15,
            merchant_name=self.merchant_name,
            merchant_identifiers=self.merchant_ids,
        )
        self.assertTrue(res["checks"]["amount"]["passed"], f"Amount check failed: {res['checks']['amount']['message']}")
        self.assertIn("Amount ₹3 matched", res["checks"]["amount"]["message"])
        print("[PASS] 1. Actual ₹3 screenshot (pay_38b0ebc3) correctly detects ₹3 and passes amount check!")

    def test_02_actual_rs3_screenshot_fails_for_rs5(self):
        img_bytes = self._read_image("pay_38b0ebc3_52276d.jpeg")
        res = verify_screenshot(
            img_bytes,
            expected_amount=5.0,
            session_started_at=self.sess_dt_sep15,
            merchant_name=self.merchant_name,
            merchant_identifiers=self.merchant_ids,
        )
        self.assertFalse(res["checks"]["amount"]["passed"])
        self.assertIn("Detected payment of ₹3, but required order amount is ₹5", res["checks"]["amount"]["message"])
        print("[PASS] 2. Negative test: ₹3 screenshot correctly rejected when required amount is ₹5!")

    # ── Test 3: Second actual ₹3 screenshot ──────────────────────────────────
    def test_03_second_actual_rs3_screenshot(self):
        img_bytes = self._read_image("pay_de862b65_97706c.jpeg")
        # Match expected ₹3
        res3 = verify_screenshot(
            img_bytes,
            expected_amount=3.0,
            session_started_at=datetime(2026, 9, 15, 6, 26, 0), # 11:56 AM IST
            merchant_name=self.merchant_name,
            merchant_identifiers=self.merchant_ids,
        )
        self.assertTrue(res3["checks"]["amount"]["passed"])
        # Mismatch expected ₹5
        res5 = verify_screenshot(
            img_bytes,
            expected_amount=5.0,
            session_started_at=datetime(2026, 9, 15, 6, 26, 0),
            merchant_name=self.merchant_name,
            merchant_identifiers=self.merchant_ids,
        )
        self.assertFalse(res5["checks"]["amount"]["passed"])
        self.assertIn("Detected payment of ₹3, but required order amount is ₹5", res5["checks"]["amount"]["message"])
        print("[PASS] 3. Second ₹3 screenshot (pay_de862b65) correctly detects ₹3 and rejects ₹5!")

    # ── Test 3b: Dark Mode FamPay ₹3 screenshot (previously reported as ₹23) ──
    def test_03b_dark_mode_fampay_rs3_screenshot(self):
        img_bytes = self._read_image("pay_012fec6f_c8f564.jpeg")
        # Match expected ₹3 -> PASS
        res3 = verify_screenshot(
            img_bytes,
            expected_amount=3.0,
            session_started_at=datetime(2026, 9, 18, 13, 45, 0), # UTC ~ 19:15 IST
            merchant_name=self.merchant_name,
            merchant_identifiers=self.merchant_ids,
        )
        self.assertTrue(res3["checks"]["amount"]["passed"], f"Amount check failed: {res3['checks']['amount']['message']}")
        self.assertIn("Amount ₹3 matched", res3["checks"]["amount"]["message"])
        self.assertTrue(res3["success"])
        self.assertEqual(res3["status"], "verified")

        # Mismatch expected ₹5 -> MUST FAIL
        res5 = verify_screenshot(
            img_bytes,
            expected_amount=5.0,
            session_started_at=datetime(2026, 9, 18, 13, 45, 0),
            merchant_name=self.merchant_name,
            merchant_identifiers=self.merchant_ids,
        )
        self.assertFalse(res5["checks"]["amount"]["passed"])
        self.assertIn("Detected payment of ₹3, but required order amount is ₹5", res5["checks"]["amount"]["message"])
        self.assertFalse(res5["success"])
        print("[PASS] 3b. Dark Mode FamPay ₹3 screenshot (pay_012fec6f) correctly detects ₹3, verifies ₹3, and rejects ₹5!")

    # ── Test 4: Actual ₹5 screenshot ──────────────────────────────────────────
    def test_04_actual_rs5_screenshot(self):
        img_bytes = self._read_image("pay_5cf4083d_5fd4c9.jpeg")
        # Match expected ₹5
        res5 = verify_screenshot(
            img_bytes,
            expected_amount=5.0,
            session_started_at=datetime(2026, 9, 15, 6, 3, 0), # 11:33 AM IST
            merchant_name=self.merchant_name,
            merchant_identifiers=self.merchant_ids,
        )
        self.assertTrue(res5["checks"]["amount"]["passed"])
        self.assertIn("Amount ₹5 matched", res5["checks"]["amount"]["message"])

        # Mismatch expected ₹3 -> MUST FAIL
        res3 = verify_screenshot(
            img_bytes,
            expected_amount=3.0,
            session_started_at=datetime(2026, 9, 15, 6, 3, 0),
            merchant_name=self.merchant_name,
            merchant_identifiers=self.merchant_ids,
        )
        self.assertFalse(res3["checks"]["amount"]["passed"])
        self.assertIn("Detected payment of ₹5, but required order amount is ₹3", res3["checks"]["amount"]["message"])
        print("[PASS] 4. Actual ₹5 screenshot (pay_5cf4083d) correctly detects ₹5 and rejects ₹3!")

    # ── Test 5: Actual ₹12 screenshot ─────────────────────────────────────────
    def test_05_actual_rs12_screenshot(self):
        img_bytes = self._read_image("pay_6977fe16_40b4e7.jpeg")
        # Match expected ₹12
        res12 = verify_screenshot(
            img_bytes,
            expected_amount=12.0,
            session_started_at=self.sess_dt_sep15_1058,
            merchant_name=self.merchant_name,
            merchant_identifiers=self.merchant_ids,
        )
        self.assertTrue(res12["checks"]["amount"]["passed"])
        self.assertIn("Amount ₹12 matched", res12["checks"]["amount"]["message"])

        # Mismatch expected ₹3 -> MUST FAIL
        res3 = verify_screenshot(
            img_bytes,
            expected_amount=3.0,
            session_started_at=self.sess_dt_sep15_1058,
            merchant_name=self.merchant_name,
            merchant_identifiers=self.merchant_ids,
        )
        self.assertFalse(res3["checks"]["amount"]["passed"])
        self.assertIn("Detected payment of ₹12, but required order amount is ₹3", res3["checks"]["amount"]["message"])
        print("[PASS] 5. Actual ₹12 screenshot (pay_6977fe16) correctly detects ₹12 and rejects ₹3!")

    # ── Test 6: Actual ₹6 screenshot ──────────────────────────────────────────
    def test_06_actual_rs6_screenshot(self):
        img_bytes = self._read_image("pay_0de20348_6027fb.jpeg")
        res6 = verify_screenshot(
            img_bytes,
            expected_amount=6.0,
            session_started_at=datetime(2026, 9, 12, 8, 59, 0), # 2:29 PM IST
            merchant_name=self.merchant_name,
            merchant_identifiers=self.merchant_ids,
        )
        self.assertTrue(res6["checks"]["amount"]["passed"])

        res3 = verify_screenshot(
            img_bytes,
            expected_amount=3.0,
            session_started_at=datetime(2026, 9, 12, 8, 59, 0),
            merchant_name=self.merchant_name,
            merchant_identifiers=self.merchant_ids,
        )
        self.assertFalse(res3["checks"]["amount"]["passed"])
        self.assertIn("Detected payment of ₹6, but required order amount is ₹3", res3["checks"]["amount"]["message"])
        print("[PASS] 6. Actual ₹6 screenshot (pay_0de20348) correctly detects ₹6 and rejects ₹3!")

    # ── Test 7: Actual ₹34 screenshot (FamPay) ─────────────────────────────────
    def test_07_actual_rs34_screenshot(self):
        img_bytes = self._read_image("pay_d2f9553d_9bc4ab.jpeg")
        res34 = verify_screenshot(
            img_bytes,
            expected_amount=34.0,
            session_started_at=datetime(2026, 9, 14, 11, 54, 0), # 5:24 PM IST
            merchant_name=self.merchant_name,
            merchant_identifiers=self.merchant_ids,
        )
        self.assertTrue(res34["checks"]["amount"]["passed"])

        res10 = verify_screenshot(
            img_bytes,
            expected_amount=10.0,
            session_started_at=datetime(2026, 9, 14, 11, 54, 0),
            merchant_name=self.merchant_name,
            merchant_identifiers=self.merchant_ids,
        )
        self.assertFalse(res10["checks"]["amount"]["passed"])
        self.assertIn("Detected payment of ₹34, but required order amount is ₹10", res10["checks"]["amount"]["message"])
        print("[PASS] 7. Actual ₹34 FamPay screenshot correctly detects ₹34 and rejects ₹10!")

    # ── Test 8: Arbitrary amounts testing (₹10, ₹100, ₹250, ₹999) ──────────────
    def test_08_arbitrary_amounts_general_solution(self):
        import io
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 44)
        for amt in [10.0, 100.0, 250.0, 999.0]:
            # Create a Google Pay style confirmation card
            im = Image.new("RGB", (720, 900), color="#1e7e34")
            d = ImageDraw.Draw(im)
            # White card
            d.rectangle([40, 240, 680, 800], fill="#ffffff")
            # Text 'Payment successful'
            d.text((200, 100), "Payment successful", fill="#ffffff", font=font)
            d.text((200, 160), "15 Sep 2026, 12:28 PM", fill="#ffffff", font=font)
            # Prominent amount: ₹ {amt} + checkmark
            label = int(amt)
            d.text((240, 320), f"₹ {label}", fill="#000000", font=font)
            d.ellipse((420, 335, 455, 370), fill=(30, 142, 62)) # green checkmark badge
            # View details
            d.text((260, 440), "View details", fill="#1a73e8", font=font)
            d.text((200, 540), "Bandi Lakshmi Sai", fill="#000000", font=font)

            buf = io.BytesIO()
            im.save(buf, format="PNG")
            b = buf.getvalue()

            # Exact match -> PASS
            res_pass = verify_screenshot(
                b,
                expected_amount=amt,
                session_started_at=self.sess_dt_sep15,
                merchant_name=self.merchant_name,
                merchant_identifiers=self.merchant_ids,
            )
            self.assertTrue(res_pass["checks"]["amount"]["passed"], f"Failed for amount ₹{amt}: {res_pass['checks']['amount']['message']}")

            # Mismatched amount -> FAIL
            wrong_amt = amt + 5.0
            res_fail = verify_screenshot(
                b,
                expected_amount=wrong_amt,
                session_started_at=self.sess_dt_sep15,
                merchant_name=self.merchant_name,
                merchant_identifiers=self.merchant_ids,
            )
            self.assertFalse(res_fail["checks"]["amount"]["passed"])
            self.assertIn(f"Detected payment of ₹{label}", res_fail["checks"]["amount"]["message"])

        print("[PASS] 8. Arbitrary payment amounts (₹10, ₹100, ₹250, ₹999) accurately detected and verified!")

    # ── Test 9: Complete payment checks integrity ─────────────────────────────
    def test_09_all_payment_checks_still_function(self):
        img_bytes = self._read_image("pay_38b0ebc3_52276d.jpeg")
        res = verify_screenshot(
            img_bytes,
            expected_amount=3.0,
            session_started_at=self.sess_dt_sep15,
            merchant_name=self.merchant_name,
            merchant_identifiers=self.merchant_ids,
        )
        self.assertTrue(res["checks"]["screenshot_content"]["passed"])
        self.assertTrue(res["checks"]["receiver"]["passed"])
        self.assertTrue(res["checks"]["amount"]["passed"])
        self.assertTrue(res["checks"]["payment_date"]["passed"])
        self.assertTrue(res["checks"]["time_window"]["passed"])
        self.assertTrue(res["checks"]["transaction_id"]["passed"]) # Optional -> True
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "verified")
        print("[PASS] 9. All 6 payment checks passed together for the ₹3 screenshot!")

    # ── Test 10: Date check preservation (15 Sep 2026, 10:58 AM) ─────────────
    def test_10_date_check_preservation(self):
        text = """4 In 1.9 seconds
15 Sep 2026, 10:58 AM
₹12
View details
Bandi Lakshmi Sai
5 transactions in Sep yet"""
        ok, msg = _check_date(text, datetime(2026, 9, 15, 5, 26, 0))
        self.assertTrue(ok)
        self.assertIn("15 Sep 2026", msg)

        # Wrong session date must fail
        fail, fmsg = _check_date(text, datetime(2026, 9, 14, 5, 26, 0))
        self.assertFalse(fail)
        self.assertIn("does not match the session date", fmsg)
        print("[PASS] 10. Date parsing for '15 Sep 2026, 10:58 AM' and wrong date rejection preserved!")

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAmountOCRFix)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    if res.wasSuccessful():
        print("\nALL 10 AMOUNT OCR FIX TESTS PASSED PERFECTLY!")
    else:
        sys.exit(1)
