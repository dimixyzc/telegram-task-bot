from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html import escape
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .todoist_client import JsonDict, format_duration


StateDict = dict[str, Any]


@dataclass(frozen=True)
class SlotSuggestion:
    key: str
    label: str
    due_string: str


@dataclass(frozen=True)
class DayOption:
    key: str
    label: str
    due_string: str


class PlannerStateStore:
    def __init__(self, path: str) -> None:
        self.path = path

    def load(self) -> StateDict:
        try:
            with open(self.path) as file:
                payload = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"tasks": {}, "days": {}}
        if not isinstance(payload, dict):
            return {"tasks": {}, "days": {}}
        payload.setdefault("tasks", {})
        payload.setdefault("days", {})
        return payload

    def save(self, state: StateDict) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp_path = f"{self.path}.tmp"
        with open(tmp_path, "w") as file:
            json.dump(state, file, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, self.path)

    def mark_decision(self, task_id: str, action: str, task_label: str = "") -> None:
        state = self.load()
        state["tasks"][task_id] = {
            "action": action,
            "label": task_label,
            "date": date.today().isoformat(),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.save(state)

    def decision_for_today(self, task_id: str, today: date | None = None) -> StateDict | None:
        today = today or date.today()
        decision = self.load().get("tasks", {}).get(task_id)
        if isinstance(decision, dict) and decision.get("date") == today.isoformat():
            return decision
        return None

    def undecided_task_ids(self, tasks: list[JsonDict], today: date | None = None) -> list[str]:
        return [
            str(task["id"])
            for task in tasks
            if not self.decision_for_today(str(task["id"]), today=today)
        ]


class PlanningEngine:
    def __init__(self, state: PlannerStateStore, default_task_duration: int = 30) -> None:
        self.state = state
        self.default_task_duration = default_task_duration

    def commitment_tasks(self, tasks_data: JsonDict, limit: int = 3) -> list[JsonDict]:
        tasks = tasks_data.get("tasks", [])
        undecided = [
            task
            for task in tasks
            if task.get("is_overdue") or task.get("is_today")
            if not self.state.decision_for_today(str(task["id"]))
        ]
        return sorted(undecided, key=_planning_sort_key)[:limit]

    def action_tasks(self, tasks_data: JsonDict, limit: int = 8) -> list[JsonDict]:
        tasks = tasks_data.get("tasks", [])
        actionable = [
            task
            for task in tasks
            if task.get("is_overdue") or task.get("is_today")
            if not self.state.decision_for_today(str(task["id"]))
        ]
        return sorted(actionable, key=_planning_sort_key)[:limit]

    def needs_nudge(self, tasks_data: JsonDict) -> bool:
        return bool(self.action_tasks(tasks_data, limit=1))

    def default_duration(self, task: JsonDict) -> int:
        duration = task.get("duration")
        if isinstance(duration, int) and duration >= 5:
            return duration
        return self.default_task_duration


def build_commitment_message(
    tasks_data: JsonDict, planner: PlanningEngine
) -> tuple[str, InlineKeyboardMarkup | None]:
    counts = tasks_data.get("counts", {})
    n_today = counts.get("due_today", 0)
    n_overdue = counts.get("overdue", 0)
    total = tasks_data.get("total_count", 0)
    commitments = planner.commitment_tasks(tasks_data)
    action_tasks = planner.action_tasks(tasks_data)

    lines = ["🌅 <b>Guten Morgen!</b>\n"]
    summary = []
    if n_overdue:
        summary.append(f"⚠️ {n_overdue} überfällig")
    if n_today:
        summary.append(f"📋 {n_today} heute fällig")
    if total:
        summary.append(f"📂 {total} offen gesamt")
    if summary:
        lines.append("  ".join(summary))
        lines.append("")

    if commitments:
        lines.append("🎯 <b>Heute wirklich</b>")
        for task in commitments:
            lines.append(f"  {_task_line(task)}")
        lines.append("")
        lines.append("📌 Entscheide jede offene Aufgabe kurz: erledigen oder auf einen passenden Tag legen.")
    else:
        lines.append("✅ Alles für heute ist entschieden.")

    return "\n".join(lines).strip(), build_planning_keyboard(action_tasks)


def build_evening_review_message(
    tasks_data: JsonDict, planner: PlanningEngine
) -> tuple[str, InlineKeyboardMarkup | None]:
    action_tasks = planner.action_tasks(tasks_data)
    lines = ["🌙 <b>Tagesabschluss</b>\n"]
    if not action_tasks:
        lines.append("✅ Keine offenen Tagesentscheidungen.")
        return "\n".join(lines).strip(), None

    lines.append(f"📌 <b>Noch zu entscheiden</b> ({len(action_tasks)}):")
    for task in action_tasks[:6]:
        lines.append(f"  {_task_line(task)}")
    lines.append("")
    lines.append("Nimm dir 30 Sekunden: erledigt, morgen oder einen passenden Tag wählen.")
    return "\n".join(lines).strip(), build_planning_keyboard(action_tasks[:6])


def build_nudge_message(
    tasks_data: JsonDict, planner: PlanningEngine
) -> tuple[str, InlineKeyboardMarkup | None]:
    action_tasks = planner.action_tasks(tasks_data, limit=5)
    if not action_tasks:
        return "✅ Deine heutigen Aufgaben sind entschieden.", None
    focus = action_tasks[0]
    lines = [
        "⏱️ <b>Plan noch offen</b>",
        "",
        f"Wenn nur eine Entscheidung: {_task_line(focus)}",
    ]
    if len(action_tasks) > 1:
        lines.append(f"<i>Plus {len(action_tasks) - 1} weitere offene Entscheidung(en).</i>")
    return "\n".join(lines), build_planning_keyboard(action_tasks)


def build_planning_keyboard(tasks: list[JsonDict], max_items: int = 6) -> InlineKeyboardMarkup | None:
    if not tasks:
        return None
    rows = []
    for task in tasks[:max_items]:
        task_id = str(task["id"])
        label = _short_label(str(task["content"]), 18)
        rows.append(
            [
                InlineKeyboardButton(f"✅ {label}", callback_data=f"done:{task_id}"),
                InlineKeyboardButton("📅 Morgen", callback_data=f"snooze1:{task_id}"),
                InlineKeyboardButton("📅 Tag", callback_data=f"date:{task_id}"),
            ]
        )
        if task.get("is_overdue") and int(task.get("days_overdue", 0)) >= 2:
            rows.append(
                [
                    InlineKeyboardButton("🅿️ Parken", callback_data=f"park:{task_id}"),
                    InlineKeyboardButton("📅 Sonntag", callback_data=f"snooze7:{task_id}"),
                ]
            )
    return InlineKeyboardMarkup(rows)


def build_date_keyboard(task: JsonDict, options: list[DayOption]) -> InlineKeyboardMarkup:
    task_id = str(task["id"])
    rows = [
        [
            InlineKeyboardButton(
                f"📅 {option.label}",
                callback_data=f"day:{task_id}:{option.key}",
            )
        ]
        for option in options
    ]
    rows.append(
        [
            InlineKeyboardButton("🅿️ Parken", callback_data=f"park:{task_id}"),
            InlineKeyboardButton("↩️ Zurück", callback_data=f"back:{task_id}"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def build_date_prompt(task: JsonDict) -> str:
    return "\n".join(
        [
            "📅 <b>Auf welchen Tag?</b>",
            "",
            _task_line(task),
        ]
    )


def build_single_task_prompt(task: JsonDict) -> tuple[str, InlineKeyboardMarkup | None]:
    return (
        "\n".join(["📌 <b>Aufgabe entscheiden</b>", "", _task_line(task)]),
        build_planning_keyboard([task], max_items=1),
    )


def day_options(today: date | None = None) -> list[DayOption]:
    today = today or date.today()
    options = [
        DayOption("today", "Heute", "today"),
        DayOption("tomorrow", "Morgen", "tomorrow"),
        DayOption("overmorrow", "Übermorgen", (today + timedelta(days=2)).isoformat()),
    ]
    for offset in range(3, 8):
        target = today + timedelta(days=offset)
        options.append(DayOption(target.isoformat(), _day_label(target), target.isoformat()))
    options.append(DayOption("next_week", "Nächste Woche", "next week"))
    return options


def day_option_by_key(options: list[DayOption], key: str) -> DayOption | None:
    for option in options:
        if option.key == key:
            return option
    return None


def _planning_sort_key(task: JsonDict) -> tuple[int, int, int, str, str]:
    return (
        0 if task.get("is_overdue") else 1,
        -int(task.get("days_overdue", 0)),
        -int(task.get("priority", 1)),
        str(task.get("due_date") or "9999-12-31"),
        str(task.get("content", "")).lower(),
    )


def _task_line(task: JsonDict) -> str:
    due = f" <i>({escape(str(task['due']))})</i>" if task.get("due") else ""
    overdue = ""
    if task.get("is_overdue"):
        overdue = f" <i>seit {int(task.get('days_overdue', 0))}d</i>"
    duration = format_duration(task.get("duration"), task.get("duration_unit"))
    duration_part = f" <i>({escape(duration)})</i>" if duration else ""
    return f"{_priority_marker(task)} {escape(str(task.get('content', '')))}{due}{overdue}{duration_part}"


def _priority_marker(task: JsonDict) -> str:
    priority = int(task.get("priority", 1))
    if priority >= 4:
        return "🔴"
    if priority == 3:
        return "🟠"
    if priority == 2:
        return "🟡"
    return "⚪"


def _short_label(value: str, limit: int) -> str:
    return value[:limit] + ("..." if len(value) > limit else "")


def _day_label(value: date) -> str:
    weekdays = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    return f"{weekdays[value.weekday()]} {value:%d.%m.}"
