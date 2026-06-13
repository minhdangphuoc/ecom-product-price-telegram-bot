from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from html import escape

from ecom_price_bot.models import DailyReport, InregoItem, PriceUpdate, WatchingProduct

MAX_DISCOUNTS_PER_VENDOR = 10
MAX_MESSAGE_LENGTH = 3800


def format_watch_index(watch: WatchingProduct) -> str:
    return str(watch.display_index) if watch.display_index is not None else "?"


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _product_link(url: str, label: str = "Open product") -> str:
    return f'<a href="{_e(url)}">{_e(label)}</a>'


def format_currency(amount: Decimal, currency: str) -> str:
    symbols = {"EUR": "EUR ", "USD": "USD ", "GBP": "GBP "}
    return f"{symbols.get(currency.upper(), currency.upper() + ' ')}{amount:.2f}"


def format_price_update(update: PriceUpdate) -> str:
    header = f"🧾 <b>[{format_watch_index(update.watch)}] {_e(update.current.name)}</b>"
    price_line = f"💰 <b>{format_currency(update.current.price, update.current.currency)}</b>"
    if update.delta is not None:
        direction = "down" if update.delta < 0 else "up" if update.delta > 0 else "same"
        if direction == "same":
            price_line += "  •  ➖ unchanged"
        else:
            trend_icon = "📉" if direction == "down" else "📈"
            price_line += f"  •  {trend_icon} {direction} {abs(update.delta):.2f}"
    else:
        price_line += "  •  🆕 new watch"
    details = [header, price_line, f"🏷️ Vendor: {_e(update.current.vendor_id)}"]
    if not update.current.in_stock:
        details.append("📦 Status: Out of stock")
    details.append(f"🔗 {_product_link(update.watch.url)}")
    return "\n".join(details)


def format_watch_list(watches: list[WatchingProduct]) -> str:
    if not watches:
        return (
            "👀 <b>Your watchlist is empty</b>\n"
            "<i>Add a product link to start tracking drops and discount codes.</i>\n\n"
            "Use <code>/watch &lt;product-url&gt;</code> to add one."
        )
    parts = [
        "👀 <b>Your Watchlist</b>\n"
        "<i>Products are numbered from 1 so you can quickly remove them or open charts.</i>"
    ]
    for watch in watches:
        parts.append(
            f"🛍️ <b>[{format_watch_index(watch)}] {_e(watch.name)}</b>\n"
            f"🏷️ Vendor: {_e(watch.vendor_id)}\n"
            f"🔗 {_product_link(watch.url)}\n"
            f"📈 Use <code>/chart {format_watch_index(watch)}</code> for a price chart."
        )
    return "\n\n".join(parts)


_INREGO_CONDITION_LABELS = {"hyvä": "Good", "loistava": "Excellent", "tyydyttävä": "Fair"}


def _format_euro(amount: Decimal) -> str:
    quantized = amount.quantize(Decimal("1")) if amount == amount.to_integral_value() else amount
    return f"{quantized:,} €".replace(",", " ")


def _format_inrego_item(item: InregoItem) -> str:
    lines = [f"💻 <b>{_e(item.name)}</b>"]

    if item.old_price is not None and item.old_price > item.price:
        price_line = f"💰 <b>{_format_euro(item.price)}</b>  <s>{_format_euro(item.old_price)}</s>"
        if item.discount_label:
            price_line += f"  •  🔻 {_e(item.discount_label)}"
    else:
        price_line = f"💰 <b>{_format_euro(item.price)}</b>"
    lines.append(price_line)

    if item.specs:
        lines.append(f"🔧 {_e(' · '.join(item.specs))}")

    meta = []
    if item.condition:
        meta.append(_INREGO_CONDITION_LABELS.get(item.condition.lower(), item.condition))
    if item.size:
        meta.append(item.size)
    if item.color:
        meta.append(item.color)
    if meta:
        lines.append(f"🏷️ {_e(' · '.join(meta))}")

    if not item.in_stock:
        lines.append("📦 Status: Out of stock")
    lines.append(f"🔗 {_product_link(item.url)}")
    return "\n".join(lines)


def format_inrego_section(items: list[InregoItem]) -> str:
    header = (
        "💻 <b>Inrego MacBooks</b>\n"
        "<i>Live refurbished stock — sells out fast.</i>"
    )
    if not items:
        return header + "\n\nNo MacBooks listed right now."
    return header + "\n\n" + "\n\n".join(_format_inrego_item(item) for item in items)


def format_daily_report(report: DailyReport) -> str:
    sections: list[str] = [
        "✨ <b>Ecom Price Bot</b>\n<i>Fresh price tracking and promo-code updates.</i>"
    ]
    if report.updates:
        sections.append(
            "📦 <b>Price Updates</b>\n\n"
            + "\n\n".join(format_price_update(update) for update in report.updates)
        )
    else:
        sections.append(
            "📦 <b>Price Updates</b>\n\n"
            "No watched products yet."
        )

    if report.new_discounts:
        grouped: dict[str, list[str]] = defaultdict(list)
        for discount in report.new_discounts:
            line = _e(discount.condition)
            if discount.code:
                line = f"{line}\n🎟️ Code: <code>{_e(discount.code)}</code>"
            line += f'\n🔗 <a href="{_e(discount.source_url)}">Open source</a>'
            grouped[discount.vendor_id].append(line)

        discount_blocks = []
        for vendor_id, items in grouped.items():
            visible_items = items[:MAX_DISCOUNTS_PER_VENDOR]
            block = f"<b>{_e(vendor_id)}</b>\n" + "\n\n".join(visible_items)
            hidden_count = len(items) - len(visible_items)
            if hidden_count > 0:
                block += f"\n\n...and {hidden_count} more discount items."
            discount_blocks.append(block)
        sections.append("🎟️ <b>Discount Codes</b>\n\n" + "\n\n".join(discount_blocks))

    if report.errors:
        sections.append(
            "⚠️ <b>Warnings</b>\n\n" + "\n".join(f"• {_e(error)}" for error in report.errors)
        )

    return "\n\n".join(sections)


def format_help() -> str:
    return (
        "✨ <b>Ecom Price Bot</b>\n"
        "<i>Track products, check promo codes, and view price charts.</i>\n\n"
        "<b>Commands</b>\n"
        "<code>/watch &lt;url&gt;</code> - add a product to the watch list\n"
        "<code>/add &lt;url&gt;</code> - alias for /watch\n"
        "<code>/list</code> - show watched products\n"
        "<code>/remove &lt;index|url&gt;</code> - remove a watched product\n"
        "<code>/refresh</code> - fetch prices and discounts now\n"
        "<code>/discounts</code> - fetch only discounts now\n"
        "<code>/chart &lt;index&gt;</code> - show a price history chart\n"
        "<code>/inrego-mac</code> - list live MacBook deals from Inrego\n"
        "<code>/help</code> - show this message"
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
