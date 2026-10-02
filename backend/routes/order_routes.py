import os
import uuid
import pymupdf
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from config import Config
from database import (
    calculate_order_price, create_order, find_order, get_order_by_id,
    create_multi_order, get_order_items, get_order_stationery_items,
    calculate_printing_duration_seconds, calculate_order_queue,
    get_payment_session
)

order_bp = Blueprint("order_bp", __name__, url_prefix="/api")

def allowed_file(filename):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in Config.ALLOWED_EXTENSIONS

def inspect_pdf_pages(file_path):
    """
    Inspects a PDF file using PyMuPDF and returns page count.
    Raises ValueError if corrupted, encrypted, or invalid.
    """
    try:
        doc = pymupdf.open(file_path)
        if doc.is_encrypted:
            if not doc.authenticate(""):
                doc.close()
                raise ValueError("PDF is password-protected. Please remove password and re-upload.")
        page_count = len(doc)
        doc.close()
        if page_count < 1:
            raise ValueError("PDF has 0 pages or contains no readable content.")
        return page_count
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Invalid or corrupted PDF file. Please ensure it is a valid PDF document.")

@order_bp.route("/inspect-file", methods=["POST"])
def inspect_file():
    """
    Inspects an uploaded file before order submission to detect page count and validity.
    """
    if "document" not in request.files:
        return jsonify({"success": False, "error": "No document file uploaded"}), 400
        
    file = request.files["document"]
    if file.filename == "":
        return jsonify({"success": False, "error": "No file selected"}), 400
        
    if not allowed_file(file.filename):
        allowed_list = ", ".join(Config.ALLOWED_EXTENSIONS)
        return jsonify({
            "success": False, 
            "error": f"Invalid file type. Allowed formats: {allowed_list}"
        }), 400

    filename = secure_filename(file.filename) or "document"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    
    file_bytes = file.read()
    if len(file_bytes) == 0:
        return jsonify({"success": False, "error": "Uploaded file is empty (0 bytes)."}), 400
        
    file_size_kb = round(len(file_bytes) / 1024, 2)
    
    if ext == "pdf":
        try:
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            if doc.is_encrypted and not doc.authenticate(""):
                doc.close()
                return jsonify({
                    "success": False,
                    "error": "The uploaded PDF is password protected. Please remove password and re-upload."
                }), 400
            page_count = len(doc)
            doc.close()
            if page_count < 1:
                return jsonify({"success": False, "error": "PDF has 0 pages."}), 400
            return jsonify({
                "success": True,
                "is_pdf": True,
                "pages": page_count,
                "filename": filename,
                "file_size_kb": file_size_kb,
                "message": f"{page_count} pages detected"
            }), 200
        except Exception:
            return jsonify({
                "success": False,
                "error": "Invalid or corrupted PDF file. Please verify and upload a valid PDF."
            }), 400
    else:
        # Non-PDF files (images, text files) default to 1 page
        return jsonify({
            "success": True,
            "is_pdf": False,
            "pages": 1,
            "filename": filename,
            "file_size_kb": file_size_kb,
            "message": "1 page detected"
        }), 200

@order_bp.route("/stationery", methods=["GET"])
def get_stationery():
    return jsonify({
        "success": True,
        "items": Config.STATIONERY_ITEMS
    }), 200

@order_bp.route("/pricing", methods=["GET"])
def get_pricing():
    return jsonify({
        "success": True,
        "pricing": Config.PRICING,
        "stationery": Config.STATIONERY_ITEMS
    }), 200

@order_bp.route("/pricing/calculate", methods=["POST"])
def calculate_quote():
    data = request.get_json() or {}
    try:
        pages = max(1, int(data.get("pages", 1)))
        copies = max(1, int(data.get("copies", 1)))
        color_mode = data.get("color_mode", "bw")
        side_mode = data.get("side_mode", "single")
        print_type = data.get("print_type", "regular")
        binding_type = data.get("binding_type", "none")
        
        quote = calculate_order_price(pages, copies, color_mode, side_mode, print_type, binding_type)
        return jsonify({
            "success": True,
            "quote": quote
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@order_bp.route("/orders", methods=["POST"])
def place_order():
    if "document" not in request.files:
        return jsonify({"success": False, "error": "No document file uploaded"}), 400
        
    file = request.files["document"]
    if file.filename == "":
        return jsonify({"success": False, "error": "Please select a file to upload"}), 400
        
    if not allowed_file(file.filename):
        allowed_list = ", ".join(Config.ALLOWED_EXTENSIONS)
        return jsonify({
            "success": False, 
            "error": f"Invalid file type. Allowed formats: {allowed_list}"
        }), 400

    form = request.form
    student_name = form.get("student_name", "").strip()
    roll_number = form.get("roll_number", "").strip()
    phone_number = form.get("phone_number", "").strip()
    email = form.get("email", "").strip()
    
    if not student_name or not roll_number or not phone_number:
        return jsonify({
            "success": False, 
            "error": "Student Name, Roll Number, and Phone Number are required"
        }), 400
        
    try:
        copies = max(1, int(form.get("copies", 1)))
    except ValueError:
        return jsonify({"success": False, "error": "Copies must be a valid number"}), 400
        
    color_mode = form.get("color_mode", "bw")
    side_mode = form.get("side_mode", "single")
    print_type = form.get("print_type", "regular")
    binding_type = form.get("binding_type", "none")
    special_instructions = form.get("special_instructions", "")
    payment_method = form.get("payment_method", "Simulated UPI (GPay/PhonePe)")

    # Secure file save
    orig_filename = secure_filename(file.filename) or "document.pdf"
    unique_prefix = uuid.uuid4().hex[:8]
    stored_filename = f"{unique_prefix}_{orig_filename}"
    upload_dir = Config.UPLOAD_FOLDER
    os.makedirs(upload_dir, exist_ok=True)
    
    saved_path = os.path.join(upload_dir, stored_filename)
    file.save(saved_path)
    file_size_kb = round(os.path.getsize(saved_path) / 1024, 2)

    # CRITICAL: Automatically inspect and determine PDF page count on backend.
    # Never trust client-supplied page counts for PDFs.
    is_pdf = orig_filename.lower().endswith(".pdf")
    if is_pdf:
        try:
            pages = inspect_pdf_pages(saved_path)
        except ValueError as err:
            if os.path.exists(saved_path):
                os.remove(saved_path)
            return jsonify({"success": False, "error": str(err)}), 400
    else:
        try:
            pages = max(1, int(form.get("pages", 1)))
        except ValueError:
            pages = 1

    # Server-side quote calculation using verified page count
    calc = calculate_order_price(pages, copies, color_mode, side_mode, print_type, binding_type)
    
    order_payload = {
        "student_name": student_name,
        "roll_number": roll_number,
        "phone_number": phone_number,
        "email": email,
        "document_name": orig_filename,
        "stored_filename": stored_filename,
        "file_size_kb": file_size_kb,
        "print_type": print_type,
        "color_mode": color_mode,
        "side_mode": side_mode,
        "pages": pages,
        "copies": copies,
        "calculated_sheets": calc["total_sheets"],
        "binding_type": binding_type,
        "special_instructions": special_instructions,
        "total_price": calc["total_price"],
        "payment_method": payment_method,
        "payment_status": "Pending Cash on Collection" if payment_method == "Cash on Collection" else "Pending"
    }

    new_order = create_order(order_payload)
    if not new_order:
        return jsonify({"success": False, "error": "Failed to create order in database"}), 500

    return jsonify({
        "success": True,
        "message": "Order placed successfully!",
        "order": new_order
    }), 201

@order_bp.route("/orders/track/<query>", methods=["GET"])
def track_order(query):
    results = find_order(query)
    if not results:
        return jsonify({
            "success": False,
            "message": f"No order found matching '{query}'. Please verify your Order ID or Token Number."
        }), 404
        
    enriched = []
    for o in results:
        o_copy = dict(o)
        o_copy["items"] = get_order_items(o["order_id"])
        o_copy["stationery_items_list"] = get_order_stationery_items(o["order_id"])
        enriched.append(o_copy)

    return jsonify({
        "success": True,
        "orders": enriched
    }), 200

@order_bp.route("/orders/<order_id>", methods=["GET"])
def get_order_details(order_id):
    order = get_order_by_id(order_id)
    if not order:
        return jsonify({"success": False, "message": "Order not found"}), 404
    items = get_order_items(order_id)
    stationery = get_order_stationery_items(order_id)
    return jsonify({"success": True, "order": order, "items": items, "stationery_items": stationery}), 200


# ─── Multi-File / Mixed Order ──────────────────────────────────────────────────

@order_bp.route("/orders/multi", methods=["POST"])
def place_multi_order():
    """
    Place a single order that contains multiple uploaded files, stationery items, or both.
    """
    form = request.form
    student_name = form.get("student_name", "").strip()
    roll_number  = form.get("roll_number",  "").strip()
    phone_number = form.get("phone_number", "").strip()
    email        = form.get("email",        "").strip()

    if not student_name or not roll_number or not phone_number:
        return jsonify({"success": False,
                        "error": "Student Name, Roll Number, and Phone Number are required"}), 400

    # ── Parse and validate stationery items ─────────────────────────────────
    stationery_raw = form.get("stationery_items", "")
    stationery_list = []
    stationery_total = 0.0
    if stationery_raw:
        import json
        try:
            parsed_items = json.loads(stationery_raw) if isinstance(stationery_raw, str) else stationery_raw
            if isinstance(parsed_items, list):
                catalog_map = {item["id"]: item for item in Config.STATIONERY_ITEMS}
                for it in parsed_items:
                    it_id = str(it.get("id", "")).strip()
                    try:
                        qty = int(it.get("quantity", 0))
                    except (ValueError, TypeError):
                        qty = 0
                    if qty > 0 and it_id in catalog_map:
                        cat_item = catalog_map[it_id]
                        unit_price = float(cat_item["price"])
                        line_total = round(unit_price * qty, 2)
                        stationery_total += line_total
                        stationery_list.append({
                            "id": it_id,
                            "name": cat_item["name"],
                            "price": unit_price,
                            "quantity": qty,
                            "subtotal": line_total,
                        })
        except Exception as e:
            return jsonify({"success": False, "error": f"Invalid stationery items format: {e}"}), 400

    stationery_total = round(stationery_total, 2)

    # ── Collect uploaded files ────────────────────────────────────────────────
    file_keys = sorted(
        [k for k in request.files if k.startswith("document_")],
        key=lambda k: int(k.split("_", 1)[1])
    )

    has_files = len(file_keys) > 0
    has_stationery = len(stationery_list) > 0

    if not has_files and not has_stationery:
        return jsonify({"success": False, "error": "Please upload documents or select stationery items to place an order."}), 400

    if len(file_keys) > 20:
        return jsonify({"success": False, "error": "Maximum 20 files per order"}), 400

    # Shared order settings
    print_type           = form.get("print_type",            "regular")
    binding_type         = form.get("binding_type",          "none")
    special_instructions = form.get("special_instructions",  "")
    payment_method       = form.get("payment_method",        "UPI")

    upload_dir = Config.UPLOAD_FOLDER
    os.makedirs(upload_dir, exist_ok=True)

    saved_items   = []   # accumulates per-file dicts for DB + response
    saved_paths   = []   # for cleanup on error

    try:
        if has_files:
            for key in file_keys:
                idx_str = key.split("_", 1)[1]          # "0", "1", …
                file    = request.files[key]

                if file.filename == "":
                    return jsonify({"success": False,
                                    "error": f"File slot {idx_str} has no file selected"}), 400

                if not allowed_file(file.filename):
                    allowed_list = ", ".join(Config.ALLOWED_EXTENSIONS)
                    return jsonify({"success": False,
                                    "error": f"File '{file.filename}' has an invalid type. Allowed: {allowed_list}"}), 400

                # Per-file settings
                try:
                    copies = max(1, int(form.get(f"copies_{idx_str}", 1)))
                except ValueError:
                    copies = 1
                color_mode = form.get(f"color_mode_{idx_str}", "bw")
                side_mode  = form.get(f"side_mode_{idx_str}",  "single")

                # Save file
                orig_filename   = secure_filename(file.filename) or "document.pdf"
                unique_prefix   = uuid.uuid4().hex[:8]
                stored_filename = f"{unique_prefix}_{orig_filename}"
                saved_path      = os.path.join(upload_dir, stored_filename)
                file.save(saved_path)
                saved_paths.append(saved_path)

                file_size_kb = round(os.path.getsize(saved_path) / 1024, 2)

                # Server-side page count
                is_pdf = orig_filename.lower().endswith(".pdf")
                if is_pdf:
                    try:
                        pages = inspect_pdf_pages(saved_path)
                    except ValueError as err:
                        return jsonify({"success": False,
                                        "error": f"File '{orig_filename}': {err}"}), 400
                else:
                    try:
                        pages = max(1, int(form.get(f"pages_{idx_str}", 1)))
                    except ValueError:
                        pages = 1

                # Server-side price calculation
                calc = calculate_order_price(
                    pages, copies, color_mode, side_mode, print_type, "none"
                )

                saved_items.append({
                    "document_name":   orig_filename,
                    "stored_filename": stored_filename,
                    "file_size_kb":    file_size_kb,
                    "pages":           pages,
                    "copies":          copies,
                    "color_mode":      color_mode,
                    "side_mode":       side_mode,
                    "calculated_sheets": calc["total_sheets"],
                    "printing_cost":   calc["printing_cost"],
                    "item_total":      calc["printing_cost"],
                })

            # ── Binding cost (applied once to whole order) ────────────────────────
            binding_cost = 0.0
            for b in Config.PRICING.get("bindings", []):
                if b["id"] == binding_type:
                    binding_cost = float(b.get("price", 0.0))
                    break

            # ── Type surcharge ───────────────────────────────────────────────────
            type_extra = 0.0
            total_copies_all = sum(it["copies"] for it in saved_items)
            for t in Config.PRICING.get("types", []):
                if t["id"] == print_type:
                    type_extra = float(t.get("extra_cost", 0.0)) * total_copies_all
                    break

            printing_total = round(
                sum(it["item_total"] for it in saved_items) + binding_cost + type_extra, 2
            )
        else:
            printing_total = 0.0
            binding_cost = 0.0
            type_extra = 0.0

        grand_total = round(printing_total + stationery_total, 2)

        # ── Verify payment session if session ID passed (legacy OCR support) ──
        session_id = form.get("payment_session_id")
        initial_payment_status = "Pending"
        if session_id:
            sess = get_payment_session(session_id)
            if not sess:
                return jsonify({
                    "success": False,
                    "error": "Payment session not found. Please restart payment."
                }), 400
            if sess.get("verification_status") != "verified":
                return jsonify({
                    "success": False,
                    "error": "Payment verification required. Please verify your payment screenshot before placing order."
                }), 400
            if abs(float(sess["order_amount"]) - grand_total) > 0.01:
                return jsonify({
                    "success": False,
                    "error": f"Payment amount mismatch: session was verified for ₹{sess['order_amount']}, but order total is ₹{grand_total}"
                }), 400
            initial_payment_status = "Paid"
        elif payment_method == "Cash on Collection":
            initial_payment_status = "Pending Cash on Collection"
        else:
            initial_payment_status = "Pending"

        order_payload = {
            "student_name":        student_name,
            "roll_number":         roll_number,
            "phone_number":        phone_number,
            "email":               email,
            "print_type":          print_type if has_files else "none",
            "binding_type":        binding_type if has_files else "none",
            "special_instructions": special_instructions,
            "printing_total":      printing_total,
            "stationery_total":    stationery_total,
            "total_price":         grand_total,
            "payment_method":      payment_method,
            "payment_status":      initial_payment_status,
        }

        new_order = create_multi_order(order_payload, saved_items, stationery_list)
        if not new_order:
            return jsonify({"success": False,
                            "error": "Failed to create order in database"}), 500

        return jsonify({
            "success":          True,
            "message":          "Order placed successfully!",
            "order":            new_order,
            "items":            saved_items,
            "stationery_items": stationery_list,
            "printing_total":   printing_total,
            "stationery_total": stationery_total,
            "grand_total":      grand_total,
        }), 201

    except Exception as exc:
        for p in saved_paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
        return jsonify({"success": False, "error": f"Unexpected error: {exc}"}), 500
