from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from telegram import Bot

if TYPE_CHECKING:
    from ecom_price_bot.config import Settings


def build_expected_webhook_url(app_base_url: str | None) -> str | None:
    if not app_base_url:
        return None

    parts = urlsplit(app_base_url.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None

    host = (parts.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return None

    return urlunsplit((parts.scheme, parts.netloc, "/telegram/webhook", "", ""))


async def sync_telegram_webhook(bot: Bot, settings: "Settings") -> str:
    expected_url = build_expected_webhook_url(settings.app_base_url)
    if not expected_url:
        return "skipped"

    info = await bot.get_webhook_info()
    if info.url == expected_url and not settings.telegram_webhook_secret:
        return "unchanged"

    await bot.set_webhook(
        url=expected_url,
        secret_token=settings.telegram_webhook_secret or None,
        drop_pending_updates=False,
    )
    return "updated"
