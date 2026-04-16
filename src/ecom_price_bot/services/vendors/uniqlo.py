from __future__ import annotations

from ecom_price_bot.services.vendor_base import GenericVendorService


class UniqloVendor(GenericVendorService):
    vendor_id = "uniqlo"
    supported_hosts = ("uniqlo.com",)
    discount_seed_urls = ("https://www.uniqlo.com/us/en/",)
