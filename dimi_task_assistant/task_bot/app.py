from __future__ import annotations

import logging

from openai import OpenAI
from telegram.ext import Application, ApplicationBuilder

from .assistant import TaskAssistant
from .config import Settings, load_settings
from .google_calendar import GoogleCalendarClient
from .planning import PlannerStateStore, PlanningEngine
from .telegram_handlers import BotRuntime
from .todoist_client import TodoistClient


def build_application(settings: Settings) -> Application:
    todoist = TodoistClient(
        api_token=settings.todoist_api_token,
        api_base=settings.todoist_api_base,
    )
    assistant = TaskAssistant(
        model=settings.openai_model,
        todoist=todoist,
        openai_client=OpenAI(api_key=settings.openai_api_key),
    )
    planner_state = PlannerStateStore(settings.state_file)
    planner = PlanningEngine(
        state=planner_state,
        default_task_duration=settings.default_task_duration,
    )
    google_calendar = (
        GoogleCalendarClient(
            token_file=settings.google_token_file,
            calendar_id=settings.google_calendar_id,
            write_enabled=settings.google_calendar_write_enabled,
        )
        if settings.google_calendar_enabled
        else None
    )
    runtime = BotRuntime(
        settings=settings,
        todoist=todoist,
        assistant=assistant,
        planner=planner,
        google_calendar=google_calendar,
    )
    app = ApplicationBuilder().token(settings.telegram_token).build()
    runtime.register_handlers(app)
    runtime.register_jobs(app)
    return app


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    settings = load_settings()
    app = build_application(settings)
    logging.getLogger(__name__).info("Bot gestartet.")
    app.run_polling(bootstrap_retries=10)
