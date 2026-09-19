import requests
import json

BASE_URL = "http://127.0.0.1:5000/api"

def run_e2e_test():
    print("=== DIGITAL XEROX E2E INTEGRATION TEST ===")
    
    # 1. Health Check
    res = requests.get(f"{BASE_URL}/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    print("[PASS] Health Check: Backend is online")

    # 2. Pricing Check
    res = requests.get(f"{BASE_URL}/pricing")
    assert res.status_code == 200
    pricing = res.json()["pricing"]
    print(f"[PASS] Pricing Active: B&W Rs.{pricing['bw_per_page']}/page, Color Rs.{pricing['color_per_page']}/page")

    # 3. Live Quote Calculation Test
    quote_payload = {
        "pages": 8,
        "copies": 2,
        "color_mode": "color",
        "side_mode": "double",
        "print_type": "project_report",
        "binding_type": "spiral"
    }
    res = requests.post(f"{BASE_URL}/pricing/calculate", json=quote_payload)
    assert res.status_code == 200
    quote = res.json()["quote"]
    # 8 pages * Rs.5 = Rs.40 * 2 copies = Rs.80 print
    # Project report extra = Rs.15 * 2 = Rs.30
    # Spiral binding = Rs.30 * 2 = Rs.60
    # Total = Rs.170. Total sheets = 4 * 2 = 8
    print(f"[PASS] Quote Calculation: Total Price = Rs.{quote['total_price']}, Sheets = {quote['total_sheets']}")
    assert quote["total_price"] == 170.0
    assert quote["total_sheets"] == 8

    # 4. Student Order Placement (with File Upload)
    with open("sample_assignment.txt", "rb") as f:
        files = {"document": ("sample_assignment.txt", f, "text/plain")}
        data = {
            "student_name": "Priya Patel",
            "roll_number": "CS-2026-104",
            "phone_number": "9876543210",
            "email": "priya.patel@college.edu",
            "pages": "8",
            "copies": "2",
            "color_mode": "color",
            "side_mode": "double",
            "print_type": "project_report",
            "binding_type": "spiral",
            "special_instructions": "High quality print please",
            "payment_method": "Simulated UPI (GPay/PhonePe)"
        }
        res = requests.post(f"{BASE_URL}/orders", data=data, files=files)
        assert res.status_code == 201, f"Order placement failed: {res.text}"
        order = res.json()["order"]
        order_id = order["order_id"]
        token_number = order["token_number"]
        print(f"[PASS] Student Order Placed: Token: {token_number}, Order ID: {order_id}, Status: {order['order_status']}")

    # 5. Student Order Tracking by Token
    res = requests.get(f"{BASE_URL}/orders/track/{token_number}")
    assert res.status_code == 200
    tracked_orders = res.json()["orders"]
    assert len(tracked_orders) > 0
    assert tracked_orders[0]["token_number"] == token_number
    assert tracked_orders[0]["order_status"] == "Received"
    print(f"[PASS] Student Tracking Verified: Status is '{tracked_orders[0]['order_status']}'")

    # 6. Staff Login
    login_payload = {"username": "staff@mlrit", "password": "xerox@mlrit"}
    res = requests.post(f"{BASE_URL}/staff/login", json=login_payload)
    assert res.status_code == 200, f"Staff login failed: {res.text}"
    token = res.json()["token"]
    print("[PASS] Staff Authentication: Logged in successfully")

    # 7. Staff Dashboard Orders & Stats
    res = requests.get(f"{BASE_URL}/staff/orders")
    assert res.status_code == 200
    orders_list = res.json()["orders"]
    matching = [o for o in orders_list if o["token_number"] == token_number]
    assert len(matching) > 0
    print(f"[PASS] Staff Order Queue: Found order {token_number} in staff queue")

    # 8. Staff Updates Status to 'Processing'
    res = requests.patch(f"{BASE_URL}/staff/orders/{order_id}/status", json={"status": "Processing"})
    assert res.status_code == 200
    assert res.json()["order"]["order_status"] == "Processing"
    print("[PASS] Staff Action: Order moved to 'Processing'")

    # 9. Staff Updates Status to 'Ready for Collection'
    res = requests.patch(f"{BASE_URL}/staff/orders/{order_id}/status", json={"status": "Ready for Collection"})
    assert res.status_code == 200
    assert res.json()["order"]["order_status"] == "Ready for Collection"
    print("[PASS] Staff Action: Order marked 'Ready for Collection'")

    # 10. Student Tracker Reflects 'Ready for Collection'
    res = requests.get(f"{BASE_URL}/orders/track/{token_number}")
    assert res.status_code == 200
    assert res.json()["orders"][0]["order_status"] == "Ready for Collection"
    print("[PASS] Student Tracker Real-Time Reflection: Order is now 'Ready for Collection'!")

    # 11. Staff Document Download Verification
    res = requests.get(f"{BASE_URL}/staff/orders/{order_id}/file")
    assert res.status_code == 200
    assert b"COLLEGE OF ENGINEERING & TECHNOLOGY" in res.content
    print("[PASS] Document Retrieval: File uploaded by student is safely stored and retrievable")

    print("\n=======================================================")
    print("SUCCESS: ALL 11 END-TO-END VERIFICATION CHECKS PASSED!")
    print("=======================================================")

if __name__ == "__main__":
    run_e2e_test()
