from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from .planning import SlotSuggestion


@dataclass
class GoogleCalendarClient:
    token_file: str
    calendar_id: str = "primary"
    write_enabled: bool = False
    client: httpx.Client | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = httpx.Client(timeout=15.0)

    def find_free_slots(
        self,
        *,
        duration_minutes: int,
        timezone: ZoneInfo,
        workday_start: time,
        workday_end: time,
        days: int = 5,
        now: datetime | None = None,
    ) -> list[SlotSuggestion]:
        now = now or datetime.now(tz=timezone)
        start = now.astimezone(timezone)
        end = start + timedelta(days=days)
        payload = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "timeZone": timezone.key,
            "items": [{"id": self.calendar_id}],
        }
        response = self.client.post(
            "https://www.googleapis.com/calendar/v3/freeBusy",
            headers=self._headers(),
            json=payload,
        )
        response.raise_for_status()
        busy = (
            response.json()
            .get("calendars", {})
            .get(self.calendar_id, {})
            .get("busy", [])
        )
        return _free_slots_from_busy(
            busy=busy,
            start=start,
            duration_minutes=duration_minutes,
            timezone=timezone,
            workday_start=workday_start,
            workday_end=workday_end,
            days=days,
        )

    def create_time_block(
        self,
        *,
        title: str,
        start: datetime,
        duration_minutes: int,
        timezone: ZoneInfo,
    ) -> str:
        if not self.write_enabled:
            raise RuntimeError("Google Calendar write access is disabled")
        end = start + timedelta(minutes=duration_minutes)
        response = self.client.post(
            f"https://www.googleapis.com/calendar/v3/calendars/{self.calendar_id}/events",
            headers=self._headers(),
            json={
                "summary": title,
                "start": {"dateTime": start.isoformat(), "timeZone": timezone.key},
                "end": {"dateTime": end.isoformat(), "timeZone": timezone.key},
            },
        )
        response.raise_for_status()
        return str(response.json().get("htmlLink", ""))

    def _headers(self) -> dict[str, str]:
        with open(self.token_file) as file:
            token_payload = json.load(file)
        token = token_payload.get("access_token") if isinstance(token_payload, dict) else None
        if not token:
            raise RuntimeError("GOOGLE_TOKEN_FILE enthaelt keinen access_token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _free_slots_from_busy(
    *,
    busy: list[dict],
    start: datetime,
    duration_minutes: int,
    timezone: ZoneInfo,
    workday_start: time,
    workday_end: time,
    days: int,
) -> list[SlotSuggestion]:
    busy_ranges = sorted(
        (
            datetime.fromisoformat(item["start"].replace("Z", "+00:00")).astimezone(timezone),
            datetime.fromisoformat(item["end"].replace("Z", "+00:00")).astimezone(timezone),
        )
        for item in busy
        if item.get("start") and item.get("end")
    )
    slots: list[SlotSuggestion] = []
    duration = timedelta(minutes=duration_minutes)
    for offset in range(days):
        day = (start + timedelta(days=offset)).date()
        cursor = datetime.combine(day, workday_start, tzinfo=timezone)
        day_end = datetime.combine(day, workday_end, tzinfo=timezone)
        if cursor < start:
            cursor = _round_up_to_next_half_hour(start)
        for busy_start, busy_end in busy_ranges:
            if busy_end <= cursor or busy_start.date() != day:
                continue
            if busy_start - cursor >= duration:
                slots.append(_slot_suggestion(len(slots), cursor))
            cursor = max(cursor, busy_end)
            if len(slots) >= 3:
                return slots
        if day_end - cursor >= duration:
            slots.append(_slot_suggestion(len(slots), cursor))
        if len(slots) >= 3:
            return slots
    return slots


def _round_up_to_next_half_hour(value: datetime) -> datetime:
    minute = 30 if value.minute < 30 else 60
    rounded = value.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute)
    return rounded


def _slot_suggestion(index: int, start: datetime) -> SlotSuggestion:
    key = chr(ord("a") + index)
    label = start.strftime("%a %H:%M")
    due_string = start.strftime("%Y-%m-%d at %H:%M")
    return SlotSuggestion(key=key, label=label, due_string=due_string)
