from __future__ import annotations

import importlib
import inspect
from collections.abc import Iterable

from ecom_price_bot.services.http_client import WebClient
from ecom_price_bot.services.vendor_base import GenericVendorService
from ecom_price_bot.services.vendors.boozt import BooztVendor
from ecom_price_bot.services.vendors.booztlet import BooztletVendor
from ecom_price_bot.services.vendors.lyko import LykoVendor
from ecom_price_bot.services.vendors.notino import NotinoVendor
from ecom_price_bot.services.vendors.prisma import PrismaVendor
from ecom_price_bot.services.vendors.uniqlo import UniqloVendor
from ecom_price_bot.services.vendors.zalando import ZalandoVendor


class VendorRegistry:
    def __init__(self, vendors: Iterable[GenericVendorService]) -> None:
        self._vendors = {vendor.vendor_id: vendor for vendor in vendors}

    @classmethod
    def build(cls, *, addon_modules: tuple[str, ...]) -> "VendorRegistry":
        web_client = WebClient()
        vendor_classes: list[type[GenericVendorService]] = [
            ZalandoVendor,
            BooztVendor,
            BooztletVendor,
            LykoVendor,
            NotinoVendor,
            PrismaVendor,
            UniqloVendor,
        ]
        vendor_classes.extend(_load_addon_vendor_classes(addon_modules))
        vendors = [vendor_class(web_client) for vendor_class in vendor_classes]
        return cls(vendors)

    def get_by_url(self, url: str) -> GenericVendorService:
        for vendor in self._vendors.values():
            if vendor.supports(url):
                return vendor
        raise ValueError(f"Unsupported vendor url: {url}")

    def get_by_vendor_id(self, vendor_id: str) -> GenericVendorService:
        try:
            return self._vendors[vendor_id]
        except KeyError as exc:
            raise ValueError(f"Unknown vendor id: {vendor_id}") from exc

    def all(self) -> list[GenericVendorService]:
        return list(self._vendors.values())


def _load_addon_vendor_classes(module_names: tuple[str, ...]) -> list[type[GenericVendorService]]:
    vendor_classes: list[type[GenericVendorService]] = []
    for module_name in module_names:
        module = importlib.import_module(module_name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj is GenericVendorService:
                continue
            if issubclass(obj, GenericVendorService) and obj.vendor_id:
                vendor_classes.append(obj)
    return vendor_classes
