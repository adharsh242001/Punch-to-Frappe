import unittest

import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "attendance_sync")
sys.path.insert(0, os.path.abspath(ROOT))

from config import settings
from processors.live_attendance import build_live_attendance


class LiveAttendanceTests(unittest.TestCase):
    def test_builds_stats_and_feed_for_today(self) -> None:
        events = [
            {
                "id": 3,
                "employee": "101",
                "event_time": "2026-05-19T18:00:00+05:30",
                "serial_no": "c",
                "device_ip": "10.10.80.51",
            },
            {
                "id": 2,
                "employee": "101",
                "event_time": "2026-05-19T09:00:00+05:30",
                "serial_no": "b",
            },
            {
                "id": 1,
                "employee": "102",
                "event_time": "2026-05-19T09:05:00+05:30",
                "serial_no": "a",
            },
            {
                "id": 4,
                "employee": "101",
                "event_time": "2026-05-18T09:00:00+05:30",
                "serial_no": "old",
            },
        ]
        employee_map = {"101": "EMP-101", "102": "EMP-102"}
        details_by_id = {
            "EMP-101": {"employee_name": "James Anderson", "department": "Engineering"},
            "EMP-102": {"employee_name": "Sarah Martinez", "department": "Product"},
        }

        settings.DEVICE_NAMES["10.10.80.51"] = "First Floor OUT"

        payload = build_live_attendance(
            events,
            today="2026-05-19",
            employee_map=employee_map,
            details_by_id=details_by_id,
            feed_limit=10,
            display_name=lambda details: str(details.get("employee_name") or ""),
        )

        self.assertEqual(payload["active_count"], 1)
        self.assertEqual(payload["punch_ins_today"], 2)
        self.assertEqual(payload["punch_outs_today"], 1)
        self.assertEqual(len(payload["feed"]), 3)
        self.assertEqual(payload["feed"][0]["employee"], "James Anderson")
        self.assertEqual(payload["feed"][0]["action"], "punch-out")
        self.assertEqual(payload["feed"][0]["device_ip"], "10.10.80.51")
        self.assertEqual(payload["feed"][0]["device_name"], "First Floor OUT")
        self.assertEqual(payload["feed"][1]["employee"], "Sarah Martinez")
        self.assertEqual(payload["feed"][1]["action"], "punch-in")
        self.assertEqual(payload["feed"][2]["employee"], "James Anderson")
        self.assertEqual(payload["feed"][2]["action"], "punch-in")


if __name__ == "__main__":
    unittest.main()
