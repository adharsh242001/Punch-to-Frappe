"""
Central attendance sync server.

Receives signed event batches from edge PCs, stores them in SQLite, and pushes
queued events to Frappe on the configured POLL_INTERVAL.
"""
import json
import logging
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

from config import settings
from hrms.frappe_client import FrappeClient
from processors.event_processor import EventProcessor
from storage.factory import create_event_store
from transport.security import (
    NODE_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    verify_auth_headers,
)


logger = logging.getLogger(__name__)
_running = True


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


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _namespaced_event(source_node: str, event: dict[str, Any]) -> dict[str, Any]:
    """Avoid serialNo collisions between independent edge PCs/devices."""
    normalized = dict(event)
    serial_no = str(normalized.get("serialNo", "")).strip()
    if serial_no and not serial_no.startswith(f"{source_node}:"):
        normalized["serialNo"] = f"{source_node}:{serial_no}"
    return normalized


class EventIngestHandler(BaseHTTPRequestHandler):
    store: Any

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("HTTP: " + format, *args)

    def do_GET(self) -> None:
        if self.path != "/health":
            _json_response(self, 404, {"error": "not_found"})
            return

        _json_response(
            self,
            200,
            {
                "ok": True,
                "pending_events": self.store.pending_inbound_count(),
            },
        )

    def do_POST(self) -> None:
        if self.path != "/events":
            _json_response(self, 404, {"error": "not_found"})
            return

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
        logger.info(
            "Received %d event(s) from %s: inserted=%d skipped=%d",
            len(safe_events),
            node_id,
            inserted,
            skipped,
        )
        _json_response(
            self,
            202,
            {"accepted": len(safe_events), "inserted": inserted, "skipped": skipped},
        )


def create_server(store: Any) -> ThreadingHTTPServer:
    EventIngestHandler.store = store
    return ThreadingHTTPServer((settings.SERVER_HOST, settings.SERVER_PORT), EventIngestHandler)


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


def process_pending_events(store: Any, processor: EventProcessor) -> int:
    rows = store.get_pending_inbound_events()
    if not rows:
        return 0

    logger.info("Processing %d queued inbound event(s).", len(rows))
    for row in rows:
        event = _namespaced_event(row["source_node"], row["payload"])
        result = processor.process(event)
        store.mark_inbound_processed(row["id"], result)

    processor.process_retries()
    return len(rows)


def main() -> None:
    _setup_logging()
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    store = create_event_store()
    frappe, processor = create_processor(store)
    server = create_server(store)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    logger.info(
        "Central sync server listening on %s:%d; push interval=%ds",
        settings.SERVER_HOST,
        settings.SERVER_PORT,
        settings.POLL_INTERVAL,
    )

    try:
        while _running:
            process_pending_events(store, processor)
            deadline = time.monotonic() + settings.POLL_INTERVAL
            while _running and time.monotonic() < deadline:
                time.sleep(min(1.0, deadline - time.monotonic()))
    finally:
        logger.info("Stopping central sync server.")
        server.shutdown()
        server.server_close()
        frappe.close()
        store.close()


if __name__ == "__main__":
    main()
