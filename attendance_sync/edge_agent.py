"""
Edge attendance agent for a site PC.

Polls the Hikvision devices reachable from this PC and sends signed batches to
the central attendance_sync.server instance. It does not talk to Frappe.
"""
import json
import logging
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

from config import settings
from devices.hikvision_client import HikvisionClient
from transport.security import make_auth_headers


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


def _validate_config() -> None:
    if not settings.DEVICE_CONFIGS:
        raise EnvironmentError("DEVICES must list the devices reachable from this edge PC.")
    if not settings.SYNC_SERVER_URL:
        raise EnvironmentError("SYNC_SERVER_URL is required on an edge PC.")
    if not settings.EDGE_NODE_ID:
        raise EnvironmentError("EDGE_NODE_ID is required on an edge PC.")
    if not settings.EDGE_NODE_SECRET:
        raise EnvironmentError("EDGE_NODE_SECRET is required on an edge PC.")


def fetch_device_events(start_time: datetime, end_time: datetime) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for device_config in settings.DEVICE_CONFIGS:
        client = HikvisionClient(
            device_ip=device_config["ip"],
            username=device_config["user"],
            password=device_config["pass"],
            major=settings.EVENT_MAJOR,
            minor=settings.EVENT_MINOR,
        )
        try:
            for event in client.fetch_events(start_time, end_time):
                events.append(event)
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected error polling device %s", device_config["ip"])
        finally:
            client.close()

    return events


def send_events(events: list[dict[str, Any]]) -> None:
    url = f"{settings.SYNC_SERVER_URL}/events"
    with requests.Session() as session:
        for start in range(0, len(events), settings.EDGE_BATCH_SIZE):
            batch = events[start : start + settings.EDGE_BATCH_SIZE]
            body = json.dumps({"events": batch}, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
            headers = make_auth_headers(settings.EDGE_NODE_ID, settings.EDGE_NODE_SECRET, body)
            headers["Content-Type"] = "application/json"
            headers["Accept"] = "application/json"

            resp = session.post(
                url,
                data=body,
                headers=headers,
                timeout=settings.EDGE_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            logger.info(
                "Sent %d event(s) to server: HTTP %d %s",
                len(batch),
                resp.status_code,
                resp.text[:200],
            )


def main() -> None:
    _setup_logging()
    _validate_config()
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info(
        "Edge agent %s starting. Devices: %s | Server: %s | Interval: %ds",
        settings.EDGE_NODE_ID,
        ", ".join(settings.DEVICE_IPS),
        settings.SYNC_SERVER_URL,
        settings.POLL_INTERVAL,
    )

    last_poll = datetime.now(timezone.utc) - timedelta(hours=settings.FIRST_RUN_LOOKBACK_HOURS)

    while _running:
        cycle_start = datetime.now(timezone.utc)
        start_time = last_poll
        end_time = cycle_start

        events = fetch_device_events(start_time, end_time)
        logger.info(
            "Fetched %d event(s) for %s -> %s",
            len(events),
            start_time.isoformat(),
            end_time.isoformat(),
        )

        try:
            if events:
                send_events(events)
            last_poll = end_time
        except requests.RequestException as exc:
            logger.warning("Could not send events to central server; will retry range: %s", exc)

        deadline = time.monotonic() + settings.POLL_INTERVAL
        while _running and time.monotonic() < deadline:
            time.sleep(min(1.0, deadline - time.monotonic()))

    logger.info("Edge agent stopped.")


if __name__ == "__main__":
    main()
