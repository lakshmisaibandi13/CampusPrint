import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "xerox-stationery-secret-key-2026")
    
    # Database
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    DATABASE_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "xerox_store.db"))
    
    # Uploads
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB
    ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "txt", "jpg", "jpeg", "png"}
    
    # Configurable Pricing (All in INR ₹)
    PRICING = {
        "bw_per_page": 2.00,       # ₹2 per page for Black & White
        "color_per_page": 5.00,    # ₹5 per page for Color
        "types": [
            {"id": "regular", "name": "Standard Document / Notes", "extra_cost": 0.0},
            {"id": "assignment", "name": "College Assignment / Lab Record", "extra_cost": 0.0},
            {"id": "project_report", "name": "Final Project Report", "extra_cost": 15.0},
            {"id": "certificate", "name": "Glossy / Certificate Print", "extra_cost": 20.0}
        ],
        "bindings": [
            {"id": "none", "name": "No Binding (Loose Sheets / Stapled)", "price": 0.0},
            {"id": "corner_staple", "name": "Corner Staple", "price": 2.0},
            {"id": "spiral", "name": "Spiral Binding (Clear Cover)", "price": 30.0},
            {"id": "soft_binding", "name": "Soft Book Binding", "price": 50.0},
            {"id": "hard_binding", "name": "Hard Bound Golden Embossed", "price": 160.0}
        ]
    }
    
    # Official College Stationery Products
    STATIONERY_ITEMS = [
        {"id": "black_pen", "name": "Black Pen", "price": 5.0, "unit": "each", "category": "Pens & Pencils"},
        {"id": "blue_pen", "name": "Blue Pen", "price": 5.0, "unit": "each", "category": "Pens & Pencils"},
        {"id": "red_pen", "name": "Red Pen", "price": 5.0, "unit": "each", "category": "Pens & Pencils"},
        {"id": "pencil", "name": "Pencil", "price": 5.0, "unit": "each", "category": "Pens & Pencils"},
        {"id": "eraser", "name": "Eraser", "price": 5.0, "unit": "each", "category": "Pens & Pencils"},
        {"id": "sharpener", "name": "Sharpener", "price": 3.0, "unit": "each", "category": "Pens & Pencils"},
        {"id": "plain_small_notebook", "name": "Small Plain Notebook", "price": 20.0, "unit": "each", "category": "Notebooks"},
        {"id": "plain_long_notebook", "name": "Long Plain Notebook", "price": 50.0, "unit": "each", "category": "Notebooks"},
        {"id": "ruled_long_notebook", "name": "Long Ruled Notebook", "price": 50.0, "unit": "each", "category": "Notebooks"},
        {"id": "assignment_booklet", "name": "Assignment Booklet", "price": 15.0, "unit": "each", "category": "Papers, Booklets & Records"},
        {"id": "record_book", "name": "Record Book", "price": 90.0, "unit": "each", "category": "Papers, Booklets & Records"},
        {"id": "record_paper", "name": "Record Paper", "price": 1.0, "unit": "per page", "category": "Papers, Booklets & Records"},
        {"id": "a4_sheet", "name": "A4 Sheet", "price": 1.0, "unit": "per sheet", "category": "Papers, Booklets & Records"},
        {"id": "bee_record", "name": "BEE Record", "price": 150.0, "unit": "each", "category": "Papers, Booklets & Records"},
        {"id": "aep_record", "name": "AEP Record", "price": 100.0, "unit": "each", "category": "Papers, Booklets & Records"},
        {"id": "english_record", "name": "English Record", "price": 100.0, "unit": "each", "category": "Papers, Booklets & Records"},
    ]
    
    # Default Staff Credentials (for local development/evaluation)
    STAFF_USERNAME = os.environ.get("STAFF_USERNAME", "staff@mlrit")
    STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD", "xerox@mlrit")
    STAFF_TOKEN_SECRET = os.environ.get("STAFF_TOKEN_SECRET", "staff-jwt-auth-token-key")

    # ── UPI / Merchant Identity ──────────────────────────────────────────────
    # Used by the payment screenshot verification service to confirm the
    # correct merchant received the payment.
    # Update MERCHANT_NAME / MERCHANT_UPI_ID to match your real UPI details.
    # From QR image scan: lakshmisaibandi@fampay / "Bandi Lakshmi sai"
    MERCHANT_UPI_ID = os.environ.get("MERCHANT_UPI_ID", "lakshmisaibandi@fampay")
    MERCHANT_NAME   = os.environ.get("MERCHANT_NAME",   "Lakshmi Sai Bandi")

    # All name/ID variants that may appear in payment app screenshots.
    # Matching is case-insensitive. Add every known variation of the
    # registered UPI name, merchant name, and UPI ID.
    MERCHANT_IDENTIFIERS = [
        "lakshmi sai bandi",
        "bandi lakshmi sai",       # reversed name order (some apps print this way)
        "lakshmi sai",
        "lakshmisaibandi",
        "lakshmisaibandi@fampay",
        "lakshmisaibandi@fam",     # OCR may truncate the domain
        "campusprint",             # display-name fallback
        "campus print",
        "campusprint@upi",
    ]

    # ── Tesseract OCR path ───────────────────────────────────────────────────
    # Explicit path to the Tesseract executable.
    # Set TESSERACT_CMD env var to override (useful on Linux/Mac servers).
    TESSERACT_CMD = os.environ.get(
        "TESSERACT_CMD",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )

    # ── Server timezone offset from UTC (hours) ──────────────────────────────
    # payment_sessions timestamps are stored as SQLite UTC.
    # UPI app screenshots show local time (IST = UTC+5.5).
    # Set this to the local timezone offset so time-window checks work.
    # Examples: IST=5.5  UTC=0  PST=-8
    TIMEZONE_OFFSET_HOURS = float(os.environ.get("TIMEZONE_OFFSET_HOURS", "5.5"))
