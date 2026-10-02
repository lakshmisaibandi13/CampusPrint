"""
test_razorpay.py
================
Unit and Integration Tests for Razorpay Standard Web Checkout Integration.

Covers:
1. Razorpay configuration loads from environment.
2. Missing credentials fail cleanly.
3. Create-order endpoint rejects nonexistent orders.
4. Create-order uses backend-calculated amount (never trusts client amount).
5. Payment verification rejects invalid signatures.
6. Payment verification accepts a correctly generated test signature.
7. Successful verification marks the correct order PAID and stores payment IDs.
8. Frontend does not contain RAZORPAY_KEY_SECRET.
9. Existing CampusPrint pricing/order tests still pass.
10. Webhook endpoint verification and processing.
"""

import os
import hmac
import hashlib
import json
import unittest
from unittest.mock import patch, MagicMock

from app import create_app
from config import Config
from database import (
    create_order,
    get_order_by_id,
    calculate_order_price,
    update_order_razorpay_order_id,
    mark_order_paid,
)


class TestRazorpayIntegration(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.test_key_id = "rzp_test_mockKey123"
        self.test_key_secret = "mockSecretKey456789"
        self.test_webhook_secret = "whsec_mockSecret123"

    # ── Test 1: Configuration loads from environment ─────────────────────────
    def test_01_razorpay_configuration_loads_from_environment(self):
        with patch.dict(os.environ, {
            "RAZORPAY_KEY_ID": self.test_key_id,
            "RAZORPAY_KEY_SECRET": self.test_key_secret,
            "RAZORPAY_WEBHOOK_SECRET": self.test_webhook_secret,
        }):
            Config.RAZORPAY_KEY_ID = self.test_key_id
            Config.RAZORPAY_KEY_SECRET = self.test_key_secret
            Config.RAZORPAY_WEBHOOK_SECRET = self.test_webhook_secret

            client = Config.get_razorpay_client()
            self.assertIsNotNone(client)
            self.assertEqual(client.auth, (self.test_key_id, self.test_key_secret))

    # ── Test 2: Missing credentials fail cleanly ─────────────────────────────
    def test_02_missing_credentials_fail_cleanly(self):
        Config.RAZORPAY_KEY_ID = ""
        Config.RAZORPAY_KEY_SECRET = ""

        with patch.dict(os.environ, {"RAZORPAY_KEY_ID": "", "RAZORPAY_KEY_SECRET": ""}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                Config.get_razorpay_client()
            self.assertIn("not configured", str(ctx.exception))

            # Testing create-order endpoint with missing credentials
            # First create a test order
            order = create_order({
                "student_name": "Test Student",
                "roll_number": "ROLL-001",
                "phone_number": "9876543210",
                "pages": 5,
                "copies": 1,
                "total_price": 25.0,
                "order_status": "Order Received",
                "payment_status": "Pending",
            })

            res = self.client.post("/api/payment/create-order", json={"order_id": order["order_id"]})
            self.assertEqual(res.status_code, 503)
            data = res.get_json()
            self.assertFalse(data["success"])
            self.assertIn("not configured", data["error"])
            # Ensure no secret or stack trace is exposed
            self.assertNotIn("Traceback", data["error"])

    # ── Test 3: Create-order endpoint rejects nonexistent orders ─────────────
    def test_03_create_order_rejects_nonexistent_orders(self):
        Config.RAZORPAY_KEY_ID = self.test_key_id
        Config.RAZORPAY_KEY_SECRET = self.test_key_secret

        res = self.client.post("/api/payment/create-order", json={"order_id": "ORD-DOESNOTEXIST-999"})
        self.assertEqual(res.status_code, 404)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertIn("not found", data["error"].lower())

    # ── Test 4: Create-order uses backend-calculated amount ──────────────────
    @patch("razorpay.Client")
    def test_04_create_order_uses_backend_calculated_amount(self, mock_razorpay_client_cls):
        Config.RAZORPAY_KEY_ID = self.test_key_id
        Config.RAZORPAY_KEY_SECRET = self.test_key_secret

        # Mock the client and order.create method
        mock_client = MagicMock()
        mock_razorpay_client_cls.return_value = mock_client
        mock_client.order.create.return_value = {
            "id": "order_mock_rzp_999",
            "amount": 3500,
            "currency": "INR",
            "receipt": "rcpt_ORD-TEST-004",
        }

        # Create order in DB with authoritative price of ₹35.00
        order = create_order({
            "student_name": "Calculated Amount Student",
            "roll_number": "ROLL-004",
            "phone_number": "9876543210",
            "pages": 7,
            "copies": 1,
            "total_price": 35.0,
            "order_status": "Order Received",
            "payment_status": "Pending",
        })

        # Client attempts to tamper with the amount (sending amount = 100 instead of 3500)
        res = self.client.post("/api/payment/create-order", json={
            "order_id": order["order_id"],
            "amount": 100,  # Should be ignored by the backend!
        })

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["amount"], 3500)  # Exactly 35.0 * 100 paise
        self.assertEqual(data["razorpay_key_id"], self.test_key_id)
        self.assertEqual(data["razorpay_order_id"], "order_mock_rzp_999")

        # Verify that mock_client.order.create was called with 3500 paise, not client-supplied 100
        call_args = mock_client.order.create.call_args[0][0]
        self.assertEqual(call_args["amount"], 3500)
        self.assertEqual(call_args["currency"], "INR")

    # ── Test 5: Payment verification rejects invalid signatures ──────────────
    def test_05_payment_verification_rejects_invalid_signatures(self):
        Config.RAZORPAY_KEY_ID = self.test_key_id
        Config.RAZORPAY_KEY_SECRET = self.test_key_secret

        order = create_order({
            "student_name": "Signature Test Student",
            "roll_number": "ROLL-005",
            "phone_number": "9876543210",
            "total_price": 20.0,
            "order_status": "Order Received",
            "payment_status": "Pending",
        })

        update_order_razorpay_order_id(order["order_id"], "order_test_sig_005")

        res = self.client.post("/api/payment/verify", json={
            "order_id": order["order_id"],
            "razorpay_order_id": "order_test_sig_005",
            "razorpay_payment_id": "pay_test_005",
            "razorpay_signature": "invalid_forged_signature_hex_12345",
        })

        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertIn("invalid signature", data["error"].lower())

        # Verify order in DB was NOT marked Paid
        refreshed = get_order_by_id(order["order_id"])
        self.assertEqual(refreshed["payment_status"], "Pending")

    # ── Test 6: Payment verification accepts valid test signature ────────────
    def test_06_payment_verification_accepts_valid_signature(self):
        Config.RAZORPAY_KEY_ID = self.test_key_id
        Config.RAZORPAY_KEY_SECRET = self.test_key_secret

        order = create_order({
            "student_name": "Valid Sig Student",
            "roll_number": "ROLL-006",
            "phone_number": "9876543210",
            "total_price": 50.0,
            "order_status": "Pending Payment",
            "payment_status": "Pending",
        })

        rzp_order_id = "order_valid_rzp_006"
        rzp_payment_id = "pay_valid_rzp_006"
        update_order_razorpay_order_id(order["order_id"], rzp_order_id)

        # Generate authentic HMAC-SHA256 signature
        payload_to_sign = f"{rzp_order_id}|{rzp_payment_id}"
        valid_signature = hmac.new(
            self.test_key_secret.encode("utf-8"),
            payload_to_sign.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        res = self.client.post("/api/payment/verify", json={
            "order_id": order["order_id"],
            "razorpay_order_id": rzp_order_id,
            "razorpay_payment_id": rzp_payment_id,
            "razorpay_signature": valid_signature,
        })

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["order"]["payment_status"], "Paid")

    # ── Test 7: Successful verification marks the correct order PAID ─────────
    def test_07_successful_verification_marks_correct_order_paid(self):
        Config.RAZORPAY_KEY_ID = self.test_key_id
        Config.RAZORPAY_KEY_SECRET = self.test_key_secret

        order = create_order({
            "student_name": "Mark Paid Student",
            "roll_number": "ROLL-007",
            "phone_number": "9876543210",
            "total_price": 75.0,
            "order_status": "Pending Payment",
            "payment_status": "Pending",
        })

        rzp_order_id = "order_mark_paid_007"
        rzp_payment_id = "pay_mark_paid_007"
        update_order_razorpay_order_id(order["order_id"], rzp_order_id)

        payload_to_sign = f"{rzp_order_id}|{rzp_payment_id}"
        valid_signature = hmac.new(
            self.test_key_secret.encode("utf-8"),
            payload_to_sign.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        res = self.client.post("/api/payment/verify", json={
            "order_id": order["order_id"],
            "razorpay_order_id": rzp_order_id,
            "razorpay_payment_id": rzp_payment_id,
            "razorpay_signature": valid_signature,
        })

        self.assertEqual(res.status_code, 200)

        # Directly inspect the database row
        stored = get_order_by_id(order["order_id"])
        self.assertEqual(stored["payment_status"], "Paid")
        self.assertEqual(stored["payment_method"], "Razorpay")
        self.assertEqual(stored["razorpay_payment_id"], rzp_payment_id)
        self.assertEqual(stored["razorpay_order_id"], rzp_order_id)
        self.assertEqual(stored["razorpay_signature"], valid_signature)
        self.assertIsNotNone(stored["payment_completed_at"])
        # Status transitioned to Order Received
        self.assertEqual(stored["order_status"], "Order Received")

    # ── Test 8: Frontend does not contain RAZORPAY_KEY_SECRET ────────────────
    def test_08_frontend_does_not_contain_razorpay_key_secret(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        frontend_dir = os.path.join(base_dir, "frontend")

        forbidden_secret = "RAZORPAY_KEY_SECRET"
        found_files = []

        for root, dirs, files in os.walk(frontend_dir):
            if "node_modules" in dirs:
                dirs.remove("node_modules")
            if "dist" in dirs:
                dirs.remove("dist")
            for filename in files:
                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        if forbidden_secret in f.read():
                            found_files.append(filepath)
                except Exception:
                    pass

        self.assertEqual(
            found_files,
            [],
            f"RAZORPAY_KEY_SECRET was found in frontend files: {found_files}"
        )

    # ── Test 9: Existing CampusPrint pricing/order logic remains intact ──────
    def test_09_existing_pricing_and_order_flow_remains_intact(self):
        # 1. Page rates
        self.assertEqual(Config.PRICING["bw_per_page"], 2.0)
        self.assertEqual(Config.PRICING["color_per_page"], 5.0)

        # 2. Quote calculations
        # Single page BW
        q1 = calculate_order_price(pages=1, copies=1, color_mode="bw", side_mode="single")
        self.assertEqual(q1["total_price"], 2.0)

        # Double sided Color 10 pages
        # 5 sheets * ₹8 = ₹40
        q2 = calculate_order_price(pages=10, copies=1, color_mode="color", side_mode="double")
        self.assertEqual(q2["total_price"], 40.0)

        # 3. Stationery catalog
        self.assertGreaterEqual(len(Config.STATIONERY_ITEMS), 13)

    # ── Test 10: Webhook verification and processing ─────────────────────────
    def test_10_webhook_verification_and_processing(self):
        Config.RAZORPAY_WEBHOOK_SECRET = self.test_webhook_secret

        order = create_order({
            "student_name": "Webhook Test Student",
            "roll_number": "ROLL-010",
            "phone_number": "9876543210",
            "total_price": 60.0,
            "order_status": "Order Received",
            "payment_status": "Pending",
        })

        rzp_order_id = "order_webhook_rzp_010"
        rzp_payment_id = "pay_webhook_rzp_010"
        update_order_razorpay_order_id(order["order_id"], rzp_order_id)

        webhook_payload = json.dumps({
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": rzp_payment_id,
                        "order_id": rzp_order_id,
                        "notes": {
                            "order_id": order["order_id"]
                        }
                    }
                }
            }
        })

        # Generate webhook signature
        signature = hmac.new(
            self.test_webhook_secret.encode("utf-8"),
            webhook_payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        res = self.client.post(
            "/api/payment/webhook",
            data=webhook_payload,
            headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"}
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "ok")

        # Verify order marked paid by webhook
        updated = get_order_by_id(order["order_id"])
        self.assertEqual(updated["payment_status"], "Paid")
        self.assertEqual(updated["razorpay_payment_id"], rzp_payment_id)


if __name__ == "__main__":
    unittest.main()
