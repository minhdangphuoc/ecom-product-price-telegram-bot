from __future__ import annotations

import re

from ecom_price_bot.services.vendor_base import GenericVendorService


class BooztletVendor(GenericVendorService):
    vendor_id = "booztlet"
    supported_hosts = ("booztlet.com",)
    discount_seed_urls = (
        "https://www.booztlet.com/eu/en",
        "https://www.booztlet.com/eu/en/campaigns/women",
    )

    def clean_product_name(self, name: str) -> str:
        cleaned = super().clean_product_name(name)
        return re.sub(r"\s+[\u2013-]\s+shop at Booztlet$", "", cleaned)
