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

TELEGRAM_TOKEN="$(bashio::config 'telegram_token')"
OPENAI_API_KEY="$(bashio::config 'openai_api_key')"
OPENAI_MODEL="$(bashio::config 'openai_model')"
TODOIST_API_TOKEN="$(bashio::config 'todoist_api_token')"
TELEGRAM_CHAT_ID="$(bashio::config 'telegram_chat_id' '')"
MORNING_TIME="$(bashio::config 'morning_time' '07:30')"
EVENING_TIME="$(bashio::config 'evening_time' '20:00')"
TIMEZONE="$(bashio::config 'timezone' 'Europe/Berlin')"

bashio::log.info "Starting Dimi Task Assistant v0.2.0"
bashio::log.info "Morning briefing at: ${MORNING_TIME} | Evening review at: ${EVENING_TIME} | TZ: ${TIMEZONE}"

exec python3 -u /opt/dimi-task-assistant/bot.py
