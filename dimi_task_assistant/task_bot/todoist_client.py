from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx


JsonDict = dict[str, Any]


def parse_due_date(due: JsonDict) -> date | None:
    due_date = due.get("date")
    if not isinstance(due_date, str) or len(due_date) < 10:
        return None
    try:
        return date.fromisoformat(due_date[:10])
    except ValueError:
        return None


def format_duration(duration: int | None, unit: str | None) -> str:
    if not duration or not unit:
        return ""
    if unit == "minute":
        if duration < 60:
            return f"{duration} min"
        hours, minutes = divmod(duration, 60)
        return f"{hours} h {minutes} min" if minutes else f"{hours} h"
    if unit == "day":
        return f"{duration} Tag{'e' if duration != 1 else ''}"
    return f"{duration} {unit}"


def normalize_task(task: JsonDict, today: date | None = None) -> JsonDict:
    today = today or date.today()
    due = task.get("due") or {}
    due_text = due.get("string") or due.get("date") or ""
    due_date = parse_due_date(due)
    is_today = bool(due_date and due_date == today)
    is_overdue = bool(due_date and due_date < today)
    days_overdue = (today - due_date).days if is_overdue and due_date else 0
    duration = task.get("duration") or {}
    return {
        "id": task["id"],
        "content": task["content"],
        "priority": task.get("priority", 1),
        "due": due_text,
        "due_date": due.get("date", "")[:10] if due.get("date") else "",
        "has_due": bool(due_text),
        "is_today": is_today,
        "is_overdue": is_overdue,
        "days_overdue": days_overdue,
        "is_recurring": bool(due.get("is_recurring", False)),
        "duration": duration.get("amount"),
        "duration_unit": duration.get("unit"),
    }


def sort_normalized_tasks(tasks: list[JsonDict]) -> list[JsonDict]:
    return sorted(
        tasks,
        key=lambda task: (
            -int(task["is_overdue"]),
            -int(task["is_today"]),
            -task["priority"],
            0 if task["has_due"] else 1,
            task["due_date"] or "9999-12-31",
            task["content"].lower(),
        ),
    )


def summarize_tasks(
    raw_tasks: list[JsonDict], filter_value: str | None = None, today: date | None = None
) -> JsonDict:
    today = today or date.today()
    normalized = sort_normalized_tasks(
        [normalize_task(task, today=today) for task in raw_tasks[:100]]
    )
    overdue = [task for task in normalized if task["is_overdue"]]
    today_items = [task for task in normalized if task["is_today"]]
    high_priority = [task for task in normalized if task["priority"] == 4]
    undated = [task for task in normalized if not task["has_due"]]
    return {
        "total_count": len(raw_tasks),
        "filter_used": filter_value or "",
        "today": today.isoformat(),
        "counts": {
            "overdue": len(overdue),
            "due_today": len(today_items),
            "priority_4": len(high_priority),
            "undated": len(undated),
        },
        "top_overdue": overdue[:8],
        "top_today": today_items[:8],
        "top_priority": high_priority[:8],
        "top_undated": undated[:5],
        "tasks": normalized,
    }


def match_tasks_by_name(tasks: list[JsonDict], query: str) -> list[JsonDict]:
    q = query.lower().strip()
    if not q:
        return []
    exact = [task for task in tasks if task["content"].lower() == q]
    if exact:
        return exact
    partial = [task for task in tasks if q in task["content"].lower()]
    if partial:
        return partial
    words = [word for word in q.split() if len(word) >= 3]
    if words:
        word_match = [
            task for task in tasks if all(word in task["content"].lower() for word in words)
        ]
        if word_match:
            return word_match
        return [
            task for task in tasks if any(word in task["content"].lower() for word in words)
        ]
    return []


@dataclass
class TodoistClient:
    api_token: str
    api_base: str = "https://api.todoist.com/api/v1"
    client: httpx.Client | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = httpx.Client(timeout=15.0)

    def headers(self) -> dict[str, str]:
        if not self.api_token:
            raise RuntimeError("TODOIST_API_TOKEN fehlt in der Konfiguration")
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def list_tasks(self, filter_value: str | None = None) -> JsonDict:
        endpoint = (
            f"{self.api_base}/tasks/filter" if filter_value else f"{self.api_base}/tasks"
        )
        params = {"query": filter_value} if filter_value else None
        response = self.client.get(endpoint, headers=self.headers(), params=params)
        response.raise_for_status()
        payload = response.json()
        tasks = payload["results"] if isinstance(payload, dict) else payload
        return summarize_tasks(tasks or [], filter_value=filter_value)

    def fetch_all_tasks(self) -> list[JsonDict]:
        tasks: list[JsonDict] = []
        cursor: str | None = None
        for _ in range(10):
            params: dict[str, str] = {}
            if cursor:
                params["cursor"] = cursor
            response = self.client.get(
                f"{self.api_base}/tasks",
                headers=self.headers(),
                params=params or None,
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                tasks.extend(payload.get("results", []))
                cursor = payload.get("next_cursor") or None
            else:
                tasks.extend(payload)
                cursor = None
            if not cursor:
                break
        return tasks

    def create_task(
        self,
        content: str,
        due_string: str | None = None,
        priority: int | None = None,
        duration: int | None = None,
        duration_unit: str | None = None,
    ) -> JsonDict:
        payload: JsonDict = {"content": content}
        if due_string:
            payload["due_string"] = due_string
        if priority:
            payload["priority"] = priority
        if duration and duration_unit:
            payload["duration"] = duration
            payload["duration_unit"] = duration_unit
        response = self.client.post(
            f"{self.api_base}/tasks", headers=self.headers(), json=payload
        )
        response.raise_for_status()
        task = response.json()
        dur = task.get("duration") or {}
        return {
            "status": "created",
            "task": {
                "id": task["id"],
                "content": task["content"],
                "priority": task.get("priority", 1),
                "due": (task.get("due") or {}).get("string", ""),
                "duration": dur.get("amount"),
                "duration_unit": dur.get("unit"),
            },
        }

    def complete_task(self, task_id: str) -> JsonDict:
        response = self.client.post(
            f"{self.api_base}/tasks/{task_id}/close", headers=self.headers()
        )
        response.raise_for_status()
        return {"status": "completed", "task_id": task_id}

    def reschedule_task(self, task_id: str, due_string: str) -> JsonDict:
        response = self.client.post(
            f"{self.api_base}/tasks/{task_id}",
            headers=self.headers(),
            json={"due_string": due_string},
        )
        response.raise_for_status()
        task = response.json()
        return {
            "status": "rescheduled",
            "task_id": task_id,
            "new_due": (task.get("due") or {}).get("string", due_string),
        }

    def reschedule_by_name(self, name_query: str, due_string: str) -> JsonDict:
        tasks = self.fetch_all_tasks()
        matches = match_tasks_by_name(tasks, name_query)
        if not matches:
            return {
                "status": "not_found",
                "query": name_query,
                "total_tasks": len(tasks),
                "hint": "Keine passende Aufgabe gefunden. Bitte nenne ein anderes Stichwort.",
            }
        if len(matches) > 1:
            return {
                "status": "multiple_found",
                "query": name_query,
                "matches": [_task_option(task) for task in matches[:5]],
                "hint": "Mehrere Aufgaben passen. Bitte nenne den genaueren Namen.",
            }
        task = matches[0]
        result = self.reschedule_task(task["id"], due_string)
        result["task_name"] = task["content"]
        return result

    def complete_by_name(self, name_query: str) -> JsonDict:
        tasks = self.fetch_all_tasks()
        matches = match_tasks_by_name(tasks, name_query)
        if not matches:
            return {
                "status": "not_found",
                "query": name_query,
                "total_tasks": len(tasks),
                "hint": "Keine passende Aufgabe gefunden. Bitte nenne ein anderes Stichwort.",
            }
        if len(matches) > 1:
            return {
                "status": "multiple_found",
                "query": name_query,
                "matches": [_task_option(task) for task in matches[:5]],
                "hint": "Mehrere Aufgaben passen. Bitte nenne den genaueren Namen.",
            }
        task = matches[0]
        result = self.complete_task(task["id"])
        result["task_name"] = task["content"]
        return result

    def batch_complete(self, name_queries: list[str]) -> JsonDict:
        tasks = self.fetch_all_tasks()
        results = []
        for query in name_queries:
            matches = match_tasks_by_name(tasks, query)
            if not matches:
                results.append({"query": query, "status": "not_found"})
            elif len(matches) > 1:
                results.append(
                    {
                        "query": query,
                        "status": "multiple_found",
                        "matches": [_task_option(task) for task in matches[:3]],
                    }
                )
            else:
                task = matches[0]
                try:
                    self.complete_task(task["id"])
                    results.append(
                        {"query": query, "status": "completed", "task": task["content"]}
                    )
                except Exception as exc:
                    results.append({"query": query, "status": "error", "error": str(exc)})
        return _batch_result(results, "completed", "completed_count")

    def batch_reschedule(self, name_queries: list[str], due_string: str) -> JsonDict:
        tasks = self.fetch_all_tasks()
        results = []
        for query in name_queries:
            matches = match_tasks_by_name(tasks, query)
            if not matches:
                results.append({"query": query, "status": "not_found"})
            elif len(matches) > 1:
                results.append(
                    {
                        "query": query,
                        "status": "multiple_found",
                        "matches": [_task_option(task) for task in matches[:3]],
                    }
                )
            else:
                task = matches[0]
                try:
                    result = self.reschedule_task(task["id"], due_string)
                    results.append(
                        {
                            "query": query,
                            "status": "rescheduled",
                            "task": task["content"],
                            "new_due": result.get("new_due", due_string),
                        }
                    )
                except Exception as exc:
                    results.append({"query": query, "status": "error", "error": str(exc)})
        payload = _batch_result(results, "rescheduled", "rescheduled_count")
        payload["new_due"] = due_string
        return payload


def _task_option(task: JsonDict) -> JsonDict:
    due = task.get("due") or {}
    return {
        "id": task.get("id", ""),
        "content": task.get("content", ""),
        "due": due.get("string") or due.get("date") or "",
    }


def _batch_result(results: list[JsonDict], success_status: str, success_key: str) -> JsonDict:
    done = [result for result in results if result["status"] == success_status]
    failed = [result for result in results if result["status"] != success_status]
    return {success_key: len(done), "failed_count": len(failed), "results": results}
