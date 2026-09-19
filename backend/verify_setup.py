"""Quick verification script — run once then delete."""
import sys
print("Python:", sys.version)

# ── Imports ──────────────────────────────────────────────────────────────────
from config import Config
print("Config OK")

from database import (
    init_db, get_db_connection, calculate_order_price,
    create_payment_session, get_payment_session,
    update_payment_session_verification,
    is_transaction_ref_used, record_used_transaction_ref,
)
print("database.py OK")

from payment_verification import verify_screenshot
print("payment_verification.py OK")

from routes.order_routes import order_bp
print("order_routes.py OK")

from routes.staff_routes import staff_bp
print("staff_routes.py OK")

from routes.payment_routes import payment_bp
print("payment_routes.py OK")

from app import create_app
app = create_app()
print("create_app() OK")

# ── Check routes are registered ───────────────────────────────────────────────
rules = sorted(str(r) for r in app.url_map.iter_rules())
payment_rules = [r for r in rules if "payment" in r]
print("Payment routes:", payment_rules)
assert len(payment_rules) >= 3, "Expected at least 3 payment routes"

# ── Pricing: Example A  (4 pages, 1 copy, B&W, single) ───────────────────────
c = calculate_order_price(4, 1, "bw", "single", "regular", "none")
assert c["total_sheets"] == 4,       f"A sheets: got {c['total_sheets']}"
assert c["printing_cost"] == 8.0,    f"A cost:   got {c['printing_cost']}"
print("Example A (4p x1 B&W single): sheets=4  cost=8  PASS")

# ── Example B  (4 pages, 3 copies, B&W, single) ──────────────────────────────
c = calculate_order_price(4, 3, "bw", "single", "regular", "none")
assert c["total_sheets"] == 12,      f"B sheets: got {c['total_sheets']}"
assert c["printing_cost"] == 24.0,   f"B cost:   got {c['printing_cost']}"
print("Example B (4p x3 B&W single): sheets=12 cost=24 PASS")

# ── Example C  (4 pages, 3 copies, Color, single) ────────────────────────────
c = calculate_order_price(4, 3, "color", "single", "regular", "none")
assert c["total_sheets"] == 12,      f"C sheets: got {c['total_sheets']}"
assert c["printing_cost"] == 60.0,   f"C cost:   got {c['printing_cost']}"
print("Example C (4p x3 Color single): sheets=12 cost=60 PASS")

# ── Example D  (4 pages, 3 copies, B&W, double) ──────────────────────────────
c = calculate_order_price(4, 3, "bw", "double", "regular", "none")
assert c["sheets_per_copy"] == 2,    f"D spc:    got {c['sheets_per_copy']}"
assert c["total_sheets"] == 6,       f"D sheets: got {c['total_sheets']}"
# Printing cost = pages × rate × copies = 4 × 2 × 3 = 24 (charged per page impression)
assert c["printing_cost"] == 24.0,   f"D cost:   got {c['printing_cost']}"
print("Example D (4p x3 B&W double): sheets=6  cost=24 PASS")

# ── Odd-page double-sided ceiling test  (5 pages, 1 copy, double) ────────────
c = calculate_order_price(5, 1, "bw", "double", "regular", "none")
assert c["sheets_per_copy"] == 3,    f"Ceil sheets/copy: got {c['sheets_per_copy']}"
assert c["total_sheets"] == 3,       f"Ceil total: got {c['total_sheets']}"
print("Ceiling test  (5p x1 B&W double): sheets=3  PASS")

# ── Payment session create / retrieve ────────────────────────────────────────
with app.app_context():
    sess = create_payment_session(30.0)
    assert sess is not None
    assert sess["order_amount"] == 30.0
    assert sess["verification_status"] == "pending"
    sid = sess["session_id"]

    fetched = get_payment_session(sid)
    assert fetched["session_id"] == sid
    print(f"Payment session create/fetch OK  (id={sid[:8]}…)")

    # Test duplicate tx ref
    record_used_transaction_ref("TXNTEST001", 30.0, sid)
    assert is_transaction_ref_used("TXNTEST001") is True
    assert is_transaction_ref_used("TXNTEST999") is False
    print("Duplicate tx-ref guard  OK")

print()
print("=" * 48)
print("ALL BACKEND VERIFICATION CHECKS PASSED")
print("=" * 48)
