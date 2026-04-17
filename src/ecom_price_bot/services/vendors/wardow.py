from __future__ import annotations

from ecom_price_bot.services.vendor_base import GenericVendorService


class WardowVendor(GenericVendorService):
    vendor_id = "wardow"
    supported_hosts = ("wardow.com",)
    discount_seed_urls = (
        "https://www.wardow.com/en/",
        "https://www.wardow.com/",
    )
