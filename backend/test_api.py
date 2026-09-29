import io
import unittest
from app import create_app
from config import Config

class XeroxAPITestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_01_health_and_pricing(self):
        # Health check
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["status"] == "healthy")

        # Pricing check
        res = self.client.get("/api/pricing")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["pricing"]["bw_per_page"], 2.0)
        self.assertEqual(data["pricing"]["color_per_page"], 5.0)

    def test_02_calculate_quote(self):
        # 10 pages, 2 copies, black and white, double sided
        # 10 pages = 5 sheets per copy * 2 copies = 10 sheets
        # 10 pages double B&W = 5 pairs * ₹3 = ₹15 * 2 copies = ₹30
        payload = {
            "pages": 10,
            "copies": 2,
            "color_mode": "bw",
            "side_mode": "double",
            "print_type": "regular",
            "binding_type": "none"
        }
        res = self.client.post("/api/pricing/calculate", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        quote = data["quote"]
        self.assertEqual(quote["printing_cost"], 30.0)
        self.assertEqual(quote["total_sheets"], 10)
        self.assertEqual(quote["total_price"], 30.0)

    def test_03_create_and_track_order(self):
        # Fake file upload
        file_content = b"This is sample project report for Digital Xerox System testing."
        data = {
            "student_name": "Aarav Sharma",
            "roll_number": "CS2026-042",
            "phone_number": "9876543210",
            "email": "aarav.sharma@college.edu",
            "pages": "5",
            "copies": "1",
            "color_mode": "color",
            "side_mode": "single",
            "print_type": "assignment",
            "binding_type": "corner_staple",
            "special_instructions": "Please staple on top-left corner",
            "payment_method": "Simulated UPI",
            "document": (io.BytesIO(file_content), "lab_record.pdf")
        }
        res = self.client.post("/api/orders", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 201)
        res_data = res.get_json()
        self.assertTrue(res_data["success"])
        order = res_data["order"]
        order_id = order["order_id"]
        token_number = order["token_number"]
        self.assertTrue(order_id.startswith("ORD-"))
        self.assertTrue(token_number.startswith("TK-"))
        self.assertEqual(order["order_status"], "Received")
        # 5 pages * ₹5 = ₹25 + ₹2 staple = ₹27
        self.assertEqual(order["total_price"], 27.0)

        # Track by order_id
        res_track = self.client.get(f"/api/orders/track/{order_id}")
        self.assertEqual(res_track.status_code, 200)
        tracked = res_track.get_json()["orders"][0]
        self.assertEqual(tracked["order_id"], order_id)

        # Track by token_number
        res_track_token = self.client.get(f"/api/orders/track/{token_number}")
        self.assertEqual(res_track_token.status_code, 200)

        # Staff tests
        # 1. Staff login
        login_res = self.client.post("/api/staff/login", json={
            "username": Config.STAFF_USERNAME,
            "password": Config.STAFF_PASSWORD
        })
        self.assertEqual(login_res.status_code, 200)
        self.assertTrue(login_res.get_json()["success"])

        # 2. Staff get orders
        staff_orders_res = self.client.get("/api/staff/orders")
        self.assertEqual(staff_orders_res.status_code, 200)
        self.assertGreater(staff_orders_res.get_json()["count"], 0)

        # 3. Staff stats
        stats_res = self.client.get("/api/staff/stats")
        self.assertEqual(stats_res.status_code, 200)
        self.assertGreater(stats_res.get_json()["stats"]["total_orders"], 0)

        # 4. Staff update status to 'Processing'
        update_res = self.client.patch(f"/api/staff/orders/{order_id}/status", json={
            "status": "Processing"
        })
        self.assertEqual(update_res.status_code, 200)
        self.assertEqual(update_res.get_json()["order"]["order_status"], "Processing")

        # 5. Staff update status to 'Ready for Collection'
        update_res = self.client.patch(f"/api/staff/orders/{order_id}/status", json={
            "status": "Ready for Collection"
        })
        self.assertEqual(update_res.status_code, 200)
        self.assertEqual(update_res.get_json()["order"]["order_status"], "Ready for Collection")

        # 6. Staff download file
        file_res = self.client.get(f"/api/staff/orders/{order_id}/file")
        self.assertEqual(file_res.status_code, 200)
        self.assertEqual(file_res.data, file_content)

if __name__ == "__main__":
    unittest.main()
