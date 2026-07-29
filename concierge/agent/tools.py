"""Catalog tools the model may call, plus the dispatcher behind them.

`create_cart` IS DELIBERATELY ABSENT and must stay absent. Human-in-the-loop is
enforced by the model having no way to reach the cart, not by asking it nicely.
A prompt instruction is a suggestion; an unexposed tool is a guarantee.

Everything handed back to the model is whitelisted and truncated. Product
`body_html` is untrusted seller text and is never forwarded.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Any, Awaitable, Callable

from google.genai import types

from concierge.agent import stubs
from concierge.domain.models import CatalogProduct
from concierge.obs.trace import emit

MAX_PRODUCTS = 8
MAX_SIZES = 12
MAX_SUGGESTIONS = 15

_backend: Any = stubs

# Products the model has actually been shown, keyed by product handle. KitItems
# are built from this, never from model prose — that is the anti-hallucination
# seam. Bound per turn so Reflex sessions cannot see each other's catalog.
_cache: ContextVar[dict[str, CatalogProduct] | None] = ContextVar("catalog_cache", default=None)


# Each capability, in preference order. Resolved by name at swap time so a
# missing one fails loudly here rather than as an AttributeError mid-demo.
_CAPABILITIES = {
    "get_taxonomy": ("get_taxonomy",),
    "get_collection": ("get_collection",),
    "search_catalog": ("search_catalog", "search_fallback"),
    "resolve_variant": ("try_resolve_variant", "resolve_variant"),
}


class _Adapter:
    """Normalises a catalog backend to the four calls the loop expects.

    commerce/catalog.py signals by exception (UnknownHandle, NoStockError) and
    names its keyword search `search_fallback`. The loop is written against
    empty-list / None returns, so the translation lives here rather than as
    try/except scattered through loop.py. UcpRateLimited is deliberately NOT
    swallowed — a rate limit must not be reported as an unservable slot.
    """

    def __init__(self, impl: Any) -> None:
        self._impl = impl
        self._fn: dict[str, Any] = {}
        missing = []
        for cap, names in _CAPABILITIES.items():
            fn = next((getattr(impl, n) for n in names if callable(getattr(impl, n, None))), None)
            if fn is None:
                missing.append(f"{cap} (looked for: {', '.join(names)})")
            else:
                self._fn[cap] = fn
        if missing:
            raise AttributeError(
                f"catalog backend {getattr(impl, '__name__', impl)!r} is missing: " + "; ".join(missing)
            )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._impl, name)

    def resolves_none_itself(self) -> bool:
        return self._fn["resolve_variant"].__name__ == "try_resolve_variant"

    def bind_too_far(self, sink: list[dict[str, Any]] | None) -> None:
        """Optional on a backend — stubs has no size ceiling. By name, not by import:
        agent/ still does not depend on commerce/."""
        fn = getattr(self._impl, "bind_too_far", None)
        if fn is not None:
            fn(sink)

    async def get_taxonomy(self) -> list[dict[str, str]]:
        return await self._fn["get_taxonomy"]()

    async def get_collection(self, handle: str, limit: int = 12) -> list[CatalogProduct]:
        try:
            return await self._fn["get_collection"](handle, limit)
        except Exception as exc:
            if type(exc).__name__ != "UnknownHandle":
                raise
            suggestions = list(getattr(exc, "suggestions", []))[:MAX_SUGGESTIONS]
            emit("guardrail.handle_rejected", {"handle": handle, "suggestions": suggestions}, level="guardrail")
            return []

    async def search_catalog(self, query: str, limit: int = 10) -> list[CatalogProduct]:
        return await self._fn["search_catalog"](query, limit)

    async def resolve_variant(self, product: CatalogProduct, requested_size: str | None = None) -> Any:
        try:
            return await self._fn["resolve_variant"](product, requested_size)
        except Exception as exc:
            if type(exc).__name__ != "NoStockError":
                raise
            return None


def set_backend(module_or_obj: Any) -> None:
    global _backend
    adapter = _Adapter(module_or_obj)
    _backend = adapter
    emit(
        "tools.backend",
        {
            "backend": getattr(module_or_obj, "__name__", type(module_or_obj).__name__),
            "resolve": adapter._fn["resolve_variant"].__name__,
            "search": adapter._fn["search_catalog"].__name__,
        },
    )


def backend() -> Any:
    return _backend


def bind_cache(cache: dict[str, CatalogProduct] | None) -> None:
    _cache.set(cache)


def cached() -> dict[str, CatalogProduct]:
    c = _cache.get()
    return c if c is not None else {}


def _remember(products: list[CatalogProduct]) -> None:
    c = _cache.get()
    if c is None:
        return
    for p in products:
        c[p.handle] = p


def _slim(p: CatalogProduct) -> dict[str, Any]:
    sizes: list[str] = []
    for v in p.variants:
        if v.available and v.size_label not in sizes:
            sizes.append(v.size_label)
    return {
        "title": p.title[:140],
        "product_handle": p.handle[:140],
        "product_url": p.product_url,
        "image_url": p.image_url or "",
        "price_minor": p.min_price_minor,
        "size_labels": sizes[:MAX_SIZES],
    }


async def _taxonomy() -> list[dict[str, str]]:
    return await _backend.get_taxonomy()


def _score(entry: dict[str, str], terms: list[str]) -> int:
    hay = f"{entry.get('title', '')} {entry.get('handle', '')}".lower()
    return sum(t in hay for t in terms)


async def list_collections(query: str = "", **_: Any) -> dict[str, Any]:
    tax = await _taxonomy()
    terms = [t for t in re.findall(r"[a-z0-9]+", (query or "").lower()) if len(t) > 2]

    if terms:
        ranked = sorted(((_score(c, terms), c) for c in tax), key=lambda r: -r[0])
        hits = [c for s, c in ranked if s > 0][:MAX_SUGGESTIONS]
    else:
        hits = tax[:MAX_SUGGESTIONS]

    emit("tool.list_collections", {"query": query, "hits": len(hits)})
    return {"collections": [{"handle": c["handle"], "title": c["title"]} for c in hits]}


async def get_collection_products(handle: str = "", limit: int = MAX_PRODUCTS, **_: Any) -> dict[str, Any]:
    handle = (handle or "").strip()
    tax = await _taxonomy()
    live = {c["handle"] for c in tax}

    # Handle rejection is a normal tool RESULT, not an exception: the model sees
    # the valid candidates and retries. Never fetch an unvalidated handle.
    if handle not in live:
        terms = [t for t in re.findall(r"[a-z0-9]+", handle.lower()) if len(t) > 2]
        ranked = sorted(((_score(c, terms), c) for c in tax), key=lambda r: -r[0])
        suggestions = [c["handle"] for s, c in ranked if s > 0][:MAX_SUGGESTIONS]
        emit(
            "guardrail.handle_rejected",
            {"handle": handle, "suggestions": suggestions[:5]},
            level="guardrail",
        )
        return {
            "error": f"'{handle}' is not a live Decathlon collection. Call get_collection_products again with one of valid_handles.",
            "valid_handles": suggestions or [c["handle"] for c in tax[:MAX_SUGGESTIONS]],
        }

    limit = max(1, min(int(limit or MAX_PRODUCTS), MAX_PRODUCTS))
    products = await _backend.get_collection(handle, limit)
    _remember(products)

    if not products:
        emit("guardrail.empty_collection", {"handles": [handle]}, level="guardrail")
        return {
            "handle": handle,
            "products": [],
            "note": "This collection is live but currently has no products in stock. The slot cannot be filled — say so, do not substitute something unrelated.",
        }

    emit("tool.get_collection_products", {"handle": handle, "count": len(products)})
    return {"handle": handle, "products": [_slim(p) for p in products]}


async def search_products(query: str = "", **_: Any) -> dict[str, Any]:
    # The MCP search rejects sentences; head nouns only.
    words = re.findall(r"[A-Za-z0-9]+", query or "")
    trimmed = " ".join(words[:3])
    if trimmed != (query or "").strip():
        emit("guardrail.query_trimmed", {"from": query, "to": trimmed}, level="guardrail")

    if not trimmed:
        return {"products": [], "note": "empty query"}

    products = await _backend.search_catalog(trimmed, MAX_PRODUCTS)
    _remember(products)
    emit("tool.search_products", {"query": trimmed, "count": len(products)})
    return {"query": trimmed, "products": [_slim(p) for p in products]}


_DECLARATIONS = [
    types.FunctionDeclaration(
        name="list_collections",
        description=(
            "Search Decathlon's live collection taxonomy for candidate collection handles. "
            "Use this FIRST for every gear slot to find out which collections actually exist. "
            "Never invent a collection handle."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(
                    type=types.Type.STRING,
                    description="Gear words to match against collection titles, e.g. 'hiking boots' or 'rain jacket'.",
                )
            },
            required=["query"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_collection_products",
        description=(
            "Fetch the real, in-stock products of ONE live collection for ONE gear slot. "
            "The handle must come from list_collections. If the handle is not live you get an "
            "error plus valid_handles — call again with one of those. An empty product list means "
            "the collection carries nothing right now; report the slot as unfillable rather than substituting."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "handle": types.Schema(
                    type=types.Type.STRING,
                    description="A collection handle returned by list_collections, e.g. 'hiking-boots'.",
                ),
                "limit": types.Schema(
                    type=types.Type.INTEGER,
                    description=f"How many products to return, 1-{MAX_PRODUCTS}.",
                ),
            },
            required=["handle"],
        ),
    ),
    types.FunctionDeclaration(
        name="search_products",
        description=(
            "Keyword fallback, only when no collection fits. The query MUST be a 1-3 word noun "
            "phrase naming the object: 'tent', 'sleeping bag', 'trail shoes'. Conditions, "
            "specifications, temperatures and sentences return nothing and will be stripped."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(
                    type=types.Type.STRING,
                    description="1-3 word noun phrase. No adjectives about weather, rating or size.",
                )
            },
            required=["query"],
        ),
    ),
]

# `tools=` takes Tool objects. A bare list of FunctionDeclaration raises
# AttributeError before any HTTP call is made.
CATALOG_TOOLS: list[types.Tool] = [types.Tool(function_declarations=_DECLARATIONS)]

DISPATCH: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "list_collections": list_collections,
    "get_collection_products": get_collection_products,
    "search_products": search_products,
}

# Wrapped, not bare, so importing tools.py without loop.py still gets the adapter.
set_backend(stubs)
