from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from ecom_price_bot.config import Settings
from ecom_price_bot.db import Database
from ecom_price_bot.models import DailyReport, Discount, PriceUpdate, TelegramUser, WatchingProduct
from ecom_price_bot.services.registry import VendorRegistry


class MonitoringController:
    def __init__(
        self,
        database: Database,
        vendor_registry: VendorRegistry,
        settings: Settings,
    ) -> None:
        self.database = database
        self.vendor_registry = vendor_registry
        self.settings = settings

    def refresh_user(self, telegram_user_id: int) -> DailyReport:
        return self.build_user_report(telegram_user_id)

    def build_user_report(
        self,
        telegram_user_id: int,
        *,
        prefetched_discounts: list[Discount] | None = None,
        extra_errors: list[str] | None = None,
    ) -> DailyReport:
        report = DailyReport()
        if extra_errors:
            report.errors.extend(extra_errors)
        watches = self.database.list_active_watches_for_user(telegram_user_id)
        for display_index, watch in enumerate(watches, start=1):
            watch.display_index = display_index
            try:
                report.updates.append(self.refresh_watch(watch))
            except Exception as exc:
                report.errors.append(
                    f"{watch.vendor_id}: failed to refresh '{watch.name}' ({watch.url}): "
                    f"{self._humanize_exception(exc)}"
                )

        report.new_discounts.extend(
            self._relevant_discounts_for_user(
                telegram_user_id,
                prefetched_discounts=prefetched_discounts,
                report=report,
            )
        )
        return report

    def refresh_discounts_for_user(self, telegram_user_id: int) -> DailyReport:
        report = DailyReport()
        report.new_discounts.extend(
            self._relevant_discounts_for_user(telegram_user_id, prefetched_discounts=None, report=report)
        )
        return report

    def collect_discounts(self) -> tuple[list[Discount], list[str]]:
        return self.collect_discounts_for_vendor_ids(
            tuple(vendor.vendor_id for vendor in self.vendor_registry.all())
        )

    def collect_discounts_for_vendor_ids(
        self,
        vendor_ids: tuple[str, ...],
    ) -> tuple[list[Discount], list[str]]:
        new_discounts: list[Discount] = []
        errors: list[str] = []
        observed_on = datetime.now(tz=UTC).date()

        if not vendor_ids:
            return new_discounts, errors

        for vendor_id in vendor_ids:
            vendor = self.vendor_registry.get_by_vendor_id(vendor_id)
            try:
                discounts = vendor.fetch_discounts()
                new_discounts.extend(self.database.save_new_discounts(discounts, observed_on))
            except Exception as exc:
                errors.append(
                    f"{vendor.vendor_id}: failed to fetch discounts: {self._humanize_exception(exc)}"
                )

        return new_discounts, errors

    def list_due_users(self, now_utc: datetime | None = None) -> list[TelegramUser]:
        current_time = now_utc or datetime.now(tz=UTC)
        due_users: list[TelegramUser] = []
        for user in self.database.list_active_users():
            if self._is_user_due(user, current_time):
                due_users.append(user)
        return due_users

    def mark_daily_report_sent(self, telegram_user_id: int, local_date: date) -> None:
        self.database.mark_daily_report_sent(telegram_user_id, local_date)

    def refresh_watch(self, watch: WatchingProduct) -> PriceUpdate:
        vendor = self.vendor_registry.get_by_vendor_id(watch.vendor_id)
        previous = self.database.get_previous_snapshot(watch.id)
        current = vendor.fetch_product(watch.url)
        self.database.save_price_snapshot(watch.id, current)
        return PriceUpdate(watch=watch, current=current, previous=previous)

    def _relevant_discounts_for_user(
        self,
        telegram_user_id: int,
        *,
        prefetched_discounts: list[Discount] | None,
        report: DailyReport,
    ) -> list[Discount]:
        vendor_ids = self.database.list_vendor_ids_for_user(telegram_user_id)
        if not vendor_ids:
            return []

        todays_discounts = prefetched_discounts
        if todays_discounts is None:
            _, discount_errors = self.collect_discounts_for_vendor_ids(vendor_ids)
            report.errors.extend(discount_errors)
            todays_discounts = self.database.list_discounts_for_date(
                datetime.now(tz=UTC).date(),
                vendor_ids=vendor_ids,
            )
        allowed_vendors = set(vendor_ids)
        return [discount for discount in todays_discounts if discount.vendor_id in allowed_vendors]

    def _is_user_due(self, user: TelegramUser, now_utc: datetime) -> bool:
        timezone_name = user.timezone or self.settings.default_timezone
        local_now = now_utc.astimezone(ZoneInfo(timezone_name))
        if user.last_daily_report_on == local_now.date():
            return False

        scheduled_at = local_now.replace(
            hour=self.settings.telegram_daily_time.hour,
            minute=self.settings.telegram_daily_time.minute,
            second=0,
            microsecond=0,
        )
        if local_now < scheduled_at:
            return False

        # Vercel Hobby cron runs can arrive at any point within the scheduled hour.
        # Treat the first invocation after the target local time as due for that date.
        return True

    def _humanize_exception(self, exc: Exception) -> str:
        message = str(exc)
        if "HTTP 401" in message or "HTTP 403" in message:
            return f"{message}. Access may be blocked or a saved login/session token may be expired."
        return message
