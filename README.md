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

## Railway deployment

1. Create a new GitHub repository and push this folder.
2. In Railway, create a new project from that GitHub repo.
3. Add these variables in Railway:
   - `TELEGRAM_TOKEN`
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL`
   - `TODOIST_API_TOKEN`
4. Railway will detect the `Procfile` and run `python bot.py` as a worker.
5. After the deploy is live, the bot keeps polling Telegram without your laptop.

## Notes

- Do not commit `.env`.
- Replace exposed Telegram tokens before production use.
- This bot currently uses polling, so no public webhook URL is required.
