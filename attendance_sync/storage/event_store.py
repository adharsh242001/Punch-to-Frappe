"""
SQLite-backed event store.

Responsibilities
────────────────
1. Track processed serialNos so the same Hikvision event is never pushed twice.
2. Track per-employee last-punch time for the 30-second de-duplication window.
3. Persist a retry queue for checkins that failed to reach Frappe.
"""
import sqlite3
import threading
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EventStore:
    """Thread-safe SQLite store for attendance events."""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._local = threading.local()
        self._init_db()

    # ── connection management ────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        """Return a per-thread connection (created on first access)."""
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(str(self._path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return self._local.conn

    def close(self) -> None:
        """Close this thread's SQLite connection if one has been opened."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            del self._local.conn

    def _init_db(self) -> None:
        conn = self._conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS processed_events (
                serial_no   TEXT PRIMARY KEY,
                employee_no TEXT NOT NULL,
                device_ip   TEXT NOT NULL,
                event_time  TEXT NOT NULL,
                pushed_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS last_punch (
                employee_id TEXT PRIMARY KEY,
                punch_time  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS retry_queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT    NOT NULL,
                event_time  TEXT    NOT NULL,
                device_ip   TEXT    NOT NULL,
                serial_no   TEXT    NOT NULL UNIQUE,
                attempts    INTEGER NOT NULL DEFAULT 0,
                next_retry  TEXT    NOT NULL,
                last_error  TEXT
            );

            CREATE TABLE IF NOT EXISTS inbound_events (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                source_node    TEXT    NOT NULL,
                source_event_id TEXT    NOT NULL,
                payload        TEXT    NOT NULL,
                status         TEXT    NOT NULL DEFAULT 'pending',
                received_at    TEXT    NOT NULL,
                processed_at   TEXT,
                last_result    TEXT,
                UNIQUE(source_node, source_event_id)
            );
            """
        )
        conn.commit()

    # ── processed events ─────────────────────────────────────────────────────

    def is_processed(self, serial_no: str) -> bool:
        """Return True if this serialNo has already been pushed."""
        cur = self._conn().execute(
            "SELECT 1 FROM processed_events WHERE serial_no = ?", (serial_no,)
        )
        return cur.fetchone() is not None

    def mark_processed(
        self,
        serial_no: str,
        employee_no: str,
        device_ip: str,
        event_time: str,
    ) -> None:
        """Record a successfully pushed event."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn().execute(
            """
            INSERT OR IGNORE INTO processed_events
                (serial_no, employee_no, device_ip, event_time, pushed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (serial_no, employee_no, device_ip, event_time, now),
        )
        self._conn().commit()

    # ── 30-second de-duplication ──────────────────────────────────────────────

    def is_duplicate_punch(
        self, employee_id: str, punch_time: datetime, window_seconds: int
    ) -> bool:
        """
        Return True if the employee already has a punch within *window_seconds*
        of *punch_time*.
        """
        cur = self._conn().execute(
            "SELECT punch_time FROM last_punch WHERE employee_id = ?",
            (employee_id,),
        )
        row = cur.fetchone()
        if row is None:
            return False
        last = datetime.fromisoformat(row["punch_time"])
        # To avoid "TypeError: can't subtract offset-naive and offset-aware datetimes",
        # strip tzinfo if they mismatch, or just unconditionally strip it since both are local.
        p_naive = punch_time.replace(tzinfo=None)
        l_naive = last.replace(tzinfo=None)
        delta = abs((p_naive - l_naive).total_seconds())
        return delta < window_seconds

    def update_last_punch(self, employee_id: str, punch_time: datetime) -> None:
        self._conn().execute(
            """
            INSERT INTO last_punch (employee_id, punch_time)
            VALUES (?, ?)
            ON CONFLICT(employee_id) DO UPDATE SET punch_time = excluded.punch_time
            """,
            (employee_id, punch_time.isoformat()),
        )
        self._conn().commit()

    # ── retry queue ───────────────────────────────────────────────────────────

    def enqueue_retry(
        self,
        employee_id: str,
        event_time: str,
        device_ip: str,
        serial_no: str,
        next_retry: datetime,
        error: str = "",
    ) -> None:
        """Add (or update attempt count of) a failed checkin to the retry queue."""
        self._conn().execute(
            """
            INSERT INTO retry_queue
                (employee_id, event_time, device_ip, serial_no, attempts, next_retry, last_error)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(serial_no) DO UPDATE SET
                attempts   = attempts + 1,
                next_retry = excluded.next_retry,
                last_error = excluded.last_error
            """,
            (
                employee_id,
                event_time,
                device_ip,
                serial_no,
                next_retry.isoformat(),
                error,
            ),
        )
        self._conn().commit()

    def get_due_retries(self, max_attempts: int) -> list[dict]:
        """Return retry rows whose next_retry <= now and attempts < max_attempts."""
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn().execute(
            """
            SELECT id, employee_id, event_time, device_ip, serial_no, attempts
            FROM retry_queue
            WHERE next_retry <= ? AND attempts < ?
            ORDER BY next_retry
            """,
            (now, max_attempts),
        )
        return [dict(row) for row in cur.fetchall()]

    def remove_retry(self, row_id: int) -> None:
        self._conn().execute("DELETE FROM retry_queue WHERE id = ?", (row_id,))
        self._conn().commit()

    def purge_dead_retries(self, max_attempts: int) -> int:
        """Delete permanently-failed entries; return how many were removed."""
        cur = self._conn().execute(
            "DELETE FROM retry_queue WHERE attempts >= ?", (max_attempts,)
        )
        self._conn().commit()
        return cur.rowcount

    # ── inbound edge queue ───────────────────────────────────────────────────

    def enqueue_inbound_events(
        self,
        source_node: str,
        events: list[dict[str, Any]],
    ) -> tuple[int, int]:
        """Store raw events received from an edge node; return inserted/skipped counts."""
        now = datetime.now(timezone.utc).isoformat()
        inserted = 0
        skipped = 0

        for event in events:
            source_event_id = self._source_event_id(event)
            payload = json.dumps(event, separators=(",", ":"), sort_keys=True)
            cur = self._conn().execute(
                """
                INSERT OR IGNORE INTO inbound_events
                    (source_node, source_event_id, payload, received_at)
                VALUES (?, ?, ?, ?)
                """,
                (source_node, source_event_id, payload, now),
            )
            if cur.rowcount:
                inserted += 1
            else:
                skipped += 1

        self._conn().commit()
        return inserted, skipped

    def get_pending_inbound_events(self, limit: int = 500) -> list[dict[str, Any]]:
        """Return queued edge events that still need to be pushed to Frappe."""
        cur = self._conn().execute(
            """
            SELECT id, source_node, payload
            FROM inbound_events
            WHERE status = 'pending'
            ORDER BY received_at, id
            LIMIT ?
            """,
            (limit,),
        )
        rows = []
        for row in cur.fetchall():
            rows.append(
                {
                    "id": row["id"],
                    "source_node": row["source_node"],
                    "payload": json.loads(row["payload"]),
                }
            )
        return rows

    def mark_inbound_processed(self, row_id: int, result: str) -> None:
        """Mark an inbound event as handled by the central processor."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn().execute(
            """
            UPDATE inbound_events
            SET status = 'done', processed_at = ?, last_result = ?
            WHERE id = ?
            """,
            (now, result, row_id),
        )
        self._conn().commit()

    def pending_inbound_count(self) -> int:
        cur = self._conn().execute(
            "SELECT COUNT(*) AS count FROM inbound_events WHERE status = 'pending'"
        )
        row = cur.fetchone()
        return int(row["count"]) if row else 0

    # ── dashboard helpers ────────────────────────────────────────────────────

    def inbound_counts(self) -> dict[str, int]:
        cur = self._conn().execute(
            "SELECT status, COUNT(*) AS count FROM inbound_events GROUP BY status"
        )
        counts = {"pending": 0, "done": 0}
        for row in cur.fetchall():
            counts[row["status"]] = int(row["count"])
        return counts

    def processed_count(self) -> int:
        cur = self._conn().execute("SELECT COUNT(*) AS count FROM processed_events")
        row = cur.fetchone()
        return int(row["count"]) if row else 0

    def retry_queue_size(self) -> int:
        cur = self._conn().execute("SELECT COUNT(*) AS count FROM retry_queue")
        row = cur.fetchone()
        return int(row["count"]) if row else 0

    def recent_inbound(self, limit: int = 50) -> list[dict[str, Any]]:
        cur = self._conn().execute(
            """
            SELECT id, source_node, payload, status, received_at, processed_at, last_result
            FROM inbound_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = []
        for row in cur.fetchall():
            try:
                payload = json.loads(row["payload"])
            except Exception:
                payload = {}
            rows.append(
                {
                    "id": row["id"],
                    "source_node": row["source_node"],
                    "status": row["status"],
                    "received_at": row["received_at"],
                    "processed_at": row["processed_at"],
                    "last_result": row["last_result"],
                    "employee": payload.get("employeeNoString") or payload.get("employeeNo"),
                    "device_ip": payload.get("deviceIP"),
                    "event_time": payload.get("time"),
                    "serial_no": payload.get("serialNo"),
                }
            )
        return rows

    def recent_processed(self, limit: int = 50) -> list[dict[str, Any]]:
        cur = self._conn().execute(
            """
            SELECT serial_no, employee_no, device_ip, event_time, pushed_at
            FROM processed_events
            ORDER BY pushed_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_retry_queue(self, limit: int = 50) -> list[dict[str, Any]]:
        cur = self._conn().execute(
            """
            SELECT id, employee_id, event_time, device_ip, serial_no, attempts,
                   next_retry, last_error
            FROM retry_queue
            ORDER BY next_retry
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def _source_event_id(event: dict[str, Any]) -> str:
        """Build a stable source id when the device serial number is missing."""
        serial_no = str(event.get("serialNo", "")).strip()
        if serial_no:
            return serial_no

        parts = [
            str(event.get("deviceIP", "")).strip(),
            str(event.get("employeeNoString", "")).strip(),
            str(event.get("time", "")).strip(),
        ]
        return "|".join(parts)
