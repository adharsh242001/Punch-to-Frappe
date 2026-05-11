"""
Attendance Sync Service — entry point.

Continuously polls Hikvision devices every POLL_INTERVAL seconds,
processes new attendance events, and pushes them to Frappe HRMS.

Usage
-----
    python main.py

Environment variables are loaded from .env (see .env.example).
"""
import logging
import signal
import sys
import time
from datetime import datetime, timezone, timedelta

# Ensure the package root is on the path when run directly
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

from config import settings
from devices.hikvision_client import HikvisionClient
from hrms.frappe_client import FrappeClient
from processors.event_processor import EventProcessor
from storage.event_store import EventStore

# ── logging setup ─────────────────────────────────────────────────────────────

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


logger = logging.getLogger(__name__)

# ── graceful shutdown ─────────────────────────────────────────────────────────

_running = True


def _handle_signal(signum, _frame) -> None:
    global _running
    logger.info("Received signal %d – shutting down gracefully…", signum)
    _running = False


# ── core poll loop ────────────────────────────────────────────────────────────

def run_poll_cycle(
    device_config: dict[str, str],
    start_time: datetime,
    end_time: datetime,
    processor: EventProcessor,
) -> None:
    """Fetch events from one device and run each through the processor."""
    client = HikvisionClient(
        device_ip=device_config["ip"],
        username=device_config["user"],
        password=device_config["pass"],
        major=settings.EVENT_MAJOR,
        minor=settings.EVENT_MINOR,
    )

    event_count = 0
    try:
        for event in client.fetch_events(start_time, end_time):
            processor.process(event)
            event_count += 1
    finally:
        client.close()

    logger.debug("[%s] Fetched %d event(s) in this cycle.", device_config["ip"], event_count)


def create_processor() -> tuple[FrappeClient, EventProcessor]:
    """Build the shared Frappe/EventProcessor infrastructure."""
    store = EventStore(settings.STORE_PATH)
    frappe = FrappeClient(
        base_url=settings.HRMS_URL,
        api_key=settings.HRMS_API_KEY,
        api_secret=settings.HRMS_API_SECRET,
    )
    employee_map = settings.load_employee_map()
    logger.info("Employee map loaded: %d entries", len(employee_map))

    processor = EventProcessor(
        frappe_client=frappe,
        store=store,
        employee_map=employee_map,
        dedup_window=settings.DEDUP_WINDOW,
        retry_max_attempts=settings.RETRY_MAX_ATTEMPTS,
        retry_backoff_base=settings.RETRY_BACKOFF_BASE,
    )
    return frappe, processor


def run_manual_sync(start_time: datetime, end_time: datetime) -> None:
    """Run a one-off sync for the requested date range."""
    if start_time >= end_time:
        raise ValueError("start_time must be earlier than end_time.")

    _setup_logging()
    logger.info(
        "=== Manual attendance sync starting: %s -> %s ===",
        start_time.isoformat(),
        end_time.isoformat(),
    )

    frappe, processor = create_processor()
    try:
        for device_config in settings.DEVICE_CONFIGS:
            try:
                run_poll_cycle(device_config, start_time, end_time, processor)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Unexpected error during manual sync for device %s",
                    device_config["ip"],
                )

        try:
            processor.process_retries()
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected error processing retry queue after manual sync")
    finally:
        frappe.close()

    logger.info("=== Manual attendance sync complete ===")


def main() -> None:
    _setup_logging()
    logger.info("=== Attendance Sync Service starting ===")
    if not settings.DEVICE_CONFIGS:
        raise EnvironmentError("DEVICES must list at least one IP when running the poller.")

    logger.info(
        "Devices: %s | Poll interval: %ds | Dedup window: %ds",
        ", ".join(settings.DEVICE_IPS),
        settings.POLL_INTERVAL,
        settings.DEDUP_WINDOW,
    )

    # Graceful-shutdown hooks
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Shared infrastructure
    frappe, processor = create_processor()

    # On first run, look back to avoid missing recent events
    last_poll: datetime = datetime.now(timezone.utc) - timedelta(
        hours=settings.FIRST_RUN_LOOKBACK_HOURS
    )

    while _running:
        cycle_start = datetime.now(timezone.utc)
        end_time = cycle_start
        start_time = last_poll

        logger.debug(
            "Polling cycle: %s → %s",
            start_time.isoformat(),
            end_time.isoformat(),
        )

        for device_config in settings.DEVICE_CONFIGS:
            try:
                run_poll_cycle(device_config, start_time, end_time, processor)
            except Exception:  # noqa: BLE001
                logger.exception("Unexpected error polling device %s", device_config["ip"])

        # Process any pending retries
        try:
            processor.process_retries()
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected error processing retry queue")

        last_poll = end_time

        # Sleep until the next poll interval, honouring shutdown signals
        elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
        sleep_for = max(0.0, settings.POLL_INTERVAL - elapsed)
        logger.debug("Cycle complete in %.2fs; sleeping %.2fs", elapsed, sleep_for)

        deadline = time.monotonic() + sleep_for
        while _running and time.monotonic() < deadline:
            time.sleep(min(1.0, deadline - time.monotonic()))

    logger.info("=== Attendance Sync Service stopped ===")
    frappe.close()


if __name__ == "__main__":
    main()
