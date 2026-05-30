from __future__ import annotations

from datetime import date
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .todoist_client import JsonDict, format_duration, parse_due_date


PRIORITY_EMOJI = {4: "🔴", 3: "🟠", 2: "🟡", 1: "⚪"}


def priority_emoji(priority: int) -> str:
    return PRIORITY_EMOJI.get(priority, "⚪")


def build_task_keyboard(
    tasks: list[JsonDict], max_items: int = 8
) -> InlineKeyboardMarkup | None:
    if not tasks:
        return None
    buttons = []
    for task in tasks[:max_items]:
        label = str(task["content"])[:22] + ("..." if len(str(task["content"])) > 22 else "")
        buttons.append(
            [
                InlineKeyboardButton(f"✅ {label}", callback_data=f"done:{task['id']}"),
                InlineKeyboardButton("📅 Heute", callback_data=f"snooze0:{task['id']}"),
                InlineKeyboardButton("📅 Morgen", callback_data=f"snooze1:{task['id']}"),
                InlineKeyboardButton("📅 Sonntag", callback_data=f"snooze7:{task['id']}"),
            ]
        )
    return InlineKeyboardMarkup(buttons)


def select_focus_task(tasks: list[JsonDict]) -> JsonDict | None:
    if not tasks:
        return None
    return sorted(
        tasks,
        key=lambda task: (
            -int(task.get("is_overdue", False)),
            -int(task.get("is_today", False)),
            -int(task.get("days_overdue", 0)),
            -int(task.get("priority", 1)),
            0 if task.get("has_due") else 1,
            task.get("due_date") or "9999-12-31",
            str(task.get("content", "")).lower(),
        ),
    )[0]


def format_task_list(
    tasks_data: JsonDict, title: str
) -> tuple[str, InlineKeyboardMarkup | None]:
    tasks = tasks_data.get("tasks", [])
    if not tasks:
        return f"<b>{escape(title)}</b>\n\n🎉 Keine Aufgaben gefunden.", None

    lines = [f"<b>{escape(title)}</b>\n"]
    for task in tasks[:8]:
        due = f" <i>({escape(str(task['due']))})</i>" if task.get("due") else ""
        overdue_marker = (
            f" ⚠️ +{task['days_overdue']}d" if task.get("is_overdue") else ""
        )
        lines.append(
            f"{priority_emoji(task['priority'])} {escape(str(task['content']))}"
            f"{due}{overdue_marker}"
        )

    if len(tasks) > 8:
        lines.append(f"\n<i>...und {len(tasks) - 8} weitere</i>")

    return "\n".join(lines), build_task_keyboard(tasks)


def format_morning_briefing(
    tasks_data: JsonDict,
) -> tuple[str, InlineKeyboardMarkup | None]:
    counts = tasks_data.get("counts", {})
    today_tasks = tasks_data.get("top_today", [])
    overdue_tasks = tasks_data.get("top_overdue", [])
    priority_tasks = tasks_data.get("top_priority", [])
    total = tasks_data.get("total_count", 0)
    n_today = counts.get("due_today", len(today_tasks))
    n_overdue = counts.get("overdue", len(overdue_tasks))

    lines = ["🌅 <b>Guten Morgen!</b>\n"]
    summary_parts = []
    if n_overdue:
        summary_parts.append(f"⚠️ {n_overdue} überfällig")
    if n_today:
        summary_parts.append(f"📋 {n_today} heute fällig")
    if total:
        summary_parts.append(f"📂 {total} offen gesamt")
    if summary_parts:
        lines.append("  ".join(summary_parts))
        lines.append("")

    if overdue_tasks or today_tasks:
        focus = select_focus_task(overdue_tasks + today_tasks)
        if focus:
            lines.append("🎯 <b>Jetzt wichtig</b>")
            lines.append(_brief_task_line(focus, include_due=True))
            lines.append("")

    if overdue_tasks:
        lines.append(f"⚠️ <b>Überfällig</b> ({n_overdue}):")
        for task in overdue_tasks[:8]:
            days = task.get("days_overdue", 0)
            flag = "🔴" if days >= 3 else "🟡"
            lines.append(f"  {flag} {_task_text(task)} <i>(seit {days}d)</i>{_duration(task)}")
        if n_overdue > 8:
            lines.append(f"  <i>...und {n_overdue - 8} weitere</i>")
        lines.append("")

    if today_tasks:
        lines.append(f"📋 <b>Heute fällig</b> ({n_today}):")
        for task in today_tasks[:8]:
            lines.append(f"  {_brief_task_line(task)}")
        lines.append("")

    extra_prio = [
        task
        for task in priority_tasks
        if task["priority"] >= 3 and not task["is_today"] and not task["is_overdue"]
    ][:4]
    if extra_prio:
        lines.append("🔺 <b>Hohe Priorität (nicht fällig)</b>:")
        for task in extra_prio:
            due = f" <i>({escape(str(task['due']))})</i>" if task.get("due") else ""
            lines.append(f"  {priority_emoji(task['priority'])} {_task_text(task)}{due}")
        lines.append("")

    if not today_tasks and not overdue_tasks:
        lines.append("🎉 Heute ist nichts fällig.")

    action_tasks = overdue_tasks[:6] + today_tasks[:4]
    return "\n".join(lines).strip(), build_task_keyboard(action_tasks)


def format_evening_review(
    tasks_data: JsonDict,
) -> tuple[str, InlineKeyboardMarkup | None]:
    counts = tasks_data.get("counts", {})
    today_tasks = tasks_data.get("top_today", [])
    overdue_tasks = tasks_data.get("top_overdue", [])
    n_today = counts.get("due_today", len(today_tasks))
    n_overdue = counts.get("overdue", len(overdue_tasks))

    lines = ["🌙 <b>Tagesabschluss</b>\n"]
    if today_tasks:
        lines.append(f"📋 <b>Heute noch offen</b> ({n_today}):")
        for task in today_tasks[:8]:
            lines.append(f"  {_brief_task_line(task)}")
        lines.append("")

    if overdue_tasks:
        lines.append(f"⚠️ <b>Überfällig</b> ({n_overdue}):")
        for task in overdue_tasks[:6]:
            days = task.get("days_overdue", 0)
            lines.append(f"  🔴 {_task_text(task)} <i>(seit {days}d)</i>{_duration(task)}")
        lines.append("")

    total_open = len(today_tasks) + len(overdue_tasks)
    if total_open == 0:
        lines.append("✅ Alles erledigt für heute.")
    else:
        focus = select_focus_task(overdue_tasks + today_tasks)
        if focus:
            lines.append(f"🎯 <b>Wenn nur noch eins:</b> {_task_text(focus)}")
        lines.append("📌 Nutze die Buttons zum Erledigen oder Verschieben.")

    action_tasks = overdue_tasks[:6] + today_tasks[:4]
    return "\n".join(lines).strip(), build_task_keyboard(action_tasks)


def format_focus(tasks_data: JsonDict) -> tuple[str, InlineKeyboardMarkup | None]:
    tasks = tasks_data.get("tasks", [])
    focus = select_focus_task(tasks)
    if not focus:
        return "🎉 Keine offenen Aufgaben! Alles erledigt.", None
    due = f"\nFällig: <i>{escape(str(focus['due']))}</i>" if focus.get("due") else ""
    overdue = (
        f"\n⚠️ Seit {focus['days_overdue']} Tag(en) überfällig!"
        if focus.get("is_overdue")
        else ""
    )
    duration = _duration(focus)
    text = (
        f"🎯 <b>Jetzt wichtig:</b>\n\n"
        f"{priority_emoji(focus['priority'])} <b>{_task_text(focus)}</b>"
        f"{due}{overdue}{duration}"
    )
    return text, build_task_keyboard([focus], max_items=1)


def format_all_task_chunks(raw_tasks: list[JsonDict]) -> list[str]:
    if not raw_tasks:
        return ["🎉 Keine offenen Aufgaben!"]
    today = date.today()
    tasks_sorted = sorted(raw_tasks, key=lambda task: _raw_sort_key(task, today))
    overdue = [
        task for task in tasks_sorted if (due := parse_due_date(task.get("due") or {})) and due < today
    ]
    due_today = [
        task for task in tasks_sorted if (due := parse_due_date(task.get("due") or {})) and due == today
    ]
    upcoming = [
        task for task in tasks_sorted if (due := parse_due_date(task.get("due") or {})) and due > today
    ]
    undated = [task for task in tasks_sorted if not (task.get("due") or {}).get("date")]

    header = f"📋 <b>Alle Aufgaben ({len(raw_tasks)})</b>\n"
    parts = [header]
    for title, group in [
        ("⚠️ Überfällig", overdue),
        ("📅 Heute", due_today),
        ("🔜 Demnächst", upcoming),
        ("📌 Ohne Datum", undated),
    ]:
        rendered = _render_raw_group(title, group, today)
        if rendered:
            parts.append(rendered)

    full_text = "\n\n".join(parts)
    if len(full_text) <= 4096:
        return [full_text]

    chunks = [header + "\n(wird in mehreren Teilen gesendet...)"]
    current = ""
    for part in parts[1:]:
        if len(current) + len(part) + 2 > 3800:
            if current:
                chunks.append(current.strip())
            current = part + "\n\n"
        else:
            current += part + "\n\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _task_text(task: JsonDict) -> str:
    return escape(str(task.get("content", "")))


def _duration(task: JsonDict) -> str:
    duration = format_duration(task.get("duration"), task.get("duration_unit"))
    return f" <i>({escape(duration)})</i>" if duration else ""


def _brief_task_line(task: JsonDict, include_due: bool = False) -> str:
    due = f" <i>({escape(str(task['due']))})</i>" if include_due and task.get("due") else ""
    return f"{priority_emoji(task['priority'])} {_task_text(task)}{due}{_duration(task)}"


def _raw_sort_key(task: JsonDict, today: date) -> tuple[int, int, str]:
    due = task.get("due") or {}
    due_date = parse_due_date(due)
    priority = task.get("priority", 1)
    if due_date and due_date < today:
        return (0, -priority, str(due_date))
    if due_date and due_date == today:
        return (1, -priority, str(due_date))
    if due_date:
        return (2, -priority, str(due_date))
    return (3, -priority, "9999")


def _render_raw_group(title: str, group: list[JsonDict], today: date) -> str | None:
    if not group:
        return None
    lines = [f"<b>{escape(title)}</b>"]
    for task in group:
        due = task.get("due") or {}
        due_text = due.get("string") or due.get("date") or ""
        due_part = f" <i>({escape(str(due_text))})</i>" if due_text else ""
        due_date = parse_due_date(due)
        overdue_days = (today - due_date).days if due_date and due_date < today else 0
        overdue_part = f" ⚠️+{overdue_days}d" if overdue_days else ""
        lines.append(
            f"{priority_emoji(task.get('priority', 1))} "
            f"{escape(str(task['content']))}{due_part}{overdue_part}"
        )
    return "\n".join(lines)
