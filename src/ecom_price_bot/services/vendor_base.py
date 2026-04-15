from __future__ import annotations

from abc import ABC
from urllib.parse import urlsplit, urlunsplit

from ecom_price_bot.models import Discount, Product
from ecom_price_bot.services.http_client import WebClient
from ecom_price_bot.services.parsing import (
    extract_article_number,
    extract_discount_code,
    extract_discount_texts,
    extract_meta_product,
    extract_price_from_text,
    extract_structured_product,
    extract_text,
    extract_title,
    normalize_url,
)


class GenericVendorService(ABC):
    vendor_id: str = ""
    supported_hosts: tuple[str, ...] = ()
    discount_seed_urls: tuple[str, ...] = ()

    def __init__(self, web_client: WebClient) -> None:
        self.web_client = web_client

    @classmethod
    def supports(cls, url: str) -> bool:
        host = urlsplit(url).netloc.lower()
        return any(host.endswith(supported_host) for supported_host in cls.supported_hosts)

    def normalize_product_url(self, url: str) -> str:
        return normalize_url(url)

    def fetch_product(self, url: str) -> Product:
        normalized_url = self.normalize_product_url(url)
        response = self.web_client.get(normalized_url)
        if self.is_block_page(response.text):
            raise ValueError(self.block_page_message(normalized_url))
        return self.parse_product_html(html_text=response.text, normalized_url=normalized_url, source_url=response.url)

    def parse_product_html(self, *, html_text: str, normalized_url: str, source_url: str) -> Product:
        parsed = extract_structured_product(html_text, normalized_url)
        if parsed is None:
            parsed = extract_meta_product(html_text, normalized_url)
        if parsed is None:
            text = extract_text(html_text)
            price_data = extract_price_from_text(text)
            if price_data is None:
                raise ValueError(f"Could not parse price for {normalized_url}")
            price, currency = price_data
            parsed = {
                "name": self.clean_product_name(extract_title(html_text)),
                "url": normalized_url,
                "price": price,
                "currency": currency,
                "in_stock": "out of stock" not in text.lower(),
                "article_number": extract_article_number(text),
            }
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

    def fetch_discounts(self) -> list[Discount]:
        discounts: list[Discount] = []
        seen: set[tuple[str | None, str]] = set()
        for url in self.get_discount_urls():
            response = self.web_client.get(url)
            if self.is_block_page(response.text):
                raise ValueError(self.block_page_message(response.url))
            for text in extract_discount_texts(response.text):
                cleaned_condition = self.clean_discount_condition(text)
                key = (extract_discount_code(cleaned_condition), cleaned_condition.casefold())
                if key in seen:
                    continue
                seen.add(key)
                discounts.append(
                    Discount(
                        vendor_id=self.vendor_id,
                        code=extract_discount_code(cleaned_condition),
                        condition=cleaned_condition,
                        source_url=response.url,
                    )
                )
        return discounts

    def clean_product_name(self, name: str) -> str:
        return " ".join(name.split())

    def clean_discount_condition(self, text: str) -> str:
        return " ".join(text.split())

    def get_discount_urls(self) -> tuple[str, ...]:
        return self.discount_seed_urls

    def base_url_from_product(self, url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, "/", "", ""))

    def is_block_page(self, html_text: str) -> bool:
        return False

    def block_page_message(self, url: str) -> str:
        return f"Access to {url} appears to be blocked."
