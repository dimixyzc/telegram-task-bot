# Dimi Task Assistant

Telegram task assistant with OpenAI and Todoist for Home Assistant OS.

## What it does

- talks to you via Telegram
- reads and writes Todoist tasks
- summarizes what is due, overdue, and important
- helps organize tasks in natural language

## Configuration

- `telegram_token`: Bot token from BotFather
- `openai_api_key`: OpenAI API key
- `openai_model`: Usually `gpt-5-mini`
- `todoist_api_token`: Todoist API token
- `telegram_chat_id`: Optional. Leave empty and run `/register` in Telegram to persist it in `/data/chat_id.txt`.
- `morning_time`: Daily briefing time, default `07:30`
- `evening_time`: Daily review time, default `20:00`
- `timezone`: Timezone for scheduled messages, default `Europe/Berlin`
- `planning_nudge_times`: Comma-separated times for short planning nudges, default `12:30,17:30`
- `workday_start` / `workday_end`: Local workday window used for calendar-aware planning options
- `default_task_duration`: Duration in minutes when a Todoist task has no duration
- `google_calendar_enabled`: Optional free/busy data from Google Calendar
- `google_calendar_write_enabled`: Optional event creation in Google Calendar, off by default
- `google_calendar_id`: Usually `primary`
- `google_token_file`: JSON file containing a Google OAuth `access_token`

## Installation on Home Assistant OS

1. Install the Samba or SSH add-on.
2. Copy this repository or at least the `dimi_task_assistant` folder plus `repository.yaml` into a subfolder of `/addons`.
3. Open Home Assistant.
4. Go to Settings -> Add-ons -> Add-on Store.
5. Open the menu and reload the store if needed.
6. Open `Dimi Task Assistant`.
7. Fill in the tokens in the add-on configuration.
8. Start the add-on.

## Notes

- The add-on uses Telegram polling, so no port needs to be exposed.
- The bot will keep running after Home Assistant restarts.
- `/all`, `/today`, `/overdue`, `/focus`, `/week`, `/briefing`, `/plan`, `/review`, `/register`, `/ping`, and `/clear` are available in the add-on.
- `/briefing`, `/plan`, and `/review` are decision-oriented: each due or overdue task can be marked done, moved to tomorrow, moved to a selected day, or parked.
