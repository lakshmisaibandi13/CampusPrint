"""
payment_routes.py
=================
UPI payment session management and screenshot verification endpoints.

Endpoints:
  GET  /api/payment/config               → current merchant name + UPI for the UI
  POST /api/payment/session              → create a new 10-min session
  POST /api/payment/session/resume       → resume existing OR create new session
  GET  /api/payment/session/<id>         → status + remaining seconds
  POST /api/payment/session/<id>/verify  → upload screenshot + run verification
"""

import os
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify

from config import Config
from database import (
    create_payment_session,
    get_payment_session,
    get_session_merchant,
    update_payment_session_verification,
    is_transaction_ref_used,
    record_used_transaction_ref,
    get_order_by_id,
    update_order_razorpay_order_id,
    mark_order_paid,
    get_order_by_razorpay_order_id,
)
from payment_verification import verify_screenshot

payment_bp = Blueprint("payment_bp", __name__, url_prefix="/api/payment")

ALLOWED_SCREENSHOT_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_SCREENSHOT_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def _allowed_screenshot(filename: str) -> bool:
    if "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in ALLOWED_SCREENSHOT_EXTENSIONS


def _remaining(session: dict) -> int:
    """Remaining seconds computed from the stored server-side UTC expiry."""
    expires_dt = datetime.fromisoformat(session["expires_at"])
    return max(0, int((expires_dt - datetime.utcnow()).total_seconds()))


def _live_merchant_snapshot() -> tuple[str, str, list]:
    """Return (upi_id, name, identifiers) from the current Config."""
    upi_id      = getattr(Config, "MERCHANT_UPI_ID",     "lakshmisaibandi@fampay")
    name        = getattr(Config, "MERCHANT_NAME",        "Lakshmi Sai Bandi")
    identifiers = getattr(Config, "MERCHANT_IDENTIFIERS", [name.lower()])
    return upi_id, name, identifiers


# ─── Merchant config for the UI ───────────────────────────────────────────────

@payment_bp.route("/config", methods=["GET"])
def payment_config():
    """Return the active merchant identity so the frontend never hardcodes it."""
    upi_id, name, _ = _live_merchant_snapshot()
    return jsonify({
        "success":       True,
        "merchant_name": name,
        "merchant_upi":  upi_id,
    }), 200


# ─── Create Payment Session ────────────────────────────────────────────────────

@payment_bp.route("/session", methods=["POST"])
def create_session():
    """Create a brand-new 10-minute payment session with merchant snapshot."""
    data = request.get_json() or {}
    try:
        order_amount = float(data.get("order_amount", 0))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid order_amount"}), 400

    if order_amount <= 0:
        return jsonify({"success": False, "error": "order_amount must be greater than zero"}), 400

    upi_id, name, identifiers = _live_merchant_snapshot()
    session = create_payment_session(order_amount, upi_id, name, identifiers)
    if not session:
        return jsonify({"success": False, "error": "Failed to create payment session"}), 500

    remaining = _remaining(session)
    return jsonify({
        "success":           True,
        "session_id":        session["session_id"],
        "order_amount":      session["order_amount"],
        "expires_at":        session["expires_at"],
        "remaining_seconds": remaining,
        "merchant_name":     name,
        "merchant_upi":      upi_id,
    }), 201


# ─── Resume-or-Create ─────────────────────────────────────────────────────────

@payment_bp.route("/session/resume", methods=["POST"])
def resume_or_create_session():
    """
    Return the existing unexpired session OR create a new one.

    This is the ONLY endpoint PaymentModal calls when opening the payment
    screen.  Passing the stored session_id resumes that session without
    resetting the 10-minute countdown.

    Body JSON:
        { "order_amount": 30.00, "session_id": "optional-existing-id" }

    Response includes:
        is_resumed      true  → existing session returned, timer NOT reset
                        false → fresh session created
        remaining_seconds → from server UTC expiry, not a frontend estimate
        merchant_name / merchant_upi → for the UI to display
    """
    data         = request.get_json() or {}
    existing_sid = (data.get("session_id") or "").strip()

    try:
        order_amount = float(data.get("order_amount", 0))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid order_amount"}), 400

    if order_amount <= 0:
        return jsonify({"success": False, "error": "order_amount must be greater than zero"}), 400

    # ── Try to resume an existing valid session ──────────────────────────────
    if existing_sid:
        existing = get_payment_session(existing_sid)
        if existing:
            remaining      = _remaining(existing)
            amount_matches = abs(float(existing["order_amount"]) - order_amount) < 0.01
            still_valid    = remaining > 0
            not_verified   = existing["verification_status"] != "verified"

            if amount_matches and still_valid and not_verified:
                _, m_name, _ = get_session_merchant(existing)
                return jsonify({
                    "success":             True,
                    "is_resumed":          True,
                    "session_id":          existing["session_id"],
                    "order_amount":        existing["order_amount"],
                    "expires_at":          existing["expires_at"],
                    "remaining_seconds":   remaining,
                    "verification_status": existing["verification_status"],
                    "merchant_name":       m_name,
                }), 200

            # Mark expired if applicable so the DB reflects reality
            if not still_valid:
                update_payment_session_verification(
                    existing_sid, "expired",
                    "Payment verification window has expired."
                )

    # ── Create a fresh session with merchant snapshot ────────────────────────
    upi_id, name, identifiers = _live_merchant_snapshot()
    session = create_payment_session(order_amount, upi_id, name, identifiers)
    if not session:
        return jsonify({"success": False, "error": "Failed to create payment session"}), 500

    remaining = _remaining(session)
    return jsonify({
        "success":             True,
        "is_resumed":          False,
        "session_id":          session["session_id"],
        "order_amount":        session["order_amount"],
        "expires_at":          session["expires_at"],
        "remaining_seconds":   remaining,
        "verification_status": "pending",
        "merchant_name":       name,
        "merchant_upi":        upi_id,
    }), 201


# ─── Get Session Status ────────────────────────────────────────────────────────

@payment_bp.route("/session/<session_id>", methods=["GET"])
def get_session(session_id: str):
    """Current session state including remaining seconds (server-authoritative)."""
    session = get_payment_session(session_id)
    if not session:
        return jsonify({"success": False, "error": "Payment session not found"}), 404

    remaining = _remaining(session)
    _, m_name, _ = get_session_merchant(session)
    return jsonify({
        "success":              True,
        "session_id":           session["session_id"],
        "order_amount":         session["order_amount"],
        "expires_at":           session["expires_at"],
        "remaining_seconds":    remaining,
        "expired":              remaining == 0,
        "verification_status":  session["verification_status"],
        "verification_message": session["verification_message"],
        "transaction_ref":      session["transaction_ref"],
        "merchant_name":        m_name,
    }), 200


# ─── Verify Payment Screenshot ─────────────────────────────────────────────────

@payment_bp.route("/session/<session_id>/verify", methods=["POST"])
def verify_payment(session_id: str):
    """
    Upload a UPI payment screenshot and run backend verification.
    All decisions are server-side — frontend values are never trusted.

    Multipart form:
        screenshot  — image file (PNG / JPG / WEBP)
    """
    # ── 1. Load & validate session ────────────────────────────────────────
    session = get_payment_session(session_id)
    if not session:
        return jsonify({"success": False, "error": "Payment session not found"}), 404

    remaining = _remaining(session)
    if remaining <= 0:
        update_payment_session_verification(
            session_id, "expired",
            "Payment session has expired. Please restart payment."
        )
        return jsonify({
            "success": False,
            "error":   "Payment session has expired. Please restart payment.",
            "expired": True,
        }), 400

    if session["verification_status"] == "verified":
        return jsonify({
            "success":         True,
            "message":         "Payment already verified for this session.",
            "transaction_ref": session["transaction_ref"],
        }), 200

    # ── 2. Validate uploaded file ──────────────────────────────────────────
    if "screenshot" not in request.files:
        return jsonify({"success": False, "error": "No screenshot file uploaded"}), 400

    f = request.files["screenshot"]
    if not f.filename:
        return jsonify({"success": False, "error": "No file selected"}), 400

    if not _allowed_screenshot(f.filename):
        return jsonify({
            "success": False,
            "error":   "Invalid file type. Please upload a PNG, JPG, JPEG, or WEBP image."
        }), 400

    image_bytes = f.read()
    if not image_bytes:
        return jsonify({"success": False, "error": "Uploaded file is empty."}), 400
    if len(image_bytes) > MAX_SCREENSHOT_SIZE_BYTES:
        return jsonify({"success": False, "error": "Screenshot too large (max 10 MB)."}), 400

    # ── 3. Save screenshot ─────────────────────────────────────────────────
    orig_ext            = f.filename.rsplit(".", 1)[-1].lower()
    screenshot_filename = f"pay_{session_id[:8]}_{uuid.uuid4().hex[:6]}.{orig_ext}"
    upload_dir          = Config.UPLOAD_FOLDER
    os.makedirs(upload_dir, exist_ok=True)
    with open(os.path.join(upload_dir, screenshot_filename), "wb") as out:
        out.write(image_bytes)

    # ── 4. Verification using SESSION merchant snapshot ────────────────────
    session_started_at          = datetime.fromisoformat(session["session_started_at"])
    expected_amount             = float(session["order_amount"])
    m_upi, m_name, m_identifiers = get_session_merchant(session)

    result = verify_screenshot(
        image_bytes,
        expected_amount,
        session_started_at,
        merchant_name=m_name,
        merchant_identifiers=m_identifiers,
    )

    transaction_ref = result.get("transaction_ref")

    # ── 5. Duplicate transaction check ────────────────────────────────────
    if result["success"] and transaction_ref:
        if is_transaction_ref_used(transaction_ref):
            result = {
                "success":         False,
                "status":          "failed",
                "message":         (
                    "This transaction reference has already been used for another order. "
                    "Please contact counter staff if this is an error."
                ),
                "checks":          result.get("checks", {}),
                "transaction_ref": transaction_ref,
            }

    # ── 6. Persist result ─────────────────────────────────────────────────
    update_payment_session_verification(
        session_id=session_id,
        status=result["status"],
        message=result["message"],
        transaction_ref=transaction_ref,
        screenshot_filename=screenshot_filename,
    )
    if result["success"] and transaction_ref:
        record_used_transaction_ref(transaction_ref, expected_amount, session_id)

    # ── 7. Return response ─────────────────────────────────────────────────
    return jsonify({
        "success":         result["success"],
        "message":         result["message"],
        "status":          result["status"],
        "checks":          result.get("checks", {}),
        "transaction_ref": transaction_ref,
        "prototype_note":  result.get("prototype_note", ""),
    }), (200 if result["success"] else 422)


# ─── Razorpay Payment Gateway Endpoints ────────────────────────────────────────

@payment_bp.route("/create-order", methods=["POST"])
def create_razorpay_order():
    """
    POST /api/payment/create-order
    1. Receive existing CampusPrint order identifier.
    2. Retrieve order from database.
    3. Calculate/read authoritative final amount from database (never trust frontend).
    4. Create Razorpay Order using:
       - amount = final amount in paise (total_price * 100)
       - currency = INR
       - receipt = unique CampusPrint order reference (max 40 chars)
    5. Return razorpay_key_id, razorpay_order_id, amount, currency.
    """
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    order_id = (data.get("order_id") or data.get("campusprint_order_id") or "").strip()

    if not order_id:
        return jsonify({"success": False, "error": "Order ID is required."}), 400

    order = get_order_by_id(order_id)
    if not order:
        return jsonify({"success": False, "error": f"Order '{order_id}' not found."}), 404

    # Check if order is already paid
    if str(order.get("payment_status", "")).strip().lower() == "paid":
        return jsonify({"success": False, "error": "Order is already paid."}), 400

    # Authoritative amount from database
    try:
        total_price = float(order.get("total_price", 0))
    except (TypeError, ValueError):
        total_price = 0.0

    if total_price <= 0:
        return jsonify({"success": False, "error": "Order amount must be greater than zero."}), 400

    amount_paise = int(round(total_price * 100))

    # Razorpay credentials check
    key_id = Config.RAZORPAY_KEY_ID or os.environ.get("RAZORPAY_KEY_ID", "")
    key_secret = Config.RAZORPAY_KEY_SECRET or os.environ.get("RAZORPAY_KEY_SECRET", "")
    if not key_id or not key_secret:
        return jsonify({
            "success": False,
            "error": "Razorpay payment gateway is not configured on this server."
        }), 503

    try:
        import razorpay
        client = razorpay.Client(auth=(key_id, key_secret))
        receipt = f"rcpt_{order_id}"[-40:]
        notes = {
            "order_id": order_id,
            "student_name": str(order.get("student_name", ""))[:50],
            "roll_number": str(order.get("roll_number", ""))[:30],
        }
        rzp_order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
            "notes": notes,
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": "Failed to create Razorpay order. Please try again."
        }), 502

    razorpay_order_id = rzp_order.get("id") if isinstance(rzp_order, dict) else getattr(rzp_order, "id", None)
    if not razorpay_order_id:
        return jsonify({
            "success": False,
            "error": "Payment gateway did not return a valid order ID."
        }), 502

    # Persist the Razorpay order ID on the CampusPrint order
    update_order_razorpay_order_id(order_id, razorpay_order_id)

    return jsonify({
        "success": True,
        "razorpay_key_id": key_id,
        "razorpay_order_id": razorpay_order_id,
        "amount": amount_paise,
        "currency": "INR",
    }), 200


@payment_bp.route("/verify", methods=["POST"])
def verify_razorpay_payment():
    """
    POST /api/payment/verify
    1. Receive razorpay_order_id, razorpay_payment_id, razorpay_signature, and order_id.
    2. Retrieve order from database.
    3. Ensure the Razorpay order belongs to the correct CampusPrint order.
    4. Verify Razorpay signature server-side using RAZORPAY_KEY_SECRET.
    5. If valid, mark the CampusPrint order as PAID.
    6. If invalid, do NOT mark the order paid and return error response.
    """
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    order_id = (data.get("order_id") or data.get("campusprint_order_id") or "").strip()
    razorpay_order_id = (data.get("razorpay_order_id") or "").strip()
    razorpay_payment_id = (data.get("razorpay_payment_id") or "").strip()
    razorpay_signature = (data.get("razorpay_signature") or "").strip()

    if not order_id:
        return jsonify({"success": False, "error": "CampusPrint order ID is required."}), 400

    if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
        return jsonify({
            "success": False,
            "error": "Missing required Razorpay payment verification parameters."
        }), 400

    order = get_order_by_id(order_id)
    if not order:
        return jsonify({"success": False, "error": f"Order '{order_id}' not found."}), 404

    # Ensure the Razorpay order belongs to the correct CampusPrint order
    stored_rzp_order_id = order.get("razorpay_order_id")
    if stored_rzp_order_id and stored_rzp_order_id != razorpay_order_id:
        return jsonify({
            "success": False,
            "error": "Razorpay order ID mismatch with CampusPrint order."
        }), 400

    key_id = Config.RAZORPAY_KEY_ID or os.environ.get("RAZORPAY_KEY_ID", "")
    key_secret = Config.RAZORPAY_KEY_SECRET or os.environ.get("RAZORPAY_KEY_SECRET", "")
    if not key_id or not key_secret:
        return jsonify({
            "success": False,
            "error": "Razorpay payment gateway credentials are not configured on this server."
        }), 503

    import razorpay
    client = razorpay.Client(auth=(key_id, key_secret))

    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature
        })
    except razorpay.errors.SignatureVerificationError:
        return jsonify({
            "success": False,
            "error": "Payment verification failed: invalid signature."
        }), 400
    except Exception:
        return jsonify({
            "success": False,
            "error": "Payment verification failed."
        }), 400

    # Signature is valid! Mark order as PAID
    updated_order = mark_order_paid(
        order_id=order_id,
        razorpay_payment_id=razorpay_payment_id,
        razorpay_signature=razorpay_signature,
        razorpay_order_id=razorpay_order_id
    )

    return jsonify({
        "success": True,
        "message": "Payment verified successfully. Order confirmed.",
        "order": updated_order
    }), 200


@payment_bp.route("/webhook", methods=["POST"])
def razorpay_webhook():
    """
    POST /api/payment/webhook
    Validates Razorpay webhook signatures using RAZORPAY_WEBHOOK_SECRET.
    Marks orders paid if webhook indicates payment.captured or order.paid.
    """
    webhook_secret = Config.RAZORPAY_WEBHOOK_SECRET or os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
    if not webhook_secret:
        return jsonify({
            "success": False,
            "error": "Webhook secret is not configured."
        }), 400

    signature = request.headers.get("X-Razorpay-Signature", "")
    if not signature:
        return jsonify({
            "success": False,
            "error": "Missing X-Razorpay-Signature header."
        }), 400

    raw_body = request.get_data()

    key_id = Config.RAZORPAY_KEY_ID or os.environ.get("RAZORPAY_KEY_ID", "")
    key_secret = Config.RAZORPAY_KEY_SECRET or os.environ.get("RAZORPAY_KEY_SECRET", "")

    import razorpay
    client = razorpay.Client(auth=(key_id or "dummy", key_secret or "dummy"))

    try:
        client.utility.verify_webhook_signature(
            raw_body.decode("utf-8") if isinstance(raw_body, bytes) else str(raw_body),
            signature,
            webhook_secret
        )
    except razorpay.errors.SignatureVerificationError:
        return jsonify({"success": False, "error": "Invalid webhook signature."}), 400
    except Exception:
        return jsonify({"success": False, "error": "Webhook signature verification error."}), 400

    payload = request.get_json(silent=True) or {}
    event = payload.get("event", "")

    if event in ("payment.captured", "order.paid"):
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_entity = payload.get("payload", {}).get("order", {}).get("entity", {})

        rzp_order_id = payment_entity.get("order_id") or order_entity.get("id")
        rzp_payment_id = payment_entity.get("id")
        notes = payment_entity.get("notes") or order_entity.get("notes") or {}
        campus_order_id = notes.get("campusprint_order_id") or notes.get("order_id")

        order = None
        if campus_order_id:
            order = get_order_by_id(campus_order_id)
        if not order and rzp_order_id:
            order = get_order_by_razorpay_order_id(rzp_order_id)

        if order and str(order.get("payment_status", "")).lower() != "paid":
            mark_order_paid(
                order_id=order["order_id"],
                razorpay_payment_id=rzp_payment_id,
                razorpay_order_id=rzp_order_id
            )

    return jsonify({"status": "ok"}), 200
