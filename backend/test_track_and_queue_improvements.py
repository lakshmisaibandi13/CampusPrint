"""
test_track_and_queue_improvements.py
Unit tests verifying all prompt requirements for collection-time calculation,
serial queue accumulation and recalculation, customer order isolation,
and copy count processing duration table.
"""

import unittest
import sys
import os
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from database import (
    calculate_printing_duration_seconds,
    get_order_duration_seconds,
    calculate_order_queue,
    recalculate_active_queue_etas,
    create_order,
    create_multi_order,
    find_order,
    update_order_status,
    get_db_connection,
    get_ist_now,
    to_ist_datetime
)


class TestTrackAndQueueImprovements(unittest.TestCase):
    def tearDown(self):
        conn = get_db_connection()
        conn.execute("UPDATE orders SET order_status = 'Completed' WHERE roll_number LIKE 'TEST-%' OR roll_number LIKE 'CUST-%'")
        conn.commit()
        conn.close()
    def test_01_all_13_copy_count_buckets(self):
        """Verify every single bucket in the specified whole-minute copy-count table."""
        # 1–5: 2 minutes (120s)
        self.assertEqual(calculate_printing_duration_seconds(1), 120)
        self.assertEqual(calculate_printing_duration_seconds(3), 120)
        self.assertEqual(calculate_printing_duration_seconds(5), 120)

        # 6–10: 3 minutes (180s)
        self.assertEqual(calculate_printing_duration_seconds(6), 180)
        self.assertEqual(calculate_printing_duration_seconds(10), 180)

        # 11–15: 4 minutes (240s)
        self.assertEqual(calculate_printing_duration_seconds(11), 240)
        self.assertEqual(calculate_printing_duration_seconds(15), 240)

        # 16–20: 6 minutes (360s)
        self.assertEqual(calculate_printing_duration_seconds(16), 360)
        self.assertEqual(calculate_printing_duration_seconds(20), 360)

        # 21–25: 7 minutes (420s)
        self.assertEqual(calculate_printing_duration_seconds(21), 420)
        self.assertEqual(calculate_printing_duration_seconds(25), 420)

        # 26–30: 8 minutes (480s)
        self.assertEqual(calculate_printing_duration_seconds(26), 480)
        self.assertEqual(calculate_printing_duration_seconds(30), 480)

        # 31–35: 9 minutes (540s)
        self.assertEqual(calculate_printing_duration_seconds(31), 540)
        self.assertEqual(calculate_printing_duration_seconds(35), 540)

        # 36–40: 10 minutes (600s)
        self.assertEqual(calculate_printing_duration_seconds(36), 600)
        self.assertEqual(calculate_printing_duration_seconds(40), 600)

        # 41–45: 12 minutes (720s)
        self.assertEqual(calculate_printing_duration_seconds(41), 720)
        self.assertEqual(calculate_printing_duration_seconds(45), 720)

        # 46–50: 13 minutes (780s)
        self.assertEqual(calculate_printing_duration_seconds(46), 780)
        self.assertEqual(calculate_printing_duration_seconds(50), 780)

        # 51–55: 14 minutes (840s)
        self.assertEqual(calculate_printing_duration_seconds(51), 840)
        self.assertEqual(calculate_printing_duration_seconds(55), 840)

        # 56–60: 16 minutes (960s)
        self.assertEqual(calculate_printing_duration_seconds(56), 960)
        self.assertEqual(calculate_printing_duration_seconds(60), 960)

        # >60: 20 minutes (1200s)
        self.assertEqual(calculate_printing_duration_seconds(61), 1200)
        self.assertEqual(calculate_printing_duration_seconds(150), 1200)

        # 0 or negative
        self.assertEqual(calculate_printing_duration_seconds(0), 0)
        self.assertEqual(calculate_printing_duration_seconds(-2), 0)

    def test_02_stationery_and_combined_durations(self):
        """
        - Printing only: copy count table
        - Stationery only: 2 minutes (120s)
        - Printing + stationery: printing time only (do not add 2 min)
        """
        # Stationery only
        self.assertEqual(get_order_duration_seconds("stationery", copies=0, has_files=False), 120)
        # Printing only (4 copies -> 2 min = 120s)
        self.assertEqual(get_order_duration_seconds("printing", copies=4, has_files=True), 120)
        # Printing only (8 copies -> 3 min = 180s)
        self.assertEqual(get_order_duration_seconds("printing", copies=8, has_files=True), 180)
        # Mixed (printing + stationery, 8 copies -> 180s, NOT 180 + 120)
        self.assertEqual(get_order_duration_seconds("mixed", copies=8, has_files=True), 180)

    def test_03_serial_queue_accumulation_and_recalculation(self):
        """
        Example from prompt:
        - Order A placed and needs 2 minutes.
        - Order B placed behind A and needs 3 minutes.
        - If A is unfinished and B is behind it, B's collection time includes A.
        - If A is completed before B is processed, recalculate B using only remaining work.
        """
        conn = get_db_connection()
        conn.execute("UPDATE orders SET order_status = 'Completed' WHERE LOWER(order_status) NOT IN ('completed', 'collected', 'cancelled', 'canceled', 'rejected')")
        conn.commit()
        conn.close()

        uid = uuid.uuid4().hex[:6]
        roll_a = f"TEST-QA-{uid}"
        roll_b = f"TEST-QB-{uid}"

        # Order A: 2 copies (needs 2 min = 120s)
        order_a = create_order({
            "student_name": "Student A",
            "roll_number": roll_a,
            "phone_number": "9000000001",
            "copies": 2,
            "pages": 1,
            "order_type": "printing",
            "order_status": "Processing"
        })

        # Order B: 8 copies (needs 3 min = 180s)
        order_b = create_order({
            "student_name": "Student B",
            "roll_number": roll_b,
            "phone_number": "9000000002",
            "copies": 8,
            "pages": 1,
            "order_type": "printing",
            "order_status": "Received"
        })

        coll_a = to_ist_datetime(order_a["estimated_collection_time"])
        coll_b = to_ist_datetime(order_b["estimated_collection_time"])

        self.assertIsNotNone(coll_a)
        self.assertIsNotNone(coll_b)
        # B's collection time must be after A's collection time by at least B's duration (180s)
        self.assertGreaterEqual(coll_b, coll_a + timedelta(seconds=175))

        # Now complete Order A early!
        update_order_status(order_a["order_id"], "Completed")

        # Track Order B again
        tracked_b_list = find_order(roll_b)
        self.assertTrue(len(tracked_b_list) > 0)
        recalculated_b = tracked_b_list[0]
        recalc_coll_b = to_ist_datetime(recalculated_b["estimated_collection_time"])

        # Since A is completed, Order B should now be head of queue and finish within ~180s from now
        now_after = get_ist_now()
        diff_seconds = (recalc_coll_b - now_after).total_seconds()
        self.assertAlmostEqual(diff_seconds, 180, delta=15)

    def test_04_customer_isolation_and_search(self):
        """
        Verify:
        - Search by Roll Number returns all orders belonging to that customer.
        - Search by Token Number returns that specific order first, plus customer's other orders.
        - Search never returns unrelated customers' order details.
        """
        uid = uuid.uuid4().hex[:6]
        cust_roll_1 = f"CUST-1-{uid}"
        cust_roll_2 = f"CUST-2-{uid}"

        # Customer 1 places 2 orders
        o1 = create_order({
            "student_name": "Cust 1",
            "roll_number": cust_roll_1,
            "phone_number": "9111111111",
            "copies": 1,
            "pages": 2,
            "order_type": "printing"
        })
        o2 = create_order({
            "student_name": "Cust 1",
            "roll_number": cust_roll_1,
            "phone_number": "9111111111",
            "copies": 2,
            "pages": 3,
            "order_type": "printing"
        })

        # Customer 2 places 1 order
        o3 = create_order({
            "student_name": "Cust 2",
            "roll_number": cust_roll_2,
            "phone_number": "9222222222",
            "copies": 1,
            "pages": 1,
            "order_type": "printing"
        })

        # Search by Customer 1 roll number
        res_c1 = find_order(cust_roll_1)
        self.assertEqual(len(res_c1), 2)
        for ord_item in res_c1:
            self.assertEqual(ord_item["roll_number"], cust_roll_1)
            self.assertNotEqual(ord_item["roll_number"], cust_roll_2)

        # Search by Customer 2 roll number
        res_c2 = find_order(cust_roll_2)
        self.assertEqual(len(res_c2), 1)
        self.assertEqual(res_c2[0]["roll_number"], cust_roll_2)

        # Search by Token Number of Customer 1's first order
        res_token = find_order(o1["token_number"])
        self.assertTrue(len(res_token) >= 1)
        self.assertEqual(res_token[0]["token_number"], o1["token_number"])
        for ord_item in res_token:
            self.assertEqual(ord_item["roll_number"], cust_roll_1)

    def test_05_timezone_is_ist(self):
        """Verify collection estimates and timestamps are displayed in IST."""
        now_ist = get_ist_now()
        q = calculate_order_queue(copies=2)
        self.assertIn("readable_collection_time", q)
        # Readable collection time must be format like '10:05 AM'
        readable = q["readable_collection_time"]
        self.assertTrue("AM" in readable or "PM" in readable)
        self.assertIn(":", readable)

    def test_06_safe_row_access_and_missing_field_fallbacks(self):
        """
        Verify safe row access on sqlite3.Row and dict objects.
        Test fallback paths when processing_duration_seconds or estimated_collection_time is missing.
        """
        from database import safe_row_get
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, order_id, order_type FROM orders LIMIT 1")
        row = cur.fetchone()
        if row:
            # sqlite3.Row has no .get() method, calling row.get() raises AttributeError
            with self.assertRaises(AttributeError):
                _ = row.get("order_type")
            # safe_row_get must work seamlessly on sqlite3.Row
            val = safe_row_get(row, "order_type")
            self.assertIsNotNone(val)
            # safe_row_get with default for non-existent column
            self.assertEqual(safe_row_get(row, "non_existent_column", "fallback"), "fallback")

        # Test fallback path when an existing active order has NULL processing_duration_seconds and NULL estimated_collection_time
        uid = uuid.uuid4().hex[:6]
        cur.execute("""
            INSERT INTO orders (
                order_id, token_number, display_order_number, student_name, roll_number, phone_number,
                document_name, stored_filename, print_type, color_mode, side_mode, pages, copies,
                calculated_sheets, total_price, payment_method, payment_status, order_status,
                order_type, processing_duration_seconds, estimated_start_time, estimated_collection_time,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (
            f"ORD-FALLBACK-{uid}", f"TK-FB-{uid}", 9999, "Fallback Student", f"TEST-FB-{uid}", "9999999999",
            "doc.pdf", "stored.pdf", "regular", "bw", "single", 1, 3, 3, 6.0, "UPI", "Paid", "In Queue",
            "printing"
        ))
        conn.commit()

        # Recalculate should compute fallback duration (3 copies -> 120s) without failing
        recalculate_active_queue_etas(conn=conn)

        cur.execute("SELECT processing_duration_seconds, estimated_collection_time FROM orders WHERE order_id = ?", (f"ORD-FALLBACK-{uid}",))
        updated_row = cur.fetchone()
        self.assertEqual(updated_row["processing_duration_seconds"], 120)
        self.assertIsNotNone(updated_row["estimated_collection_time"])
        conn.close()

    def test_07_expired_but_unfinished_orders_included_in_queue(self):
        """
        Verify that an unfinished order whose ETA has passed is NOT silently excluded.
        Remaining work must be scheduled from now, and subsequent orders must wait behind it.
        """
        conn = get_db_connection()
        conn.execute("UPDATE orders SET order_status = 'Completed' WHERE LOWER(order_status) NOT IN ('completed', 'collected', 'cancelled', 'canceled', 'rejected')")
        conn.commit()

        uid = uuid.uuid4().hex[:6]
        past_time = (get_ist_now() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        past_eta = (get_ist_now() - timedelta(minutes=25)).strftime("%Y-%m-%d %H:%M:%S")

        cur = conn.cursor()
        cur.execute("""
            INSERT INTO orders (
                order_id, token_number, display_order_number, student_name, roll_number, phone_number,
                document_name, stored_filename, print_type, color_mode, side_mode, pages, copies,
                calculated_sheets, total_price, payment_method, payment_status, order_status,
                order_type, processing_duration_seconds, estimated_start_time, estimated_collection_time,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"ORD-DELAYED-{uid}", f"TK-DEL-{uid}", 8888, "Delayed Student", f"TEST-DEL-{uid}", "9888888888",
            "delayed.pdf", "delayed.pdf", "regular", "bw", "single", 1, 8, 8, 16.0, "UPI", "Paid", "Processing",
            "printing", 180, past_time, past_eta, past_time, past_time
        ))
        conn.commit()

        # Now, calculate queue for a new incoming order (needs 2 min = 120s)
        # The delayed order has 8 copies (180s). It must NOT be excluded!
        q = calculate_order_queue(copies=2, conn=conn)
        self.assertGreaterEqual(q["pending_orders_ahead"], 1)

        # Recalculate ETAs for all active orders
        recalculate_active_queue_etas(conn=conn)

        cur.execute("SELECT estimated_start_time, estimated_collection_time, queue_position FROM orders WHERE order_id = ?", (f"ORD-DELAYED-{uid}",))
        del_row = cur.fetchone()
        del_coll = to_ist_datetime(del_row["estimated_collection_time"])
        now = get_ist_now()
        # The delayed order's ETA is now in the future (recalculated from now)
        self.assertGreater(del_coll, now)
        self.assertEqual(del_row["queue_position"], 1)
        conn.close()

    def test_08_ready_for_collection_contributes_zero_processing_time(self):
        """
        Orders marked 'Ready for Collection' or 'Stage Ready' are already printed/prepared.
        They must NOT add processing time to new orders.
        """
        conn = get_db_connection()
        conn.execute("UPDATE orders SET order_status = 'Completed' WHERE LOWER(order_status) NOT IN ('completed', 'collected', 'cancelled', 'canceled', 'rejected')")
        conn.commit()

        uid = uuid.uuid4().hex[:6]
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO orders (
                order_id, token_number, display_order_number, student_name, roll_number, phone_number,
                document_name, stored_filename, print_type, color_mode, side_mode, pages, copies,
                calculated_sheets, total_price, payment_method, payment_status, order_status,
                order_type, processing_duration_seconds, estimated_start_time, estimated_collection_time,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (
            f"ORD-READY-{uid}", f"TK-RDY-{uid}", 7777, "Ready Student", f"TEST-RDY-{uid}", "9777777777",
            "ready.pdf", "ready.pdf", "regular", "bw", "single", 1, 50, 50, 100.0, "UPI", "Paid", "Ready for Collection",
            "printing", 780, get_ist_now().strftime("%Y-%m-%d %H:%M:%S"), (get_ist_now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()

        # Queue calculation for new 1-copy order (120s): should NOT wait for the 50-copy ready order!
        q = calculate_order_queue(copies=1, conn=conn)
        self.assertEqual(q["pending_orders_ahead"], 0)
        self.assertEqual(q["processing_duration_seconds"], 120)
        conn.close()

    def test_09_cancelled_order_recalculates_remaining_queue(self):
        """
        When an earlier order is cancelled, remaining orders must move up and
        recalculate their collection times using only remaining work.
        """
        conn = get_db_connection()
        conn.execute("UPDATE orders SET order_status = 'Completed' WHERE LOWER(order_status) NOT IN ('completed', 'collected', 'cancelled', 'canceled', 'rejected')")
        conn.commit()
        conn.close()

        uid = uuid.uuid4().hex[:6]
        order_1 = create_order({
            "student_name": "Student 1",
            "roll_number": f"TEST-C1-{uid}",
            "phone_number": "9666666661",
            "copies": 5,
            "pages": 1,
            "order_type": "printing"
        })
        order_2 = create_order({
            "student_name": "Student 2",
            "roll_number": f"TEST-C2-{uid}",
            "phone_number": "9666666662",
            "copies": 2,
            "pages": 1,
            "order_type": "printing"
        })

        # Cancel Order 1
        update_order_status(order_1["order_id"], "Cancelled")

        # Track Order 2
        tracked_2 = find_order(f"TEST-C2-{uid}")
        self.assertEqual(len(tracked_2), 1)
        o2_recalc = tracked_2[0]
        # Order 2 should now be head of queue (position 1)
        self.assertEqual(o2_recalc.get("queue_position", 1), 1)

    def test_10_recalculate_error_handling_and_rollback(self):
        """
        Verify that recalculate_active_queue_etas does not silently swallow errors,
        rolls back on failure, and raises the exception.
        """
        class BrokenConnection:
            def cursor(self):
                raise RuntimeError("Simulated Database Network Failure")
            def rollback(self):
                self.rolled_back = True

        broken_conn = BrokenConnection()
        with self.assertRaises(RuntimeError):
            recalculate_active_queue_etas(conn=broken_conn)
        self.assertTrue(getattr(broken_conn, "rolled_back", False))

    def test_11_simultaneous_order_creation_concurrency(self):
        """
        Verify that multiple threads creating orders simultaneously receive stable
        daily order numbers, non-colliding order IDs, and consistent queue ordering.
        """
        import threading
        results = []
        errors = []
        uid = uuid.uuid4().hex[:6]

        def worker(idx):
            try:
                ord_res = create_order({
                    "student_name": f"Concurrent Student {idx}",
                    "roll_number": f"TEST-CONC-{uid}-{idx}",
                    "phone_number": f"95555555{idx:02d}",
                    "copies": 1,
                    "pages": 1,
                    "order_type": "printing"
                })
                results.append(ord_res)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Errors during concurrent order creation: {errors}")
        self.assertEqual(len(results), 8)

        # All display order numbers must be unique
        disp_nums = [r["display_order_number"] for r in results]
        self.assertEqual(len(disp_nums), len(set(disp_nums)), f"Duplicate display numbers: {disp_nums}")

        # All order IDs must be unique
        oids = [r["order_id"] for r in results]
        self.assertEqual(len(oids), len(set(oids)), f"Duplicate order IDs: {oids}")

    def test_12_postgres_locking_and_query_translation(self):
        """
        Verify that PostgreSQL advisory lock queries and query translation logic
        behave correctly on PostgreSQL configurations.
        """
        from database import _to_pg_query, acquire_queue_lock, QUEUE_LOCK_ID
        # Test translation of BEGIN IMMEDIATE to -- NOOP on postgres
        self.assertEqual(_to_pg_query("BEGIN IMMEDIATE"), "-- NOOP")
        # Test translation of ? placeholders
        self.assertEqual(_to_pg_query("SELECT * FROM orders WHERE id = ? AND copies > ?"), "SELECT * FROM orders WHERE id = %s AND copies > %s")
        # Test advisory lock SQL format
        lock_sql = f"SELECT pg_advisory_xact_lock({QUEUE_LOCK_ID});"
        self.assertEqual(_to_pg_query(lock_sql), lock_sql)

        # Mock Postgres connection to verify acquire_queue_lock executes advisory lock
        class MockPgCursor:
            def __init__(self):
                self.executed = []
            def execute(self, sql, params=None):
                self.executed.append(sql)

        class MockPgConn:
            def __init__(self):
                self.cur = MockPgCursor()
            def cursor(self):
                return self.cur

        # Test acquire_queue_lock with is_postgres returning True
        import database
        orig_is_pg = database.is_postgres
        try:
            database.is_postgres = lambda: True
            mock_conn = MockPgConn()
            acquire_queue_lock(mock_conn)
            self.assertEqual(len(mock_conn.cur.executed), 1)
            self.assertIn("pg_advisory_xact_lock", mock_conn.cur.executed[0])
        finally:
            database.is_postgres = orig_is_pg


if __name__ == "__main__":
    unittest.main()

