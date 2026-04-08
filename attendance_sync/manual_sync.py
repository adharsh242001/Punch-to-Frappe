"""
Manual attendance sync runner.

Use this when you want to fetch and upload attendance events for a specific
date/time range without starting the continuous polling service.

Examples
--------
    python manual_sync.py --from "2026-03-01 00:00:00" --to "2026-03-01 23:59:59"
    python manual_sync.py --from "2026-03-01T00:00:00+05:30" --to "2026-03-02T00:00:00+05:30"
"""
import argparse
import sys
from datetime import datetime

# Ensure the package root is on the path when run directly
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

from main import run_manual_sync


def _parse_datetime(value: str) -> datetime:
    """
    Parse CLI datetime input.

    Accepted formats:
      - 2026-03-01 09:00:00
      - 2026-03-01T09:00:00
      - 2026-03-01T09:00:00+05:30
    """
    normalized = value.strip().replace(" ", "T")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid datetime {value!r}. Use ISO-like format such as "
            "'2026-03-01 09:00:00' or '2026-03-01T09:00:00+05:30'."
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch and upload attendance events for a specific date range."
    )
    parser.add_argument(
        "--from",
        dest="start_time",
        required=True,
        type=_parse_datetime,
        help="Start datetime for event fetch range.",
    )
    parser.add_argument(
        "--to",
        dest="end_time",
        required=True,
        type=_parse_datetime,
        help="End datetime for event fetch range.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_manual_sync(args.start_time, args.end_time)


if __name__ == "__main__":
    main()
