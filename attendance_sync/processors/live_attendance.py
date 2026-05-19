"""Build live attendance feed and summary stats for dashboard widgets."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from processors.punch_selection import punch_sort_key


def live_calendar_today() -> str:
    from config import settings

    tz_name = str(settings.FRAPPE_AUTO_PUSH_TIMEZONE or "").strip()
    if tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name)).date().isoformat()
        except Exception:  # noqa: BLE001
            pass
    return datetime.now(timezone.utc).date().isoformat()


def _event_date(event_time: str) -> str:
    return event_time.split("T", 1)[0].split(" ", 1)[0] if event_time else ""


def _action_for_punch_index(index: int) -> str:
    return "punch-in" if index % 2 == 1 else "punch-out"


def build_live_attendance(
    events: list[dict[str, Any]],
    *,
    today: str,
    employee_map: dict[str, str],
    details_by_id: dict[str, dict[str, Any]],
    feed_limit: int = 50,
    display_name: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    """
    Derive today's live feed and counters from raw inbound punch events.

    Per employee per calendar day, punches are ordered chronologically. Odd-indexed
    punches are treated as punch-in, even-indexed as punch-out.
    """
    today_events: list[dict[str, Any]] = []
    for event in events:
        event_time = str(event.get("event_time") or "").strip()
        employee = str(event.get("employee") or "").strip()
        if not employee or not event_time:
            continue
        if _event_date(event_time) != today:
            continue
        today_events.append(event)

    by_employee: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in today_events:
        by_employee[str(event["employee"])].append(event)

    punch_index_by_serial: dict[str, int] = {}
    active_count = 0
    punch_ins_today = 0
    punch_outs_today = 0

    for employee, employee_events in by_employee.items():
        ordered = sorted(
            employee_events,
            key=lambda item: punch_sort_key(
                {
                    "time": item.get("event_time"),
                    "serial_no": item.get("serial_no"),
                }
            ),
        )
        punch_count = len(ordered)
        if punch_count <= 0:
            continue
        punch_ins_today += 1
        if punch_count % 2 == 1:
            active_count += 1
        if punch_count >= 2 and punch_count % 2 == 0:
            punch_outs_today += 1
        for index, item in enumerate(ordered, start=1):
            serial_no = str(item.get("serial_no") or item.get("id") or "")
            if serial_no:
                punch_index_by_serial[serial_no] = index

    feed_source = sorted(
        today_events,
        key=lambda item: punch_sort_key(
            {
                "time": item.get("event_time"),
                "serial_no": item.get("serial_no"),
            }
        ),
        reverse=True,
    )

    feed: list[dict[str, Any]] = []
    for event in feed_source[:feed_limit]:
        device_employee_no = str(event.get("employee") or "").strip()
        frappe_employee_id = employee_map.get(device_employee_no, "")
        details = details_by_id.get(frappe_employee_id, {})
        serial_no = str(event.get("serial_no") or "")
        punch_index = punch_index_by_serial.get(serial_no, 1)
        device_name = str(event.get("name") or "").strip()
        employee_label = device_name or display_name(details) or device_employee_no
        feed.append(
            {
                "id": str(event.get("id") or serial_no or device_employee_no),
                "employee": employee_label,
                "department": str(details.get("department") or "").strip(),
                "action": _action_for_punch_index(punch_index),
                "time": str(event.get("event_time") or ""),
                "device_employee_no": device_employee_no,
                "frappe_employee_id": frappe_employee_id,
            }
        )

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "date": today,
        "active_count": active_count,
        "punch_ins_today": punch_ins_today,
        "punch_outs_today": punch_outs_today,
        "feed": feed,
    }
