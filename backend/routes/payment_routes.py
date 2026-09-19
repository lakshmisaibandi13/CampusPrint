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
