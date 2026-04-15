from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ecom_price_bot.models import Product
from ecom_price_bot.services.http_client import (
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    FetchError,
    HttpResponse,
)
from ecom_price_bot.services.vendor_base import GenericVendorService


class PrismaVendor(GenericVendorService):
    vendor_id = "prisma"
    supported_hosts = ("prisma.fi",)
    # Prisma product pages expose structured product data cleanly, but the
    # generic discount extractor currently picks up internal mapping strings on
    # the storefront and produces false promo codes. Keep discount crawling off
    # until Prisma-specific promo parsing is added.
    discount_seed_urls = ()

    def fetch_product(self, url: str) -> Product:
        normalized_url = self.normalize_product_url(url)
        try:
            return super().fetch_product(normalized_url)
        except FetchError as exc:
            if "HTTP 403" not in str(exc):
                raise

        response = self._fallback_get(normalized_url)
        if self.is_block_page(response.text):
            raise ValueError(self.block_page_message(normalized_url))
        return self.parse_product_html(
            html_text=response.text,
            normalized_url=normalized_url,
            source_url=response.url,
        )

    def _fallback_get(self, url: str) -> HttpResponse:
        request = Request(
            url,
            headers={
                "Accept-Language": "fi-FI,fi;q=0.9,en-US;q=0.8,en;q=0.7",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/135.0.0.0 Safari/537.36"
                ),
            },
        )
        try:
            with urlopen(request, timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8", "ignore")
                return HttpResponse(
                    url=str(response.geturl()),
                    status_code=response.status,
                    text=body,
                )
        except HTTPError as exc:
            raise FetchError(f"Failed to fetch {url}: HTTP {exc.code}") from exc
        except URLError as exc:
            raise FetchError(f"Failed to fetch {url}: {exc.reason}") from exc
