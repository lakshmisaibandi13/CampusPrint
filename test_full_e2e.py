import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
import urllib.request
import json
import uuid
from generate_test_screenshot import make_screenshot

BASE = 'http://localhost:5173'

print('=== 1. TEST FRONTEND HOMEPAGE & STATIC ASSETS ===')
html = urllib.request.urlopen(f'{BASE}/').read().decode()
assert '<div id="root"></div>' in html
print('[PASS] Frontend root index.html is served')

qr_res = urllib.request.urlopen(f'{BASE}/payment_qr.png')
assert qr_res.status == 200 and len(qr_res.read()) > 40000
print('[PASS] QR image /payment_qr.png is served (200 OK, >40KB)')

print('\n=== 2. TEST PDF INSPECTION (Vite Proxy -> Backend) ===')
boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
with open('sample_test.pdf', 'rb') as f:
    pdf_bytes = f.read()

body = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="document"; filename="sample_test.pdf"\r\n'
    f'Content-Type: application/pdf\r\n\r\n'
).encode() + pdf_bytes + f'\r\n--{boundary}--\r\n'.encode()

req = urllib.request.Request(
    f'{BASE}/api/inspect-file',
    data=body,
    headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
)
res = json.loads(urllib.request.urlopen(req).read().decode())
assert res['success'] and res['pages'] == 1
print(f'[PASS] File inspected: {res["pages"]} page, {res["file_size_kb"]} KB')

print('\n=== 3. TEST PAYMENT SESSION CREATION ===')
order_amount = 2.0
req = urllib.request.Request(
    f'{BASE}/api/payment/session/resume',
    data=json.dumps({'order_amount': order_amount}).encode(),
    headers={'Content-Type': 'application/json'}
)
sess = json.loads(urllib.request.urlopen(req).read().decode())
assert sess['success'] and sess['remaining_seconds'] > 500
sid = sess['session_id']
print(f'[PASS] Payment session created: id={sid}, remaining={sess["remaining_seconds"]}s, merchant={sess["merchant_name"]}, upi={sess["merchant_upi"]}')

print('\n=== 4. TEST SCREENSHOT OCR VERIFICATION ===')
make_screenshot(amount=order_amount, out_path='test_e2e_screenshot.png')
with open('test_e2e_screenshot.png', 'rb') as f:
    img_bytes = f.read()

b_ocr = '----WebKitFormBoundary' + uuid.uuid4().hex
ocr_body = (
    f'--{b_ocr}\r\n'
    f'Content-Disposition: form-data; name="screenshot"; filename="test_e2e_screenshot.png"\r\n'
    f'Content-Type: image/png\r\n\r\n'
).encode() + img_bytes + f'\r\n--{b_ocr}--\r\n'.encode()

req = urllib.request.Request(
    f'{BASE}/api/payment/session/{sid}/verify',
    data=ocr_body,
    headers={'Content-Type': f'multipart/form-data; boundary={b_ocr}'}
)
ocr_res = json.loads(urllib.request.urlopen(req).read().decode())
assert ocr_res['success'] and ocr_res['status'] == 'verified', f"OCR Failed: {ocr_res}"
txn_ref = ocr_res['transaction_ref']
print(f'[PASS] OCR Verification passed! Transaction Ref: {txn_ref}')
for k, v in ocr_res['checks'].items():
    print(f'   - {k}: {v["passed"]} ({v["message"]})')

print('\n=== 5. TEST MULTI-ORDER PLACEMENT WITH PAYMENT REF ===')
b_order = '----WebKitFormBoundary' + uuid.uuid4().hex
order_form = (
    f'--{b_order}\r\nContent-Disposition: form-data; name="student_name"\r\n\r\nBandi Lakshmi\r\n'
    f'--{b_order}\r\nContent-Disposition: form-data; name="roll_number"\r\n\r\n2026-CS-001\r\n'
    f'--{b_order}\r\nContent-Disposition: form-data; name="phone_number"\r\n\r\n9876543210\r\n'
    f'--{b_order}\r\nContent-Disposition: form-data; name="email"\r\n\r\nlakshmi@college.edu\r\n'
    f'--{b_order}\r\nContent-Disposition: form-data; name="print_type"\r\n\r\nregular\r\n'
    f'--{b_order}\r\nContent-Disposition: form-data; name="binding_type"\r\n\r\nnone\r\n'
    f'--{b_order}\r\nContent-Disposition: form-data; name="payment_method"\r\n\r\nUPI\r\n'
    f'--{b_order}\r\nContent-Disposition: form-data; name="payment_session_id"\r\n\r\n{sid}\r\n'
    f'--{b_order}\r\nContent-Disposition: form-data; name="upi_transaction_ref"\r\n\r\n{txn_ref}\r\n'
    f'--{b_order}\r\nContent-Disposition: form-data; name="copies_0"\r\n\r\n1\r\n'
    f'--{b_order}\r\nContent-Disposition: form-data; name="color_mode_0"\r\n\r\nbw\r\n'
    f'--{b_order}\r\nContent-Disposition: form-data; name="side_mode_0"\r\n\r\nsingle\r\n'
    f'--{b_order}\r\nContent-Disposition: form-data; name="document_0"; filename="sample_test.pdf"\r\n'
    f'Content-Type: application/pdf\r\n\r\n'
).encode() + pdf_bytes + f'\r\n--{b_order}--\r\n'.encode()

req = urllib.request.Request(
    f'{BASE}/api/orders/multi',
    data=order_form,
    headers={'Content-Type': f'multipart/form-data; boundary={b_order}'}
)
placed = json.loads(urllib.request.urlopen(req).read().decode())
assert placed['success'], f"Order failed: {placed}"
order = placed['order']
disp_no = order['display_order_number']
token = order['token_number']
print(f'[PASS] Order Placed successfully! Order #{disp_no}, Token: {token}, ID: {order["order_id"]}')

print('\n=== 6. TEST ORDER TRACKING ===')
track_res = json.loads(urllib.request.urlopen(f'{BASE}/api/orders/track/{token}').read().decode())
assert track_res['success'] and len(track_res['orders']) > 0
tracked = track_res['orders'][0]
print(f'[PASS] Order tracked by token {token}: Order #{tracked["display_order_number"]}, status={tracked["order_status"]}')

print('\n=== 7. TEST STAFF LOGIN & PERMISSIONS ===')
req = urllib.request.Request(
    f'{BASE}/api/staff/login',
    data=json.dumps({'username': 'staff', 'password': 'xerox@admin'}).encode(),
    headers={'Content-Type': 'application/json'}
)
try:
    urllib.request.urlopen(req)
    assert False, 'Old credentials should fail'
except urllib.error.HTTPError as e:
    assert e.code == 401
    print('[PASS] Old staff credentials (staff/xerox@admin) correctly rejected with 401')

req = urllib.request.Request(
    f'{BASE}/api/staff/login',
    data=json.dumps({'username': 'staff@mlrit', 'password': 'xerox@mlrit'}).encode(),
    headers={'Content-Type': 'application/json'}
)
login_res = json.loads(urllib.request.urlopen(req).read().decode())
assert login_res['success']
print(f'[PASS] New staff credentials (staff@mlrit/xerox@mlrit) accepted: user={login_res["user"]["username"]}')

staff_orders = json.loads(urllib.request.urlopen(f'{BASE}/api/staff/orders').read().decode())
assert staff_orders['success'] and staff_orders['count'] > 0
matching_order = [o for o in staff_orders['orders'] if o['token_number'] == token][0]
print(f'[PASS] Staff dashboard lists Order #{matching_order["display_order_number"]}, Token {matching_order["token_number"]}, Student {matching_order["student_name"]}')

# Clean up e2e test order so live daily order sequence is preserved
try:
    import sqlite3
    c_conn = sqlite3.connect('backend/xerox_store.db')
    c_cur = c_conn.cursor()
    c_cur.execute("DELETE FROM order_items WHERE order_id = ?", (order["order_id"],))
    c_cur.execute("DELETE FROM order_stationery_items WHERE order_id = ?", (order["order_id"],))
    c_cur.execute("DELETE FROM orders WHERE order_id = ?", (order["order_id"],))
    c_conn.commit()
    c_conn.close()
except Exception:
    pass

print('\n=== ALL E2E TESTS PASSED PERFECTLY! ===')

