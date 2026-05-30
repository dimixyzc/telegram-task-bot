from __future__ import annotations

import asyncio
import logging
import os
import re

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .assistant import TaskAssistant
from .config import Settings
from .formatters import (
    format_all_task_chunks,
    format_evening_review,
    format_focus,
    format_morning_briefing,
    format_task_list,
)
from .todoist_client import TodoistClient


logger = logging.getLogger(__name__)
_ALLOWED_TAGS = {"b", "i", "u", "s", "code", "pre", "a"}


class BotRuntime:
    def __init__(
        self, settings: Settings, todoist: TodoistClient, assistant: TaskAssistant
    ) -> None:
        self.settings = settings
        self.todoist = todoist
        self.assistant = assistant
        self.active_chat_id = self._load_chat_id()

    def _load_chat_id(self) -> str:
        if self.settings.telegram_chat_id:
            return self.settings.telegram_chat_id
        try:
            with open(self.settings.chat_id_file) as file:
                return file.read().strip()
        except FileNotFoundError:
            return ""

    def _save_chat_id(self, chat_id: str) -> None:
        try:
            os.makedirs(os.path.dirname(self.settings.chat_id_file), exist_ok=True)
            with open(self.settings.chat_id_file, "w") as file:
                file.write(chat_id)
        except Exception as exc:
            logger.warning("Chat-ID konnte nicht gespeichert werden: %s", exc)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "👋 <b>Hi! Ich bin dein Task-Assistent.</b>\n\n"
            "Ich verbinde dich mit Todoist und halte dich auf dem Laufenden.\n\n"
            "<b>Befehle:</b>\n"
            "/all - Alle Aufgaben komplett\n"
            "/today - Aufgaben für heute\n"
            "/overdue - Überfällige Aufgaben\n"
            "/focus - Wichtigste Aufgabe jetzt\n"
            "/week - Nächste 7 Tage\n"
            "/briefing - Morgen-Briefing manuell\n"
            "/review - Abend-Review manuell\n"
            "/register - Diese Chat-ID für tägliche Nachrichten eintragen\n"
            "/ping - Verbindung testen\n"
            "/clear - Gesprächskontext zurücksetzen\n\n"
            "<b>Oder einfach schreiben:</b>\n"
            "<i>„Was steht heute an?“</i>\n"
            "<i>„Lege an: Zahnarzt morgen 14 Uhr“</i>\n"
            "<i>„Verschieb Zahnarzt auf Freitag“</i>",
            parse_mode="HTML",
        )

    async def cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.info(
            "Ping empfangen: chat_id=%s user_id=%s",
            update.effective_chat.id if update.effective_chat else "",
            update.effective_user.id if update.effective_user else "",
        )
        await update.message.reply_text("pong ✅")

    async def cmd_register(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        self.active_chat_id = str(update.effective_chat.id)
        self._save_chat_id(self.active_chat_id)
        logger.info("Chat-ID registriert: %s", self.active_chat_id)
        await update.message.reply_text(
            "✅ <b>Registriert!</b>\n\n"
            f"Deine Chat-ID: <code>{self.active_chat_id}</code>\n"
            "Ich speichere sie persistent in <code>/data/chat_id.txt</code>. "
            "Die Add-on-Konfiguration kann sie optional überschreiben.\n\n"
            "Ich schicke dir täglich:\n"
            f"🌅 Morgens um <b>{self.settings.morning_time}</b> dein Briefing\n"
            f"🌙 Abends um <b>{self.settings.evening_time}</b> deinen Tagesabschluss\n\n"
            f"Zeitzone: <i>{self.settings.timezone}</i>",
            parse_mode="HTML",
        )

    async def cmd_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_typing(update, context)
        try:
            text, keyboard = format_task_list(self.todoist.list_tasks("today"), "📋 Heute fällig")
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as exc:
            await update.message.reply_text(f"❌ Fehler: {exc}")

    async def cmd_overdue(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._send_typing(update, context)
        try:
            text, keyboard = format_task_list(
                self.todoist.list_tasks("overdue"), "⚠️ Überfällige Aufgaben"
            )
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as exc:
            await update.message.reply_text(f"❌ Fehler: {exc}")

    async def cmd_focus(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_typing(update, context)
        try:
            tasks_data = self.todoist.list_tasks("today | overdue")
            if not tasks_data.get("tasks"):
                tasks_data = self.todoist.list_tasks(None)
            text, keyboard = format_focus(tasks_data)
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as exc:
            await update.message.reply_text(f"❌ Fehler: {exc}")

    async def cmd_week(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_typing(update, context)
        try:
            text, keyboard = format_task_list(
                self.todoist.list_tasks("next 7 days"), "📅 Nächste 7 Tage"
            )
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as exc:
            await update.message.reply_text(f"❌ Fehler: {exc}")

    async def cmd_briefing(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._send_typing(update, context)
        try:
            text, keyboard = format_morning_briefing(
                self.todoist.list_tasks("today | overdue")
            )
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as exc:
            await update.message.reply_text(f"❌ Fehler: {exc}")

    async def cmd_review(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_typing(update, context)
        try:
            text, keyboard = format_evening_review(
                self.todoist.list_tasks("today | overdue")
            )
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as exc:
            await update.message.reply_text(f"❌ Fehler: {exc}")

    async def cmd_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_typing(update, context)
        try:
            for chunk in format_all_task_chunks(self.todoist.fetch_all_tasks()):
                await update.message.reply_text(chunk, parse_mode="HTML")
        except Exception as exc:
            await update.message.reply_text(f"❌ Fehler: {exc}")

    async def cmd_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.assistant.clear_history()
        await update.message.reply_text("🔄 Gesprächsverlauf gelöscht.")

    async def handle_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        await query.answer()
        data = query.data or ""
        current_text = query.message.text or query.message.caption or ""

        try:
            if data.startswith("done:"):
                task_id = data[5:]
                self.todoist.complete_task(task_id)
                status_line = "✅ <i>Erledigt</i>"
            elif data.startswith("snooze0:"):
                task_id = data[8:]
                self.todoist.reschedule_task(task_id, "today")
                status_line = "📅 <i>Auf heute gesetzt</i>"
            elif data.startswith("snooze1:"):
                task_id = data[8:]
                self.todoist.reschedule_task(task_id, "tomorrow")
                status_line = "📅 <i>Auf morgen verschoben</i>"
            elif data.startswith("snooze7:"):
                task_id = data[8:]
                self.todoist.reschedule_task(task_id, "next sunday")
                status_line = "📅 <i>Auf nächsten Sonntag verschoben</i>"
            else:
                return

            task_label = _find_task_label(query.message.reply_markup, task_id)
            label_suffix = f" - <i>{task_label}</i>" if task_label else ""
            new_text = current_text + f"\n{status_line}{label_suffix}"
            remaining_rows = _remaining_keyboard_rows(query.message.reply_markup, task_id)
            if remaining_rows:
                await query.edit_message_text(
                    new_text,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(remaining_rows),
                )
            else:
                await query.edit_message_text(
                    new_text + "\n\n🎉 <i>Alle Aufgaben bearbeitet!</i>",
                    parse_mode="HTML",
                )
        except Exception as exc:
            logger.error("Callback-Fehler: %s", exc)
            try:
                await query.edit_message_text(
                    current_text + f"\n\n❌ Fehler: {exc}", parse_mode="HTML"
                )
            except Exception:
                pass

    async def chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        try:
            if not self.active_chat_id:
                self.active_chat_id = str(update.effective_chat.id)
                self._save_chat_id(self.active_chat_id)
                logger.info("Chat-ID auto-registriert: %s", self.active_chat_id)

            user_text = update.message.text or ""
            logger.info(
                "Nachricht empfangen: chat_id=%s user_id=%s length=%s",
                update.effective_chat.id if update.effective_chat else "",
                update.effective_user.id if update.effective_user else "",
                len(user_text),
            )
            await self._send_typing(update, context)
            if len(user_text) > 2000:
                user_text = user_text[:2000] + "\n[...Nachricht gekuerzt]"
            reply = await asyncio.to_thread(self.assistant.get_reply_text, user_text)
            await safe_send(update.message, reply)
        except Exception as exc:
            logger.exception("Fehler beim Verarbeiten einer Chat-Nachricht")
            await update.message.reply_text(
                "❌ Ich habe die Nachricht empfangen, aber beim Verarbeiten ist ein Fehler aufgetreten.\n"
                f"<code>{sanitize_html(str(exc))}</code>",
                parse_mode="HTML",
            )

    async def job_morning_briefing(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.active_chat_id:
            logger.warning("Keine Chat-ID gesetzt - Morning Briefing uebersprungen.")
            return
        try:
            text, keyboard = format_morning_briefing(
                self.todoist.list_tasks("today | overdue")
            )
            await context.bot.send_message(
                chat_id=self.active_chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            logger.info("Morning Briefing gesendet.")
        except Exception as exc:
            logger.error("Morning Briefing Fehler: %s", exc)

    async def job_evening_review(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.active_chat_id:
            logger.warning("Keine Chat-ID gesetzt - Evening Review uebersprungen.")
            return
        try:
            text, keyboard = format_evening_review(
                self.todoist.list_tasks("today | overdue")
            )
            await context.bot.send_message(
                chat_id=self.active_chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            logger.info("Evening Review gesendet.")
        except Exception as exc:
            logger.error("Evening Review Fehler: %s", exc)

    def register_handlers(self, app: Application) -> None:
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("register", self.cmd_register))
        app.add_handler(CommandHandler("ping", self.cmd_ping))
        app.add_handler(CommandHandler("all", self.cmd_all))
        app.add_handler(CommandHandler("today", self.cmd_today))
        app.add_handler(CommandHandler("overdue", self.cmd_overdue))
        app.add_handler(CommandHandler("focus", self.cmd_focus))
        app.add_handler(CommandHandler("week", self.cmd_week))
        app.add_handler(CommandHandler("briefing", self.cmd_briefing))
        app.add_handler(CommandHandler("review", self.cmd_review))
        app.add_handler(CommandHandler("clear", self.cmd_clear))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.chat))
        app.add_error_handler(self.handle_error)

    async def handle_error(
        self, update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.exception("Telegram-Handler-Fehler", exc_info=context.error)

    def register_jobs(self, app: Application) -> None:
        if not app.job_queue:
            logger.warning(
                "JobQueue nicht verfuegbar - installiere python-telegram-bot[job-queue]."
            )
            return
        app.job_queue.run_daily(
            self.job_morning_briefing,
            self.settings.morning_time_value,
            name="morning_briefing",
        )
        app.job_queue.run_daily(
            self.job_evening_review,
            self.settings.evening_time_value,
            name="evening_review",
        )
        logger.info(
            "Geplant: Briefing %s, Review %s (%s)",
            self.settings.morning_time,
            self.settings.evening_time,
            self.settings.timezone,
        )

    async def _send_typing(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )


def sanitize_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)

    def strip_tag(match: re.Match) -> str:
        tag = match.group(1).lower().split()[0].lstrip("/")
        return match.group(0) if tag in _ALLOWED_TAGS else ""

    return re.sub(r"<(/?\w[^>]*)>", strip_tag, text)


async def safe_send(message, text: str, parse_mode: str = "HTML") -> None:
    clean = sanitize_html(text)
    chunks = [clean[index : index + 4000] for index in range(0, max(len(clean), 1), 4000)]
    for chunk in chunks:
        try:
            await message.reply_text(chunk, parse_mode=parse_mode)
        except Exception:
            plain = re.sub(r"<[^>]+>", "", chunk)
            await message.reply_text(plain)


def _find_task_label(reply_markup: InlineKeyboardMarkup | None, task_id: str) -> str:
    if not reply_markup:
        return ""
    for row in reply_markup.inline_keyboard:
        for button in row:
            if button.callback_data == f"done:{task_id}":
                return button.text.replace("✅ ", "").strip()
    return ""


def _remaining_keyboard_rows(
    reply_markup: InlineKeyboardMarkup | None, task_id: str
) -> list:
    if not reply_markup:
        return []
    remaining_rows = []
    for row in reply_markup.inline_keyboard:
        row_task_id = None
        for button in row:
            callback_data = button.callback_data or ""
            for prefix in ("done:", "snooze0:", "snooze1:", "snooze7:"):
                if callback_data.startswith(prefix):
                    row_task_id = callback_data[len(prefix) :]
                    break
            if row_task_id:
                break
        if row_task_id != task_id:
            remaining_rows.append(row)
    return remaining_rows
