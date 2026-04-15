from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(slots=True)
class TelegramUser:
    telegram_user_id: int
    chat_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    is_bot: bool
    timezone: str
    last_daily_report_on: date | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Product:
    vendor_id: str
    name: str
    url: str
    price: Decimal
    currency: str
    in_stock: bool = True
    article_number: str | None = None
    raw_payload: str | None = None


@dataclass(slots=True)
class Discount:
    vendor_id: str
    condition: str
    source_url: str
    code: str | None = None


@dataclass(slots=True)
class WatchingProduct:
    id: str
    telegram_user_id: int
    name: str
    url: str
    vendor_id: str
    active: bool
    created_at: datetime
    updated_at: datetime
    display_index: int | None = None


@dataclass(slots=True)
class PriceSnapshot:
    id: str
    watching_product_id: str
    observed_at: datetime
    product_name: str
    product_price: Decimal
    currency: str
    in_stock: bool
    article_number: str | None = None


@dataclass(slots=True)
class PriceUpdate:
    watch: WatchingProduct
    current: Product
    previous: PriceSnapshot | None = None

    @property
    def delta(self) -> Decimal | None:
        if self.previous is None:
            return None
        return self.current.price - self.previous.product_price


@dataclass(slots=True)
class DailyReport:
    updates: list[PriceUpdate] = field(default_factory=list)
    new_discounts: list[Discount] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
