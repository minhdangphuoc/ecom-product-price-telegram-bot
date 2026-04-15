from __future__ import annotations

import html
import json
import re
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup


PROMO_HINT_PATTERN = re.compile(r"(?i)\b(code|voucher|coupon|promo|discount|save|off|deal|sale)\b")
NOISE_PATTERN = re.compile(
    r"(?i)\b(newsletter|gift card|return policy|privacy|track your parcel|investor|careers)\b"
)
CODE_PATTERN = re.compile(
    r"(?i)\b(?:code|voucher|coupon|promo(?:tional)?(?:\s+code)?|discount(?:\s+code)?)\b"
    r"[^A-Z0-9]{0,24}([A-Z0-9-]{4,20})"
)
PRICE_WITH_SYMBOL_PATTERN = re.compile(
    "([$\\u20ac\\u00a3])\\s*([0-9]+(?:[.,][0-9]{2})?)"
)
PRICE_WITH_CODE_PATTERN = re.compile(r"\b(EUR|USD|GBP)\s*([0-9]+(?:[.,][0-9]{2})?)\b", re.I)
ARTICLE_NUMBER_PATTERN = re.compile(r"(?i)article number[:\s]+([A-Z0-9-]+)")


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def parse_json_ld_documents(html_text: str) -> list[object]:
    soup = BeautifulSoup(html_text, "html.parser")
    documents: list[object] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw_text = script.string or script.get_text(strip=True)
        if not raw_text:
            continue
        try:
            documents.append(json.loads(raw_text))
        except json.JSONDecodeError:
            continue
    return documents


def walk_json(node: object):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk_json(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_json(item)


def extract_structured_product(html_text: str, current_url: str) -> dict[str, object] | None:
    documents = parse_json_ld_documents(html_text)
    normalized_url = normalize_url(current_url)

    for document in documents:
        for node in walk_json(document):
            if not isinstance(node, dict):
                continue
            type_value = node.get("@type")
            type_names = (
                {type_value}
                if isinstance(type_value, str)
                else set(type_value or [])
                if isinstance(type_value, list)
                else set()
            )
            if not {"Product", "ProductGroup"} & type_names:
                continue

            product = _extract_product_candidate(node, normalized_url)
            if product is not None:
                return product
    return None


def _extract_product_candidate(node: dict[str, object], current_url: str) -> dict[str, object] | None:
    variants = node.get("hasVariant")
    if isinstance(variants, list):
        best_variant = None
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            variant_url = normalize_url(str(variant.get("url", "")))
            if variant_url and variant_url == current_url:
                best_variant = variant
                break
            if best_variant is None and variant.get("offers"):
                best_variant = variant
        if best_variant is not None:
            product = _build_product_candidate(best_variant, node.get("name"), current_url)
            if product is not None:
                return product

    return _build_product_candidate(node, None, current_url)


def _build_product_candidate(
    node: dict[str, object],
    fallback_name: object,
    current_url: str,
) -> dict[str, object] | None:
    offers = node.get("offers")
    if isinstance(offers, list):
        offers = next((offer for offer in offers if isinstance(offer, dict)), None)
    if not isinstance(offers, dict):
        offers = {}

    price = offers.get("price") or offers.get("lowPrice")
    currency = offers.get("priceCurrency")
    if price is None or currency is None:
        return None

    availability = str(offers.get("availability", ""))
    return {
        "name": str(node.get("name") or fallback_name or "").strip(),
        "url": normalize_url(str(node.get("url") or current_url)),
        "price": Decimal(str(price)),
        "currency": str(currency).upper(),
        "in_stock": "outofstock" not in availability.lower(),
        "article_number": str(node.get("sku") or node.get("productID") or "").strip() or None,
    }


def extract_meta_product(html_text: str, current_url: str) -> dict[str, object] | None:
    soup = BeautifulSoup(html_text, "html.parser")
    meta_price = soup.find("meta", attrs={"property": "product:price:amount"})
    meta_currency = soup.find("meta", attrs={"property": "product:price:currency"})
    if meta_price and meta_currency and meta_price.get("content") and meta_currency.get("content"):
        return {
            "name": extract_title(html_text),
            "url": normalize_url(current_url),
            "price": Decimal(meta_price["content"]),
            "currency": meta_currency["content"].upper(),
            "in_stock": "out of stock" not in extract_text(html_text).lower(),
            "article_number": extract_article_number(extract_text(html_text)),
        }
    return None


def extract_title(html_text: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    if soup.title and soup.title.string:
        return " ".join(soup.title.string.split())
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        return " ".join(str(og_title["content"]).split())
    h1 = soup.find(["h1", "h2"])
    return " ".join(h1.get_text(" ", strip=True).split()) if h1 else "Unknown product"


def extract_text(html_text: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def extract_article_number(text: str) -> str | None:
    match = ARTICLE_NUMBER_PATTERN.search(text)
    return match.group(1).strip() if match else None


def extract_price_from_text(text: str) -> tuple[Decimal, str] | None:
    match = PRICE_WITH_SYMBOL_PATTERN.search(text)
    if match:
        currency = {"\u20ac": "EUR", "$": "USD", "\u00a3": "GBP"}[match.group(1)]
        return Decimal(match.group(2).replace(",", ".")), currency

    match = PRICE_WITH_CODE_PATTERN.search(text)
    if match:
        return Decimal(match.group(2).replace(",", ".")), match.group(1).upper()
    return None


def extract_discount_texts(html_text: str) -> list[str]:
    soup = BeautifulSoup(html_text, "html.parser")
    texts: list[str] = []

    title = extract_title(html_text)
    if PROMO_HINT_PATTERN.search(title):
        texts.append(title)

    for meta_name in ("description", "og:description"):
        meta = soup.find("meta", attrs={"name": meta_name}) or soup.find(
            "meta", attrs={"property": meta_name}
        )
        if meta and meta.get("content"):
            texts.append(" ".join(str(meta["content"]).split()))

    for tag in soup.find_all(True):
        joined_classes = " ".join(tag.get("class", []))
        joined_id = tag.get("id", "")
        descriptor = f"{joined_classes} {joined_id}".lower()
        if any(keyword in descriptor for keyword in ("promo", "discount", "voucher", "coupon", "banner", "deal")):
            text = " ".join(tag.get_text(" ", strip=True).split())
            if 8 <= len(text) <= 280:
                texts.append(text)

    for raw_match in re.findall(
        r'"(?:text|title|description|content|label|html)"\s*:\s*"([^"\n]{10,320})"',
        html_text,
        re.I,
    ):
        cleaned = html.unescape(raw_match.replace("\\/", "/"))
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = " ".join(cleaned.split())
        if cleaned:
            texts.append(cleaned)

    deduped: list[str] = []
    seen: set[str] = set()
    for raw_text in texts:
        text = " ".join(raw_text.split())
        key = text.casefold()
        if key in seen:
            continue
        if len(text) < 8 or len(text) > 280:
            continue
        if NOISE_PATTERN.search(text):
            continue
        if PROMO_HINT_PATTERN.search(text) or CODE_PATTERN.search(text):
            deduped.append(text)
            seen.add(key)
    return deduped


def extract_discount_code(text: str) -> str | None:
    match = CODE_PATTERN.search(text)
    return match.group(1).upper() if match else None
