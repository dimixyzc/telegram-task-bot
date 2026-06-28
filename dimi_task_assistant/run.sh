#!/usr/bin/with-contenv bashio

set -euo pipefail

export TELEGRAM_TOKEN
export OPENAI_API_KEY
export OPENAI_MODEL
export TODOIST_API_TOKEN
export TELEGRAM_CHAT_ID
export MORNING_TIME
export EVENING_TIME
export TIMEZONE
export PLANNING_NUDGE_TIMES
export WORKDAY_START
export WORKDAY_END
export DEFAULT_TASK_DURATION
export GOOGLE_CALENDAR_ENABLED
export GOOGLE_CALENDAR_WRITE_ENABLED
export GOOGLE_CALENDAR_ID
export GOOGLE_TOKEN_FILE

TELEGRAM_TOKEN="$(bashio::config 'telegram_token')"
OPENAI_API_KEY="$(bashio::config 'openai_api_key')"
OPENAI_MODEL="$(bashio::config 'openai_model')"
TODOIST_API_TOKEN="$(bashio::config 'todoist_api_token')"
TELEGRAM_CHAT_ID="$(bashio::config 'telegram_chat_id' '')"
MORNING_TIME="$(bashio::config 'morning_time' '07:30')"
EVENING_TIME="$(bashio::config 'evening_time' '20:00')"
TIMEZONE="$(bashio::config 'timezone' 'Europe/Berlin')"
PLANNING_NUDGE_TIMES="$(bashio::config 'planning_nudge_times' '12:30,17:30')"
WORKDAY_START="$(bashio::config 'workday_start' '09:00')"
WORKDAY_END="$(bashio::config 'workday_end' '18:00')"
DEFAULT_TASK_DURATION="$(bashio::config 'default_task_duration' '30')"
GOOGLE_CALENDAR_ENABLED="$(bashio::config 'google_calendar_enabled' 'false')"
GOOGLE_CALENDAR_WRITE_ENABLED="$(bashio::config 'google_calendar_write_enabled' 'false')"
GOOGLE_CALENDAR_ID="$(bashio::config 'google_calendar_id' 'primary')"
GOOGLE_TOKEN_FILE="$(bashio::config 'google_token_file' '/data/google_token.json')"

bashio::log.info "Starting Dimi Task Assistant v0.3.0"
bashio::log.info "Morning briefing at: ${MORNING_TIME} | Evening review at: ${EVENING_TIME} | Nudges: ${PLANNING_NUDGE_TIMES} | TZ: ${TIMEZONE}"

exec python3 -u /opt/dimi-task-assistant/bot.py
