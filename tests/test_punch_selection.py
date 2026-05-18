import unittest

from attendance_sync.processors.punch_selection import (
    select_daily_first_last_events,
    select_daily_punches,
)


class PunchSelectionTests(unittest.TestCase):
    def test_four_punches_only_select_first_in_and_last_out(self) -> None:
        punches = [
            {"serial_no": "mid-a", "event_dt": "2026-05-18T09:30:00+05:30"},
            {"serial_no": "last", "event_dt": "2026-05-18T18:05:00+05:30"},
            {"serial_no": "first", "event_dt": "2026-05-18T08:55:00+05:30"},
            {"serial_no": "mid-b", "event_dt": "2026-05-18T14:10:00+05:30"},
        ]

        selected = select_daily_punches(punches, lambda item: item)

        self.assertEqual(
            selected,
            [
                (punches[2], "IN", "first_punch_in"),
                (punches[1], "OUT", "last_punch_out"),
            ],
        )

    def test_one_punch_is_only_in(self) -> None:
        punches = [{"serial_no": "only", "event_dt": "2026-05-18T09:30:00+05:30"}]

        selected = select_daily_punches(punches, lambda item: item)

        self.assertEqual(selected, [(punches[0], "IN", "first_punch_in")])

    def test_overview_uses_same_first_last_ordering(self) -> None:
        events = [
            {"serial_no": "2", "time": "2026-05-18T10:00:00+05:30"},
            {"serial_no": "1", "time": "2026-05-18T09:00:00+05:30"},
            {"serial_no": "3", "time": "2026-05-18T18:00:00+05:30"},
        ]

        selected = select_daily_first_last_events(events)

        self.assertEqual(selected["first"], events[1])
        self.assertEqual(selected["last"], events[2])


if __name__ == "__main__":
    unittest.main()
