"""Live retrieval: storefront collection feeds + MCP variant resolution.

Two surfaces, two price representations (SPEC.md §3.3):
  * storefront feed  -> `price` is a decimal STRING in MAJOR units ("50.00")
  * MCP get_product  -> `price` is {"amount": 5000, "currency": "USD"}, MINOR units
Never cache the catalog to disk — a local copy reads as mocked.
"""

from __future__ import annotations

import asyncio
import difflib
import re
from typing import Any

import httpx

from concierge.commerce.ucp import CONTEXT, call_ucp
from concierge.domain.guardrails import check_query_shape
from concierge.domain.models import (
    CatalogProduct,
    CatalogVariant,
    ResolvedVariant,
    major_string_to_minor,
)
from concierge.obs.trace import emit

BASE = "https://www.decathlon.com"

_client: httpx.AsyncClient | None = None
_taxonomy: list[dict[str, str]] | None = None
_tax_lock = asyncio.Lock()

# product gid -> [{"name": str, "values": [label, ...]}]. Labels only: option
# labels are stable, availability is not and must never be served from a cache.
_labels: dict[str, list[dict[str, Any]]] = {}


class UnknownHandle(Exception):
    """Raised so the model can retry against a real handle — it hallucinates them."""

    def __init__(self, handle: str, suggestions: list[str]) -> None:
        super().__init__(f"unknown collection handle {handle!r}; did you mean: {', '.join(suggestions)}")
        self.handle = handle
        self.suggestions = suggestions


class NoStockError(Exception):
    def __init__(self, product: CatalogProduct, grid: list[tuple[str, bool]]) -> None:
        super().__init__(f"no available variant for {product.title!r}")
        self.product = product
        self.grid = grid


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True)
    return _client


async def aclose() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def get_taxonomy(force: bool = False) -> list[dict[str, str]]:
    global _taxonomy
    async with _tax_lock:
        if _taxonomy is None or force:
            r = await client().get(f"{BASE}/collections.json?limit=250")
            r.raise_for_status()
            _taxonomy = [{"handle": c["handle"], "title": c["title"]} for c in r.json()["collections"]]
            emit("catalog.taxonomy", {"count": len(_taxonomy)})
    return _taxonomy


async def validate_handles(handles: list[str]) -> tuple[list[str], list[str]]:
    known = {c["handle"] for c in await get_taxonomy()}
    valid = [h for h in handles if h in known]
    invalid = [h for h in handles if h not in known]
    if invalid:
        emit("catalog.invalid_handles", {"invalid": ",".join(invalid)}, "guardrail")
    return valid, invalid


_STOP = {"a", "all", "an", "and", "at", "for", "in", "of", "s", "shop", "the", "to", "with"}


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", s.lower()) if t and t not in _STOP}


def suggest_handles(bad: str, taxonomy: list[dict[str, str]], k: int = 5) -> list[str]:
    want = _tokens(bad)
    low = bad.lower()

    def rank(c: dict[str, str]) -> tuple[int, float]:
        overlap = len(want & (_tokens(c["handle"]) | _tokens(c["title"])))
        ratio = max(
            difflib.SequenceMatcher(None, low, c["handle"].lower()).ratio(),
            difflib.SequenceMatcher(None, low, c["title"].lower()).ratio(),
        )
        return overlap, ratio

    return [c["handle"] for c in sorted(taxonomy, key=rank, reverse=True)[:k]]


def map_product(raw: dict[str, Any]) -> CatalogProduct:
    images = raw.get("images") or []
    variants = [
        CatalogVariant(
            variant_gid=f"gid://shopify/ProductVariant/{v['id']}",
            size_label=v.get("title") or "",
            price_minor=major_string_to_minor(v["price"]),
            available=bool(v.get("available")),
        )
        for v in raw.get("variants") or []
    ]
    return CatalogProduct(
        product_gid=f"gid://shopify/Product/{raw['id']}",
        handle=raw["handle"],
        title=raw["title"],
        product_url=f"{BASE}/products/{raw['handle']}",
        image_url=(images[0].get("src") if images else None),
        product_type=raw.get("product_type") or "",
        vendor=raw.get("vendor") or "",
        option_names=[o["name"] for o in raw.get("options") or []],
        variants=variants,
    )


async def get_collection(handle: str, limit: int = 12) -> list[CatalogProduct]:
    _, invalid = await validate_handles([handle])
    if invalid:
        raise UnknownHandle(handle, suggest_handles(handle, await get_taxonomy()))

    r = await client().get(f"{BASE}/collections/{handle}/products.json?limit={limit}")
    r.raise_for_status()

    products = []
    for raw in r.json().get("products", []):
        try:
            products.append(map_product(raw))
        except Exception as exc:  # one malformed product must not cost the whole slot
            emit("catalog.unmappable", {"handle": raw.get("handle"), "error": str(exc)[:200]}, "error")
    emit("catalog.collection", {"handle": handle, "products": len(products)})
    return products


def sanitize_query(q: str) -> str:
    """Descriptive queries return ZERO (SPEC.md §3.3) — conditions and specs belong in
    the selection step, never in the query. One implementation, in domain/guardrails.py.
    An empty return means the query held no searchable noun: skip the search entirely
    rather than reducing "under 2 kg" to a keyword that cannot match."""
    return check_query_shape(q)


def _map_mcp_product(raw: dict[str, Any]) -> CatalogProduct:
    media = raw.get("media") or []
    variants = [
        CatalogVariant(
            variant_gid=v["id"],
            size_label=v.get("title") or "",
            price_minor=v["price"]["amount"],
            available=bool((v.get("availability") or {}).get("available")),
        )
        for v in raw.get("variants") or []
    ]
    _remember(raw["id"], raw.get("options") or [])
    return CatalogProduct(
        product_gid=raw["id"],
        handle=raw["handle"],
        title=raw["title"],
        product_url=raw.get("url") or f"{BASE}/products/{raw['handle']}",
        image_url=(media[0].get("url") if media else None),
        option_names=[o["name"] for o in raw.get("options") or []],
        variants=variants,
    )


async def search_fallback(query: str, limit: int = 10) -> list[CatalogProduct]:
    q = sanitize_query(query)
    if not q:
        emit("catalog.search_skipped", {"raw": query}, "guardrail")
        return []

    data = await call_ucp(
        "search_catalog",
        {"catalog": {"query": q, "context": CONTEXT, "pagination": {"limit": limit}}},
    )
    products = [_map_mcp_product(p) for p in data.get("products") or []]
    emit("catalog.search_fallback", {"query": q, "products": len(products)})
    return products


search_catalog = search_fallback  # name the agent lane's backend protocol calls


def _remember(gid: str, options: list[dict[str, Any]]) -> None:
    _labels[gid] = [
        {"name": o["name"], "values": [v["label"] for v in o.get("values") or []]} for o in options
    ]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip().casefold()


def _is_size(name: str) -> bool:
    return "size" in name.casefold()


def _num(s: str) -> float | None:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*", s)
    return float(m.group(1)) if m else None


def _parts(label: str) -> set[str]:
    return {p for p in re.split(r"[\s/\-–—]+", _norm(label)) if p}


def _match_index(labels: list[str], requested: str) -> int | None:
    for i, lab in enumerate(labels):
        if lab == requested:
            return i
    rn = _num(requested)
    if rn is not None:
        for i, lab in enumerate(labels):
            ln = _num(lab)
            if ln is not None and ln == rn:
                return i
    want = _norm(requested)
    for i, lab in enumerate(labels):
        if _norm(lab) == want:
            return i
    for i, lab in enumerate(labels):
        if want in _parts(lab):
            return i
    return None


def _nearest_available(values: list[tuple[str, bool]], start: int) -> int | None:
    n = len(values)
    for d in range(1, n):
        for j in (start + d, start - d):  # tie -> larger index
            if 0 <= j < n and values[j][1]:
                return j
    return None


def _choose_size(values: list[tuple[str, bool]], requested: str | None) -> tuple[int, bool] | None:
    if not any(a for _, a in values):
        return None
    if requested is None:
        return next(i for i, (_, a) in enumerate(values) if a), False

    idx = _match_index([lab for lab, _ in values], requested)
    if idx is not None:
        if values[idx][1]:
            return idx, False
        near = _nearest_available(values, idx)
        return (near, True) if near is not None else None

    rn = _num(requested)
    if rn is not None:
        numeric = [(i, _num(lab)) for i, (lab, a) in enumerate(values) if a and _num(lab) is not None]
        if numeric:
            return min(numeric, key=lambda p: abs(p[1] - rn))[0], True
    return next(i for i, (_, a) in enumerate(values) if a), True


async def _get_product(gid: str, selected: list[dict[str, str]] | None) -> dict[str, Any]:
    catalog: dict[str, Any] = {"id": gid, "context": CONTEXT}
    if selected:
        catalog["selected"] = selected
    data = await call_ucp("get_product", {"catalog": catalog})
    return data["product"]


async def _option_labels(gid: str) -> list[dict[str, Any]]:
    if gid not in _labels:
        product = await _get_product(gid, None)  # no selection -> labels only, availability is null
        _remember(gid, product.get("options") or [])
        emit("catalog.labels", {"product": gid, "options": ",".join(o["name"] for o in _labels[gid])})
    return _labels[gid]


def _canonical(selected: list[dict[str, str]], options: list[dict[str, Any]]) -> list[dict[str, str]]:
    """A label the server does not recognise fails SILENTLY — every value comes back
    exists:false with an empty variants list. Remap against the labels it echoed."""
    by_name = {o["name"]: [v["label"] for v in o.get("values") or []] for o in options}
    out = []
    for sel in selected:
        labels = by_name.get(sel["name"], [])
        label = sel["label"]
        if label not in labels:
            match = next((l for l in labels if _norm(l) == _norm(label)), None)
            if match is not None:
                label = match
        out.append({"name": sel["name"], "label": label})
    return out


async def _grid(gid: str, selected: list[dict[str, str]]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    product = await _get_product(gid, selected)
    fixed = _canonical(selected, product.get("options") or [])
    if fixed != selected:
        emit("catalog.label_canonicalised", {"product": gid, "selected": str(fixed)}, "guardrail")
        product = await _get_product(gid, fixed)
    _remember(gid, product.get("options") or [])
    return product, fixed


def _values(product: dict[str, Any], name: str) -> list[tuple[str, bool]]:
    for o in product.get("options") or []:
        if o["name"] == name:
            return [(v["label"], bool(v.get("available"))) for v in o.get("values") or []]
    return []


def _next_option(product: dict[str, Any], name: str, seen: list[str]) -> str | None:
    """A colour value is available when SOME variant of it is in stock, so a sold-out
    first colour is a false unservable slot unless we try the others."""
    return next((lab for lab, avail in _values(product, name) if avail and lab not in seen), None)


async def resolve_variant(product: CatalogProduct, requested_size: str | None = None) -> ResolvedVariant:
    gid = product.product_gid
    options = await _option_labels(gid)
    size_opt = next((o for o in options if _is_size(o["name"])), None)
    base = [o for o in options if o is not size_opt and o["values"]]
    selected = [{"name": o["name"], "label": o["values"][0]} for o in base]

    if size_opt is None:
        seen: list[str] = []
        grid: dict[str, Any] = {}
        for _ in range(3):
            grid, selected = await _grid(gid, selected)
            variants = grid.get("variants") or []
            if variants and (variants[0].get("availability") or {}).get("available"):
                return _resolved(product, variants[0], requested_size, False)
            if not base:
                break
            seen.append(selected[0]["label"])
            nxt = _next_option(grid, base[0]["name"], seen)
            if nxt is None:
                break
            emit("catalog.option_fallback", {"product": gid, "option": base[0]["name"], "label": nxt})
            selected = [{"name": base[0]["name"], "label": nxt}] + selected[1:]
        emit("catalog.no_stock", {"product": gid, "title": product.title}, "guardrail")
        raise NoStockError(product, _values(grid, base[0]["name"]) if base else [])

    # a selection must be NON-EMPTY or every value comes back available:null, so a
    # product whose only option is Size is probed with a size instead.
    probe = selected or [{"name": size_opt["name"], "label": size_opt["values"][0]}]

    tried: list[str] = []
    chosen: tuple[int, bool] | None = None
    sizes: list[tuple[str, bool]] = []

    for _ in range(3):  # first colour, then up to 2 the grid marks available
        grid, probe = await _grid(gid, probe)
        sizes = _values(grid, size_opt["name"])
        emit(
            "catalog.grid",
            {"product": gid, "selection": str(probe), "available": sum(1 for _, a in sizes if a)},
        )
        chosen = _choose_size(sizes, requested_size)
        if chosen is not None or not base:
            break
        tried.append(probe[0]["label"])
        nxt = _next_option(grid, base[0]["name"], tried)
        if nxt is None:
            break
        emit("catalog.option_fallback", {"product": gid, "option": base[0]["name"], "label": nxt})
        probe = [{"name": base[0]["name"], "label": nxt}] + probe[1:]

    selected = [s for s in probe if s["name"] != size_opt["name"]]

    if chosen is None:
        emit("catalog.no_stock", {"product": gid, "title": product.title}, "guardrail")
        raise NoStockError(product, sizes)

    idx, substituted = chosen
    label = sizes[idx][0]
    emit(
        "catalog.size_matched",
        {"product": gid, "requested": requested_size, "label": label, "substituted": substituted},
        "guardrail" if substituted else "info",
    )

    full = selected + [{"name": size_opt["name"], "label": label}]
    resolved = await _get_product(gid, full)
    variants = resolved.get("variants") or []
    if not variants:
        raise NoStockError(product, sizes)
    return _resolved(product, variants[0], requested_size, substituted)


async def try_resolve_variant(
    product: CatalogProduct, requested_size: str | None = None
) -> ResolvedVariant | None:
    """None instead of NoStockError, for callers that treat a sold-out product as an
    unservable slot. Rate limits still propagate."""
    try:
        return await resolve_variant(product, requested_size)
    except NoStockError:
        return None


def _resolved(
    product: CatalogProduct, variant: dict[str, Any], requested_size: str | None, substituted: bool
) -> ResolvedVariant:
    available = bool((variant.get("availability") or {}).get("available"))
    if not available:
        raise NoStockError(product, [(variant.get("title") or "", False)])
    rv = ResolvedVariant(
        variant_gid=variant["id"],
        size_label=variant.get("title") or "",
        price_minor=variant["price"]["amount"],  # MCP price is already minor units
        available=True,
        substituted=substituted,
        requested_size=requested_size,
    )
    emit(
        "catalog.variant_resolved",
        {
            "product": product.product_gid,
            "variant": rv.variant_gid,
            "label": rv.size_label,
            "price_minor": rv.price_minor,
            "substituted": rv.substituted,
        },
    )
    return rv
