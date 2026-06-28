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
DEFAULT_STATE_FILE = "/data/taskbot_state.json"
DEFAULT_PLANNING_NUDGE_TIMES = "12:30,17:30"
DEFAULT_WORKDAY_START = "09:00"
DEFAULT_WORKDAY_END = "18:00"
DEFAULT_DEFAULT_TASK_DURATION = 30


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
    state_file: str
    planning_nudge_times: str
    workday_start: str
    workday_end: str
    default_task_duration: int
    google_calendar_enabled: bool
    google_calendar_write_enabled: bool
    google_calendar_id: str
    google_token_file: str
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

    @property
    def planning_nudge_time_values(self) -> list[time]:
        return [
            parse_hhmm(part, self.zoneinfo)
            for part in self.planning_nudge_times.split(",")
            if part.strip()
        ]

    @property
    def workday_start_value(self) -> time:
        return parse_hhmm(self.workday_start, self.zoneinfo)

    @property
    def workday_end_value(self) -> time:
        return parse_hhmm(self.workday_end, self.zoneinfo)


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
        state_file=os.getenv("STATE_FILE", DEFAULT_STATE_FILE).strip() or DEFAULT_STATE_FILE,
        planning_nudge_times=os.getenv(
            "PLANNING_NUDGE_TIMES", DEFAULT_PLANNING_NUDGE_TIMES
        ).strip()
        or DEFAULT_PLANNING_NUDGE_TIMES,
        workday_start=os.getenv("WORKDAY_START", DEFAULT_WORKDAY_START).strip()
        or DEFAULT_WORKDAY_START,
        workday_end=os.getenv("WORKDAY_END", DEFAULT_WORKDAY_END).strip()
        or DEFAULT_WORKDAY_END,
        default_task_duration=int(
            os.getenv("DEFAULT_TASK_DURATION", str(DEFAULT_DEFAULT_TASK_DURATION))
            or DEFAULT_DEFAULT_TASK_DURATION
        ),
        google_calendar_enabled=_env_bool("GOOGLE_CALENDAR_ENABLED", False),
        google_calendar_write_enabled=_env_bool("GOOGLE_CALENDAR_WRITE_ENABLED", False),
        google_calendar_id=os.getenv("GOOGLE_CALENDAR_ID", "primary").strip() or "primary",
        google_token_file=os.getenv("GOOGLE_TOKEN_FILE", "/data/google_token.json").strip()
        or "/data/google_token.json",
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
    for nudge_time in settings.planning_nudge_times.split(","):
        if nudge_time.strip():
            parse_hhmm(nudge_time.strip(), settings.zoneinfo)
    parse_hhmm(settings.workday_start, settings.zoneinfo)
    parse_hhmm(settings.workday_end, settings.zoneinfo)
    if settings.default_task_duration < 5:
        raise ValueError("DEFAULT_TASK_DURATION muss mindestens 5 Minuten sein")


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
