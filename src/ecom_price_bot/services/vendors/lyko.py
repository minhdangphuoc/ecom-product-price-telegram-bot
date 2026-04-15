from __future__ import annotations

from ecom_price_bot.services.vendor_base import GenericVendorService


class LykoVendor(GenericVendorService):
    vendor_id = "lyko"
    supported_hosts = (
        "lyko.com",
        "lyko.se",
        "lyko.no",
        "lyko.fi",
        "lyko.dk",
        "lyko.de",
        "lyko.nl",
        "lyko.at",
        "lyko.it",
        "lyko.fr",
        "lyko.es",
        "lyko.pl",
        "lyko.co.uk",
    )
    discount_seed_urls = (
        "https://lyko.com/en",
        "https://lyko.com/en/deals-steals/campaigns",
        "https://lyko.com/en/sale",
    )
