"""
Central attendance sync server.

Receives signed event batches from edge PCs, stores them in SQLite, and pushes
queued events to Frappe only when the dashboard/manual API asks it to.

Also serves a small dashboard at "/" with live status, recent events, retry
queue, per-node connection status, and a manual "Push now" button.
"""
import json
import logging
import errno
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

from config import settings
from config.env_file import read_env, update_env
from hrms.frappe_client import FrappeClient
from processors.event_processor import EventProcessor
from processors.punch_selection import select_daily_punches
from storage.factory import create_event_store
from transport.security import (
    NODE_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    verify_auth_headers,
)


logger = logging.getLogger(__name__)
_running = True

# Serialises pushes so the same event is never processed by two requests at once.
_push_lock = threading.Lock()

# Wakes the server loop for shutdown.
_wake_event = threading.Event()

_DASHBOARD_HTML_PATH = Path(__file__).resolve().parent / "dashboard.html"
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_last_push_lock = threading.Lock()
_last_push: dict[str, Any] = {
    "started_at": None,
    "finished_at": None,
    "processed": 0,
    "retries": 0,
    "results": {},
    "error": None,
    "trigger": None,
}

# Keys treated as secrets in the config API: masked in GET, blank-on-PUT means keep.
_SECRET_KEYS = {"HRMS_API_KEY", "HRMS_API_SECRET", "POSTGRES_DSN"}

# Whitelist of plain key/value config fields editable via the dashboard.
_EDITABLE_KEYS = (
    "HRMS_URL",
    "HRMS_API_KEY",
    "HRMS_API_SECRET",
    "POLL_INTERVAL",
    "DEDUP_WINDOW",
    "LOG_LEVEL",
    "SERVER_HOST",
    "SERVER_PORT",
    "STORAGE_BACKEND",
    "POSTGRES_DSN",
    "DEFAULT_LOG_TYPE",
)


def _int_query(params: dict[str, list[str]], key: str, default: int, minimum: int, maximum: int) -> int:
    raw = (params.get(key) or [""])[0]
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


class NodeTracker:
    """In-memory record of which edge nodes have called /events recently."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._nodes: dict[str, dict[str, Any]] = {}

    def record(self, node_id: str, accepted: int, inserted: int, skipped: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            entry = self._nodes.setdefault(
                node_id,
                {"first_seen": now, "total_accepted": 0, "total_inserted": 0, "total_skipped": 0},
            )
            entry["last_seen"] = now
            entry["last_accepted"] = accepted
            entry["last_inserted"] = inserted
            entry["last_skipped"] = skipped
            entry["total_accepted"] += accepted
            entry["total_inserted"] += inserted
            entry["total_skipped"] += skipped

    def record_unauthorized(self, node_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            entry = self._nodes.setdefault(node_id or "(unknown)", {"first_seen": now})
            entry["last_unauthorized_at"] = now

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict({"node_id": k}, **v) for k, v in self._nodes.items()]


_node_tracker = NodeTracker()


def _setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if settings.LOG_FILE:
        handlers.append(logging.FileHandler(settings.LOG_FILE, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def _handle_signal(signum, _frame) -> None:
    global _running
    logger.info("Received signal %d; shutting down gracefully.", signum)
    _running = False
    _wake_event.set()


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _html_response(handler: BaseHTTPRequestHandler, status: int, body: str) -> None:
    encoded = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def _namespaced_event(source_node: str, event: dict[str, Any]) -> dict[str, Any]:
    """Avoid serialNo collisions between independent edge PCs/devices."""
    normalized = dict(event)
    serial_no = str(normalized.get("serialNo", "")).strip()
    if serial_no and not serial_no.startswith(f"{source_node}:"):
        normalized["serialNo"] = f"{source_node}:{serial_no}"
    return normalized


def _parse_node_keys(raw: str) -> list[dict[str, str]]:
    nodes: list[dict[str, str]] = []
    for entry in raw.split(","):
        if ":" not in entry:
            continue
        node_id, secret = entry.split(":", 1)
        node_id = node_id.strip()
        secret = secret.strip()
        if node_id:
            nodes.append({"node_id": node_id, "secret": secret})
    return nodes


def _load_config_view() -> dict[str, Any]:
    """Return current .env values with secrets masked, suitable for the UI."""
    env = read_env(_ENV_PATH)
    values: dict[str, Any] = {}
    for key in _EDITABLE_KEYS:
        raw = env.get(key, "")
        if key in _SECRET_KEYS:
            values[key] = {"set": bool(raw), "value": ""}
        else:
            values[key] = {"set": bool(raw), "value": raw}

    nodes = [
        {"node_id": n["node_id"], "secret_set": bool(n["secret"])}
        for n in _parse_node_keys(env.get("SERVER_NODE_KEYS", ""))
    ]
    return {
        "env_path": str(_ENV_PATH),
        "values": values,
        "nodes": nodes,
    }


def _save_config(body: dict[str, Any]) -> list[str]:
    """
    Persist user-supplied config changes to the .env file.

    Body shape:
      {
        "values": {KEY: "new value", ...},
        "nodes":  [{node_id, secret}, ...]      # full replacement of SERVER_NODE_KEYS
      }
    For secret keys, an empty/missing value means "keep existing". For node
    secrets, an empty secret on an existing node means "keep its existing
    secret"; a new node_id with empty secret is rejected.
    """
    incoming_values = body.get("values") or {}
    if not isinstance(incoming_values, dict):
        raise ValueError("values must be an object")

    current = read_env(_ENV_PATH)
    updates: dict[str, str] = {}

    for key, new_value in incoming_values.items():
        if key not in _EDITABLE_KEYS:
            continue
        new_value = "" if new_value is None else str(new_value)
        if key in _SECRET_KEYS and new_value == "":
            continue
        updates[key] = new_value

    if "nodes" in body:
        nodes_in = body.get("nodes") or []
        if not isinstance(nodes_in, list):
            raise ValueError("nodes must be a list")
        existing_secrets = {n["node_id"]: n["secret"] for n in _parse_node_keys(current.get("SERVER_NODE_KEYS", ""))}
        merged: list[str] = []
        for entry in nodes_in:
            if not isinstance(entry, dict):
                raise ValueError("each node must be an object")
            node_id = str(entry.get("node_id", "")).strip()
            secret = str(entry.get("secret", "")).strip()
            if not node_id:
                continue
            if "," in node_id or ":" in node_id:
                raise ValueError(f"node_id '{node_id}' may not contain ',' or ':'")
            if not secret:
                secret = existing_secrets.get(node_id, "")
            if not secret:
                raise ValueError(f"secret required for new node '{node_id}'")
            if "," in secret:
                raise ValueError(f"secret for '{node_id}' may not contain ','")
            merged.append(f"{node_id}:{secret}")
        updates["SERVER_NODE_KEYS"] = ",".join(merged)

    update_env(_ENV_PATH, updates)
    return list(updates.keys())


def _load_employee_map_view() -> dict[str, Any]:
    employee_map = settings.load_employee_map()
    return {
        "path": str(settings.employee_map_path()),
        "count": len(employee_map),
        "entries": [
            {"device_employee_no": key, "frappe_employee_id": value}
            for key, value in sorted(employee_map.items(), key=lambda item: item[0].lower())
        ],
    }


def _save_employee_map(body: dict[str, Any]) -> int:
    entries = body.get("entries")
    if not isinstance(entries, list):
        raise ValueError("entries must be a list")

    employee_map: dict[str, str] = {}
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"entry #{index} must be an object")
        device_employee_no = str(entry.get("device_employee_no", "")).strip()
        frappe_employee_id = str(entry.get("frappe_employee_id", "")).strip()
        if not device_employee_no and not frappe_employee_id:
            continue
        if not device_employee_no:
            raise ValueError(f"entry #{index} is missing device_employee_no")
        if not frappe_employee_id:
            raise ValueError(f"entry #{index} is missing frappe_employee_id")
        if device_employee_no in employee_map:
            raise ValueError(f"duplicate device_employee_no: {device_employee_no}")
        employee_map[device_employee_no] = frappe_employee_id

    path = settings.employee_map_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(employee_map, indent=2, sort_keys=True) + "\n"
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        fh.write(content)
    try:
        tmp_path.replace(path)
    except OSError as exc:
        if exc.errno != errno.EBUSY:
            raise
        logger.warning(
            "Could not atomically replace employee map at %s; falling back to in-place write.",
            path,
        )
        with path.open("w", encoding="utf-8") as fh:
            fh.write(content)
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
    return len(employee_map)


def _filter_attendance_overview(
    rows: list[dict[str, Any]],
    search: str = "",
    date_from: str = "",
    date_to: str = "",
) -> list[dict[str, Any]]:
    search_text = search.lower()
    filtered: list[dict[str, Any]] = []
    for row in rows:
        date = str(row.get("date") or "")
        if date_from and date < date_from:
            continue
        if date_to and date > date_to:
            continue
        if search_text:
            haystack = " ".join(
                str(part)
                for part in [
                    row.get("employee"),
                    row.get("date"),
                    row.get("first_time"),
                    row.get("last_time"),
                    *(row.get("source_nodes") or []),
                    *(row.get("devices") or []),
                ]
            ).lower()
            if search_text not in haystack:
                continue
        filtered.append(row)
    return filtered


def process_pending_events(store: Any, processor: EventProcessor) -> dict[str, Any]:
    """Drain queued inbound events and run retry queue. Thread-safe."""
    with _push_lock:
        rows = store.get_pending_inbound_events()
        processed = 0
        results: dict[str, int] = {}
        if rows:
            logger.info("Processing %d queued inbound event(s).", len(rows))

            ready_rows: list[dict[str, Any]] = []
            for row in rows:
                event = _namespaced_event(row["source_node"], row["payload"])
                result, prepared = processor.prepare_event(event)
                if result == "ready" and prepared is not None:
                    ready_rows.append({"row": row, "prepared": prepared})
                    continue

                store.mark_inbound_processed(row["id"], result)
                results[result] = results.get(result, 0) + 1
                processed += 1

            grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for item in ready_rows:
                prepared = item["prepared"]
                key = (prepared["hrms_id"], prepared["event_date"])
                grouped.setdefault(key, []).append(item)

            selected_ids: set[int] = set()
            for (_employee_id, _event_date), items in grouped.items():
                selected = select_daily_punches(items, lambda item: item["prepared"])
                for item, log_type, label in selected:
                    row = item["row"]
                    prepared = item["prepared"]
                    selected_ids.add(row["id"])
                    result = processor.push_prepared_event(prepared, log_type=log_type)
                    result_key = f"{label}_{result}"
                    store.mark_inbound_processed(row["id"], result_key)
                    results[result_key] = results.get(result_key, 0) + 1
                    processed += 1

            for item in ready_rows:
                row = item["row"]
                if row["id"] in selected_ids:
                    continue
                store.mark_inbound_processed(row["id"], "skipped_middle_punch")
                results["skipped_middle_punch"] = results.get("skipped_middle_punch", 0) + 1
                processed += 1

        retries = processor.process_retries(force=True)
        return {"processed": processed, "retries": int(retries or 0), "results": results}


def run_push(store: Any, processor: EventProcessor, trigger: str) -> dict[str, Any]:
    """Run a push cycle and remember the latest outcome for the dashboard."""
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        result = process_pending_events(store, processor)
        snapshot = {
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "processed": result["processed"],
            "retries": result["retries"],
            "results": result["results"],
            "error": None,
            "trigger": trigger,
        }
        with _last_push_lock:
            _last_push.update(snapshot)
        return {"ok": True, **result}
    except Exception as exc:
        snapshot = {
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "processed": 0,
            "retries": 0,
            "results": {},
            "error": str(exc),
            "trigger": trigger,
        }
        with _last_push_lock:
            _last_push.update(snapshot)
        raise


def latest_push_snapshot() -> dict[str, Any]:
    with _last_push_lock:
        return dict(_last_push)


class EventIngestHandler(BaseHTTPRequestHandler):
    store: Any
    processor: EventProcessor

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("HTTP: " + format, *args)

    # ── routing ──────────────────────────────────────────────────────────────

    def do_GET(self) -> None:
        try:
            self._dispatch_get()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled GET %s failed", self.path)
            self._safe_json_response(500, {"ok": False, "error": str(exc)})

    def _dispatch_get(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/health":
            _json_response(
                self, 200,
                {"ok": True, "pending_events": self.store.pending_inbound_count()},
            )
            return
        if path in ("/", "/dashboard"):
            self._serve_dashboard()
            return
        if path == "/api/status":
            self._serve_status()
            return
        if path == "/api/events":
            _json_response(self, 200, {"events": self.store.recent_inbound(100)})
            return
        if path == "/api/punch-records":
            page = _int_query(query, "page", 1, 1, 100000)
            page_size = _int_query(query, "page_size", 100, 10, 1000)
            search = (query.get("search") or [""])[0].strip()
            date_from = (query.get("from") or [""])[0].strip()
            date_to = (query.get("to") or [""])[0].strip()
            status = (query.get("status") or [""])[0].strip()
            _json_response(
                self,
                200,
                self.store.punch_records(
                    page=page,
                    page_size=page_size,
                    search=search,
                    date_from=date_from,
                    date_to=date_to,
                    status=status,
                ),
            )
            return
        if path == "/api/attendance-overview":
            page = _int_query(query, "page", 1, 1, 100000)
            page_size = _int_query(query, "page_size", 100, 10, 1000)
            search = (query.get("search") or [""])[0].strip()
            date_from = (query.get("from") or [""])[0].strip()
            date_to = (query.get("to") or [""])[0].strip()
            all_rows = self.store.attendance_overview(limit=None)
            filtered_rows = _filter_attendance_overview(all_rows, search, date_from, date_to)
            total = len(filtered_rows)
            start = (page - 1) * page_size
            end = start + page_size
            _json_response(
                self,
                200,
                {
                    "overview": filtered_rows[start:end],
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "has_next": end < total,
                    "has_prev": page > 1,
                },
            )
            return
        if path == "/api/alerts":
            _json_response(self, 200, {"alerts": self.store.dashboard_alerts()})
            return
        if path == "/api/retries":
            _json_response(self, 200, {"retries": self.store.get_retry_queue(100)})
            return
        if path == "/api/processed":
            _json_response(self, 200, {"processed": self.store.recent_processed(100)})
            return
        if path == "/api/config":
            _json_response(self, 200, _load_config_view())
            return
        if path == "/api/employee-map":
            _json_response(self, 200, _load_employee_map_view())
            return
        _json_response(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:
        try:
            self._dispatch_post()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unhandled POST %s failed", self.path)
            self._safe_json_response(500, {"ok": False, "error": str(exc)})

    def _dispatch_post(self) -> None:
        if self.path == "/events":
            self._handle_events_post()
            return
        if self.path == "/api/push":
            try:
                result = run_push(self.store, self.processor, trigger="manual")
            except Exception as exc:  # noqa: BLE001
                logger.exception("Manual push failed")
                _json_response(self, 500, {"ok": False, "error": str(exc)})
                return
            _json_response(self, 200, result)
            return
        if self.path == "/api/config":
            self._handle_config_post()
            return
        if self.path == "/api/employee-map":
            self._handle_employee_map_post()
            return
        _json_response(self, 404, {"error": "not_found"})

    def _safe_json_response(self, status: int, payload: Any) -> None:
        try:
            _json_response(self, status, payload)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            logger.debug("HTTP client disconnected before error response was sent")

    def _handle_config_post(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            _json_response(self, 400, {"error": "invalid_json"})
            return

        try:
            written = _save_config(body)
        except ValueError as exc:
            _json_response(self, 400, {"error": str(exc)})
            return
        except PermissionError as exc:
            _json_response(
                self, 500,
                {"error": f"cannot write {_ENV_PATH}: {exc}. "
                          "In Docker, ensure the host file is writable by uid 10001 "
                          "(e.g. `chown 10001:10001 .env.server` or `chmod 666 .env.server`)."},
            )
            return
        except OSError as exc:
            _json_response(self, 500, {"error": f"cannot write {_ENV_PATH}: {exc}"})
            return

        _json_response(
            self, 200,
            {
                "ok": True,
                "written_keys": sorted(written),
                "restart_required": True,
                "env_path": str(_ENV_PATH),
            },
        )

    def _handle_employee_map_post(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            _json_response(self, 400, {"error": "invalid_json"})
            return

        try:
            count = _save_employee_map(body)
        except ValueError as exc:
            _json_response(self, 400, {"error": str(exc)})
            return
        except PermissionError as exc:
            _json_response(
                self,
                500,
                {
                    "error": f"cannot write {settings.employee_map_path()}: {exc}. "
                    "In Docker, mount employee_map.json read-write and make it writable "
                    "by uid 10001 (e.g. `chown 10001:10001 employee_map.json`)."
                },
            )
            return
        except OSError as exc:
            _json_response(
                self,
                500,
                {"error": f"cannot write {settings.employee_map_path()}: {exc}"},
            )
            return

        _json_response(
            self,
            200,
            {
                "ok": True,
                "count": count,
                "path": str(settings.employee_map_path()),
                "restart_required": True,
            },
        )

    # ── handlers ─────────────────────────────────────────────────────────────

    def _handle_events_post(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)

        node_id = self.headers.get(NODE_HEADER, "")
        timestamp = self.headers.get(TIMESTAMP_HEADER, "")
        signature = self.headers.get(SIGNATURE_HEADER, "")
        if not verify_auth_headers(
            node_id=node_id,
            timestamp=timestamp,
            signature=signature,
            body=body,
            allowed_secrets=settings.SERVER_NODE_KEYS,
        ):
            _node_tracker.record_unauthorized(node_id)
            _json_response(self, 401, {"error": "unauthorized"})
            return

        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            _json_response(self, 400, {"error": "invalid_json"})
            return

        events = payload.get("events")
        if not isinstance(events, list):
            _json_response(self, 400, {"error": "events_must_be_list"})
            return

        safe_events = [event for event in events if isinstance(event, dict)]
        inserted, skipped = self.store.enqueue_inbound_events(node_id, safe_events)
        _node_tracker.record(node_id, len(safe_events), inserted, skipped)
        logger.info(
            "Received %d event(s) from %s: inserted=%d skipped=%d",
            len(safe_events), node_id, inserted, skipped,
        )
        _json_response(
            self, 202,
            {"accepted": len(safe_events), "inserted": inserted, "skipped": skipped},
        )

    def _serve_dashboard(self) -> None:
        try:
            html = _DASHBOARD_HTML_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            _html_response(self, 500, "<h1>dashboard.html missing</h1>")
            return
        _html_response(self, 200, html)

    def _serve_status(self) -> None:
        counts = self.store.inbound_counts()
        payload = {
            "now": datetime.now(timezone.utc).isoformat(),
            "server": {
                "host": settings.SERVER_HOST,
                "port": settings.SERVER_PORT,
                "poll_interval": settings.POLL_INTERVAL,
                "storage_backend": settings.STORAGE_BACKEND,
                "hrms_url": settings.HRMS_URL,
            },
            "counts": {
                "pending": counts.get("pending", 0),
                "done": counts.get("done", 0),
                "processed_total": self.store.processed_count(),
                "retry_queue": self.store.retry_queue_size(),
            },
            "last_push": latest_push_snapshot(),
            "configured_nodes": sorted(settings.SERVER_NODE_KEYS.keys()),
            "nodes": _node_tracker.snapshot(),
        }
        _json_response(self, 200, payload)


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    """HTTP server that does not print tracebacks for client disconnects."""

    def handle_error(self, request: Any, client_address: Any) -> None:
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            logger.debug("HTTP client disconnected early: %s", client_address)
            return
        super().handle_error(request, client_address)


def create_server(store: Any, processor: EventProcessor) -> ThreadingHTTPServer:
    EventIngestHandler.store = store
    EventIngestHandler.processor = processor
    return QuietThreadingHTTPServer((settings.SERVER_HOST, settings.SERVER_PORT), EventIngestHandler)


def create_processor(store: Any) -> tuple[FrappeClient, EventProcessor]:
    if not settings.SERVER_NODE_KEYS:
        raise EnvironmentError("SERVER_NODE_KEYS must list at least one node_id:secret pair.")
    if not settings.HRMS_URL:
        raise EnvironmentError("HRMS_URL is required on the central server.")
    if not settings.HRMS_API_KEY:
        raise EnvironmentError("HRMS_API_KEY is required on the central server.")
    if not settings.HRMS_API_SECRET:
        raise EnvironmentError("HRMS_API_SECRET is required on the central server.")

    frappe = FrappeClient(
        base_url=settings.HRMS_URL,
        api_key=settings.HRMS_API_KEY,
        api_secret=settings.HRMS_API_SECRET,
    )
    employee_map = settings.load_employee_map()
    processor = EventProcessor(
        frappe_client=frappe,
        store=store,
        employee_map=employee_map,
        dedup_window=settings.DEDUP_WINDOW,
        retry_max_attempts=settings.RETRY_MAX_ATTEMPTS,
        retry_backoff_base=settings.RETRY_BACKOFF_BASE,
    )
    return frappe, processor


def main() -> None:
    _setup_logging()
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    store = create_event_store()
    frappe, processor = create_processor(store)
    server = create_server(store, processor)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    logger.info(
        "Central sync server listening on %s:%d; dashboard at http://%s:%d/ | Frappe push is manual",
        settings.SERVER_HOST, settings.SERVER_PORT,
        settings.SERVER_HOST, settings.SERVER_PORT,
    )

    try:
        while _running:
            _wake_event.wait(timeout=1.0)
            _wake_event.clear()
    finally:
        logger.info("Stopping central sync server.")
        server.shutdown()
        server.server_close()
        frappe.close()
        store.close()


if __name__ == "__main__":
    main()
