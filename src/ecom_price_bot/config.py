from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time

from dotenv import load_dotenv


def _parse_optional_id_tuple(raw_value: str) -> tuple[int, ...]:
    values = [item.strip() for item in raw_value.split(",") if item.strip()]
    return tuple(int(value) for value in values)


def _parse_daily_time(raw_value: str) -> time:
    hours, minutes = raw_value.split(":", maxsplit=1)
    return time(hour=int(hours), minute=int(minutes))


@dataclass(slots=True)
class Settings:
    telegram_bot_token: str
    telegram_allowed_user_ids: tuple[int, ...]
    telegram_webhook_secret: str | None
    default_timezone: str
    telegram_daily_time: time
    daily_refresh_window_minutes: int
    supabase_db_url: str
    vendor_addon_modules: tuple[str, ...]
    cron_secret: str | None
    app_base_url: str | None
    chart_signing_secret: str | None

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()

        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required.")

        supabase_db_url = os.getenv("SUPABASE_DB_URL", "").strip()
        if not supabase_db_url:
            raise ValueError("SUPABASE_DB_URL is required.")

        addon_modules = tuple(
            item.strip()
            for item in os.getenv("VENDOR_ADDON_MODULES", "").split(",")
            if item.strip()
        )

        app_base_url = os.getenv("APP_BASE_URL", "").strip() or None
        chart_signing_secret = os.getenv("CHART_SIGNING_SECRET", "").strip() or None
        telegram_webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip() or None
        cron_secret = os.getenv("CRON_SECRET", "").strip() or None

        return cls(
            telegram_bot_token=token,
            telegram_allowed_user_ids=_parse_optional_id_tuple(
                os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()
            ),
            telegram_webhook_secret=telegram_webhook_secret,
            default_timezone=os.getenv("TIMEZONE", "America/Los_Angeles").strip(),
            telegram_daily_time=_parse_daily_time(
                os.getenv("TELEGRAM_DAILY_TIME", "09:00").strip()
            ),
            daily_refresh_window_minutes=int(
                os.getenv("DAILY_REFRESH_WINDOW_MINUTES", "20").strip()
            ),
            supabase_db_url=supabase_db_url,
            vendor_addon_modules=addon_modules,
            cron_secret=cron_secret,
            app_base_url=app_base_url,
            chart_signing_secret=chart_signing_secret,
        )
