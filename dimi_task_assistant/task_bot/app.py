from __future__ import annotations

import logging

from openai import OpenAI
from telegram.ext import Application, ApplicationBuilder

from .assistant import TaskAssistant
from .config import Settings, load_settings
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
    runtime = BotRuntime(settings=settings, todoist=todoist, assistant=assistant)
    app = ApplicationBuilder().token(settings.telegram_token).build()
    runtime.register_handlers(app)
    runtime.register_jobs(app)
    return app


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    settings = load_settings()
    app = build_application(settings)
    logging.getLogger(__name__).info("Bot gestartet.")
    app.run_polling()
