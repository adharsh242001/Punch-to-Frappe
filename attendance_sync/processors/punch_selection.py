"""Rules for choosing which daily punches are pushed to Frappe."""
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar

T = TypeVar("T")


def _sort_value(value: Any) -> tuple[int, float | str]:
    if isinstance(value, datetime):
        return (0, value.timestamp())
    if isinstance(value, str):
        try:
            return (0, datetime.fromisoformat(value).timestamp())
        except ValueError:
            return (1, value)
    return (1, str(value))


def punch_sort_key(prepared: dict[str, Any]) -> tuple[tuple[int, float | str], str]:
    """Return a deterministic sort key for one prepared/raw punch."""
    value = prepared.get("event_dt") or prepared.get("time") or prepared.get("raw_time") or ""
    serial_no = str(prepared.get("serial_no") or prepared.get("serialNo") or "")
    return (_sort_value(value), serial_no)


def select_daily_punches(
    items: list[T],
    prepared_for: Callable[[T], dict[str, Any]],
) -> list[tuple[T, str | None, str]]:
    """
    Select the daily punches to push and assign derived Frappe log types.

    Rules:
    - 1 punch: first punch as IN.
    - 2+ punches: first punch as IN, last punch as OUT.

    The device only supplies punch times; IN/OUT is derived from the first and
    last punch positions.
    """
    if not items:
        return []

    ordered = sorted(items, key=lambda item: punch_sort_key(prepared_for(item)))
    if len(ordered) == 1:
        return [(ordered[0], "IN", "first_punch_in")]

    candidates = [
        (ordered[0], "IN", "first_punch_in"),
        (ordered[-1], "OUT", "last_punch_out"),
    ]

    selected: list[tuple[T, str | None, str]] = []
    seen_serials: set[str] = set()
    for item, log_type, label in candidates:
        serial_no = str(prepared_for(item)["serial_no"])
        if serial_no in seen_serials:
            continue
        selected.append((item, log_type, label))
        seen_serials.add(serial_no)
    return selected


def select_daily_first_last_events(events: list[dict[str, Any]]) -> dict[str, dict[str, Any] | None]:
    """Return display first/last events using the same ordering as push selection."""
    empty = {
        "first": None,
        "last": None,
    }
    if not events:
        return empty

    ordered = sorted(events, key=punch_sort_key)
    boundaries = dict(empty)
    boundaries["first"] = ordered[0]
    if len(ordered) > 1:
        boundaries["last"] = ordered[-1]
    return boundaries
