from __future__ import annotations

import logging
from datetime import UTC, datetime
from html import escape
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
    format_watch_index,
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
                    f"⚠️ <b>Request failed</b>\n{escape(str(exc), quote=True)}",
                )
            except Exception:
                logger.exception(
                    "Failed to send Telegram error message for user %s",
                    synced_user.telegram_user_id,
                )

    async def send_daily_reports(self, *, force: bool = False) -> dict[str, int]:
        now_utc = datetime.now(tz=UTC)
        target_users = (
            self.dependencies.database.list_all_users()
            if force
            else self.dependencies.monitoring_controller.list_due_users(now_utc)
        )
        sent = 0
        failed = 0

        _, discount_errors = self.dependencies.monitoring_controller.collect_discounts()
        todays_discounts = self.dependencies.database.list_discounts_for_date(now_utc.date())

        for user in target_users:
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
        return {"targets": len(target_users), "sent": sent, "failed": failed}

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
                await self._send_text(
                    chat_id,
                    "➕ <b>Add a watched product</b>\nUse <code>/watch &lt;product-url&gt;</code>",
                )
                return
            try:
                result = self.dependencies.watchlist_controller.add_watch(
                    synced_user.telegram_user_id,
                    argument,
                )
                await self._send_text(
                    chat_id,
                    "✅ <b>Watch added</b>\n\n"
                    + format_daily_report(DailyReport(updates=[result])),
                )
            except Exception as exc:
                await self._send_text(
                    chat_id,
                    f"⚠️ <b>Failed to add watch</b>\n{escape(str(exc), quote=True)}",
                )
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
                    await self._send_text(chat_id, "🧹 <b>Your watchlist is already empty.</b>")
                    return
                await self._send_text(
                    chat_id,
                    "🗑️ <b>Choose a product to remove</b>",
                    reply_markup=self._build_watch_keyboard(watches),
                )
                return
            removed = self.dependencies.watchlist_controller.remove_watch(
                synced_user.telegram_user_id,
                argument,
            )
            if removed is None:
                await self._send_text(
                    chat_id,
                    "🔎 <b>No watch matched</b>\nTry a watch index from <code>/list</code> or paste the product URL.",
                )
                return
            await self._send_text(
                chat_id,
                f"🗑️ <b>Removed watch [{format_watch_index(removed)}]</b>\n{escape(removed.name, quote=True)}",
            )
            return

        if command == "refresh":
            await self._send_text(
                chat_id,
                "⏳ <b>Refreshing prices and discount codes</b>\nThis can take a few seconds.",
            )
            report = self.dependencies.monitoring_controller.refresh_user(synced_user.telegram_user_id)
            await self._send_text(chat_id, format_daily_report(report))
            return

        if command == "discounts":
            await self._send_text(
                chat_id,
                "🎟️ <b>Refreshing discount codes</b>\nThis can take a few seconds.",
            )
            report = self.dependencies.monitoring_controller.refresh_discounts_for_user(
                synced_user.telegram_user_id
            )
            await self._send_text(chat_id, format_daily_report(report))
            return

        if command == "chart":
            if not argument or not argument.isdigit():
                await self._send_text(
                    chat_id,
                    "📈 <b>Open a chart</b>\nUse <code>/chart &lt;watch-index&gt;</code>",
                )
                return
            await self._send_chart(synced_user, argument, reply_chat_id=synced_user.chat_id)
            return

        if command:
            await self._send_text(chat_id, format_help())

    async def _handle_callback(self, update: Update, synced_user: TelegramUser) -> None:
        query = update.callback_query
        if query is None or query.data is None:
            return

        parts = query.data.split(":", maxsplit=2)
        action = parts[0]
        display_index: int | None = None
        raw_id = ""
        if len(parts) == 2:
            raw_id = parts[1]
        elif len(parts) == 3:
            if parts[1].isdigit():
                display_index = int(parts[1])
            raw_id = parts[2]

        if not raw_id:
            await query.answer("Unsupported action", show_alert=True)
            return

        if action == "remove":
            removed = self.dependencies.watchlist_controller.remove_watch(
                synced_user.telegram_user_id,
                raw_id,
            )
            await query.answer()
            if removed is None:
                await query.edit_message_text("That watch item was already removed.")
                return
            label = display_index if display_index is not None else format_watch_index(removed)
            await query.edit_message_text(f"Removed watch [{label}] {removed.name}")
            return

        if action == "chart":
            await query.answer()
            await self._send_chart(
                synced_user,
                raw_id,
                reply_chat_id=synced_user.chat_id,
                display_index=display_index,
            )
            return

        await query.answer("Unsupported action", show_alert=True)

    async def _send_chart(
        self,
        synced_user: TelegramUser,
        watch_identifier: str,
        reply_chat_id: int,
        display_index: int | None = None,
    ) -> None:
        watch = self.dependencies.watchlist_controller.get_watch(
            synced_user.telegram_user_id,
            watch_identifier,
        )
        if watch is None:
            await self.bot.send_message(
                chat_id=reply_chat_id,
                text="🔎 <b>Unknown watch index.</b>",
                parse_mode="HTML",
            )
            return

        history = self.dependencies.watchlist_controller.get_price_history(
            synced_user.telegram_user_id,
            watch.id,
            limit=180,
        )
        chart_bytes = render_price_history_chart(watch, history)
        reply_markup = self._build_chart_link_markup(synced_user, watch.id)
        label = str(display_index) if display_index is not None else format_watch_index(watch)
        await self.bot.send_photo(
            chat_id=reply_chat_id,
            photo=InputFile(BytesIO(chart_bytes), filename=f"watch-{label}.png"),
            caption=(
                f"📈 <b>Price chart</b>\n"
                f"<b>[{label}] {escape(watch.name, quote=True)}</b>"
            ),
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    def _build_watch_keyboard(self, watches: list) -> InlineKeyboardMarkup | None:
        if not watches:
            return None
        rows = []
        for watch in watches:
            label = format_watch_index(watch)
            rows.append(
                [
                    InlineKeyboardButton(f"Chart {label}", callback_data=f"chart:{label}:{watch.id}"),
                    InlineKeyboardButton(f"Remove {label}", callback_data=f"remove:{label}:{watch.id}"),
                ]
            )
        return InlineKeyboardMarkup(rows)

    def _build_chart_link_markup(
        self,
        synced_user: TelegramUser,
        watch_id: str,
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
                parse_mode="HTML",
                disable_web_page_preview=True,
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
