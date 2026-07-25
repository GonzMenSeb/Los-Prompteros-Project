from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from concierge.domain.models import CatalogProduct, CatalogVariant, KitItem, major_string_to_minor
from concierge.obs import trace

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures"
BASE = "https://www.decathlon.com"

# A real, live-verified product/variant pair (fixtures/get_product_*.json).
PRODUCT_GID = "gid://shopify/Product/7839703466046"
VARIANT_GID = "gid://shopify/ProductVariant/41919445434430"


def load(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def feed(handle: str) -> list[dict]:
    return load(f"collection_{handle}")


def catalog(handle: str) -> list[CatalogProduct]:
    """The SPEC.md §4.3 field mapping, applied to a dumped feed. Kept here rather
    than imported from catalog.py so these tests never depend on another lane."""
    out = []
    for p in feed(handle):
        images = p.get("images") or []
        out.append(
            CatalogProduct(
                product_gid=f"gid://shopify/Product/{p['id']}",
                handle=p["handle"],
                title=p["title"],
                product_url=f"{BASE}/products/{p['handle']}",
                image_url=images[0]["src"] if images else None,
                product_type=p.get("product_type", ""),
                vendor=p.get("vendor", ""),
                option_names=[o["name"] for o in p.get("options", [])],
                variants=[
                    CatalogVariant(
                        variant_gid=f"gid://shopify/ProductVariant/{v['id']}",
                        size_label=v["title"],
                        price_minor=major_string_to_minor(v["price"]),
                        available=v["available"],
                    )
                    for v in p.get("variants", [])
                ],
            )
        )
    return out


def item(**over: Any) -> KitItem:
    base: dict[str, Any] = {
        "slot": "boots",
        "product_title": "Quechua Men's NH500 Warm Waterproof High Leather Hiking Boots",
        "product_url": f"{BASE}/products/quechua-mens-nh500",
        "image_url": "https://cdn.shopify.com/s/files/1/1330/6287/files/8641979.jpg",
        "variant_id": VARIANT_GID,
        "size_label": "Dark Cinnamon / 9.5",
        "price_minor": 10000,
        "available": True,
    }
    return KitItem(**{**base, **over})


@pytest.fixture(autouse=True)
def _clean_trace():
    trace.bind_sink(None)
    trace.reset()
    yield
    trace.reset()


@pytest.fixture
def sink() -> list:
    events: list = []
    trace.bind_sink(events)
    yield events
    trace.bind_sink(None)
