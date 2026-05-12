"""PostgreSQL-backed event store for the central Docker server."""
import json
import threading
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row


class PostgresEventStore:
    """Thread-local PostgreSQL store implementing the EventStore interface."""

    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise EnvironmentError("POSTGRES_DSN is required when STORAGE_BACKEND=postgres.")
        self._dsn = dsn
        self._local = threading.local()
        self._init_db()

    def _conn(self) -> psycopg.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = psycopg.connect(self._dsn, row_factory=dict_row)
        return self._local.conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            del self._local.conn

    def _init_db(self) -> None:
        conn = self._conn()
        with conn.transaction():
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_events (
                    serial_no   TEXT PRIMARY KEY,
                    employee_no TEXT NOT NULL,
                    device_ip   TEXT NOT NULL,
                    event_time  TEXT NOT NULL,
                    pushed_at   TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS last_punch (
                    employee_id TEXT PRIMARY KEY,
                    punch_time  TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS retry_queue (
                    id          BIGSERIAL PRIMARY KEY,
                    employee_id TEXT    NOT NULL,
                    event_time  TEXT    NOT NULL,
                    device_ip   TEXT    NOT NULL,
                    serial_no   TEXT    NOT NULL UNIQUE,
                    attempts    INTEGER NOT NULL DEFAULT 0,
                    next_retry  TEXT    NOT NULL,
                    last_error  TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS inbound_events (
                    id              BIGSERIAL PRIMARY KEY,
                    source_node     TEXT    NOT NULL,
                    source_event_id TEXT    NOT NULL,
                    payload         JSONB   NOT NULL,
                    status          TEXT    NOT NULL DEFAULT 'pending',
                    received_at     TEXT    NOT NULL,
                    processed_at    TEXT,
                    last_result     TEXT,
                    UNIQUE(source_node, source_event_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_inbound_events_pending
                ON inbound_events (status, received_at, id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_retry_queue_due
                ON retry_queue (next_retry, attempts)
                """
            )

    def is_processed(self, serial_no: str) -> bool:
        row = self._conn().execute(
            "SELECT 1 FROM processed_events WHERE serial_no = %s",
            (serial_no,),
        ).fetchone()
        return row is not None

    def mark_processed(
        self,
        serial_no: str,
        employee_no: str,
        device_ip: str,
        event_time: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn().transaction():
            self._conn().execute(
                """
                INSERT INTO processed_events
                    (serial_no, employee_no, device_ip, event_time, pushed_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (serial_no) DO NOTHING
                """,
                (serial_no, employee_no, device_ip, event_time, now),
            )

    def is_duplicate_punch(
        self, employee_id: str, punch_time: datetime, window_seconds: int
    ) -> bool:
        row = self._conn().execute(
            "SELECT punch_time FROM last_punch WHERE employee_id = %s",
            (employee_id,),
        ).fetchone()
        if row is None:
            return False

        last = datetime.fromisoformat(row["punch_time"])
        p_naive = punch_time.replace(tzinfo=None)
        l_naive = last.replace(tzinfo=None)
        return abs((p_naive - l_naive).total_seconds()) < window_seconds

    def update_last_punch(self, employee_id: str, punch_time: datetime) -> None:
        with self._conn().transaction():
            self._conn().execute(
                """
                INSERT INTO last_punch (employee_id, punch_time)
                VALUES (%s, %s)
                ON CONFLICT (employee_id)
                DO UPDATE SET punch_time = EXCLUDED.punch_time
                """,
                (employee_id, punch_time.isoformat()),
            )

    def enqueue_retry(
        self,
        employee_id: str,
        event_time: str,
        device_ip: str,
        serial_no: str,
        next_retry: datetime,
        error: str = "",
    ) -> None:
        with self._conn().transaction():
            self._conn().execute(
                """
                INSERT INTO retry_queue
                    (employee_id, event_time, device_ip, serial_no, attempts, next_retry, last_error)
                VALUES (%s, %s, %s, %s, 1, %s, %s)
                ON CONFLICT (serial_no) DO UPDATE SET
                    attempts = retry_queue.attempts + 1,
                    next_retry = EXCLUDED.next_retry,
                    last_error = EXCLUDED.last_error
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

    def get_due_retries(self, max_attempts: int) -> list[dict]:
        rows = self._conn().execute(
            """
            SELECT id, employee_id, event_time, device_ip, serial_no, attempts
            FROM retry_queue
            WHERE next_retry <= %s AND attempts < %s
            ORDER BY next_retry
            """,
            (datetime.now(timezone.utc).isoformat(), max_attempts),
        ).fetchall()
        return [dict(row) for row in rows]

    def remove_retry(self, row_id: int) -> None:
        with self._conn().transaction():
            self._conn().execute("DELETE FROM retry_queue WHERE id = %s", (row_id,))

    def purge_dead_retries(self, max_attempts: int) -> int:
        with self._conn().transaction():
            cur = self._conn().execute(
                "DELETE FROM retry_queue WHERE attempts >= %s",
                (max_attempts,),
            )
        return cur.rowcount or 0

    def enqueue_inbound_events(
        self,
        source_node: str,
        events: list[dict[str, Any]],
    ) -> tuple[int, int]:
        now = datetime.now(timezone.utc).isoformat()
        inserted = 0
        skipped = 0

        with self._conn().transaction():
            for event in events:
                source_event_id = self._source_event_id(event)
                row = self._conn().execute(
                    """
                    INSERT INTO inbound_events
                        (source_node, source_event_id, payload, received_at)
                    VALUES (%s, %s, %s::jsonb, %s)
                    ON CONFLICT (source_node, source_event_id) DO NOTHING
                    RETURNING id
                    """,
                    (
                        source_node,
                        source_event_id,
                        json.dumps(event, separators=(",", ":"), sort_keys=True),
                        now,
                    ),
                ).fetchone()
                if row:
                    inserted += 1
                else:
                    skipped += 1

        return inserted, skipped

    def get_pending_inbound_events(self, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._conn().execute(
            """
            SELECT id, source_node, payload
            FROM inbound_events
            WHERE status = 'pending'
            ORDER BY received_at, id
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "source_node": row["source_node"],
                "payload": row["payload"]
                if isinstance(row["payload"], dict)
                else json.loads(row["payload"]),
            }
            for row in rows
        ]

    def mark_inbound_processed(self, row_id: int, result: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn().transaction():
            self._conn().execute(
                """
                UPDATE inbound_events
                SET status = 'done', processed_at = %s, last_result = %s
                WHERE id = %s
                """,
                (now, result, row_id),
            )

    def pending_inbound_count(self) -> int:
        row = self._conn().execute(
            "SELECT COUNT(*) AS count FROM inbound_events WHERE status = 'pending'"
        ).fetchone()
        return int(row["count"]) if row else 0

    @staticmethod
    def _source_event_id(event: dict[str, Any]) -> str:
        serial_no = str(event.get("serialNo", "")).strip()
        if serial_no:
            return serial_no

        parts = [
            str(event.get("deviceIP", "")).strip(),
            str(event.get("employeeNoString", "")).strip(),
            str(event.get("time", "")).strip(),
        ]
        return "|".join(parts)
