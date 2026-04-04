import os
import json
from collections.abc import Sequence

from dotenv import load_dotenv
import httpx
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters


load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
TODOIST_API_TOKEN = os.getenv("TODOIST_API_TOKEN")
TODOIST_API_BASE = "https://api.todoist.com/api/v1"
SYSTEM_PROMPT = (
    "Du bist ein deutschsprachiger Task-Assistent in Telegram. "
    "Hilf beim Planen, Priorisieren und Formulieren von Aufgaben. "
    "Antworte knapp, konkret und handlungsorientiert. "
    "Wenn der Nutzer unklare Aufgaben schreibt, formuliere sie in klare naechste Schritte um. "
    "Nutze Todoist-Tools, wenn der Nutzer Aufgaben sehen, anlegen oder erledigen will. "
    "Wenn echte Todoist-Synchronisation noch nicht verfuegbar ist, sage das klar in einem Satz."
)


if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN fehlt in der .env Datei")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY fehlt in der .env Datei")


client = OpenAI(api_key=OPENAI_API_KEY)
previous_response_ids: dict[int, str] = {}
http_client = httpx.Client(timeout=15.0)
TOOLS: list[dict[str, object]] = [
    {
        "type": "function",
        "name": "list_tasks",
        "description": "Listet offene Todoist-Aufgaben auf.",
        "parameters": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "Optionaler Todoist-Filter, z.B. 'today', 'overdue' oder 'p1'.",
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
                    "description": "Todoist-Prioritaet von 1 bis 4.",
                    "enum": [1, 2, 3, 4],
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
]


def build_input(user_text: str) -> Sequence[dict[str, object]]:
    return [{"role": "user", "content": [{"type": "input_text", "text": user_text}]}]


def todoist_headers() -> dict[str, str]:
    if not TODOIST_API_TOKEN:
        raise RuntimeError("TODOIST_API_TOKEN fehlt in der .env Datei")
    return {
        "Authorization": f"Bearer {TODOIST_API_TOKEN}",
        "Content-Type": "application/json",
    }


def list_tasks(filter_value: str | None = None) -> str:
    endpoint = f"{TODOIST_API_BASE}/tasks/filter" if filter_value else f"{TODOIST_API_BASE}/tasks"
    params = {"query": filter_value} if filter_value else None
    response = http_client.get(endpoint, headers=todoist_headers(), params=params)
    response.raise_for_status()
    payload = response.json()
    tasks = payload["results"] if isinstance(payload, dict) else payload
    if not tasks:
        return "Keine offenen Aufgaben gefunden."

    lines = []
    for task in tasks[:20]:
        due = task.get("due") or {}
        due_text = due.get("string") or due.get("date")
        suffix = f" | faellig: {due_text}" if due_text else ""
        lines.append(f"[{task['id']}] p{task.get('priority', 1)} | {task['content']}{suffix}")
    return "\n".join(lines)


def create_task(content: str, due_string: str | None = None, priority: int | None = None) -> str:
    payload: dict[str, object] = {"content": content}
    if due_string:
        payload["due_string"] = due_string
    if priority:
        payload["priority"] = priority

    response = http_client.post(
        f"{TODOIST_API_BASE}/tasks",
        headers=todoist_headers(),
        json=payload,
    )
    response.raise_for_status()
    task = response.json()
    return f"Task erstellt: [{task['id']}] {task['content']}"


def complete_task(task_id: str) -> str:
    response = http_client.post(
        f"{TODOIST_API_BASE}/tasks/{task_id}/close",
        headers=todoist_headers(),
    )
    response.raise_for_status()
    return f"Task {task_id} als erledigt markiert."


def execute_tool(name: str, arguments: str) -> str:
    parsed = json.loads(arguments or "{}")
    if name == "list_tasks":
        return list_tasks(parsed.get("filter"))
    if name == "create_task":
        return create_task(
            content=parsed["content"],
            due_string=parsed.get("due_string"),
            priority=parsed.get("priority"),
        )
    if name == "complete_task":
        return complete_task(parsed["task_id"])
    raise ValueError(f"Unbekanntes Tool: {name}")


def get_reply_text(user_id: int, user_text: str) -> str:
    request: dict[str, object] = {
        "model": OPENAI_MODEL,
        "instructions": SYSTEM_PROMPT,
        "input": build_input(user_text),
        "tools": TOOLS,
    }
    previous_response_id = previous_response_ids.get(user_id)
    if previous_response_id:
        request["previous_response_id"] = previous_response_id

    response = client.responses.create(**request)
    while True:
        previous_response_ids[user_id] = response.id
        function_calls = [
            item for item in getattr(response, "output", [])
            if getattr(item, "type", "") == "function_call"
        ]
        if not function_calls:
            if getattr(response, "output_text", ""):
                return response.output_text

            text_parts: list[str] = []
            for item in getattr(response, "output", []):
                for content in getattr(item, "content", []):
                    text = getattr(content, "text", "")
                    if text:
                        text_parts.append(text)
            return "\n".join(text_parts).strip() or "Ich konnte gerade keine Antwort erzeugen."

        tool_outputs: list[dict[str, str]] = []
        for call in function_calls:
            try:
                output = execute_tool(call.name, call.arguments)
            except Exception as exc:
                output = f"Fehler beim Tool-Aufruf: {exc}"
            tool_outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": output,
                }
            )

        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=SYSTEM_PROMPT,
            previous_response_id=response.id,
            input=tool_outputs,
            tools=TOOLS,
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! Ich bin dein Task-Assistent. Schreib mir eine Aufgabe oder frage mich nach Priorisierung."
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    previous_response_ids.pop(update.effective_user.id, None)
    await update.message.reply_text("Kontext fuer diesen Chat geloescht.")


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = get_reply_text(update.effective_user.id, update.message.text)
    await update.message.reply_text(reply)


def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    print("Bot laeuft...")
    app.run_polling()


if __name__ == "__main__":
    main()
