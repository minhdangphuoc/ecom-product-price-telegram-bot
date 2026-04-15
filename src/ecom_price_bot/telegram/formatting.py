from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from ecom_price_bot.models import DailyReport, PriceUpdate, WatchingProduct

MAX_DISCOUNTS_PER_VENDOR = 10
MAX_MESSAGE_LENGTH = 3800


def format_currency(amount: Decimal, currency: str) -> str:
    symbols = {"EUR": "EUR ", "USD": "USD ", "GBP": "GBP "}
    return f"{symbols.get(currency.upper(), currency.upper() + ' ')}{amount:.2f}"


def format_price_update(update: PriceUpdate) -> str:
    base = f"[{update.watch.id}] {update.current.name}\n{format_currency(update.current.price, update.current.currency)}"
    if update.delta is not None:
        direction = "down" if update.delta < 0 else "up" if update.delta > 0 else "same"
        if direction == "same":
            base += " (unchanged)"
        else:
            base += f" ({direction} {abs(update.delta):.2f})"
    else:
        base += " (new watch)"
    if not update.current.in_stock:
        base += "\nStatus: Out of stock"
    base += f"\nVendor: {update.current.vendor_id}\n{update.watch.url}"
    return base


def format_watch_list(watches: list[WatchingProduct]) -> str:
    if not watches:
        return "No watched products yet. Use /watch <product-url> to add one."
    parts = ["Watching products:"]
    for watch in watches:
        parts.append(
            f"[{watch.id}] {watch.name} ({watch.vendor_id})\n"
            f"{watch.url}\n"
            f"Use /chart {watch.id} for a price chart."
        )
    return "\n\n".join(parts)


def format_daily_report(report: DailyReport) -> str:
    sections: list[str] = []
    if report.updates:
        sections.append(
            "Daily price update:\n\n" + "\n\n".join(format_price_update(update) for update in report.updates)
        )
    else:
        sections.append("Daily price update:\n\nNo watched products yet.")

    if report.new_discounts:
        grouped: dict[str, list[str]] = defaultdict(list)
        for discount in report.new_discounts:
            line = discount.condition
            if discount.code:
                line = f"{line}\nCode: {discount.code}"
            line += f"\n{discount.source_url}"
            grouped[discount.vendor_id].append(line)

        discount_blocks = []
        for vendor_id, items in grouped.items():
            visible_items = items[:MAX_DISCOUNTS_PER_VENDOR]
            block = f"{vendor_id}:\n" + "\n\n".join(visible_items)
            hidden_count = len(items) - len(visible_items)
            if hidden_count > 0:
                block += f"\n\n...and {hidden_count} more discount items."
            discount_blocks.append(block)
        sections.append("New discount codes today:\n\n" + "\n\n".join(discount_blocks))

    if report.errors:
        sections.append("Warnings:\n\n" + "\n".join(f"- {error}" for error in report.errors))

    return "\n\n".join(sections)


def format_help() -> str:
    return (
        "Commands:\n"
        "/watch <url> - add a product to the watch list\n"
        "/add <url> - alias for /watch\n"
        "/list - show watched products\n"
        "/remove <id|url> - remove a watched product\n"
        "/refresh - fetch prices and discounts now\n"
        "/discounts - fetch only discounts now\n"
        "/chart <id> - show a price history chart for a watched product\n"
        "/help - show this message"
    )


def split_message(text: str, *, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_length:
        split_at = remaining.rfind("\n\n", 0, max_length)
        if split_at == -1:
            split_at = remaining.rfind("\n", 0, max_length)
        if split_at == -1:
            split_at = max_length
        chunk = remaining[:split_at].rstrip()
        if not chunk:
            chunk = remaining[:max_length]
            split_at = max_length
        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
