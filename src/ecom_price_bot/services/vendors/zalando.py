from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from ecom_price_bot.services.vendor_base import GenericVendorService


class ZalandoVendor(GenericVendorService):
    vendor_id = "zalando"
    supported_hosts = ("zalando.de", "zalando.com", "zalando.nl", "zalando.be", "zalando.pl")
    discount_seed_urls = ("https://en.zalando.de/",)

    def normalize_product_url(self, url: str) -> str:
        parts = urlsplit(url)
        cleaned_query = ""
        return urlunsplit((parts.scheme, parts.netloc, parts.path, cleaned_query, ""))

    def get_discount_urls(self) -> tuple[str, ...]:
        return self.discount_seed_urls

    def clean_product_name(self, name: str) -> str:
        cleaned = super().clean_product_name(name)
        return cleaned.replace(" | ZALANDO", "").replace(" - Zalando", "").replace(" - ZALANDO", "")

    def is_block_page(self, html_text: str) -> bool:
        lowered = html_text.lower()
        markers = (
            "site can't be reached right now",
            "entity-dns-error",
            "powered and protected by privacy",
            "powered and protected by",
            "akamai-logo",
            "akamai-privacy",
        )
        return any(marker in lowered for marker in markers)

    def block_page_message(self, url: str) -> str:
        return (
            f"Zalando returned a protection or temporary error page for {url}. "
            "This environment may need a browser session, a different network path, or a fresh session token."
        )
