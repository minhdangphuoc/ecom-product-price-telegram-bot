from __future__ import annotations

import re

from ecom_price_bot.services.vendor_base import GenericVendorService


class BooztVendor(GenericVendorService):
    vendor_id = "boozt"
    supported_hosts = ("boozt.com",)
    discount_seed_urls = (
        "https://www.boozt.com/eu/en",
        "https://www.boozt.com/eu/en/campaigns",
    )

    def clean_product_name(self, name: str) -> str:
        cleaned = super().clean_product_name(name)
        return re.sub(r"\s+[\u2013-]\s+shop at Boozt\.com$", "", cleaned)
