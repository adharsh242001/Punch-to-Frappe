"""Rules for choosing which daily punches are pushed to Frappe."""
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


def select_daily_punches(
    items: list[T],
    prepared_for: Callable[[T], dict[str, Any]],
) -> list[tuple[T, str | None, str]]:
    """
    Select the daily punches to push and assign derived Frappe log types.

    Rules:
    - 1 punch: first punch as IN.
    - 2 or 3 punches: first punch as IN, last punch as OUT.
    - 4+ punches: first as IN, second without log type, second-last without
      log type, and last as OUT.

    The device only supplies punch times; only the outer boundary punches get
    derived IN/OUT direction.
    """
    if not items:
        return []

    ordered = sorted(items, key=lambda item: prepared_for(item)["event_dt"])
    if len(ordered) == 1:
        return [(ordered[0], "IN", "first_punch_in")]

    if len(ordered) >= 4:
        candidates = [
            (ordered[0], "IN", "first_punch_in"),
            (ordered[1], None, "second_punch"),
            (ordered[-2], None, "second_last_punch"),
            (ordered[-1], "OUT", "last_punch_out"),
        ]
    else:
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
