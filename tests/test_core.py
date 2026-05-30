from __future__ import annotations

import unittest
from datetime import date

from dimi_task_assistant.task_bot.config import parse_hhmm
from dimi_task_assistant.task_bot.formatters import (
    format_morning_briefing,
    select_focus_task,
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
