import os
import re
import random
import string
import threading
import sqlite3
from datetime import datetime, date, timedelta, timezone
from config import Config

# Asia/Kolkata (IST, UTC+05:30) timezone definition
try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30), "IST")


def get_ist_now() -> datetime:
    """Return timezone-aware current datetime in Asia/Kolkata (IST, UTC+05:30)."""
    return datetime.now(IST)


def to_ist_datetime(val) -> datetime | None:
    """Safely convert string, date, or datetime to timezone-aware IST datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.replace(tzinfo=IST) if val.tzinfo is None else val.astimezone(IST)
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time(), tzinfo=IST)
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", ""))
        return dt.replace(tzinfo=IST) if dt.tzinfo is None else dt.astimezone(IST)
    except Exception:
        return None

# Optional PostgreSQL driver support (installed via psycopg2-binary)
try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

_order_creation_lock = threading.Lock()


def is_postgres() -> bool:
    """Return True if a DATABASE_URL is configured for PostgreSQL."""
    db_url = getattr(Config, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")
    return bool(db_url and db_url.strip())


def _to_pg_query(sql: str) -> str:
    """
    Translates SQLite-style queries to PostgreSQL-compatible queries:
    1. Converts SQLite-specific 'BEGIN IMMEDIATE' to a no-op comment.
    2. Converts SQLite 'SUBSTR(created_at, 1, 10)' to 'DATE(created_at)' for Postgres timestamps.
    3. Replaces '?' parameter placeholders with '%s' outside quotes.
    """
    trimmed = sql.strip().rstrip(";").strip()
    if trimmed.upper() == "BEGIN IMMEDIATE":
        return "-- NOOP"

    # Replace SUBSTR on timestamps which PostgreSQL rejects
    sql_mod = sql.replace("SUBSTR(created_at, 1, 10)", "DATE(created_at)")

    out = []
    in_single = False
    in_double = False
    i = 0
    n = len(sql_mod)
    while i < n:
        ch = sql_mod[i]
        if ch == "'" and not in_double:
            if in_single and i + 1 < n and sql_mod[i + 1] == "'":
                out.append("''")
                i += 2
                continue
            in_single = not in_single
            out.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
        elif ch == '?' and not in_single and not in_double:
            out.append('%s')
        else:
            out.append(ch)
        i += 1
    return "".join(out)


class PostgresCursorWrapper:
    """Wraps psycopg2 cursor to provide seamless compatibility with sqlite3 cursor semantics."""
    def __init__(self, raw_cursor):
        self._cur = raw_cursor

    def execute(self, sql, params=None):
        translated = _to_pg_query(sql)
        if translated.strip() == "-- NOOP":
            return self
        if params is None:
            self._cur.execute(translated)
        else:
            self._cur.execute(translated, params)
        return self

    def executemany(self, sql, seq_of_params):
        translated = _to_pg_query(sql)
        self._cur.executemany(translated, seq_of_params)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, size=None):
        return self._cur.fetchmany(size) if size is not None else self._cur.fetchmany()

    def close(self):
        self._cur.close()

    def __iter__(self):
        return iter(self._cur)

    def __getattr__(self, name):
        return getattr(self._cur, name)


class PostgresConnectionWrapper:
    """Wraps psycopg2 connection to provide conn.execute() and standard connection semantics."""
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        return PostgresCursorWrapper(self._conn.cursor())

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()

    def __getattr__(self, name):
        return getattr(self._conn, name)


def get_db_connection():
    """
    Returns a database connection.
    If DATABASE_URL is set, connects to PostgreSQL using psycopg2 (for Render campusprint-db).
    Otherwise, connects to the local SQLite database for development and testing.
    """
    db_url = getattr(Config, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")
    if db_url and db_url.strip():
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError("DATABASE_URL is configured but psycopg2 is not installed. Run 'pip install psycopg2-binary'.")
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        raw_conn = psycopg2.connect(db_url, cursor_factory=psycopg2.extras.DictCursor)
        return PostgresConnectionWrapper(raw_conn)
    else:
        conn = sqlite3.connect(Config.DATABASE_PATH, timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn


def init_db():
    """Initializes tables, applies live migrations, and seeds default staff credentials."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if is_postgres():
        # PostgreSQL Schema & Migrations
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            order_id TEXT UNIQUE NOT NULL,
            token_number TEXT NOT NULL,
            display_order_number INTEGER,
            student_name TEXT NOT NULL,
            roll_number TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            email TEXT,
            document_name TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            file_size_kb REAL DEFAULT 0,
            print_type TEXT NOT NULL,
            color_mode TEXT NOT NULL,
            side_mode TEXT NOT NULL,
            pages INTEGER NOT NULL,
            copies INTEGER NOT NULL,
            calculated_sheets INTEGER NOT NULL,
            binding_type TEXT DEFAULT 'none',
            special_instructions TEXT,
            total_price REAL NOT NULL,
            payment_method TEXT NOT NULL,
            payment_status TEXT NOT NULL,
            order_status TEXT NOT NULL DEFAULT 'Received',
            rejection_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            order_type TEXT DEFAULT 'printing',
            stationery_total REAL DEFAULT 0.0,
            printing_total REAL DEFAULT 0.0,
            stationery_items TEXT DEFAULT '[]',
            print_pages_total INTEGER DEFAULT 0,
            processing_duration_seconds INTEGER DEFAULT 0,
            queue_position INTEGER DEFAULT 0,
            estimated_start_time TIMESTAMP,
            estimated_collection_time TIMESTAMP,
            payment_completed_at TIMESTAMP
        );
        """)

        cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS display_order_number INTEGER;")

        cursor.execute("""
            UPDATE orders 
            SET display_order_number = (
                SELECT COUNT(*) FROM orders o2 WHERE o2.id <= orders.id
            )
            WHERE display_order_number IS NULL
        """)

        NEW_ORDER_COLUMNS = [
            ("order_type", "TEXT DEFAULT 'printing'"),
            ("stationery_total", "REAL DEFAULT 0.0"),
            ("printing_total", "REAL DEFAULT 0.0"),
            ("stationery_items", "TEXT DEFAULT '[]'"),
            ("print_pages_total", "INTEGER DEFAULT 0"),
            ("processing_duration_seconds", "INTEGER DEFAULT 0"),
            ("queue_position", "INTEGER DEFAULT 0"),
            ("estimated_start_time", "TIMESTAMP"),
            ("estimated_collection_time", "TIMESTAMP"),
            ("payment_completed_at", "TIMESTAMP"),
            ("razorpay_order_id", "TEXT"),
            ("razorpay_payment_id", "TEXT"),
            ("razorpay_signature", "TEXT"),
            ("payment_id", "TEXT"),
            ("demo_transaction_id", "TEXT"),
        ]
        for _col, _spec in NEW_ORDER_COLUMNS:
            cursor.execute(f"ALTER TABLE orders ADD COLUMN IF NOT EXISTS {_col} {_spec};")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_stationery_items (
            id SERIAL PRIMARY KEY,
            order_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            item_name TEXT NOT NULL,
            unit_price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            subtotal REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        );
        """)

        try:
            cursor.execute("UPDATE orders SET print_pages_total = pages * copies WHERE print_pages_total IS NULL OR print_pages_total = 0")
        except Exception:
            pass

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_sessions (
            id SERIAL PRIMARY KEY,
            session_id TEXT UNIQUE NOT NULL,
            order_amount REAL NOT NULL,
            session_started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            screenshot_filename TEXT,
            verification_status TEXT NOT NULL DEFAULT 'pending',
            verification_message TEXT,
            transaction_ref TEXT,
            verified_at TIMESTAMP,
            merchant_upi_id TEXT DEFAULT '',
            merchant_name TEXT DEFAULT '',
            merchant_identifiers TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        for _col, _default in [
            ("merchant_upi_id",      "''"),
            ("merchant_name",        "''"),
            ("merchant_identifiers", "'[]'"),
        ]:
            cursor.execute(f"ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS {_col} TEXT DEFAULT {_default};")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS used_transaction_refs (
            id SERIAL PRIMARY KEY,
            transaction_ref TEXT UNIQUE NOT NULL,
            order_amount REAL NOT NULL,
            session_id TEXT NOT NULL,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id SERIAL PRIMARY KEY,
            order_id TEXT NOT NULL,
            item_index INTEGER NOT NULL DEFAULT 0,
            document_name TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            file_size_kb REAL DEFAULT 0,
            pages INTEGER NOT NULL,
            copies INTEGER NOT NULL DEFAULT 1,
            color_mode TEXT NOT NULL DEFAULT 'bw',
            side_mode TEXT NOT NULL DEFAULT 'single',
            calculated_sheets INTEGER NOT NULL,
            printing_cost REAL NOT NULL DEFAULT 0,
            item_total REAL NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS staff_users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'staff'
        );
        """)
    else:
        # SQLite Schema & Migrations
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE NOT NULL,
            token_number TEXT NOT NULL,
            display_order_number INTEGER,
            student_name TEXT NOT NULL,
            roll_number TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            email TEXT,
            document_name TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            file_size_kb REAL DEFAULT 0,
            print_type TEXT NOT NULL,
            color_mode TEXT NOT NULL,
            side_mode TEXT NOT NULL,
            pages INTEGER NOT NULL,
            copies INTEGER NOT NULL,
            calculated_sheets INTEGER NOT NULL,
            binding_type TEXT DEFAULT 'none',
            special_instructions TEXT,
            total_price REAL NOT NULL,
            payment_method TEXT NOT NULL,
            payment_status TEXT NOT NULL,
            order_status TEXT NOT NULL DEFAULT 'Received',
            rejection_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN display_order_number INTEGER")
        except Exception:
            pass

        cursor.execute("""
            UPDATE orders 
            SET display_order_number = (
                SELECT COUNT(*) FROM orders o2 WHERE o2.id <= orders.id
            )
            WHERE display_order_number IS NULL
        """)

        NEW_ORDER_COLUMNS = [
            ("order_type", "TEXT DEFAULT 'printing'"),
            ("stationery_total", "REAL DEFAULT 0.0"),
            ("printing_total", "REAL DEFAULT 0.0"),
            ("stationery_items", "TEXT DEFAULT '[]'"),
            ("print_pages_total", "INTEGER DEFAULT 0"),
            ("processing_duration_seconds", "INTEGER DEFAULT 0"),
            ("queue_position", "INTEGER DEFAULT 0"),
            ("estimated_start_time", "TIMESTAMP"),
            ("estimated_collection_time", "TIMESTAMP"),
            ("payment_completed_at", "TIMESTAMP"),
            ("razorpay_order_id", "TEXT"),
            ("razorpay_payment_id", "TEXT"),
            ("razorpay_signature", "TEXT"),
            ("payment_id", "TEXT"),
            ("demo_transaction_id", "TEXT"),
        ]
        for _col, _spec in NEW_ORDER_COLUMNS:
            try:
                cursor.execute(f"ALTER TABLE orders ADD COLUMN {_col} {_spec}")
            except Exception:
                pass

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_stationery_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            item_name TEXT NOT NULL,
            unit_price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            subtotal REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        );
        """)

        try:
            cursor.execute("UPDATE orders SET print_pages_total = pages * copies WHERE print_pages_total IS NULL OR print_pages_total = 0")
        except Exception:
            pass

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            order_amount REAL NOT NULL,
            session_started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            screenshot_filename TEXT,
            verification_status TEXT NOT NULL DEFAULT 'pending',
            verification_message TEXT,
            transaction_ref TEXT,
            verified_at TIMESTAMP,
            merchant_upi_id TEXT DEFAULT '',
            merchant_name TEXT DEFAULT '',
            merchant_identifiers TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        for _col, _default in [
            ("merchant_upi_id",      "''"),
            ("merchant_name",        "''"),
            ("merchant_identifiers", "'[]'"),
        ]:
            try:
                cursor.execute(
                    f"ALTER TABLE payment_sessions ADD COLUMN {_col} TEXT DEFAULT {_default}"
                )
            except Exception:
                pass

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS used_transaction_refs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_ref TEXT UNIQUE NOT NULL,
            order_amount REAL NOT NULL,
            session_id TEXT NOT NULL,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            item_index INTEGER NOT NULL DEFAULT 0,
            document_name TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            file_size_kb REAL DEFAULT 0,
            pages INTEGER NOT NULL,
            copies INTEGER NOT NULL DEFAULT 1,
            color_mode TEXT NOT NULL DEFAULT 'bw',
            side_mode TEXT NOT NULL DEFAULT 'single',
            calculated_sheets INTEGER NOT NULL,
            printing_cost REAL NOT NULL DEFAULT 0,
            item_total REAL NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS staff_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'staff'
        );
        """)

    # Seed / update staff user
    cursor.execute("SELECT id FROM staff_users WHERE username = ?", (Config.STAFF_USERNAME,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO staff_users (username, password, role) VALUES (?, ?, ?)",
            (Config.STAFF_USERNAME, Config.STAFF_PASSWORD, "admin")
        )
    else:
        cursor.execute(
            "UPDATE staff_users SET password = ? WHERE username = ?",
            (Config.STAFF_PASSWORD, Config.STAFF_USERNAME)
        )

    # Clean up stale rows for old default usernames
    OLD_DEFAULT_USERNAMES = ["staff", "staff@melody", "admin"]
    for _old in OLD_DEFAULT_USERNAMES:
        if _old != Config.STAFF_USERNAME:
            cursor.execute("DELETE FROM staff_users WHERE username = ?", (_old,))

    conn.commit()
    conn.close()


def generate_order_id(for_date: str = None):
    if for_date:
        now_str = str(for_date)[:10].replace("-", "")
    else:
        now_str = get_ist_now().strftime("%Y%m%d")
    random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"ORD-{now_str}-{random_suffix}"


def generate_token_number(conn=None):
    _own = conn is None
    if _own:
        conn = get_db_connection()
    cursor = conn.cursor()
    today_start = get_ist_now().strftime("%Y-%m-%d 00:00:00")
    cursor.execute("SELECT COUNT(*) FROM orders WHERE created_at >= ?", (today_start,))
    count = cursor.fetchone()[0]
    if _own:
        conn.close()
    token_num = 101 + count
    return f"TK-{token_num}"


def calculate_order_price(pages, copies, color_mode, side_mode, print_type_id="regular", binding_id="none"):
    pricing = Config.PRICING
    
    # 1. Base rate per page
    rate_per_page = pricing["color_per_page"] if color_mode.lower() == "color" else pricing["bw_per_page"]
    
    # 2. Calculated paper sheets & printing cost
    is_double = side_mode.lower() == "double"
    is_color = color_mode.lower() == "color"

    if pages <= 0:
        sheets_per_copy = 0
        cost_per_copy = 0.0
    elif is_double:
        sheets_per_copy = (pages + 1) // 2
        if is_color:
            cost_per_copy = (pages // 2) * 8.0 + (pages % 2) * 5.0
        else:
            cost_per_copy = (pages // 2) * 3.0 + (pages % 2) * 2.0
    else:
        sheets_per_copy = pages
        if is_color:
            cost_per_copy = pages * 5.0
        else:
            cost_per_copy = pages * 2.0

    total_sheets = sheets_per_copy * copies
    printing_cost = cost_per_copy * copies
    
    # 4. Optional print type surcharge
    type_extra = 0.0
    for t in pricing.get("types", []):
        if t["id"] == print_type_id:
            type_extra = float(t.get("extra_cost", 0.0)) * copies
            break
            
    # 5. Optional binding cost
    binding_cost = 0.0
    for b in pricing.get("bindings", []):
        if b["id"] == binding_id:
            binding_cost = float(b.get("price", 0.0)) * copies
            break

    total = round(printing_cost + type_extra + binding_cost, 2)
    return {
        "rate_per_page": rate_per_page,
        "sheets_per_copy": sheets_per_copy,
        "total_sheets": total_sheets,
        "printing_cost": round(printing_cost, 2),
        "type_extra": round(type_extra, 2),
        "binding_cost": round(binding_cost, 2),
        "total_price": total
    }


def calculate_printing_duration_seconds(total_pages: int) -> int:
    """
    Printing Processing-Time Table (exact threshold-based):
    1–5 print copies/pages   = 1 minute 30 seconds (90s)
    6–10 print copies/pages  = 3 minutes (180s)
    11–15 print copies/pages = 4 minutes (240s)
    16–20 print copies/pages = 6 minutes (360s)
    21–25 print copies/pages = 7 minutes (420s)
    26–30 print copies/pages = 8 minutes (480s)
    31–35 print copies/pages = 9 minutes (540s)
    36–40 print copies/pages = 9 minutes 40 seconds (580s)
    41–45 print copies/pages = 10 minutes 40 seconds (640s)
    46–50 print copies/pages = 11 minutes 40 seconds (700s)
    >50 pages: 700s + 60s per additional 5 pages.
    """
    if total_pages <= 0:
        return 0
    if 1 <= total_pages <= 5:
        return 90
    elif 6 <= total_pages <= 10:
        return 180
    elif 11 <= total_pages <= 15:
        return 240
    elif 16 <= total_pages <= 20:
        return 360
    elif 21 <= total_pages <= 25:
        return 420
    elif 26 <= total_pages <= 30:
        return 480
    elif 31 <= total_pages <= 35:
        return 540
    elif 36 <= total_pages <= 40:
        return 580
    elif 41 <= total_pages <= 45:
        return 640
    elif 46 <= total_pages <= 50:
        return 700
    else:
        extra_blocks = (total_pages - 50 + 4) // 5
        return 700 + extra_blocks * 60


def calculate_order_queue(total_print_pages: int, conn=None) -> dict:
    """
    Two-Worker Shop Model:
      Worker 1: Printing / Xerox (bottleneck queue)
      Worker 2: Stationery preparation (in parallel)

    Stationery-only orders do NOT enter or add time to the printing queue.
    Printing / Mixed orders queue sequentially behind active pending printing orders.
    When an order is Ready for Collection, Completed, Collected, or Rejected,
    its remaining time is automatically excluded from the queue.
    """
    _own = conn is None
    if _own:
        conn = get_db_connection()
    cursor = conn.cursor()

    now = get_ist_now()

    # Stationery only: Worker 2 prepares in parallel
    if total_print_pages <= 0:
        duration_seconds = 120  # Fixed 2 minutes total for any stationery-only order
        coll_time = now + timedelta(seconds=duration_seconds)
        res = {
            "processing_duration_seconds": duration_seconds,
            "queue_position": 0,
            "pending_orders_ahead": 0,
            "estimated_start_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "estimated_collection_time": coll_time.strftime("%Y-%m-%d %H:%M:%S"),
            "readable_collection_time": coll_time.strftime("%I:%M %p").lstrip("0"),
            "readable_duration": "2 min"
        }
        if _own:
            conn.close()
        return res

    duration_seconds = calculate_printing_duration_seconds(total_print_pages)

    # Fetch active pending printing orders from today.
    # Excludes orders already Completed, Ready for Collection, Cancelled, or Failed payment.
    today_date = now.strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT id, order_id, display_order_number, print_pages_total, pages, copies,
               processing_duration_seconds, estimated_collection_time, created_at, order_status, payment_status
        FROM orders
        WHERE LOWER(order_status) IN ('received', 'order received', 'processing', 'printing in progress')
          AND LOWER(COALESCE(payment_status, 'verified')) NOT IN ('failed', 'rejected')
          AND (print_pages_total > 0 OR (print_pages_total IS NULL AND pages > 0))
          AND DATE(created_at) = ?
        ORDER BY id ASC
    """, (today_date,))
    pending_rows = cursor.fetchall()

    printer_free_at = now
    active_ahead_count = 0

    for p in pending_rows:
        p_coll = to_ist_datetime(p["estimated_collection_time"])
        if not p_coll:
            p_pages = p["print_pages_total"] or (p["pages"] * (p["copies"] or 1))
            p_dur = calculate_printing_duration_seconds(p_pages)
            p_created = to_ist_datetime(p["created_at"]) or now
            p_coll = p_created + timedelta(seconds=p_dur)

        # Only orders whose collection time is in the future have remaining processing time
        if p_coll and p_coll > now:
            active_ahead_count += 1
            if p_coll > printer_free_at:
                printer_free_at = p_coll

    estimated_start = printer_free_at
    estimated_collection = estimated_start + timedelta(seconds=duration_seconds)
    queue_pos = active_ahead_count + 1

    m = duration_seconds // 60
    s = duration_seconds % 60
    if m > 0 and s > 0:
        readable_dur = f"{m}m {s}s"
    elif m > 0:
        readable_dur = f"{m} min"
    else:
        readable_dur = f"{s} sec"

    res = {
        "processing_duration_seconds": duration_seconds,
        "queue_position": queue_pos,
        "pending_orders_ahead": active_ahead_count,
        "estimated_start_time": estimated_start.strftime("%Y-%m-%d %H:%M:%S"),
        "estimated_collection_time": estimated_collection.strftime("%Y-%m-%d %H:%M:%S"),
        "readable_collection_time": estimated_collection.strftime("%I:%M %p").lstrip("0"),
        "readable_duration": readable_dur
    }

    if _own:
        conn.close()
    return res


def _serialize_order(order_dict: dict, conn=None) -> dict:
    """Helper to enrich raw DB order dict with parsed JSON, queue status, and formatted times."""
    if not order_dict:
        return order_dict
    import json
    d = dict(order_dict)

    # Standardize datetime/date fields to ISO/string format for consistent API responses
    for dt_col in [
        "created_at", "updated_at", "estimated_start_time",
        "estimated_collection_time", "payment_completed_at"
    ]:
        if dt_col in d and d[dt_col] is not None:
            if isinstance(d[dt_col], (datetime, date)):
                d[dt_col] = d[dt_col].strftime("%Y-%m-%d %H:%M:%S")
            else:
                d[dt_col] = str(d[dt_col])

    if d.get("display_order_number") is None:
        d["display_order_number"] = d.get("id", 1)

    if not d.get("payment_id") and d.get("razorpay_payment_id"):
        d["payment_id"] = d.get("razorpay_payment_id")
    elif not d.get("razorpay_payment_id") and d.get("payment_id"):
        d["razorpay_payment_id"] = d.get("payment_id")

    raw_s = d.get("stationery_items")
    if isinstance(raw_s, str):
        try:
            d["stationery_items"] = json.loads(raw_s)
        except Exception:
            d["stationery_items"] = []
    elif raw_s is None:
        d["stationery_items"] = []

    if not d["stationery_items"] and d.get("order_id"):
        try:
            _own = conn is None
            c = get_db_connection() if _own else conn
            cur = c.cursor()
            cur.execute("""
                SELECT item_id as id, item_name as name, unit_price as price, quantity, subtotal 
                FROM order_stationery_items WHERE order_id = ? ORDER BY id ASC
            """, (d["order_id"],))
            items = [dict(r) for r in cur.fetchall()]
            if items:
                d["stationery_items"] = items
            if _own:
                c.close()
        except Exception:
            pass

    ect = d.get("estimated_collection_time")
    if ect:
        try:
            dt = to_ist_datetime(ect)
            d["readable_collection_time"] = dt.strftime("%I:%M %p").lstrip("0") if dt else str(ect)
        except Exception:
            d["readable_collection_time"] = str(ect)
    else:
        d["readable_collection_time"] = None

    # Calculate live queue position if order is currently pending
    st = (d.get("order_status") or "").lower()
    if st in ("received", "order received", "processing", "printing in progress") and (d.get("print_pages_total", 0) > 0 or d.get("pages", 0) > 0):
        try:
            _own = conn is None
            c = get_db_connection() if _own else conn
            cur = c.cursor()
            order_created = str(d.get("created_at") or "")[:10]
            cur.execute("""
                SELECT COUNT(*) FROM orders
                WHERE id < ?
                  AND DATE(created_at) = ?
                  AND LOWER(order_status) IN ('received', 'order received', 'processing', 'printing in progress')
                  AND LOWER(COALESCE(payment_status, 'verified')) NOT IN ('failed', 'rejected')
                  AND LOWER(COALESCE(order_status, '')) NOT IN ('completed', 'collected', 'cancelled', 'canceled', 'ready for collection', 'stage ready', 'rejected')
                  AND (print_pages_total > 0 OR (print_pages_total IS NULL AND pages > 0))
            """, (d["id"], order_created))
            ahead = cur.fetchone()[0]
            d["pending_orders_ahead"] = ahead
            d["current_queue_position"] = ahead + 1
            if _own:
                c.close()
        except Exception:
            d["pending_orders_ahead"] = 0
            d["current_queue_position"] = d.get("queue_position", 1)
    else:
        d["pending_orders_ahead"] = 0
        d["current_queue_position"] = 0

    return d


def create_order(order_data):
    import json
    with _order_creation_lock:
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
        except Exception:
            pass

        try:
            cursor = conn.cursor()

            created_at_val = order_data.get("created_at") or get_ist_now().strftime("%Y-%m-%d %H:%M:%S")
            target_date = str(created_at_val)[:10]

            order_id     = generate_order_id(for_date=target_date)
            token_number = generate_token_number(conn=conn)
            display_num  = next_display_order_number(conn, for_date=target_date)

            pages = int(order_data.get("pages", 1))
            copies = int(order_data.get("copies", 1))
            print_pages_total = pages * copies
            stationery_total = float(order_data.get("stationery_total", 0.0))
            printing_total = float(order_data.get("printing_total", order_data.get("total_price", 0.0)))
            total_price = float(order_data.get("total_price", printing_total + stationery_total))
            order_type = order_data.get("order_type", "printing")
            stationery_items = order_data.get("stationery_items", [])
            stationery_items_json = json.dumps(stationery_items) if isinstance(stationery_items, list) else str(stationery_items)

            queue_info = calculate_order_queue(print_pages_total, conn=conn)
            initial_status = order_data.get("order_status", "Received")

            cursor.execute("""
                INSERT INTO orders (
                    order_id, token_number, display_order_number,
                    student_name, roll_number, phone_number, email,
                    document_name, stored_filename, file_size_kb, print_type, color_mode,
                    side_mode, pages, copies, calculated_sheets, binding_type,
                    special_instructions, total_price, payment_method, payment_status,
                    order_status, order_type, stationery_total, printing_total,
                    stationery_items, print_pages_total, processing_duration_seconds,
                    queue_position, estimated_start_time, estimated_collection_time,
                    payment_completed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_id,
                token_number,
                display_num,
                order_data["student_name"].strip(),
                order_data["roll_number"].strip(),
                order_data["phone_number"].strip(),
                order_data.get("email", "").strip(),
                order_data.get("document_name", "Document"),
                order_data.get("stored_filename", ""),
                order_data.get("file_size_kb", 0),
                order_data.get("print_type", "regular"),
                order_data.get("color_mode", "bw"),
                order_data.get("side_mode", "single"),
                pages,
                copies,
                int(order_data.get("calculated_sheets", 1)),
                order_data.get("binding_type", "none"),
                order_data.get("special_instructions", ""),
                total_price,
                order_data.get("payment_method", "Simulated UPI"),
                order_data.get("payment_status", "Paid"),
                initial_status,
                order_type,
                stationery_total,
                printing_total,
                stationery_items_json,
                print_pages_total,
                queue_info["processing_duration_seconds"],
                queue_info["queue_position"],
                queue_info["estimated_start_time"] or None,
                queue_info["estimated_collection_time"] or None,
                created_at_val,
                created_at_val,
                created_at_val,
            ))
            conn.commit()
            
            cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
            row = cursor.fetchone()
            order_dict = _serialize_order(dict(row), conn=conn) if row else None
            return order_dict
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def get_order_by_id(order_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    res = _serialize_order(dict(row), conn=conn) if row else None
    conn.close()
    return res


def find_order(search_query):
    query = search_query.strip().upper()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM orders 
        WHERE UPPER(order_id) = ? 
           OR UPPER(token_number) = ? 
           OR UPPER(roll_number) = ? 
           OR phone_number = ?
        ORDER BY id DESC LIMIT 5
    """, (query, query, query, search_query.strip()))
    rows = cursor.fetchall()
    res = [_serialize_order(dict(r), conn=conn) for r in rows]
    conn.close()
    return res


def list_orders(status=None, search=None, sort_by="desc"):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    sql = "SELECT * FROM orders WHERE 1=1"
    params = []
    
    if status and status.strip() and status.lower() != "all":
        st_clean = status.strip().lower()
        if st_clean in ("received", "order received"):
            sql += " AND LOWER(order_status) IN ('received', 'order received', 'payment successful')"
        elif st_clean in ("processing", "printing in progress", "preparing stationery"):
            sql += " AND LOWER(order_status) IN ('processing', 'printing in progress', 'preparing stationery')"
        elif st_clean in ("ready", "ready for collection", "stage ready"):
            sql += " AND LOWER(order_status) IN ('ready', 'ready for collection', 'stage ready')"
        elif st_clean in ("completed", "collected"):
            sql += " AND LOWER(order_status) IN ('completed', 'collected')"
        else:
            sql += " AND LOWER(order_status) = ?"
            params.append(st_clean)
        
    if search and search.strip():
        term = f"%{search.strip()}%"
        sql += """ AND (
            LOWER(order_id) LIKE LOWER(?) OR 
            LOWER(token_number) LIKE LOWER(?) OR 
            LOWER(student_name) LIKE LOWER(?) OR 
            LOWER(roll_number) LIKE LOWER(?) OR 
            LOWER(phone_number) LIKE LOWER(?)
        )"""
        params.extend([term, term, term, term, term])
        
    if sort_by == "asc":
        sql += " ORDER BY id ASC"
    else:
        sql += " ORDER BY id DESC"
        
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    res = [_serialize_order(dict(r), conn=conn) for r in rows]
    conn.close()
    return res


def update_order_status(order_id, new_status, rejection_reason=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orders 
        SET order_status = ?, rejection_reason = ?, updated_at = CURRENT_TIMESTAMP
        WHERE order_id = ?
    """, (new_status, rejection_reason, order_id))
    conn.commit()
    
    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    res = _serialize_order(dict(row), conn=conn) if row else None
    conn.close()
    return res


def update_order_razorpay_order_id(order_id: str, razorpay_order_id: str) -> bool:
    """Associate a generated Razorpay order ID with the CampusPrint order."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orders
        SET razorpay_order_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE order_id = ?
    """, (razorpay_order_id, order_id))
    conn.commit()
    conn.close()
    return True


def mark_order_paid(order_id: str, razorpay_payment_id: str = None,
                    razorpay_signature: str = None, razorpay_order_id: str = None) -> dict | None:
    """
    Mark a CampusPrint order as PAID upon verified Razorpay payment.
    Updates payment_status, payment_method, payment_completed_at, and Razorpay transaction IDs.
    Transitions order_status from 'Pending Payment' to 'Order Received' if applicable.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orders
        SET payment_status = 'Paid',
            order_status = CASE 
                WHEN LOWER(order_status) IN ('pending payment', 'received') THEN 'Order Received'
                ELSE order_status 
            END,
            payment_completed_at = CURRENT_TIMESTAMP,
            payment_method = 'Razorpay',
            payment_id = COALESCE(?, payment_id, ?),
            razorpay_payment_id = COALESCE(?, razorpay_payment_id),
            razorpay_signature = COALESCE(?, razorpay_signature),
            razorpay_order_id = COALESCE(?, razorpay_order_id),
            updated_at = CURRENT_TIMESTAMP
        WHERE order_id = ?
    """, (razorpay_payment_id, razorpay_payment_id, razorpay_payment_id, razorpay_signature, razorpay_order_id, order_id))
    conn.commit()

    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    res = _serialize_order(dict(row), conn=conn) if row else None
    conn.close()
    return res


def mark_order_demo_paid(order_id: str, demo_payment_id: str,
                         demo_payment_method: str = "Demo Payment") -> dict | None:
    """
    Mark a CampusPrint order as PAID upon verified demo payment simulation.
    Updates payment_status, payment_method, payment_completed_at, and generated demo payment IDs.
    Transitions order_status from 'Pending' / 'Received' to 'Order Received'.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orders
        SET payment_status = 'Paid',
            order_status = CASE 
                WHEN LOWER(order_status) IN ('pending payment', 'received', 'pending') THEN 'Order Received'
                ELSE order_status 
            END,
            payment_completed_at = CURRENT_TIMESTAMP,
            payment_method = ?,
            payment_id = ?,
            razorpay_payment_id = ?,
            demo_transaction_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE order_id = ?
    """, (demo_payment_method, demo_payment_id, demo_payment_id, demo_payment_id, order_id))
    conn.commit()

    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    res = _serialize_order(dict(row), conn=conn) if row else None
    conn.close()
    return res


def get_order_by_razorpay_order_id(razorpay_order_id: str) -> dict | None:
    """Retrieve an order by its Razorpay order ID (used for webhooks and verification)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE razorpay_order_id = ?", (razorpay_order_id,))
    row = cursor.fetchone()
    res = _serialize_order(dict(row), conn=conn) if row else None
    conn.close()
    return res


def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM orders")
    total_orders = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM orders WHERE LOWER(order_status) IN ('received', 'order received', 'payment successful')")
    received = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM orders WHERE LOWER(order_status) IN ('processing', 'printing in progress', 'preparing stationery')")
    processing = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM orders WHERE LOWER(order_status) IN ('ready for collection', 'stage ready', 'ready')")
    ready = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM orders WHERE LOWER(order_status) IN ('completed', 'collected')")
    completed = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM orders WHERE LOWER(order_status) = 'rejected'")
    rejected = cursor.fetchone()[0]
    
    cursor.execute("SELECT COALESCE(SUM(total_price), 0) FROM orders WHERE LOWER(order_status) != 'rejected'")
    total_revenue = round(float(cursor.fetchone()[0]), 2)
    
    today_start = get_ist_now().strftime("%Y-%m-%d 00:00:00")
    cursor.execute("SELECT COUNT(*) FROM orders WHERE created_at >= ?", (today_start,))
    today_orders = cursor.fetchone()[0]
    
    conn.close()
    return {
        "total_orders": total_orders,
        "received": received,
        "processing": processing,
        "ready": ready,
        "completed": completed,
        "rejected": rejected,
        "total_revenue": total_revenue,
        "today_orders": today_orders
    }


def create_multi_order(order_data: dict, items: list[dict] = None, stationery_items: list[dict] = None) -> dict | None:
    """
    Create one parent order row + N order_item rows for files + N order_stationery_items rows.
    Supports:
      - Printing only (items present, stationery_items empty)
      - Stationery only (items empty/None, stationery_items present)
      - Mixed (both items and stationery_items present)
    """
    import json
    with _order_creation_lock:
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
        except Exception:
            pass

        try:
            cursor = conn.cursor()

            created_at_val = order_data.get("created_at") or get_ist_now().strftime("%Y-%m-%d %H:%M:%S")
            target_date = str(created_at_val)[:10]

            order_id     = generate_order_id(for_date=target_date)
            token_number = generate_token_number(conn=conn)
            display_num  = next_display_order_number(conn, for_date=target_date)

            has_files = items is not None and len(items) > 0
            has_stationery = stationery_items is not None and len(stationery_items) > 0

            if has_files and has_stationery:
                order_type = "mixed"
            elif has_stationery:
                order_type = "stationery"
            else:
                order_type = "printing"

            if has_files:
                total_pages  = sum(it["pages"] * it["copies"] for it in items)
                total_sheets = sum(it["calculated_sheets"] for it in items)
                total_copies = sum(it["copies"] for it in items)
                primary      = items[0]
                all_names    = ", ".join(it["document_name"] for it in items)
                file_size_kb = sum(it.get("file_size_kb", 0) for it in items)
                stored_file  = primary["stored_filename"]
                color_mode   = primary["color_mode"]
                side_mode    = primary["side_mode"]
            else:
                total_pages  = 0
                total_sheets = 0
                total_copies = 0
                item_names   = [f"{it.get('quantity', 1)}x {it.get('name', 'Item')}" for it in (stationery_items or [])]
                all_names    = f"Stationery: {', '.join(item_names)}" if item_names else "Stationery Order"
                file_size_kb = 0
                stored_file  = ""
                color_mode   = "none"
                side_mode    = "none"

            printing_total   = float(order_data.get("printing_total", 0.0))
            stationery_total = float(order_data.get("stationery_total", 0.0))
            grand_total      = float(order_data.get("total_price", printing_total + stationery_total))
            stationery_json  = json.dumps(stationery_items or [])

            queue_info = calculate_order_queue(total_pages, conn=conn)
            initial_status = order_data.get("order_status", "Order Received")

            cursor.execute("""
                INSERT INTO orders (
                    order_id, token_number, display_order_number,
                    student_name, roll_number, phone_number, email,
                    document_name, stored_filename, file_size_kb, print_type, color_mode,
                    side_mode, pages, copies, calculated_sheets, binding_type,
                    special_instructions, total_price, payment_method, payment_status,
                    order_status, order_type, stationery_total, printing_total,
                    stationery_items, print_pages_total, processing_duration_seconds,
                    queue_position, estimated_start_time, estimated_collection_time,
                    payment_completed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_id,
                token_number,
                display_num,
                order_data["student_name"].strip(),
                order_data["roll_number"].strip(),
                order_data["phone_number"].strip(),
                order_data.get("email", "").strip(),
                all_names,
                stored_file,
                file_size_kb,
                order_data.get("print_type", "regular"),
                color_mode,
                side_mode,
                total_pages,
                total_copies,
                total_sheets,
                order_data.get("binding_type", "none"),
                order_data.get("special_instructions", ""),
                grand_total,
                order_data.get("payment_method", "UPI"),
                order_data.get("payment_status", "Paid"),
                initial_status,
                order_type,
                stationery_total,
                printing_total,
                stationery_json,
                total_pages,
                queue_info["processing_duration_seconds"],
                queue_info["queue_position"],
                queue_info["estimated_start_time"] or None,
                queue_info["estimated_collection_time"] or None,
                created_at_val,
                created_at_val,
                created_at_val,
            ))

            # Insert file items if present
            if has_files:
                for idx, item in enumerate(items):
                    cursor.execute("""
                        INSERT INTO order_items (
                            order_id, item_index, document_name, stored_filename, file_size_kb,
                            pages, copies, color_mode, side_mode, calculated_sheets,
                            printing_cost, item_total, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        order_id, idx,
                        item["document_name"], item["stored_filename"],
                        item.get("file_size_kb", 0),
                        int(item["pages"]), int(item["copies"]),
                        item["color_mode"], item["side_mode"],
                        int(item["calculated_sheets"]),
                        float(item["printing_cost"]), float(item["item_total"]),
                        created_at_val,
                    ))

            # Insert stationery items if present
            if has_stationery:
                for s_item in stationery_items:
                    cursor.execute("""
                        INSERT INTO order_stationery_items (
                            order_id, item_id, item_name, unit_price, quantity, subtotal, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        order_id,
                        s_item.get("id", ""),
                        s_item.get("name", ""),
                        float(s_item.get("price", 0)),
                        int(s_item.get("quantity", 0)),
                        float(s_item.get("subtotal", 0)),
                        created_at_val,
                    ))

            conn.commit()
            cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
            row = cursor.fetchone()
            order_dict = _serialize_order(dict(row), conn=conn) if row else None
            return order_dict
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def get_order_items(order_id: str) -> list[dict]:
    """Return all order_items rows for a given order_id, ordered by item_index."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM order_items WHERE order_id = ? ORDER BY item_index ASC",
        (order_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    items = []
    for r in rows:
        d = dict(r)
        if "created_at" in d and isinstance(d["created_at"], (datetime, date)):
            d["created_at"] = d["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        items.append(d)
    return items


def get_order_stationery_items(order_id: str) -> list[dict]:
    """Return all order_stationery_items rows for a given order_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, order_id, item_id, item_name, unit_price, quantity, subtotal, created_at FROM order_stationery_items WHERE order_id = ? ORDER BY id ASC",
        (order_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    items = []
    for r in rows:
        d = dict(r)
        if "created_at" in d and isinstance(d["created_at"], (datetime, date)):
            d["created_at"] = d["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        items.append(d)
    return items


def next_display_order_number(conn=None, for_date: str = None) -> int:
    """Return the next sequential display order number for TODAY (1-based, resets daily)."""
    _own = conn is None
    if _own:
        conn = get_db_connection()
    if for_date is None:
        for_date = get_ist_now().strftime("%Y-%m-%d")
    else:
        for_date = str(for_date)[:10]

    cursor = conn.cursor()
    cursor.execute("""
        SELECT COALESCE(MAX(display_order_number), 0)
        FROM orders
        WHERE DATE(created_at) = ?
    """, (for_date,))
    current_max = cursor.fetchone()[0]
    if _own:
        conn.close()
    return current_max + 1


def get_session_merchant(session: dict) -> tuple[str, str, list]:
    """Return (upi_id, name, identifiers) from a session dict."""
    import json as _json
    upi_id = (session.get("merchant_upi_id") or "").strip()
    name   = (session.get("merchant_name")   or "").strip()
    raw    = session.get("merchant_identifiers") or "[]"
    try:
        identifiers = _json.loads(raw)
    except (ValueError, TypeError):
        identifiers = []

    if not identifiers:
        from config import Config as _C
        upi_id      = upi_id or getattr(_C, "MERCHANT_UPI_ID", "")
        name        = name   or getattr(_C, "MERCHANT_NAME",   "")
        identifiers = getattr(_C, "MERCHANT_IDENTIFIERS", [name.lower()])

    return upi_id, name, identifiers


def create_payment_session(order_amount: float,
                           merchant_upi_id: str = "",
                           merchant_name: str = "",
                           merchant_identifiers: list | None = None) -> dict:
    """Create a 10-minute payment verification session."""
    import uuid as _uuid
    import json as _json
    session_id = _uuid.uuid4().hex
    identifiers_json = _json.dumps(merchant_identifiers or [])
    expires_at = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO payment_sessions (
            session_id, order_amount, session_started_at, expires_at,
            merchant_upi_id, merchant_name, merchant_identifiers
        )
        VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
    """, (session_id, order_amount, expires_at, merchant_upi_id, merchant_name, identifiers_json))
    conn.commit()
    cursor.execute("SELECT * FROM payment_sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    res = dict(row) if row else None
    if res:
        for dt_col in ["session_started_at", "expires_at", "verified_at", "created_at"]:
            if dt_col in res and res[dt_col] is not None:
                if isinstance(res[dt_col], (datetime, date)):
                    res[dt_col] = res[dt_col].strftime("%Y-%m-%d %H:%M:%S")
                else:
                    res[dt_col] = str(res[dt_col])
    conn.close()
    return res


def get_payment_session(session_id: str) -> dict | None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payment_sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    res = dict(row) if row else None
    if res:
        for dt_col in ["session_started_at", "expires_at", "verified_at", "created_at"]:
            if dt_col in res and res[dt_col] is not None:
                if isinstance(res[dt_col], (datetime, date)):
                    res[dt_col] = res[dt_col].strftime("%Y-%m-%d %H:%M:%S")
                else:
                    res[dt_col] = str(res[dt_col])
    conn.close()
    return res


def update_payment_session_verification(session_id: str, status: str, message: str,
                                        transaction_ref: str | None = None,
                                        screenshot_filename: str | None = None) -> dict | None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE payment_sessions
        SET verification_status = ?,
            verification_message = ?,
            transaction_ref = COALESCE(?, transaction_ref),
            screenshot_filename = COALESCE(?, screenshot_filename),
            verified_at = CASE WHEN ? = 'verified' THEN CURRENT_TIMESTAMP ELSE verified_at END
        WHERE session_id = ?
    """, (status, message, transaction_ref, screenshot_filename, status, session_id))
    conn.commit()
    cursor.execute("SELECT * FROM payment_sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    res = dict(row) if row else None
    if res:
        for dt_col in ["session_started_at", "expires_at", "verified_at", "created_at"]:
            if dt_col in res and res[dt_col] is not None:
                if isinstance(res[dt_col], (datetime, date)):
                    res[dt_col] = res[dt_col].strftime("%Y-%m-%d %H:%M:%S")
                else:
                    res[dt_col] = str(res[dt_col])
    conn.close()
    return res


def is_transaction_ref_used(transaction_ref: str) -> bool:
    """Return True if this UPI reference was already used successfully."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM used_transaction_refs WHERE transaction_ref = ?",
        (transaction_ref,)
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def record_used_transaction_ref(transaction_ref: str, order_amount: float, session_id: str):
    """Mark a transaction reference as consumed so it cannot be reused."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO used_transaction_refs (transaction_ref, order_amount, session_id) VALUES (?, ?, ?)",
            (transaction_ref, order_amount, session_id)
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()
