from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from ecom_price_bot.models import PriceSnapshot, WatchingProduct
from ecom_price_bot.telegram.formatting import format_currency


def render_price_history_chart(watch: WatchingProduct, history: list[PriceSnapshot]) -> bytes:
    width = 900
    height = 480
    margin_left = 80
    margin_right = 40
    margin_top = 70
    margin_bottom = 80

    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    title = f"Price history: {watch.name[:70]}"
    draw.text((margin_left, 20), title, fill="#111827", font=font)

    if not history:
        draw.text((margin_left, 120), "No price history available yet.", fill="#6b7280", font=font)
        return _to_png_bytes(image)

    prices = [float(snapshot.product_price) for snapshot in history]
    min_price = min(prices)
    max_price = max(prices)
    if min_price == max_price:
        min_price -= 1.0
        max_price += 1.0

    padding = max((max_price - min_price) * 0.1, 1.0)
    lower_bound = min_price - padding
    upper_bound = max_price + padding

    plot_left = margin_left
    plot_top = margin_top
    plot_right = width - margin_right
    plot_bottom = height - margin_bottom
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    draw.rectangle((plot_left, plot_top, plot_right, plot_bottom), outline="#d1d5db", width=1)

    y_steps = 5
    for step in range(y_steps + 1):
        ratio = step / y_steps
        y = plot_bottom - int(plot_height * ratio)
        price_value = lower_bound + (upper_bound - lower_bound) * ratio
        draw.line((plot_left, y, plot_right, y), fill="#e5e7eb", width=1)
        label = f"{price_value:.2f}"
        draw.text((10, y - 6), label, fill="#6b7280", font=font)

    if len(history) == 1:
        x_points = [plot_left + plot_width // 2]
    else:
        x_points = [
            plot_left + int(index * plot_width / (len(history) - 1))
            for index in range(len(history))
        ]

    points: list[tuple[int, int]] = []
    for x, snapshot in zip(x_points, history, strict=True):
        ratio = (float(snapshot.product_price) - lower_bound) / (upper_bound - lower_bound)
        y = plot_bottom - int(ratio * plot_height)
        points.append((x, y))

    if len(points) >= 2:
        draw.line(points, fill="#0f766e", width=3)
    for x, y in points:
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill="#0f766e", outline="#ffffff")

    label_count = min(6, len(history))
    if label_count == 1:
        label_indexes = [0]
    else:
        label_indexes = sorted(
            {
                round(index * (len(history) - 1) / (label_count - 1))
                for index in range(label_count)
            }
        )

    for index in label_indexes:
        x = x_points[index]
        label = history[index].observed_at.strftime("%Y-%m-%d")
        draw.text((x - 30, plot_bottom + 12), label, fill="#6b7280", font=font)

    latest = history[-1]
    summary = (
        f"Latest: {format_currency(latest.product_price, latest.currency)}   "
        f"Points: {len(history)}   Vendor: {watch.vendor_id}"
    )
    draw.text((margin_left, height - 35), summary, fill="#111827", font=font)

    return _to_png_bytes(image)


def _to_png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
