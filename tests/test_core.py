from __future__ import annotations

import unittest
from datetime import date, datetime, time
from tempfile import TemporaryDirectory

from dimi_task_assistant.task_bot.config import parse_hhmm
from dimi_task_assistant.task_bot.formatters import (
    format_morning_briefing,
    select_focus_task,
)
from dimi_task_assistant.task_bot.google_calendar import _free_slots_from_busy
from dimi_task_assistant.task_bot.planning import (
    PlannerStateStore,
    PlanningEngine,
    build_commitment_message,
)
from dimi_task_assistant.task_bot.telegram_handlers import sanitize_html
from dimi_task_assistant.task_bot.todoist_client import (
    format_duration,
    match_tasks_by_name,
    normalize_task,
    summarize_tasks,
)
from zoneinfo import ZoneInfo


class TodoistCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today = date(2026, 5, 30)
        self.raw_tasks = [
            {
                "id": "1",
                "content": "Steuer vorbereiten",
                "priority": 4,
                "due": {"date": "2026-05-28", "string": "28. Mai"},
                "duration": {"amount": 90, "unit": "minute"},
            },
            {
                "id": "2",
                "content": "Einkauf",
                "priority": 2,
                "due": {"date": "2026-05-30", "string": "heute"},
            },
            {
                "id": "3",
                "content": "Idee notieren",
                "priority": 1,
            },
        ]

    def test_normalize_task_marks_overdue_and_duration(self) -> None:
        task = normalize_task(self.raw_tasks[0], today=self.today)
        self.assertTrue(task["is_overdue"])
        self.assertEqual(task["days_overdue"], 2)
        self.assertEqual(task["duration"], 90)

    def test_summarize_tasks_sorts_actionable_items_first(self) -> None:
        summary = summarize_tasks(self.raw_tasks, filter_value="today | overdue", today=self.today)
        self.assertEqual(summary["counts"]["overdue"], 1)
        self.assertEqual(summary["counts"]["due_today"], 1)
        self.assertEqual([task["id"] for task in summary["tasks"]], ["1", "2", "3"])

    def test_match_tasks_by_name_modes(self) -> None:
        self.assertEqual(match_tasks_by_name(self.raw_tasks, "Steuer vorbereiten")[0]["id"], "1")
        self.assertEqual(match_tasks_by_name(self.raw_tasks, "kauf")[0]["id"], "2")
        self.assertEqual(match_tasks_by_name(self.raw_tasks, "idee später")[0]["id"], "3")
        self.assertEqual(match_tasks_by_name(self.raw_tasks, "nicht vorhanden"), [])

    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(30, "minute"), "30 min")
        self.assertEqual(format_duration(90, "minute"), "1 h 30 min")
        self.assertEqual(format_duration(1, "day"), "1 Tag")


class FormatterTests(unittest.TestCase):
    def test_morning_briefing_contains_focus_and_escaped_task(self) -> None:
        summary = summarize_tasks(
            [
                {
                    "id": "1",
                    "content": "A & B klären",
                    "priority": 4,
                    "due": {"date": "2026-05-29", "string": "gestern"},
                },
                {
                    "id": "2",
                    "content": "Heute anrufen",
                    "priority": 2,
                    "due": {"date": "2026-05-30", "string": "heute"},
                },
            ],
            today=date(2026, 5, 30),
        )
        text, keyboard = format_morning_briefing(summary)
        self.assertIn("Jetzt wichtig", text)
        self.assertIn("A &amp; B klären", text)
        self.assertIsNotNone(keyboard)

    def test_select_focus_prioritizes_overdue_before_today(self) -> None:
        summary = summarize_tasks(
            [
                {
                    "id": "today",
                    "content": "Heute hoch",
                    "priority": 4,
                    "due": {"date": "2026-05-30"},
                },
                {
                    "id": "overdue",
                    "content": "Alt niedrig",
                    "priority": 1,
                    "due": {"date": "2026-05-28"},
                },
            ],
            today=date(2026, 5, 30),
        )
        self.assertEqual(select_focus_task(summary["tasks"])["id"], "overdue")


class PlanningTests(unittest.TestCase):
    def test_commitment_message_limits_to_three_undecided_tasks(self) -> None:
        today = date(2026, 5, 30)
        raw_tasks = [
            {
                "id": str(index),
                "content": f"Task {index}",
                "priority": 4 if index == 1 else 1,
                "due": {"date": today.isoformat(), "string": "heute"},
            }
            for index in range(1, 6)
        ]
        with TemporaryDirectory() as tmpdir:
            state = PlannerStateStore(f"{tmpdir}/state.json")
            planner = PlanningEngine(state=state)
            summary = summarize_tasks(raw_tasks, today=today)
            text, keyboard = build_commitment_message(summary, planner)

        self.assertIn("Heute wirklich", text)
        self.assertEqual(text.count("Task "), 3)
        self.assertIsNotNone(keyboard)

    def test_planner_state_hides_decided_tasks_for_today(self) -> None:
        today = date.today()
        raw_tasks = [
            {
                "id": "1",
                "content": "Schon entschieden",
                "priority": 4,
                "due": {"date": today.isoformat(), "string": "heute"},
            },
            {
                "id": "2",
                "content": "Noch offen",
                "priority": 1,
                "due": {"date": today.isoformat(), "string": "heute"},
            },
        ]
        with TemporaryDirectory() as tmpdir:
            state = PlannerStateStore(f"{tmpdir}/state.json")
            state.mark_decision("1", "tomorrow")
            planner = PlanningEngine(state=state)
            summary = summarize_tasks(raw_tasks, today=today)
            commitments = planner.commitment_tasks(summary)

        self.assertEqual([task["id"] for task in commitments], ["2"])

    def test_free_slots_skip_busy_ranges(self) -> None:
        tz = ZoneInfo("Europe/Berlin")
        slots = _free_slots_from_busy(
            busy=[
                {
                    "start": "2026-05-30T09:00:00+02:00",
                    "end": "2026-05-30T10:00:00+02:00",
                }
            ],
            start=datetime(2026, 5, 30, 8, 0, tzinfo=tz),
            duration_minutes=30,
            timezone=tz,
            workday_start=time(9, 0, tzinfo=tz),
            workday_end=time(18, 0, tzinfo=tz),
            days=1,
        )

        self.assertEqual(slots[0].due_string, "2026-05-30 at 10:00")


class UtilityTests(unittest.TestCase):
    def test_sanitize_html_keeps_supported_tags_and_replaces_breaks(self) -> None:
        self.assertEqual(
            sanitize_html("<b>Hi</b><br><div>Weg</div>"),
            "<b>Hi</b>\nWeg",
        )

    def test_sanitize_html_converts_visible_newline_escape(self) -> None:
        self.assertEqual(sanitize_html("Hi!\\nWie kann ich helfen?"), "Hi!\nWie kann ich helfen?")

    def test_parse_hhmm(self) -> None:
        parsed = parse_hhmm("07:30", ZoneInfo("Europe/Berlin"))
        self.assertEqual(parsed.hour, 7)
        self.assertEqual(parsed.minute, 30)
        self.assertEqual(parsed.tzinfo.key, "Europe/Berlin")


if __name__ == "__main__":
    unittest.main()
