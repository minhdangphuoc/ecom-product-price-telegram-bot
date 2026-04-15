from __future__ import annotations

from ecom_price_bot.db import Database
from ecom_price_bot.models import PriceSnapshot, PriceUpdate, WatchingProduct
from ecom_price_bot.services.registry import VendorRegistry


class WatchlistController:
    def __init__(self, database: Database, vendor_registry: VendorRegistry) -> None:
        self.database = database
        self.vendor_registry = vendor_registry

    def add_watch(self, telegram_user_id: int, url: str) -> PriceUpdate:
        vendor = self.vendor_registry.get_by_url(url)
        product = vendor.fetch_product(url)
        watch = self.database.upsert_watching_product(
            telegram_user_id=telegram_user_id,
            name=product.name,
            url=vendor.normalize_product_url(product.url),
            vendor_id=vendor.vendor_id,
        )
        previous = self.database.get_previous_snapshot(watch.id)
        self.database.save_price_snapshot(watch.id, product)
        return PriceUpdate(watch=watch, current=product, previous=previous)

    def remove_watch(self, telegram_user_id: int, identifier: str) -> WatchingProduct | None:
        return self.database.remove_watch(telegram_user_id, identifier)

    def list_watches(self, telegram_user_id: int) -> list[WatchingProduct]:
        return self.database.list_active_watches_for_user(telegram_user_id)

    def get_watch(self, telegram_user_id: int, watch_id: int) -> WatchingProduct | None:
        return self.database.get_watch_for_user(telegram_user_id, watch_id)

    def get_price_history(
        self,
        telegram_user_id: int,
        watch_id: int,
        limit: int = 90,
    ) -> list[PriceSnapshot]:
        return self.database.list_price_history_for_user(telegram_user_id, watch_id, limit=limit)
