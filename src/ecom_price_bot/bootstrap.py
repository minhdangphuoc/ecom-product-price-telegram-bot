from __future__ import annotations

from dataclasses import dataclass

from telegram import Bot

from ecom_price_bot.config import Settings
from ecom_price_bot.controllers.monitoring_controller import MonitoringController
from ecom_price_bot.controllers.watchlist_controller import WatchlistController
from ecom_price_bot.db import Database
from ecom_price_bot.services.registry import VendorRegistry


@dataclass(slots=True)
class Dependencies:
    settings: Settings
    database: Database
    vendor_registry: VendorRegistry
    watchlist_controller: WatchlistController
    monitoring_controller: MonitoringController
    telegram_bot: Bot


_dependencies: Dependencies | None = None


def get_dependencies() -> Dependencies:
    global _dependencies
    if _dependencies is None:
        settings = Settings.load()
        database = Database(settings.supabase_db_url)
        vendor_registry = VendorRegistry.build(addon_modules=settings.vendor_addon_modules)
        watchlist_controller = WatchlistController(database=database, vendor_registry=vendor_registry)
        monitoring_controller = MonitoringController(
            database=database,
            vendor_registry=vendor_registry,
            settings=settings,
        )
        telegram_bot = Bot(token=settings.telegram_bot_token)
        _dependencies = Dependencies(
            settings=settings,
            database=database,
            vendor_registry=vendor_registry,
            watchlist_controller=watchlist_controller,
            monitoring_controller=monitoring_controller,
            telegram_bot=telegram_bot,
        )
    return _dependencies
