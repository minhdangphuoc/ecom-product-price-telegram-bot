from __future__ import annotations

import logging
from datetime import UTC, datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update

from ecom_price_bot.bootstrap import Dependencies
from ecom_price_bot.charts import render_price_history_chart
from ecom_price_bot.models import DailyReport, TelegramUser
from ecom_price_bot.security import sign_chart_token
from ecom_price_bot.telegram.formatting import (
    format_daily_report,
    format_help,
    format_watch_list,
    split_message,
)

logger = logging.getLogger(__name__)


class TelegramWebhookHandler:
    def __init__(self, dependencies: Dependencies) -> None:
        self.dependencies = dependencies
        self.bot = dependencies.telegram_bot

    async def handle_update(self, payload: dict) -> None:
        update = Update.de_json(payload, self.bot)
        telegram_user = update.effective_user
        chat = update.effective_chat
        if telegram_user is None or chat is None:
            return

        if not self._is_allowed_user(telegram_user.id):
            if update.effective_message:
                await self._send_text(chat.id, "This user is not authorized for the bot.")
            elif update.callback_query:
                await update.callback_query.answer("Unauthorized", show_alert=True)
            return

        synced_user = self.dependencies.database.upsert_telegram_user(
            telegram_user_id=telegram_user.id,
            chat_id=chat.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            language_code=telegram_user.language_code,
            is_bot=telegram_user.is_bot,
            default_timezone=self.dependencies.settings.default_timezone,
        )

        try:
            if update.callback_query:
                await self._handle_callback(update, synced_user)
                return

            message = update.effective_message
            if message is None or not message.text:
                return
            await self._handle_message(update, synced_user)
        except Exception as exc:
            logger.exception(
                "Failed to handle Telegram update for user %s",
                synced_user.telegram_user_id,
            )
            try:
                await self._send_text(
                    synced_user.chat_id,
                    f"Request failed: {exc}",
                )
            except Exception:
                logger.exception(
                    "Failed to send Telegram error message for user %s",
                    synced_user.telegram_user_id,
                )

    async def send_daily_reports(self) -> dict[str, int]:
        now_utc = datetime.now(tz=UTC)
        due_users = self.dependencies.monitoring_controller.list_due_users(now_utc)
        sent = 0
        failed = 0

        _, discount_errors = self.dependencies.monitoring_controller.collect_discounts()
        todays_discounts = self.dependencies.database.list_discounts_for_date(now_utc.date())

        for user in due_users:
            report = self.dependencies.monitoring_controller.build_user_report(
                user.telegram_user_id,
                prefetched_discounts=todays_discounts,
                extra_errors=discount_errors,
            )
            try:
                await self._send_text(user.chat_id, format_daily_report(report))
                local_date = now_utc.astimezone(ZoneInfo(user.timezone)).date()
                self.dependencies.monitoring_controller.mark_daily_report_sent(
                    user.telegram_user_id,
                    local_date,
                )
                sent += 1
            except Exception:
                failed += 1
        return {"sent": sent, "failed": failed}

    async def _handle_message(self, update: Update, synced_user: TelegramUser) -> None:
        message = update.effective_message
        if message is None or not message.text:
            return

        command, argument = self._parse_command(message.text)
        chat_id = synced_user.chat_id

        if command in {"start", "help"}:
            await self._send_text(chat_id, format_help())
            return

        if command in {"watch", "add"}:
            if not argument:
                await self._send_text(chat_id, "Usage: /watch <product-url>")
                return
            try:
                result = self.dependencies.watchlist_controller.add_watch(
                    synced_user.telegram_user_id,
                    argument,
                )
                await self._send_text(
                    chat_id,
                    "Watch added successfully.\n\n"
                    + format_daily_report(DailyReport(updates=[result])),
                )
            except Exception as exc:
                await self._send_text(chat_id, f"Failed to add watch: {exc}")
            return

        if command == "list":
            watches = self.dependencies.watchlist_controller.list_watches(synced_user.telegram_user_id)
            await self._send_text(
                chat_id,
                format_watch_list(watches),
                reply_markup=self._build_watch_keyboard(watches),
            )
            return

        if command == "remove":
            if not argument:
                watches = self.dependencies.watchlist_controller.list_watches(synced_user.telegram_user_id)
                if not watches:
                    await self._send_text(chat_id, "Watch list is already empty.")
                    return
                await self._send_text(
                    chat_id,
                    "Choose a product to remove:",
                    reply_markup=self._build_watch_keyboard(watches),
                )
                return
            removed = self.dependencies.watchlist_controller.remove_watch(
                synced_user.telegram_user_id,
                argument,
            )
            if removed is None:
                await self._send_text(chat_id, "Nothing matched that watch id or url.")
                return
            await self._send_text(chat_id, f"Removed watch [{removed.id}] {removed.name}")
            return

        if command == "refresh":
            await self._send_text(chat_id, "Refreshing prices and discounts. This can take a few seconds.")
            report = self.dependencies.monitoring_controller.refresh_user(synced_user.telegram_user_id)
            await self._send_text(chat_id, format_daily_report(report))
            return

        if command == "discounts":
            await self._send_text(chat_id, "Refreshing discounts. This can take a few seconds.")
            report = self.dependencies.monitoring_controller.refresh_discounts_for_user(
                synced_user.telegram_user_id
            )
            await self._send_text(chat_id, format_daily_report(report))
            return

        if command == "chart":
            if not argument or not argument.isdigit():
                await self._send_text(chat_id, "Usage: /chart <watch-id>")
                return
            await self._send_chart(synced_user, int(argument), reply_chat_id=synced_user.chat_id)
            return

        if command:
            await self._send_text(chat_id, format_help())

    async def _handle_callback(self, update: Update, synced_user: TelegramUser) -> None:
        query = update.callback_query
        if query is None or query.data is None:
            return

        action, _, raw_id = query.data.partition(":")
        if not raw_id.isdigit():
            await query.answer("Unsupported action", show_alert=True)
            return

        watch_id = int(raw_id)

        if action == "remove":
            removed = self.dependencies.watchlist_controller.remove_watch(
                synced_user.telegram_user_id,
                raw_id,
            )
            await query.answer()
            if removed is None:
                await query.edit_message_text("That watch item was already removed.")
                return
            await query.edit_message_text(f"Removed watch [{removed.id}] {removed.name}")
            return

        if action == "chart":
            await query.answer()
            await self._send_chart(synced_user, watch_id, reply_chat_id=synced_user.chat_id)
            return

        await query.answer("Unsupported action", show_alert=True)

    async def _send_chart(self, synced_user: TelegramUser, watch_id: int, reply_chat_id: int) -> None:
        watch = self.dependencies.watchlist_controller.get_watch(synced_user.telegram_user_id, watch_id)
        if watch is None:
            await self.bot.send_message(chat_id=reply_chat_id, text="Unknown watch id.")
            return

        history = self.dependencies.watchlist_controller.get_price_history(
            synced_user.telegram_user_id,
            watch_id,
            limit=180,
        )
        chart_bytes = render_price_history_chart(watch, history)
        reply_markup = self._build_chart_link_markup(synced_user, watch_id)
        await self.bot.send_photo(
            chat_id=reply_chat_id,
            photo=InputFile(BytesIO(chart_bytes), filename=f"watch-{watch_id}.png"),
            caption=f"Price chart for [{watch.id}] {watch.name}",
            reply_markup=reply_markup,
        )

    def _build_watch_keyboard(self, watches: list) -> InlineKeyboardMarkup | None:
        if not watches:
            return None
        rows = []
        for watch in watches:
            rows.append(
                [
                    InlineKeyboardButton(f"Chart {watch.id}", callback_data=f"chart:{watch.id}"),
                    InlineKeyboardButton(f"Remove {watch.id}", callback_data=f"remove:{watch.id}"),
                ]
            )
        return InlineKeyboardMarkup(rows)

    def _build_chart_link_markup(
        self,
        synced_user: TelegramUser,
        watch_id: int,
    ) -> InlineKeyboardMarkup | None:
        app_base_url = self.dependencies.settings.app_base_url
        signing_secret = self.dependencies.settings.chart_signing_secret
        if not app_base_url or not signing_secret:
            return None

        signature = sign_chart_token(signing_secret, synced_user.telegram_user_id, watch_id)
        url = (
            f"{app_base_url.rstrip('/')}/chart"
            f"?telegram_user_id={synced_user.telegram_user_id}"
            f"&watch_id={watch_id}"
            f"&sig={signature}"
        )
        return InlineKeyboardMarkup([[InlineKeyboardButton("Open chart link", url=url)]])

    async def _send_text(
        self,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        parts = split_message(text)
        for index, part in enumerate(parts):
            await self.bot.send_message(
                chat_id=chat_id,
                text=part,
                reply_markup=reply_markup if index == len(parts) - 1 else None,
            )

    def _is_allowed_user(self, telegram_user_id: int) -> bool:
        allowed = self.dependencies.settings.telegram_allowed_user_ids
        return not allowed or telegram_user_id in allowed

    def _parse_command(self, text: str) -> tuple[str | None, str]:
        stripped = text.strip()
        if not stripped.startswith("/"):
            return None, ""
        parts = stripped.split(maxsplit=1)
        command = parts[0][1:].split("@", maxsplit=1)[0].lower()
        argument = parts[1].strip() if len(parts) > 1 else ""
        return command, argument
