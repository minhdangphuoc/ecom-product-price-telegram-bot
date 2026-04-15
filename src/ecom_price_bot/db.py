from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from ecom_price_bot.models import (
    Discount,
    PriceSnapshot,
    Product,
    TelegramUser,
    WatchingProduct,
)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class Database:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection]:
        connection = psycopg.connect(self.database_url, row_factory=dict_row)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    @contextmanager
    def advisory_lock(self, lock_key: int) -> Iterator[bool]:
        connection = psycopg.connect(self.database_url, row_factory=dict_row)
        try:
            row = connection.execute(
                "SELECT pg_try_advisory_lock(%s) AS locked",
                (lock_key,),
            ).fetchone()
            locked = bool(row["locked"])
            yield locked
        finally:
            try:
                connection.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
                connection.commit()
            finally:
                connection.close()

    def upsert_telegram_user(
        self,
        *,
        telegram_user_id: int,
        chat_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None,
        is_bot: bool,
        default_timezone: str,
    ) -> TelegramUser:
        with self.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO public.telegram_users (
                    telegram_user_id,
                    chat_id,
                    username,
                    first_name,
                    last_name,
                    language_code,
                    is_bot,
                    timezone,
                    last_seen_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (telegram_user_id)
                DO UPDATE SET
                    chat_id = EXCLUDED.chat_id,
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    language_code = EXCLUDED.language_code,
                    is_bot = EXCLUDED.is_bot,
                    last_seen_at = now(),
                    updated_at = now()
                RETURNING *
                """,
                (
                    telegram_user_id,
                    chat_id,
                    username,
                    first_name,
                    last_name,
                    language_code,
                    is_bot,
                    default_timezone,
                ),
            ).fetchone()
        return self._row_to_telegram_user(row)

    def list_active_users(self) -> list[TelegramUser]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT u.*
                FROM public.telegram_users u
                INNER JOIN public.watched_products w
                    ON w.telegram_user_id = u.telegram_user_id
                WHERE w.active = TRUE
                ORDER BY u.telegram_user_id ASC
                """
            ).fetchall()
        return [self._row_to_telegram_user(row) for row in rows]

    def mark_daily_report_sent(self, telegram_user_id: int, local_date: date) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE public.telegram_users
                SET last_daily_report_on = %s,
                    updated_at = now()
                WHERE telegram_user_id = %s
                """,
                (local_date, telegram_user_id),
            )

    def upsert_watching_product(
        self,
        *,
        telegram_user_id: int,
        name: str,
        url: str,
        vendor_id: str,
    ) -> WatchingProduct:
        with self.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO public.watched_products (
                    telegram_user_id,
                    name,
                    url,
                    vendor_id,
                    active
                )
                VALUES (%s, %s, %s, %s, TRUE)
                ON CONFLICT (telegram_user_id, url)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    vendor_id = EXCLUDED.vendor_id,
                    active = TRUE,
                    updated_at = now()
                RETURNING *
                """,
                (telegram_user_id, name, url, vendor_id),
            ).fetchone()
        return self._row_to_watching_product(row)

    def list_active_watches_for_user(self, telegram_user_id: int) -> list[WatchingProduct]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM public.watched_products
                WHERE telegram_user_id = %s
                  AND active = TRUE
                ORDER BY created_at ASC
                """,
                (telegram_user_id,),
            ).fetchall()
        return [self._row_to_watching_product(row) for row in rows]

    def get_watch_for_user(
        self,
        telegram_user_id: int,
        watch_id: int,
    ) -> WatchingProduct | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM public.watched_products
                WHERE telegram_user_id = %s
                  AND id = %s
                  AND active = TRUE
                """,
                (telegram_user_id, watch_id),
            ).fetchone()
        return self._row_to_watching_product(row) if row else None

    def remove_watch(
        self,
        telegram_user_id: int,
        identifier: str,
    ) -> WatchingProduct | None:
        with self.connect() as connection:
            if identifier.isdigit():
                row = connection.execute(
                    """
                    UPDATE public.watched_products
                    SET active = FALSE,
                        updated_at = now()
                    WHERE telegram_user_id = %s
                      AND id = %s
                      AND active = TRUE
                    RETURNING *
                    """,
                    (telegram_user_id, int(identifier)),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    UPDATE public.watched_products
                    SET active = FALSE,
                        updated_at = now()
                    WHERE telegram_user_id = %s
                      AND url = %s
                      AND active = TRUE
                    RETURNING *
                    """,
                    (telegram_user_id, identifier),
                ).fetchone()
        return self._row_to_watching_product(row) if row else None

    def save_price_snapshot(self, watch_id: int, product: Product) -> PriceSnapshot:
        with self.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO public.price_snapshots (
                    watching_product_id,
                    observed_at,
                    product_name,
                    product_price,
                    currency,
                    in_stock,
                    article_number,
                    raw_payload
                )
                VALUES (%s, now(), %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    watch_id,
                    product.name,
                    product.price,
                    product.currency,
                    product.in_stock,
                    product.article_number,
                    product.raw_payload,
                ),
            ).fetchone()
        return self._row_to_price_snapshot(row)

    def get_previous_snapshot(self, watch_id: int) -> PriceSnapshot | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM public.price_snapshots
                WHERE watching_product_id = %s
                ORDER BY observed_at DESC
                LIMIT 1
                """,
                (watch_id,),
            ).fetchone()
        return self._row_to_price_snapshot(row) if row else None

    def list_price_history_for_user(
        self,
        telegram_user_id: int,
        watch_id: int,
        limit: int = 90,
    ) -> list[PriceSnapshot]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT s.*
                FROM public.price_snapshots s
                INNER JOIN public.watched_products w
                    ON w.id = s.watching_product_id
                WHERE w.telegram_user_id = %s
                  AND w.id = %s
                ORDER BY s.observed_at DESC
                LIMIT %s
                """,
                (telegram_user_id, watch_id, limit),
            ).fetchall()
        snapshots = [self._row_to_price_snapshot(row) for row in rows]
        snapshots.reverse()
        return snapshots

    def list_vendor_ids_for_user(self, telegram_user_id: int) -> tuple[str, ...]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT vendor_id
                FROM public.watched_products
                WHERE telegram_user_id = %s
                  AND active = TRUE
                ORDER BY vendor_id ASC
                """,
                (telegram_user_id,),
            ).fetchall()
        return tuple(row["vendor_id"] for row in rows)

    def save_new_discounts(self, discounts: list[Discount], observed_on: date) -> list[Discount]:
        inserted: list[Discount] = []
        with self.connect() as connection:
            for discount in discounts:
                fingerprint = hashlib.sha1(
                    json.dumps(
                        {
                            "code": discount.code,
                            "condition": discount.condition,
                            "source_url": discount.source_url,
                        },
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest()

                row = connection.execute(
                    """
                    INSERT INTO public.discount_snapshots (
                        vendor_id,
                        observed_on,
                        code,
                        condition,
                        source_url,
                        fingerprint
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (vendor_id, observed_on, fingerprint)
                    DO NOTHING
                    RETURNING vendor_id, code, condition, source_url
                    """,
                    (
                        discount.vendor_id,
                        observed_on,
                        discount.code,
                        discount.condition,
                        discount.source_url,
                        fingerprint,
                    ),
                ).fetchone()
                if row:
                    inserted.append(
                        Discount(
                            vendor_id=row["vendor_id"],
                            code=row["code"],
                            condition=row["condition"],
                            source_url=row["source_url"],
                        )
                    )
        return inserted

    def list_discounts_for_date(
        self,
        observed_on: date,
        vendor_ids: tuple[str, ...] | None = None,
    ) -> list[Discount]:
        with self.connect() as connection:
            if vendor_ids:
                rows = connection.execute(
                    """
                    SELECT vendor_id, code, condition, source_url
                    FROM public.discount_snapshots
                    WHERE observed_on = %s
                      AND vendor_id = ANY(%s)
                    ORDER BY vendor_id ASC, created_at ASC
                    """,
                    (observed_on, list(vendor_ids)),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT vendor_id, code, condition, source_url
                    FROM public.discount_snapshots
                    WHERE observed_on = %s
                    ORDER BY vendor_id ASC, created_at ASC
                    """,
                    (observed_on,),
                ).fetchall()
        return [
            Discount(
                vendor_id=row["vendor_id"],
                code=row["code"],
                condition=row["condition"],
                source_url=row["source_url"],
            )
            for row in rows
        ]

    def _row_to_telegram_user(self, row: dict) -> TelegramUser:
        return TelegramUser(
            telegram_user_id=row["telegram_user_id"],
            chat_id=row["chat_id"],
            username=row["username"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            language_code=row["language_code"],
            is_bot=bool(row["is_bot"]),
            timezone=row["timezone"],
            last_daily_report_on=row["last_daily_report_on"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_watching_product(self, row: dict) -> WatchingProduct:
        return WatchingProduct(
            id=row["id"],
            telegram_user_id=row["telegram_user_id"],
            name=row["name"],
            url=row["url"],
            vendor_id=row["vendor_id"],
            active=bool(row["active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_price_snapshot(self, row: dict) -> PriceSnapshot:
        return PriceSnapshot(
            id=row["id"],
            watching_product_id=row["watching_product_id"],
            observed_at=row["observed_at"],
            product_name=row["product_name"],
            product_price=row["product_price"]
            if isinstance(row["product_price"], Decimal)
            else Decimal(str(row["product_price"])),
            currency=row["currency"],
            in_stock=bool(row["in_stock"]),
            article_number=row["article_number"],
        )
