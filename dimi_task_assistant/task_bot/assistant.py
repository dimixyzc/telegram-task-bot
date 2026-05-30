from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from .todoist_client import TodoistClient


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "list_tasks",
        "description": "Listet offene Todoist-Aufgaben auf.",
        "parameters": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": (
                        "Optionaler Todoist-Filter, z.B. 'today', 'overdue', 'p1', "
                        "'next 7 days', 'today | overdue'."
                    ),
                }
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "create_task",
        "description": "Erstellt eine neue Todoist-Aufgabe.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Aufgabenname."},
                "due_string": {
                    "type": "string",
                    "description": "Natuerliche Faelligkeit, z.B. 'morgen 14 Uhr'.",
                },
                "priority": {
                    "type": "integer",
                    "description": "Todoist-Prioritaet: 4=hoch, 3=mittel, 2=niedrig, 1=keine.",
                    "enum": [1, 2, 3, 4],
                },
                "duration": {
                    "type": "integer",
                    "description": "Optionale Dauer, z.B. 30 oder 90.",
                },
                "duration_unit": {
                    "type": "string",
                    "description": "Einheit fuer duration: 'minute' oder 'day'.",
                    "enum": ["minute", "day"],
                },
            },
            "required": ["content"],
        },
    },
    {
        "type": "function",
        "name": "complete_task",
        "description": "Markiert eine Todoist-Aufgabe als erledigt.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Die Todoist-Task-ID."}
            },
            "required": ["task_id"],
        },
    },
    {
        "type": "function",
        "name": "reschedule_task",
        "description": "Verschiebt das Faelligkeitsdatum einer Todoist-Aufgabe.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Die Todoist-Task-ID."},
                "due_string": {
                    "type": "string",
                    "description": "Neues Faelligkeitsdatum, z.B. 'morgen' oder 'naechsten Montag 9:00'.",
                },
            },
            "required": ["task_id", "due_string"],
        },
    },
    {
        "type": "function",
        "name": "reschedule_by_name",
        "description": "Sucht eine Aufgabe per Name/Stichwort und verschiebt sie.",
        "parameters": {
            "type": "object",
            "properties": {
                "name_query": {"type": "string", "description": "Stichwort aus dem Aufgabennamen."},
                "due_string": {"type": "string", "description": "Neues Faelligkeitsdatum."},
            },
            "required": ["name_query", "due_string"],
        },
    },
    {
        "type": "function",
        "name": "complete_by_name",
        "description": "Sucht eine Aufgabe per Name/Stichwort und markiert sie als erledigt.",
        "parameters": {
            "type": "object",
            "properties": {
                "name_query": {"type": "string", "description": "Stichwort aus dem Aufgabennamen."}
            },
            "required": ["name_query"],
        },
    },
    {
        "type": "function",
        "name": "batch_complete",
        "description": "Erledigt mehrere Aufgaben gleichzeitig per Namenssuche.",
        "parameters": {
            "type": "object",
            "properties": {
                "name_queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Liste von Aufgaben-Stichworten.",
                }
            },
            "required": ["name_queries"],
        },
    },
    {
        "type": "function",
        "name": "batch_reschedule",
        "description": "Verschiebt mehrere Aufgaben gleichzeitig auf dasselbe Datum.",
        "parameters": {
            "type": "object",
            "properties": {
                "name_queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Liste von Aufgaben-Stichworten.",
                },
                "due_string": {"type": "string", "description": "Zieldatum."},
            },
            "required": ["name_queries", "due_string"],
        },
    },
]


SYSTEM_PROMPT = (
    "Du bist ein deutschsprachiger Task-Assistent in Telegram. "
    "Hilf beim Planen, Priorisieren und Formulieren von Aufgaben. "
    "Antworte knapp, konkret und handlungsorientiert. "
    "Nutze Todoist-Tools, wenn der Nutzer Aufgaben sehen, anlegen, erledigen oder verschieben will. "
    "Zeige keine langen Rohlisten mit IDs. "
    "Bei 'Was steht an?' nenne zuerst 'Jetzt wichtig', dann optional 'Danach' und 'Auffaellig'. "
    "Bei 'Was ist heute wichtig?' zeige nur heutige oder akut ueberfaellige Punkte. "
    "Bei 'Welche sind am wichtigsten?' zeige die Top 3 bis 5 mit kurzem Grund. "
    "Wenn der Nutzer eine Aufgabe beim Namen nennt und verschieben will, nutze reschedule_by_name. "
    "Wenn der Nutzer eine Aufgabe beim Namen nennt und abhaken will, nutze complete_by_name. "
    "reschedule_task und complete_task nur nutzen, wenn du eine task_id aus list_tasks hast. "
    "Falls mehrere Aufgaben passen, frage kurz nach dem genaueren Namen und liste kurze Optionen. "
    "Bestatige kurz, was du gemacht hast. "
    "Formatiere Antworten ausschliesslich mit Telegram-HTML: <b>, <i>, <code>. "
    "Nutze echte Zeilenumbrueche im Text, niemals sichtbare Zeichenfolgen wie \\n "
    "und niemals <br>. Kein Markdown, keine Sternchen."
)


class TaskAssistant:
    def __init__(
        self,
        model: str,
        todoist: TodoistClient,
        openai_client: OpenAI | None = None,
        max_history_pairs: int = 10,
    ) -> None:
        self.model = model
        self.todoist = todoist
        self.client = openai_client or OpenAI()
        self.max_history_pairs = max_history_pairs
        self._history: list[dict[str, Any]] = []

    def clear_history(self) -> None:
        self._history = []

    def execute_tool(self, name: str, arguments: str) -> str:
        parsed = json.loads(arguments or "{}")
        if name == "list_tasks":
            payload = self.todoist.list_tasks(parsed.get("filter"))
        elif name == "create_task":
            payload = self.todoist.create_task(
                content=parsed["content"],
                due_string=parsed.get("due_string"),
                priority=parsed.get("priority"),
                duration=parsed.get("duration"),
                duration_unit=parsed.get("duration_unit"),
            )
        elif name == "complete_task":
            payload = self.todoist.complete_task(parsed["task_id"])
        elif name == "reschedule_task":
            payload = self.todoist.reschedule_task(parsed["task_id"], parsed["due_string"])
        elif name == "reschedule_by_name":
            payload = self.todoist.reschedule_by_name(
                parsed["name_query"], parsed["due_string"]
            )
        elif name == "complete_by_name":
            payload = self.todoist.complete_by_name(parsed["name_query"])
        elif name == "batch_complete":
            payload = self.todoist.batch_complete(parsed["name_queries"])
        elif name == "batch_reschedule":
            payload = self.todoist.batch_reschedule(
                parsed["name_queries"], parsed["due_string"]
            )
        else:
            raise ValueError(f"Unbekanntes Tool: {name}")
        return json.dumps(payload, ensure_ascii=False)

    def get_reply_text(self, user_text: str) -> str:
        response = self.client.responses.create(
            model=self.model,
            instructions=SYSTEM_PROMPT,
            input=self._history_as_input(user_text),
            tools=TOOLS,
        )
        for _ in range(8):
            function_calls = [
                item
                for item in getattr(response, "output", [])
                if getattr(item, "type", "") == "function_call"
            ]
            if not function_calls:
                reply = _extract_output_text(response)
                self._append_to_history(user_text, reply)
                return reply

            tool_outputs: list[dict[str, str]] = []
            for call in function_calls:
                try:
                    output = self.execute_tool(call.name, call.arguments)
                except Exception as exc:
                    output = f"Fehler beim Tool-Aufruf: {exc}"
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": output,
                    }
                )

            response = self.client.responses.create(
                model=self.model,
                instructions=SYSTEM_PROMPT,
                input=list(response.output) + tool_outputs,
                tools=TOOLS,
            )

        reply = "Ich haenge gerade in einer Schleife. Schreib bitte nochmal kuerzer."
        self._append_to_history(user_text, reply)
        return reply

    def _history_as_input(self, user_text: str) -> list[dict[str, Any]]:
        messages = list(self._history)
        messages.append(
            {"role": "user", "content": [{"type": "input_text", "text": user_text}]}
        )
        return messages

    def _append_to_history(self, user_text: str, assistant_text: str) -> None:
        self._history.append(
            {"role": "user", "content": [{"type": "input_text", "text": user_text}]}
        )
        self._history.append(
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": assistant_text}],
            }
        )
        max_entries = self.max_history_pairs * 2
        if len(self._history) > max_entries:
            self._history = self._history[-max_entries:]


def _extract_output_text(response: Any) -> str:
    if getattr(response, "output_text", ""):
        return response.output_text
    text_parts: list[str] = []
    for item in getattr(response, "output", []):
        for content in getattr(item, "content", []):
            text = getattr(content, "text", "")
            if text:
                text_parts.append(text)
    return "\n".join(text_parts).strip() or "Ich konnte gerade keine Antwort erzeugen."
