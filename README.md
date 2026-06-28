# Telegram Task Bot

Telegram bot with OpenAI Responses API and Todoist integration.

## Local run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

## Docker on NUC / Home Assistant host

This is the recommended setup if you want the bot to run permanently on your Intel NUC.

1. Copy this folder to the NUC.
2. Create or copy `.env` with these variables:
   - `TELEGRAM_TOKEN`
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL`
   - `TODOIST_API_TOKEN`
   - `TELEGRAM_CHAT_ID` optional; `/register` can persist it automatically
   - `MORNING_TIME`, default `07:30`
   - `EVENING_TIME`, default `20:00`
   - `TIMEZONE`, default `Europe/Berlin`
   - `PLANNING_NUDGE_TIMES`, default `12:30,17:30`
   - `WORKDAY_START`, `WORKDAY_END`, defaults `09:00` and `18:00`
   - `DEFAULT_TASK_DURATION`, default `30`
   - optional Google Calendar flags: `GOOGLE_CALENDAR_ENABLED`, `GOOGLE_CALENDAR_WRITE_ENABLED`, `GOOGLE_CALENDAR_ID`, `GOOGLE_TOKEN_FILE`
3. Build and start the container:

```bash
docker compose up -d --build
```

4. Check logs:

```bash
docker compose logs -f
```

5. Restart after code changes:

```bash
docker compose up -d --build
```

6. Stop the bot:

```bash
docker compose down
```

Notes:
- The bot uses polling, so it does not need an exposed port.
- `restart: unless-stopped` makes it come back automatically after NUC reboots.
- If Home Assistant runs on the same NUC, keep this bot separate from Home Assistant itself. Run it as an additional Docker service.
- Morning and evening messages now focus on daily decisions. `/plan` shows still-undecided due or overdue tasks, and nudge jobs remind you if they are still unresolved.
- Google Calendar is optional. If enabled, the bot reads `GOOGLE_TOKEN_FILE` as JSON with an `access_token` and uses free/busy data for slot suggestions. With write access disabled, Todoist remains the only system the bot updates.

## Home Assistant OS add-on

If you use Home Assistant OS on the NUC, the recommended route is the included custom add-on in this repository.

Relevant files:

- [repository.yaml](repository.yaml)
- [dimi_task_assistant/config.yaml](dimi_task_assistant/config.yaml)
- [dimi_task_assistant/DOCS.md](dimi_task_assistant/DOCS.md)

Install flow on Home Assistant OS:

1. Install the Samba or SSH add-on.
2. Copy this repository into a subfolder of `/addons` on your Home Assistant device.
3. In Home Assistant, open Settings -> Add-ons -> Add-on Store.
4. Reload the add-on store.
5. Open `Dimi Task Assistant`.
6. Fill in:
   - `telegram_token`
   - `openai_api_key`
   - `openai_model`
- `todoist_api_token`
- `telegram_chat_id` optional; use `/register` if you leave it empty
- `morning_time`
- `evening_time`
- `timezone`
   - optional planning and Google Calendar settings
7. Start the add-on and inspect the logs.

The add-on stores the registered chat ID in `/data/chat_id.txt`, so daily messages keep working across restarts. Setting `telegram_chat_id` in the add-on configuration overrides that persisted value.

## Railway deployment

1. Create a new GitHub repository and push this folder.
2. In Railway, create a new project from that GitHub repo.
3. Add these variables in Railway:
   - `TELEGRAM_TOKEN`
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL`
   - `TODOIST_API_TOKEN`
   - `TELEGRAM_CHAT_ID` if you want scheduled messages without local `/register` persistence
   - `MORNING_TIME`
   - `EVENING_TIME`
   - `TIMEZONE`
4. Railway will detect the `Procfile` and run `python bot.py` as a worker.
5. After the deploy is live, the bot keeps polling Telegram without your laptop.

## Notes

- Do not commit `.env`.
- Replace exposed Telegram tokens before production use.
- This bot currently uses polling, so no public webhook URL is required.
- Root Docker, Railway, and the Home Assistant add-on all start the same shared bot implementation.
