from __future__ import annotations

from ecom_price_bot.services.vendor_base import GenericVendorService


class NotinoVendor(GenericVendorService):
    vendor_id = "notino"
    supported_hosts = (
        "notino.fi",
        "notino.se",
        "notino.no",
        "notino.dk",
        "notino.ee",
        "notino.lv",
        "notino.lt",
        "notino.pl",
        "notino.cz",
        "notino.sk",
        "notino.hu",
        "notino.ro",
        "notino.bg",
        "notino.hr",
        "notino.si",
        "notino.gr",
        "notino.de",
        "notino.at",
        "notino.fr",
        "notino.it",
        "notino.es",
        "notino.pt",
        "notino.ie",
        "notino.co.uk",
    )
    discount_seed_urls = (
        "https://www.notino.fi/",
        "https://www.notino.fi/kupongit-ja-notino-alennuskoodit/",
        "https://www.notino.fi/alennusmyynti/",
    )
