from __future__ import annotations

from ecom_price_bot.services.vendor_base import GenericVendorService


class PrismaVendor(GenericVendorService):
    vendor_id = "prisma"
    supported_hosts = ("prisma.fi",)
    # Prisma product pages expose structured product data cleanly, but the
    # generic discount extractor currently picks up internal mapping strings on
    # the storefront and produces false promo codes. Keep discount crawling off
    # until Prisma-specific promo parsing is added.
    discount_seed_urls = ()
