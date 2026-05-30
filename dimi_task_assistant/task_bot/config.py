from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> bool:
        return False


DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_TIMEZONE = "Europe/Berlin"
DEFAULT_MORNING_TIME = "07:30"
DEFAULT_EVENING_TIME = "20:00"
DEFAULT_CHAT_ID_FILE = "/data/chat_id.txt"


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    openai_api_key: str
    openai_model: str
    todoist_api_token: str
    telegram_chat_id: str
    morning_time: str
    evening_time: str
    timezone: str
    chat_id_file: str
    todoist_api_base: str = "https://api.todoist.com/api/v1"

    @property
    def zoneinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def morning_time_value(self) -> time:
        return parse_hhmm(self.morning_time, self.zoneinfo)

    @property
    def evening_time_value(self) -> time:
        return parse_hhmm(self.evening_time, self.zoneinfo)


def parse_hhmm(time_str: str, tz: ZoneInfo) -> time:
    parts = time_str.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Ungueltige Uhrzeit '{time_str}', erwartet HH:MM")
    hour, minute = map(int, parts)
    return time(hour, minute, tzinfo=tz)


def load_settings() -> Settings:
    load_dotenv()
    settings = Settings(
        telegram_token=os.getenv("TELEGRAM_TOKEN", "").strip(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        todoist_api_token=os.getenv("TODOIST_API_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        morning_time=os.getenv("MORNING_TIME", DEFAULT_MORNING_TIME).strip()
        or DEFAULT_MORNING_TIME,
        evening_time=os.getenv("EVENING_TIME", DEFAULT_EVENING_TIME).strip()
        or DEFAULT_EVENING_TIME,
        timezone=os.getenv("TIMEZONE", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE,
        chat_id_file=os.getenv("CHAT_ID_FILE", DEFAULT_CHAT_ID_FILE).strip()
        or DEFAULT_CHAT_ID_FILE,
    )
    validate_settings(settings)
    return settings


def validate_settings(settings: Settings) -> None:
    if not settings.telegram_token:
        raise ValueError("TELEGRAM_TOKEN fehlt in der Konfiguration")
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY fehlt in der Konfiguration")
    parse_hhmm(settings.morning_time, settings.zoneinfo)
    parse_hhmm(settings.evening_time, settings.zoneinfo)
