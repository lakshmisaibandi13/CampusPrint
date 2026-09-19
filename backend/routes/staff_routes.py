import os
from flask import Blueprint, request, jsonify, send_from_directory
from config import Config
from database import (
    get_db_connection, 
    list_orders, 
    get_order_by_id, 
    update_order_status, 
    get_stats
)

staff_bp = Blueprint("staff_bp", __name__, url_prefix="/api/staff")

VALID_STATUSES = [
    "Received", "Order Received", "Payment Successful",
    "Processing", "Printing in Progress", "Preparing Stationery",
    "Stage Ready", "Ready for Collection", "Collected", "Completed", "Rejected"
]

@staff_bp.route("/login", methods=["POST"])
def staff_login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM staff_users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return jsonify({"success": False, "error": "Invalid staff credentials"}), 401
        
    # Simple, secure mock session token
    token = f"staff-auth-session-{user['id']}-xerox"
    return jsonify({
        "success": True,
        "message": "Login successful",
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"]
        }
    }), 200

@staff_bp.route("/stats", methods=["GET"])
def staff_dashboard_stats():
    stats = get_stats()
    return jsonify({"success": True, "stats": stats}), 200

@staff_bp.route("/orders", methods=["GET"])
def staff_get_orders():
    status = request.args.get("status")
    search = request.args.get("search")
    sort_by = request.args.get("sort", "desc")
    
    orders = list_orders(status=status, search=search, sort_by=sort_by)
    return jsonify({
        "success": True, 
        "count": len(orders),
        "orders": orders
    }), 200

@staff_bp.route("/orders/<order_id>", methods=["GET"])
def staff_order_detail(order_id):
    order = get_order_by_id(order_id)
    if not order:
        return jsonify({"success": False, "error": "Order not found"}), 404
    return jsonify({"success": True, "order": order}), 200

@staff_bp.route("/orders/<order_id>/status", methods=["PATCH"])
def staff_update_status(order_id):
    data = request.get_json() or {}
    new_status = data.get("status", "").strip()
    rejection_reason = data.get("rejection_reason")
    
    if new_status not in VALID_STATUSES:
        return jsonify({
            "success": False, 
            "error": f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}"
        }), 400
        
    if new_status == "Rejected" and not rejection_reason:
        rejection_reason = "Order rejected by staff (e.g. invalid document or corrupted format)."

    updated = update_order_status(order_id, new_status, rejection_reason)
    if not updated:
        return jsonify({"success": False, "error": "Order not found"}), 404
        
    return jsonify({
        "success": True,
        "message": f"Order status updated to '{new_status}'",
        "order": updated
    }), 200

@staff_bp.route("/orders/<order_id>/file", methods=["GET"])
def download_order_document(order_id):
    order = get_order_by_id(order_id)
    if not order:
        return jsonify({"success": False, "error": "Order not found"}), 404
        
    filename = order.get("stored_filename")
    if not filename:
        return jsonify({"success": False, "error": "File record not found"}), 404
        
    upload_dir = Config.UPLOAD_FOLDER
    file_path = os.path.join(upload_dir, filename)
    if not os.path.exists(file_path):
        return jsonify({"success": False, "error": "Document file not found on server disk"}), 404

    as_attachment = request.args.get("download", "false").lower() == "true"
    return send_from_directory(
        upload_dir, 
        filename, 
        download_name=order.get("document_name", filename), 
        as_attachment=as_attachment
    )
