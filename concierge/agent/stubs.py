"""Fixture-backed stand-in for commerce/catalog.py.

Same four async callables Dev A ships, so loop.py is testable without touching
Decathlon's MCP endpoint. `set_backend(catalog)` swaps it out.

One divergence from live behaviour, deliberate: a handle that exists in the
taxonomy but has no `fixtures/collection_<handle>.json` returns `[]`, which the
loop reads as an unservable slot. Only 9 of the 228 collections were dumped.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from concierge.domain.models import (
    CatalogProduct,
    CatalogVariant,
    ResolvedVariant,
    major_string_to_minor,
)

BASE = "https://www.decathlon.com"
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@lru_cache(maxsize=1)
def _taxonomy() -> tuple[dict[str, str], ...]:
    return tuple(json.loads((FIXTURES / "collections.json").read_text()))


@lru_cache(maxsize=64)
def _raw(handle: str) -> tuple[dict, ...] | None:
    path = FIXTURES / f"collection_{handle}.json"
    if not path.exists():
        return None
    return tuple(json.loads(path.read_text()))


def _to_product(raw: dict) -> CatalogProduct | None:
    variants: list[CatalogVariant] = []
    for v in raw.get("variants") or []:
        try:
            variants.append(
                CatalogVariant(
                    variant_gid=f"gid://shopify/ProductVariant/{v['id']}",
                    size_label=v.get("title") or "One Size",
                    price_minor=major_string_to_minor(v["price"]),
                    available=bool(v.get("available")),
                )
            )
        except Exception:
            continue

    images = raw.get("images") or []
    try:
        return CatalogProduct(
            product_gid=f"gid://shopify/Product/{raw['id']}",
            handle=raw["handle"],
            title=raw["title"],
            product_url=f"{BASE}/products/{raw['handle']}",
            image_url=images[0].get("src") if images else None,
            product_type=raw.get("product_type") or "",
            vendor=raw.get("vendor") or "",
            option_names=[o["name"] for o in raw.get("options") or []],
            variants=variants,
        )
    except Exception:
        return None


def _products(raw: tuple[dict, ...], limit: int) -> list[CatalogProduct]:
    out: list[CatalogProduct] = []
    for item in raw:
        p = _to_product(item)
        if p is not None:
            out.append(p)
        if len(out) >= limit:
            break
    return out


async def get_taxonomy() -> list[dict[str, str]]:
    return [dict(c) for c in _taxonomy()]


async def get_collection(handle: str, limit: int = 12) -> list[CatalogProduct]:
    raw = _raw(handle)
    if raw is None:
        return []
    return _products(raw, limit)


async def search_catalog(query: str, limit: int = 10) -> list[CatalogProduct]:
    terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2]
    if not terms:
        return []

    hits: list[tuple[int, CatalogProduct]] = []
    for path in sorted(FIXTURES.glob("collection_*.json")):
        raw = _raw(path.stem.removeprefix("collection_"))
        for item in raw or ():
            haystack = f"{item.get('title', '')} {item.get('product_type', '')}".lower()
            score = sum(t in haystack for t in terms)
            if score:
                p = _to_product(item)
                if p is not None:
                    hits.append((score, p))

    hits.sort(key=lambda h: -h[0])
    seen: set[str] = set()
    out: list[CatalogProduct] = []
    for _, p in hits:
        if p.handle in seen:
            continue
        seen.add(p.handle)
        out.append(p)
        if len(out) >= limit:
            break
    return out


_SIZE_WORDS = {"xs", "s", "m", "l", "xl", "xxl", "xxxl", "onesize", "os", "unique"}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9.]", "", s.lower())


def _numeric(s: str) -> float | None:
    try:
        return float(s)
    except ValueError:
        return None


def _size_tokens(s: str) -> set[str]:
    # Variant labels are "<Colour> / <Size>". Matching on the whole label makes a
    # colour collision look like a size match, so compare size tokens only.
    out = set()
    for part in s.split("/"):
        p = _norm(part)
        if p and (_numeric(p) is not None or p in _SIZE_WORDS):
            out.add(p)
    return out


def _matches(label: str, requested: str) -> bool:
    want, got = _size_tokens(requested), _size_tokens(label)
    if not want:
        return _norm(label) == _norm(requested)
    if want & got:
        return True
    for w in want:
        wn = _numeric(w)
        if wn is None:
            continue
        for g in got:
            gn = _numeric(g)
            if gn is not None and abs(gn - wn) < 1e-6:
                return True
    return False


async def resolve_variant(
    product: CatalogProduct, requested_size: str | None = None
) -> ResolvedVariant | None:
    live = [v for v in product.variants if v.available]
    if not live:
        return None

    if requested_size:
        for v in live:
            if _matches(v.size_label, requested_size):
                return ResolvedVariant(
                    variant_gid=v.variant_gid,
                    size_label=v.size_label,
                    price_minor=v.price_minor,
                    available=True,
                    substituted=False,
                    requested_size=requested_size,
                )

    v = live[0]
    return ResolvedVariant(
        variant_gid=v.variant_gid,
        size_label=v.size_label,
        price_minor=v.price_minor,
        available=True,
        substituted=bool(requested_size),
        requested_size=requested_size,
    )
