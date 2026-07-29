"""Live retrieval: storefront collection feeds + MCP variant resolution.

Two surfaces, two price representations (SPEC.md §3.3):
  * storefront feed  -> `price` is a decimal STRING in MAJOR units ("50.00")
  * MCP get_product  -> `price` is {"amount": 5000, "currency": "USD"}, MINOR units
Never cache the catalog to disk — a local copy reads as mocked.

THE STOREFRONT USES `requests` WITH NO CONNECTION REUSE, AND BOTH HALVES OF THAT
ARE DELIBERATE (AGENTS.md). Measured 28 Jul 2026: decathlon.com's storefront
refuses REUSED connections. Every pooled client is 429'd (httpx always, even idle
and single-shot; `requests.Session` fails 20 of 24 feeds at 6.4 req/s) and every
fresh-connection client is served (urllib 24/24 at 9.3 req/s, `requests` with no
Session 24/24 at 11.4 req/s). Faster unpooled and clean, slower pooled and
refused — so it is neither rate nor the library. `ucp.py` stays on httpx: the MCP
endpoint is a different limiter and is unaffected, verified working the same hour.
Do not "unify the clients" and do not "reuse a Session" without re-measuring.
"""

from __future__ import annotations

import asyncio
import difflib
import random
import re
import time
from contextvars import ContextVar
from typing import Any

import requests

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

_taxonomy: list[dict[str, str]] | None = None
_tax_lock = asyncio.Lock()

# product gid -> [{"name": str, "values": [label, ...]}]. Labels only: option
# labels are stable, availability is not and must never be served from a cache.
_labels: dict[str, list[dict[str, Any]]] = {}

_RESOLVED_TTL = 120.0
_resolved_cache: dict[tuple[str, str | None], tuple[float, ResolvedVariant]] = {}


class UnknownHandle(Exception):
    """Raised so the model can retry against a real handle — it hallucinates them."""

    def __init__(self, handle: str, suggestions: list[str]) -> None:
        super().__init__(f"unknown collection handle {handle!r}; did you mean: {', '.join(suggestions)}")
        self.handle = handle
        self.suggestions = suggestions


class CatalogUnavailable(Exception):
    """The storefront refused or failed a request that outlived its retry budget.

    Distinct from an empty collection, and the distinction is load-bearing: an empty
    collection is a fact about stock, this is the absence of one. Reporting it as
    "nothing in stock" fabricates an inventory claim from a request that never
    completed, which is exactly what the guardrail principle exists to prevent."""

    def __init__(self, url: str, status: int | None = None, detail: str = "") -> None:
        super().__init__(f"storefront unavailable ({detail or status}) for {url}")
        self.url = url
        self.status = status
        self.detail = detail
        self.rate_limited = status == 429


class NoStockError(Exception):
    def __init__(self, product: CatalogProduct, grid: list[tuple[str, bool]]) -> None:
        super().__init__(f"no available variant for {product.title!r}")
        self.product = product
        self.grid = grid


REQUEST_TIMEOUT = 30.0


def client() -> Any:
    """The `requests` MODULE, deliberately — NOT a `requests.Session`.

    A Session pools connections, and connection REUSE is what the storefront
    refuses. Measured 28 Jul 2026, same 24-feed burst at 6 concurrent, minutes
    apart:

        urllib, fresh conn per request   24/24 OK   9.3 req/s
        requests, NO Session             24/24 OK  11.4 req/s
        requests, shared Session          4/24 OK   6.4 req/s   <- pooled
        httpx (pools by design)           always 429

    Faster unpooled and clean; slower pooled and refused — so it is neither rate
    nor the library. `requests.get()` opens one connection, uses it once and closes
    it, which is the only configuration measured clean under our real load.
    **Do not "optimise" this into a Session.** The TLS handshake per request is
    the price of the feed working at all, and it costs ~2 s across a whole turn."""
    return requests


async def aclose() -> None:
    """Nothing to close — no pooled connections are held, on purpose (see client()).
    Kept because scripts/ and the tests call it as part of the module's contract."""
    return None


# ── storefront transport: bounded backoff, and a latch that decays ──────────
#
# The storefront has its own limiter, separate from MCP's: `collections.json`
# returned 429 on 28 Jul 2026 with no MCP lockout in play. It advertises
# `Retry-After: 60` and that hint is NOT honest — still 429 after 25 minutes of
# quiet — so there is no recovery figure here worth acting on, and none of MCP's
# numbers transfer either. The retry ladder stays even though `requests` is not
# currently being limited: a limiter we are not tripping today is not a limiter
# that has gone away, and Decathlon's agents.md asks agents to back off on 429.
#
# The shape of the response IS borrowed from the MCP surface, where it is
# measured: bursts trip a limiter that a trickle survives. So a 429 serialises
# the storefront and spaces it out. Unlike ucp.py the latch DECAYS, and that
# difference is deliberate: create_cart is one call per demo, but _prefetch is
# ~24 every turn, so a permanent latch would cost every later turn ~36 s for one
# transient 429.
SEM = asyncio.Semaphore(6)

# A burst governor for the MULTI-SESSION case, not the fix for the 429 — rate was
# tested and exonerated (11.4 req/s clean unpooled, 6.4 req/s refused pooled; see
# client()). SEM bounds concurrency, which is not the same as bounding rate once
# several browser sessions prefetch at once. Cheap insurance, and agents.md asks
# for it: ~1.9 s across a whole turn.
MIN_INTERVAL = 0.08  # ~12 req/s ceiling, at the rate that measured clean

MAX_ATTEMPTS = 4
RETRY_BUDGET_SECONDS = 12.0  # TOTAL per request, not per attempt: _tax_lock is held
BACKOFF_BASE = 0.6           # across the whole sequence and every session waits on it
BACKOFF_CAP = 4.0
PACE_SECONDS = 1.5
COOLDOWN_SECONDS = 60.0

_paced_until = 0.0
_pace_lock = asyncio.Lock()
_last_send = 0.0

_gap_lock = asyncio.Lock()
_last_start = 0.0


async def _space() -> None:
    """Hold the floor only long enough to stamp the slot, so requests still overlap
    up to SEM — this bounds the RATE, not the concurrency."""
    global _last_start
    async with _gap_lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last_start)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_start = time.monotonic()


def _latch() -> None:
    global _paced_until
    _paced_until = time.monotonic() + COOLDOWN_SECONDS


def _paced() -> bool:
    return time.monotonic() < _paced_until


async def _send(url: str) -> requests.Response:
    """`requests` is synchronous and the whole app is not — this is the seam. SEM(6)
    already bounds it, so the thread pool never grows past that."""
    return await asyncio.to_thread(lambda: client().get(url, timeout=REQUEST_TIMEOUT))


async def _fetch(url: str) -> requests.Response:
    global _last_send
    if not _paced():
        async with SEM:
            await _space()
            return await _send(url)

    async with _pace_lock:
        wait = PACE_SECONDS - (time.monotonic() - _last_send)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            return await _send(url)
        finally:
            _last_send = time.monotonic()


def _retry_after(value: str | None) -> float | None:
    """Seconds form only. The HTTP-date form is left unparsed rather than guessed at;
    an unreadable hint falls through to backoff, which is the safe direction."""
    try:
        return max(0.0, float((value or "").strip()))
    except ValueError:
        return None


def _delay(attempt: int, hint: float | None, remaining: float) -> float | None:
    """None means the budget cannot cover another wait — give up and degrade.

    The storefront's measured hint is `Retry-After: 60` (28 Jul 2026), so one attempt
    then degrade IS the live path here, not an edge case. 60 s is not absurd the way
    MCP's 48 minutes is; it is simply longer than a turn can be made to wait, and
    `_tax_lock` is held for every second of it. A stalled turn is worse than a short
    kit. The exponential ladder below is what runs when no hint is sent at all."""
    wait = min(BACKOFF_CAP, BACKOFF_BASE * 2**attempt)
    wait *= 0.5 + random.random() / 2  # jitter, or a burst retries in lockstep
    if hint is not None:
        wait = max(wait, hint)
    return None if wait > remaining else wait


async def _get(url: str, what: str) -> Any:
    deadline = time.monotonic() + RETRY_BUDGET_SECONDS
    status: int | None = None
    detail = ""

    for attempt in range(MAX_ATTEMPTS):
        hint: float | None = None
        try:
            r = await _fetch(url)
        except requests.RequestException as exc:
            status, detail = None, f"{type(exc).__name__}: {exc}"[:160]
        else:
            if r.status_code < 400:
                return r.json()
            status, detail = r.status_code, f"HTTP {r.status_code}"
            if r.status_code == 429:
                hint = _retry_after(r.headers.get("Retry-After"))
                _latch()
                emit(
                    "catalog.rate_limited",
                    {"what": what, "attempt": attempt + 1, "retry_after": r.headers.get("Retry-After")},
                    "error",
                )
            elif r.status_code < 500:  # 404 and friends: retrying cannot help
                break

        wait = _delay(attempt, hint, deadline - time.monotonic())
        if wait is None or attempt == MAX_ATTEMPTS - 1:
            break
        emit("catalog.retry", {"what": what, "attempt": attempt + 1, "in_s": round(wait, 2), "why": detail})
        await asyncio.sleep(wait)

    emit("catalog.unavailable", {"what": what, "status": status, "error": detail}, "error")
    raise CatalogUnavailable(url, status, detail)


async def get_taxonomy(force: bool = False) -> list[dict[str, str]]:
    """The lock is held across the retries on purpose — one queue against a limiter
    beats a thundering herd — which is what bounds RETRY_BUDGET_SECONDS.

    A stale taxonomy is served rather than failing the turn: it is handles and titles,
    which are stable, and it is already a process-lifetime cache. Availability is never
    served from it."""
    global _taxonomy
    async with _tax_lock:
        if _taxonomy is None or force:
            try:
                data = await _get(f"{BASE}/collections.json?limit=250", "taxonomy")
            except CatalogUnavailable:
                if _taxonomy is None:
                    raise
                emit("catalog.taxonomy_stale", {"count": len(_taxonomy)}, "guardrail")
                return _taxonomy
            _taxonomy = [{"handle": c["handle"], "title": c["title"]} for c in data["collections"]]
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
    gid = f"gid://shopify/Product/{raw['id']}"
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
        product_gid=gid,
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

    data = await _get(f"{BASE}/collections/{handle}/products.json?limit={limit}", f"collection:{handle}")

    products = []
    for raw in data.get("products", []):
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


# Ordered, because "nearest available" has to be measurable. Aliases share a rung.
_GARMENT_RANK = {
    "xxs": 0, "2xs": 0, "xs": 1, "s": 2, "m": 3, "l": 4,
    "xl": 5, "xxl": 6, "2xl": 6, "xxxl": 7, "3xl": 7, "4xl": 8, "5xl": 9,
}
_GARMENT = frozenset(_GARMENT_RANK)


def _is_real_size(label: str) -> bool:
    """"One Size" / "70 L" is a placeholder, not a size the customer could have asked
    for — resolving to it is not a substitution and must not be disclosed as one."""
    return _num(label) is not None or _norm(label) in _GARMENT


def _num(s: str) -> float | None:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*", s)
    return float(m.group(1)) if m else None


# The model writes sizes the way the customer said them — "US 10.5", "men's L",
# "size 8" — while feed labels are bare ("10.5", "L"). Unstripped, none of them
# match, and `_choose_size` falls through to "first available, flagged as a
# substitution": a US 10.5 request came back as a 6.5 with 10.5 in stock.
_SIZE_NOISE = re.compile(
    r"(?:\b|^)(?:us|uk|eu|eur|men(?:'s|s)?|women(?:'s|s)?|size[sd]?|shoe[s]?)(?:\b|$)", re.I
)


# Labels are letter codes; customers say words. "Large" matched nothing and fell to
# the last resort, which flags a substitution that did not happen.
_GARMENT_ALIASES = {
    "extra small": "xs", "x small": "xs", "xsmall": "xs",
    "small": "s", "medium": "m", "large": "l",
    "extra large": "xl", "x large": "xl", "xlarge": "xl",
    "2x": "xxl", "2xl": "xxl", "double extra large": "xxl",
}


def _clean_request(requested: str) -> str:
    """Never splits on the apostrophe: "women's S" would yield a stray "s" that is
    indistinguishable from the garment size S."""
    out = re.sub(r"\s+", " ", _SIZE_NOISE.sub(" ", requested)).strip()
    return _GARMENT_ALIASES.get(out.casefold(), out) or requested


def _num_in(s: str) -> float | None:
    """A number anywhere in the REQUEST. `_num` stays strict for labels — a label
    counts as numeric only when it is nothing but a number."""
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def _parts(label: str) -> set[str]:
    return {p for p in re.split(r"[\s/\-–—]+", _norm(label)) if p}


def _match_index(labels: list[str], requested: str) -> int | None:
    for i, lab in enumerate(labels):
        if lab == requested:
            return i
    rn = _num_in(requested)
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


# A refusal has to reach the customer's prose, and the tools adapter deliberately
# collapses NoStockError to None on the way up. Same shape as obs.trace.bind_sink: the
# loop binds a list for the turn and drains it after `_select`, so nothing is global
# and nothing crosses a layer boundary as an argument.
_too_far: ContextVar[list[dict[str, Any]] | None] = ContextVar("too_far", default=None)


def bind_too_far(sink: list[dict[str, Any]] | None) -> None:
    _too_far.set(sink)


def _record_too_far(requested: str, offered: str, steps: float) -> None:
    sink = _too_far.get()
    if sink is not None:
        sink.append({"requested": requested, "offered": offered, "steps": steps})


# How far "nearest available" may travel before it stops being a substitution and
# starts being a different garment. Observed live: an XL request handed an S, disclosed
# as "check the fit before you order". Both numbers are calibration knobs, not truths —
# 10.5 -> 11.5 sits EXACTLY on the ceiling, so an EU ladder or third-sizes would need
# these retuned rather than assumed.
MAX_SIZE_STEPS = 2
_RUNG = 0.5  # US sizes step by a half, so 10.5 -> 11.5 is two rungs, not one


def _rank(label: str) -> tuple[str, float] | None:
    """Position on a size ladder, or None when the label is not one — "One Size",
    a capacity, a height range. Three shapes occur live: a bare number, a bare garment
    code, and the MT500's whole title, where the code has to be picked out of the parts."""
    n = _num(label)
    if n is not None:
        return "num", n / _RUNG
    tokens = _parts(label) & _GARMENT
    # Two garment tokens in one label is not a ladder position worth trusting.
    return ("garment", float(_GARMENT_RANK[next(iter(tokens))])) if len(tokens) == 1 else None


def _substitute(values: list[tuple[str, bool]], requested: str, idx: int) -> tuple[int, bool] | None:
    """Every substituted exit in `_choose_size` funnels through here.

    Distance is measured in LADDER STEPS, never in list index. The feed groups variants
    by colour, so the colour boundary sits inside the index space: with
    Red/S,M,L,XL then Blue/S, a sold-out XL is ONE index from Blue/S and three sizes
    from it. An index ceiling would have let the reported bug straight through.
    """
    want, got = _rank(requested), _rank(values[idx][0])
    if want is not None and got is not None:
        # A garment request against a numeric ladder is a category error, not a
        # far-away size. Refuse it rather than treat it as unmeasurable.
        steps = abs(want[1] - got[1]) if want[0] == got[0] else float("inf")
        if steps > MAX_SIZE_STEPS:
            _record_too_far(requested, values[idx][0], steps)
            emit(
                "guardrail.size_too_far",
                {"requested": requested, "offered": values[idx][0], "steps": steps, "max": MAX_SIZE_STEPS},
                level="guardrail",
            )
            return None
    # Either rank unmeasurable: allow. Refusing what cannot be measured would make
    # every "One Size" product unservable for no reason.
    return idx, True


def _choose_size(values: list[tuple[str, bool]], requested: str | None) -> tuple[int, bool] | None:
    if not any(a for _, a in values):
        return None
    if requested is None:
        return next(i for i, (_, a) in enumerate(values) if a), False

    requested = _clean_request(requested)
    idx = _match_index([lab for lab, _ in values], requested)
    if idx is not None:
        if values[idx][1]:
            return idx, False
        near = _nearest_available(values, idx)
        return _substitute(values, requested, near) if near is not None else None

    rn = _num_in(requested)
    if rn is not None:
        numeric = [(i, _num(lab)) for i, (lab, a) in enumerate(values) if a and _num(lab) is not None]
        if numeric:
            # Landing on the requested number IS the requested size. Reporting it as a
            # substitution told the customer their in-stock size was sold out.
            best, found = min(numeric, key=lambda p: abs(p[1] - rn))
            return (best, False) if found == rn else _substitute(values, requested, best)

    offered_a_choice = len(values) > 1 or _is_real_size(values[0][0])
    first = next(i for i, (_, a) in enumerate(values) if a)
    # Not a substitution when there was no choice on offer, so no ceiling applies.
    return _substitute(values, requested, first) if offered_a_choice else (first, False)


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


def _feed_values(product: CatalogProduct) -> list[tuple[str, bool]]:
    """Size component of every variant, in feed order. A feed variant `title` is the
    option values joined by ' / ' in `option_names` order, so 'Dark Cinnamon / 6.5'
    yields '6.5' and the numeric nearest-size search keeps working.

    Positional splitting is only trusted when the part count matches the option count.
    An option VALUE may itself contain a slash — the MT500 bag is Colour+Size and reads
    'Smoked Black / M / 5\'2"-5\'5"' — and mis-slicing that would match on a height
    range. Falling back to the whole title is safe: `_match_index` tokenises it."""
    idx = next((i for i, name in enumerate(product.option_names) if _is_size(name)), None)
    out: list[tuple[str, bool]] = []
    for v in product.variants:
        parts = [p.strip() for p in v.size_label.split("/")]
        if idx is not None and len(parts) == len(product.option_names):
            out.append((parts[idx], v.available))
        else:
            out.append((v.size_label, v.available))
    return out


def _resolve_from_feed(product: CatalogProduct, requested_size: str | None) -> ResolvedVariant | None:
    """Resolve against data we already hold, at ZERO MCP calls.

    The storefront feed carries every variant's id, title, price and stock flag, the
    id IS the MCP variant GID (verified: feed 41919445434430 'Dark Cinnamon / 6.5' ==
    get_product's gid://shopify/ProductVariant/41919445434430), and the collection
    feed's `available` cross-checks against `get_product` exactly (AGENTS.md §Catalog).
    The three-call grid walk therefore buys nothing — and it was what tripped the rate
    limiter: 3 calls x 8 slots is a 24-request burst, and a trip costs ~48 minutes.
    """
    values = _feed_values(product)
    if not values:
        return None

    chosen: tuple[int, bool] | None = None
    if requested_size:
        # The same size usually exists in several colours. An exact available match in
        # a later colour beats the nearest size in the first one, which `_choose_size`
        # alone would pick — and would then disclose a substitution that never happened.
        want = _norm(_clean_request(requested_size))
        exact = next((i for i, (lab, avail) in enumerate(values) if avail and _norm(lab) == want), None)
        if exact is not None:
            chosen = (exact, False)

    if chosen is None:
        chosen = _choose_size(values, requested_size)
    if chosen is None:
        return None

    idx, substituted = chosen
    variant = product.variants[idx]
    emit(
        "catalog.size_matched",
        {
            "product": product.product_gid,
            "requested": requested_size,
            "label": variant.size_label,
            "substituted": substituted,
            "source": "storefront_feed",
        },
        "guardrail" if substituted else "info",
    )
    rv = ResolvedVariant(
        variant_gid=variant.variant_gid,
        size_label=variant.size_label,
        price_minor=variant.price_minor,
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
            "source": "storefront_feed",
        },
    )
    return rv


async def resolve_variant(product: CatalogProduct, requested_size: str | None = None) -> ResolvedVariant:
    """Per-person resolution repeats the same (product, size) pair, so successes are
    held briefly. Bounded by TTL because this DOES hold availability — unlike _labels.
    create_cart stays the authoritative stock check; a line that sold out in between
    is caught by the cart guardrail. Failures are never cached: stock comes back."""
    key = (product.product_gid, requested_size)
    hit = _resolved_cache.get(key)
    if hit is not None and time.monotonic() - hit[0] < _RESOLVED_TTL:
        emit("catalog.variant_cached", {"product": key[0], "size": requested_size})
        return hit[1]

    variant = await _resolve_variant(product, requested_size)
    _resolved_cache[key] = (time.monotonic(), variant)
    return variant


async def _resolve_variant(product: CatalogProduct, requested_size: str | None) -> ResolvedVariant:
    from_feed = _resolve_from_feed(product, requested_size)
    if from_feed is not None:
        return from_feed

    if product.variants:
        # Every variant and its stock flag came from the feed, so "nothing matched"
        # here is the real answer rather than a gap worth spending MCP calls on.
        emit("catalog.no_stock", {"product": product.product_gid, "title": product.title}, "guardrail")
        raise NoStockError(product, _feed_values(product))

    emit("catalog.feed_variantless", {"product": product.product_gid}, "guardrail")
    return await _resolve_via_mcp(product, requested_size)


async def _resolve_via_mcp(product: CatalogProduct, requested_size: str | None) -> ResolvedVariant:
    """The verified three-call grid walk. Only reachable for a product the feed handed
    us with no variants at all — kept because it is proven against live behaviour
    (`get_product` with no `selected` returns available: null, hence the partial probe)."""
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
