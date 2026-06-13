from __future__ import annotations

import html
import json
import logging
import re
from decimal import Decimal, InvalidOperation

from ecom_price_bot.models import InregoItem
from ecom_price_bot.services.http_client import WebClient

logger = logging.getLogger(__name__)

BASE_URL = "https://shop.inrego.fi"
MACBOOK_URL = f"{BASE_URL}/macbook"

_CARD_START = re.compile(r'<li class="liProduct')
_DATA_GDL = re.compile(r'data-gdl="(.*?)"', re.S)
_INFO_HREF = re.compile(r'product-item-info-link\s*"\s*href="([^"]+)"', re.S)
_PROD_NAME = re.compile(r'class="prodName">(.*?)</span>', re.S)
_USP_BLOCK = re.compile(r'<ul class="prodUSPs">(.*?)</ul>', re.S)
_SPEC_BLOCK = re.compile(r'<ul class="prodSpecs">(.*?)</ul>', re.S)
_LI_ITEM = re.compile(r'<li[^>]*>(.*?)</li>', re.S)
_CONDITION = re.compile(r'image-container__specs">.*?<span[^>]*>(.*?)</span>', re.S)
_DISCOUNT = re.compile(r'badge-discount[^>]*>\s*<span[^>]*>(.*?)</span>', re.S)
_CURRENT_PRICE = re.compile(r'current-price">(.*?)</span>', re.S)
_ORD_PRICE = re.compile(r'ordPrice">(.*?)</span>', re.S)
_PRICE_NUMBER = re.compile(r'([\d\s.,\xa0]+)\s*€')


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def _parse_price(fragment: str | None) -> Decimal | None:
    if not fragment:
        return None
    match = _PRICE_NUMBER.search(html.unescape(fragment))
    if not match:
        return None
    digits = re.sub(r"[^\d]", "", match.group(1))
    if not digits:
        return None
    try:
        return Decimal(digits)
    except InvalidOperation:
        return None


def _split_cards(page: str) -> list[str]:
    starts = [match.start() for match in _CARD_START.finditer(page)]
    if not starts:
        return []
    bounds = starts + [len(page)]
    return [page[bounds[i] : bounds[i + 1]] for i in range(len(starts))]


def _parse_card(card: str) -> InregoItem | None:
    gdl: dict = {}
    gdl_match = _DATA_GDL.search(card)
    if gdl_match:
        try:
            gdl = json.loads(html.unescape(gdl_match.group(1)))
        except json.JSONDecodeError:
            gdl = {}

    name_match = _PROD_NAME.search(card)
    name = _text(name_match.group(1)) if name_match else _text(str(gdl.get("name", "")))
    if not name:
        return None

    price = _parse_price(_CURRENT_PRICE.search(card).group(1)) if _CURRENT_PRICE.search(card) else None
    if price is None:
        price = _parse_price(card)
    if price is None:
        return None

    href_match = _INFO_HREF.search(card)
    url = BASE_URL + href_match.group(1) if href_match else MACBOOK_URL

    usp_match = _USP_BLOCK.search(card)
    usps = [_text(item) for item in _LI_ITEM.findall(usp_match.group(1))] if usp_match else []
    size = usps[0] if usps else None
    color = usps[1] if len(usps) > 1 else None

    spec_match = _SPEC_BLOCK.search(card)
    specs = [_text(item) for item in _LI_ITEM.findall(spec_match.group(1))] if spec_match else []

    condition_match = _CONDITION.search(card)
    condition = _text(condition_match.group(1)) if condition_match else None

    discount_match = _DISCOUNT.search(card)
    discount_label = _text(discount_match.group(1)) if discount_match else None

    ord_match = _ORD_PRICE.search(card)
    old_price = _parse_price(ord_match.group(1)) if ord_match else None

    return InregoItem(
        name=name,
        url=url,
        price=price,
        old_price=old_price,
        discount_label=discount_label,
        condition=condition,
        size=size,
        color=color,
        specs=specs,
        in_stock=bool(gdl.get("inStock", True)),
    )


def parse_macbooks(page: str) -> list[InregoItem]:
    items: list[InregoItem] = []
    for card in _split_cards(page):
        item = _parse_card(card)
        if item is not None:
            items.append(item)
    return items


class InregoMacbookScraper:
    """Scrapes the live MacBook catalog from shop.inrego.fi.

    Stateless on purpose: stock sells out fast, so every check fetches the
    current listing and the results are relayed without being stored.
    """

    def __init__(self, web_client: WebClient | None = None) -> None:
        self.web_client = web_client or WebClient()

    def fetch_macbooks(self) -> list[InregoItem]:
        response = self.web_client.get(MACBOOK_URL)
        return parse_macbooks(response.text)
