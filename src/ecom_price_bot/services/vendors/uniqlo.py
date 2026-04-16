from __future__ import annotations

import json
from decimal import Decimal

from ecom_price_bot.models import Product
from ecom_price_bot.services.vendor_base import GenericVendorService

_PRELOADED_STATE_MARKER = "window.__PRELOADED_STATE__ = "


class UniqloVendor(GenericVendorService):
    vendor_id = "uniqlo"
    supported_hosts = ("uniqlo.com",)
    discount_seed_urls = ("https://www.uniqlo.com/us/en/",)

    def parse_product_html(self, *, html_text: str, normalized_url: str, source_url: str) -> Product:
        parsed = self._extract_preloaded_product(html_text, normalized_url)
        if parsed is not None:
            return Product(
                vendor_id=self.vendor_id,
                name=self.clean_product_name(str(parsed["name"])),
                url=str(parsed["url"]),
                price=parsed["price"],
                currency=str(parsed["currency"]),
                in_stock=bool(parsed["in_stock"]),
                article_number=parsed.get("article_number"),
                raw_payload=f"source_url={source_url}",
            )
        return super().parse_product_html(
            html_text=html_text,
            normalized_url=normalized_url,
            source_url=source_url,
        )

    def clean_product_name(self, name: str) -> str:
        cleaned = super().clean_product_name(name)
        if "|" in cleaned and "uniqlo" in cleaned.casefold():
            cleaned = cleaned.split("|", maxsplit=1)[0].strip()
        return cleaned

    def _extract_preloaded_product(
        self,
        html_text: str,
        normalized_url: str,
    ) -> dict[str, object] | None:
        state = self._extract_preloaded_state(html_text)
        if state is None:
            return None

        pdp_key = str(state.get("pdp", {}).get("product") or "").strip()
        entity = state.get("entity", {})
        if not isinstance(entity, dict):
            return None
        pdp_entity = entity.get("pdpEntity", {})
        if not isinstance(pdp_entity, dict) or not pdp_entity:
            return None

        product_entry = pdp_entity.get(pdp_key) if pdp_key else None
        if not isinstance(product_entry, dict):
            product_entry = next(
                (value for value in pdp_entity.values() if isinstance(value, dict)),
                None,
            )
        if not isinstance(product_entry, dict):
            return None

        product = product_entry.get("product", {})
        if not isinstance(product, dict):
            return None

        prices = product.get("prices", {})
        if not isinstance(prices, dict):
            return None
        price_info = prices.get("promo") or prices.get("base")
        if not isinstance(price_info, dict):
            return None

        currency_info = price_info.get("currency", {})
        if not isinstance(currency_info, dict):
            currency_info = {}
        currency = str(currency_info.get("code") or "").upper()
        price_value = price_info.get("value")
        if price_value is None or not currency:
            return None

        representative = product.get("representative", {})
        if not isinstance(representative, dict):
            representative = {}

        article_number = representative.get("itemId") or product.get("productId")

        return {
            "name": str(product.get("name") or "").strip(),
            "url": normalized_url,
            "price": Decimal(str(price_value)),
            "currency": currency,
            "in_stock": bool(representative.get("sales", True)),
            "article_number": str(article_number).strip() if article_number else None,
        }

    def _extract_preloaded_state(self, html_text: str) -> dict[str, object] | None:
        start = html_text.find(_PRELOADED_STATE_MARKER)
        if start == -1:
            return None
        start += len(_PRELOADED_STATE_MARKER)

        end = html_text.find("</script>", start)
        if end == -1:
            return None

        raw_state = html_text[start:end].strip()
        if raw_state.endswith(";"):
            raw_state = raw_state[:-1]

        try:
            parsed = json.loads(raw_state)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
