"""
Event processor.

Ties together:
  - Hikvision event fetching
  - Employee mapping
  - De-duplication (serialNo + 30-second window)
  - Pushing to Frappe HRMS
  - Retry queue management
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from config import settings
from hrms.frappe_client import FrappeClient, FrappeAPIError
from storage.event_store import EventStore

logger = logging.getLogger(__name__)


def _parse_event_time(raw: str) -> datetime | None:
    """
    Convert the device timestamp to a timezone-aware datetime.

    Device format: ``2026-03-04T09:24:29+05:30``
    Returns UTC-aware datetime, or None if unparseable.
    """
    if not raw:
        return None
    try:
        # Python 3.7+ handles ISO-8601 with ±HH:MM offsets natively
        return datetime.fromisoformat(raw)
    except ValueError:
        logger.warning("Unrecognised event timestamp format: %r", raw)
        return None


def _format_for_frappe(dt: datetime) -> str:
    """
    Produce the ``YYYY-MM-DD HH:MM:SS`` string Frappe expects.

    The time is kept in the device's local timezone (no UTC conversion)
    so it matches working hours as recorded on-site.
    """
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class EventProcessor:
    """
    Processes raw Hikvision events and pushes checkins to Frappe HRMS.

    Parameters
    ----------
    frappe_client:
        Configured :class:`FrappeClient` instance.
    store:
        Configured :class:`EventStore` instance.
    employee_map:
        Dict mapping device employee-number strings to HRMS employee IDs.
    dedup_window:
        Seconds within which a second punch from the same employee is ignored.
    retry_max_attempts:
        Maximum push attempts before an event is discarded.
    retry_backoff_base:
        Exponential-backoff base in seconds for retries.
    """

    def __init__(
        self,
        frappe_client: FrappeClient,
        store: EventStore,
        employee_map: dict[str, str],
        dedup_window: int = 30,
        retry_max_attempts: int = 5,
        retry_backoff_base: float = 2.0,
    ) -> None:
        self._frappe = frappe_client
        self._store = store
        self._employee_map = employee_map
        self._dedup_window = dedup_window
        self._retry_max = retry_max_attempts
        self._retry_base = retry_backoff_base

    # ── main entry point ──────────────────────────────────────────────────────

    def process(self, event: dict[str, Any]) -> None:
        """
        Handle one raw event dict from a Hikvision device.

        Fields expected in *event*:
          employeeNoString, name, time, serialNo, deviceIP
        """
        serial_no = str(event.get("serialNo", "")).strip()
        device_ip = event.get("deviceIP", "")
        raw_time = event.get("time", "")
        employee_no = str(event.get("employeeNoString", "")).strip()
        name = event.get("name", "")

        if not serial_no:
            logger.warning("Event missing serialNo – skipping: %s", event)
            return

        # 1. Skip already-processed events (serialNo dedup)
        if self._store.is_processed(serial_no):
            logger.debug(
                "Skipping already-processed event serialNo=%s employee=%s",
                serial_no,
                employee_no,
            )
            return

        # 2. Parse timestamp
        event_dt = _parse_event_time(raw_time)
        if event_dt is None:
            logger.warning(
                "Could not parse timestamp for serialNo=%s raw=%r – skipping",
                serial_no,
                raw_time,
            )
            return

        # 3. Map device employee number → HRMS employee ID
        hrms_id = self._employee_map.get(employee_no)
        if hrms_id is None:
            logger.warning(
                "No HRMS mapping for employee=%s (%s) device=%s – skipping",
                employee_no,
                name,
                device_ip,
            )
            return

        # 4. 30-second window dedup per employee
        if self._store.is_duplicate_punch(hrms_id, event_dt, self._dedup_window):
            logger.info(
                "Duplicate punch within %ds window: employee=%s time=%s – skipping",
                self._dedup_window,
                hrms_id,
                event_dt,
            )
            # Still mark as processed so we don't keep evaluating it
            self._store.mark_processed(serial_no, employee_no, device_ip, raw_time)
            return

        # 5. Push to Frappe
        frappe_time = _format_for_frappe(event_dt)
        self._push_checkin(
            hrms_id=hrms_id,
            frappe_time=frappe_time,
            device_ip=device_ip,
            serial_no=serial_no,
            employee_no=employee_no,
            event_dt=event_dt,
            raw_time=raw_time,
            log_type=settings.DEFAULT_LOG_TYPE,
            latitude=settings.LATITUDE,
            longitude=settings.LONGITUDE,
        )

    def process_retries(self) -> None:
        """Drain the retry queue, re-pushing events that are now due."""
        due = self._store.get_due_retries(self._retry_max)
        if not due:
            return

        logger.info("Processing %d retry item(s)…", len(due))
        for row in due:
            self._push_checkin(
                hrms_id=row["employee_id"],
                frappe_time=row["event_time"],
                device_ip=row["device_ip"],
                serial_no=row["serial_no"],
                employee_no=row["employee_id"],
                event_dt=datetime.fromisoformat(row["event_time"]),
                raw_time=row["event_time"],
                retry_row_id=row["id"],
                attempt=row["attempts"],
                log_type=settings.DEFAULT_LOG_TYPE,
                latitude=settings.LATITUDE,
                longitude=settings.LONGITUDE,
            )

        # Clean up permanently dead entries
        removed = self._store.purge_dead_retries(self._retry_max)
        if removed:
            logger.warning("Discarded %d event(s) that exceeded max retries.", removed)

    # ── internal helpers ──────────────────────────────────────────────────────

    def _push_checkin(
        self,
        *,
        hrms_id: str,
        frappe_time: str,
        device_ip: str,
        serial_no: str,
        employee_no: str,
        event_dt: datetime,
        raw_time: str,
        retry_row_id: int | None = None,
        attempt: int = 0,
        log_type: str | None = None,
        latitude: str | float | None = None,
        longitude: str | float | None = None,
    ) -> None:
        # Resolve friendly name if configured, otherwise use IP
        device_id = settings.DEVICE_NAMES.get(device_ip, device_ip)

        try:
            self._frappe.push_checkin(
                employee=hrms_id,
                event_time=frappe_time,
                device_id=device_id,
                log_type=log_type,
                latitude=latitude,
                longitude=longitude,
            )
            logger.info(
                "Checkin pushed: employee=%s time=%s device=%s serial=%s",
                hrms_id,
                frappe_time,
                device_ip,
                serial_no,
            )
            # Success: record as processed and update last-punch time
            self._store.mark_processed(serial_no, employee_no, device_ip, raw_time)
            self._store.update_last_punch(hrms_id, event_dt)

            # Remove from retry queue if this was a retry
            if retry_row_id is not None:
                self._store.remove_retry(retry_row_id)

        except FrappeAPIError as exc:
            if exc.is_duplicate:
                logger.info(
                    "Frappe reports duplicate for serial=%s – marking processed.",
                    serial_no,
                )
                self._store.mark_processed(serial_no, employee_no, device_ip, raw_time)
                if retry_row_id is not None:
                    self._store.remove_retry(retry_row_id)
                return

            if exc.is_client_error:
                logger.error(
                    "Permanent client error for serial=%s: %s – discarding.",
                    serial_no,
                    exc,
                )
                # Mark processed to avoid infinite reprocessing
                self._store.mark_processed(serial_no, employee_no, device_ip, raw_time)
                if retry_row_id is not None:
                    self._store.remove_retry(retry_row_id)
                return

            # Transient error → schedule retry
            next_attempt = attempt + 1
            delay = self._retry_base ** next_attempt
            next_retry = datetime.now(timezone.utc) + timedelta(seconds=delay)
            logger.warning(
                "Push failed for serial=%s (attempt %d): %s – retrying in %.0fs",
                serial_no,
                next_attempt,
                exc,
                delay,
            )
            self._store.enqueue_retry(
                employee_id=hrms_id,
                event_time=frappe_time,
                device_ip=device_ip,
                serial_no=serial_no,
                next_retry=next_retry,
                error=str(exc),
            )
