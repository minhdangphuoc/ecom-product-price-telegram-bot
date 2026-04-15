from __future__ import annotations

from uuid import UUID

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
        watch = self._resolve_watch_with_index(telegram_user_id, watch.id) or watch
        return PriceUpdate(watch=watch, current=product, previous=previous)

    def remove_watch(self, telegram_user_id: int, identifier: str) -> WatchingProduct | None:
        watch = self._resolve_watch(telegram_user_id, identifier)
        if watch is None:
            if self._looks_like_uuid(identifier):
                return self.database.remove_watch_by_id(telegram_user_id, identifier)
            if not identifier.isdigit():
                return self.database.remove_watch_by_url(telegram_user_id, identifier)
            return None

        removed = self.database.remove_watch_by_id(telegram_user_id, watch.id)
        if removed is not None:
            removed.display_index = watch.display_index
        return removed

    def list_watches(self, telegram_user_id: int) -> list[WatchingProduct]:
        return self._with_display_indexes(
            self.database.list_active_watches_for_user(telegram_user_id)
        )

    def get_watch(self, telegram_user_id: int, identifier: str) -> WatchingProduct | None:
        return self._resolve_watch(telegram_user_id, identifier)

    def get_price_history(
        self,
        telegram_user_id: int,
        watch_id: str,
        limit: int = 90,
    ) -> list[PriceSnapshot]:
        return self.database.list_price_history_for_user(telegram_user_id, watch_id, limit=limit)

    def _resolve_watch(self, telegram_user_id: int, identifier: str) -> WatchingProduct | None:
        if identifier.isdigit():
            watches = self.list_watches(telegram_user_id)
            index = int(identifier)
            if 1 <= index <= len(watches):
                return watches[index - 1]
            return None
        if self._looks_like_uuid(identifier):
            return self._resolve_watch_with_index(telegram_user_id, identifier)
        return None

    def _resolve_watch_with_index(
        self,
        telegram_user_id: int,
        watch_id: str,
    ) -> WatchingProduct | None:
        watches = self.list_watches(telegram_user_id)
        for watch in watches:
            if watch.id == watch_id:
                return watch
        return None

    def _with_display_indexes(self, watches: list[WatchingProduct]) -> list[WatchingProduct]:
        for index, watch in enumerate(watches, start=1):
            watch.display_index = index
        return watches

    def _looks_like_uuid(self, value: str) -> bool:
        try:
            UUID(value)
        except ValueError:
            return False
        return True
