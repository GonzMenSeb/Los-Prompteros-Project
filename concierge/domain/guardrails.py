"""Deterministic guardrails — SPEC.md §6.1, §6.2.

A guardrail written in the prompt is a suggestion; a guardrail written in Python
is a guarantee. Everything here is pure and synchronous, and every verdict emits
a trace event at level="guardrail" so a judge can watch it fire.
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from concierge.domain.models import (
    CatalogProduct,
    GearSlot,
    Kit,
    KitItem,
    minor_to_display,
)
from concierge.obs.trace import emit


class CoverageVerdict(BaseModel):
    servable: list[str] = Field(default_factory=list)
    unservable: list[str] = Field(default_factory=list)
    reasons: dict[str, str] = Field(default_factory=dict)


class StockRejection(BaseModel):
    slot: str = ""
    product_title: str = ""
    size_label: str = ""
    reason: str = ""
    detail: str = ""


class StockVerdict(BaseModel):
    ok: bool = True
    items: list[KitItem] = Field(default_factory=list)
    rejected: list[StockRejection] = Field(default_factory=list)


class SwapCandidate(BaseModel):
    variant_id: str
    product_title: str
    price_minor: int
    slot: str = ""


class BudgetVerdict(BaseModel):
    ok: bool = True
    budget_minor: int | None = None
    total_minor: int = 0
    over_by_minor: int = 0
    nothing_fits: bool = False
    swap_candidates: list[SwapCandidate] = Field(default_factory=list)
    message: str = ""


class ProvenanceVerdict(BaseModel):
    ok: bool = True
    renderable: list[KitItem] = Field(default_factory=list)
    dropped: list[dict] = Field(default_factory=list)


class SpecClaim(BaseModel):
    text: str
    kind: str
    start: int
    end: int


def check_coverage(
    slots: Sequence[GearSlot],
    retrieved: Mapping[str, Sequence[CatalogProduct]],
) -> CoverageVerdict:
    """`retrieved` is keyed by COLLECTION HANDLE. A handle that was fetched and
    came back empty must be present with []; absent means never fetched."""
    verdict = CoverageVerdict()

    for slot in slots:
        if not slot.collection_handles:
            verdict.unservable.append(slot.name)
            verdict.reasons[slot.name] = "no_handles"
            continue

        best = ""
        for handle in slot.collection_handles:
            if handle not in retrieved:
                best = best or "handle_not_retrieved"
                continue
            products = retrieved[handle]
            if not products:
                best = "empty_collection"
                continue
            if any(v.available for p in products for v in p.variants):
                best = "ok"
                break
            best = "no_stock"

        if best == "ok":
            verdict.servable.append(slot.name)
        else:
            verdict.unservable.append(slot.name)
            verdict.reasons[slot.name] = best

    emit(
        "guardrail.coverage",
        {
            "servable": verdict.servable,
            "unservable": verdict.unservable,
            "reasons": verdict.reasons,
        },
        "guardrail",
    )
    return verdict


def check_stock(candidates: Sequence[Mapping[str, Any]]) -> StockVerdict:
    """Feed raw dicts, never KitItems. `KitItem.available: Literal[True]` makes an
    out-of-stock item unconstructible; this is the friendly path that reports it
    instead of throwing a ValidationError into the UI."""
    verdict = StockVerdict()

    for c in candidates:
        slot = str(c.get("slot", ""))
        title = str(c.get("product_title", ""))
        size = str(c.get("size_label", ""))

        if c.get("available") is not True:
            verdict.rejected.append(
                StockRejection(
                    slot=slot,
                    product_title=title,
                    size_label=size,
                    reason="out_of_stock",
                    detail=f"{title} in {size or 'the requested size'} is sold out",
                )
            )
            continue

        try:
            verdict.items.append(KitItem(**dict(c)))
        except ValidationError as e:
            verdict.rejected.append(
                StockRejection(
                    slot=slot,
                    product_title=title,
                    size_label=size,
                    reason="invalid_item",
                    detail="; ".join(
                        f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()
                    )[:400],
                )
            )

    verdict.ok = not verdict.rejected
    emit(
        "guardrail.stock",
        {
            "confirmed": len(verdict.items),
            "rejected": [r.model_dump() for r in verdict.rejected],
        },
        "guardrail",
    )
    return verdict


def check_budget(kit: Kit, budget_minor: int | None = None) -> BudgetVerdict:
    """Integer arithmetic in minor units, computed in code, never by the model."""
    budget = budget_minor if budget_minor is not None else kit.budget_minor
    total = kit.total_minor

    verdict = BudgetVerdict(budget_minor=budget, total_minor=total)

    if budget is None:
        verdict.message = f"Kit total {minor_to_display(total)}. No budget set."
        emit("guardrail.budget", verdict.model_dump(), "guardrail")
        return verdict

    if not kit.items:
        # "kit us both out for $40" that fits nothing must not report "$40 under
        # budget" — an empty kit is the nothing-fits case, not a cheap one.
        verdict.ok = False
        verdict.nothing_fits = True
        verdict.message = f"Nothing fits {minor_to_display(budget)} — I could not put a single item in the kit."
        emit("guardrail.budget", verdict.model_dump(), "guardrail")
        return verdict

    if total <= budget:
        verdict.message = (
            f"{minor_to_display(total)} of {minor_to_display(budget)} — "
            f"{minor_to_display(budget - total)} under budget."
        )
        emit("guardrail.budget", verdict.model_dump(), "guardrail")
        return verdict

    verdict.ok = False
    verdict.over_by_minor = total - budget

    cheapest = min((i.price_minor for i in kit.items), default=None)
    verdict.nothing_fits = cheapest is None or cheapest > budget

    if verdict.nothing_fits:
        verdict.message = (
            f"Nothing in this kit fits {minor_to_display(budget)} — the cheapest single item "
            f"is {minor_to_display(cheapest)}."
            if cheapest is not None
            else f"Nothing fits {minor_to_display(budget)}."
        )
        emit("guardrail.budget", verdict.model_dump(), "guardrail")
        return verdict

    # most expensive first: swapping those closes the gap in the fewest changes
    for item in sorted(kit.items, key=lambda i: i.price_minor * i.quantity, reverse=True):
        verdict.swap_candidates.append(
            SwapCandidate(
                variant_id=item.variant_id,
                product_title=item.product_title,
                price_minor=item.price_minor,
                slot=item.slot,
            )
        )
        if sum(s.price_minor for s in verdict.swap_candidates) >= verdict.over_by_minor:
            break

    verdict.message = (
        f"{minor_to_display(total)} is {minor_to_display(verdict.over_by_minor)} over the "
        f"{minor_to_display(budget)} budget. Swap: "
        + ", ".join(s.product_title for s in verdict.swap_candidates)
        + "."
    )
    emit("guardrail.budget", verdict.model_dump(), "guardrail")
    return verdict


def check_substitution(items: Sequence[KitItem]) -> list[str]:
    """One explicit disclosure sentence per substituted size. Never silently swap.

    `KitItem` carries no requested size — only the flag — so the sentence names the
    size actually being bought and says plainly that it is not the one asked for.
    """
    sentences = [
        f"{i.product_title}: the size you asked for was out of stock, so this is "
        f"{i.size_label} instead — check the fit before you order."
        for i in items
        if i.size_substituted
    ]
    emit("guardrail.substitution", {"count": len(sentences), "disclosures": sentences}, "guardrail")
    return sentences


def check_size_confirmation(items: Sequence[KitItem]) -> list[str]:
    """One sentence per wearable whose size the customer never gave.

    Without a requested size `_choose_size` takes the first available variant, and
    nothing else flags it: `size_substituted` stays False because no size was asked
    for. Observed live 29 Jul 2026 — a 9.5 request arrived one turn too late and the
    cart went out with a 7. This is the only guardrail that catches that case.
    """
    sentences = [
        f"{i.product_title}: I put a {i.size_label} in the cart because you haven't told "
        f"me your size yet — tell me and I'll swap that line."
        for i in items
        if not i.size_confirmed
    ]
    emit("guardrail.size_unconfirmed", {"count": len(sentences), "asks": sentences}, "guardrail")
    return sentences


_VARIANT_GID = "gid://shopify/ProductVariant/"


def check_provenance(items: Sequence[KitItem | Mapping[str, Any]]) -> ProvenanceVerdict:
    """Nothing renders that isn't a real variant: a card needs a variant GID AND a
    product URL. A prose-only product mention has neither and is dropped."""
    verdict = ProvenanceVerdict()

    for raw in items:
        if isinstance(raw, KitItem):
            verdict.renderable.append(raw)
            continue

        data = dict(raw)
        title = str(data.get("product_title", "") or data.get("title", ""))
        variant_id = str(data.get("variant_id", "") or "")
        url = str(data.get("product_url", "") or "")

        if not variant_id.startswith(_VARIANT_GID):
            verdict.dropped.append({"product_title": title, "reason": "no_variant_id"})
            continue
        if not url.startswith(("http://", "https://")):
            verdict.dropped.append({"product_title": title, "reason": "no_product_url"})
            continue
        try:
            verdict.renderable.append(KitItem(**data))
        except ValidationError as e:
            verdict.dropped.append(
                {"product_title": title, "reason": "invalid_item", "detail": str(e)[:300]}
            )

    verdict.ok = not verdict.dropped
    emit(
        "guardrail.provenance",
        {"renderable": len(verdict.renderable), "dropped": verdict.dropped},
        "guardrail",
    )
    return verdict


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

# A role marker makes everything up to its close tag untrusted, so the CONTENT goes
# too — stripping only the tag would leave the payload reading as ordinary copy.
_ROLE_BLOCK = re.compile(r"(?is)<\s*(system|assistant|user|instructions?)\b[^>]*>.*?(?:<\s*/\s*\1\s*>|\Z)")

_INJECTION = re.compile(
    r"""(?ix)
    ignore \s+ (all \s+ |any \s+ |your \s+ |the \s+ )* (previous|prior|above|earlier|system) |
    disregard \s+ (all \s+ |any \s+ |your \s+ |the \s+ )* (previous|prior|above|earlier|instruction|system) |
    (you \s+ are \s+ now|from \s+ now \s+ on|new \s+ instructions?) |
    (system \s* (prompt|message|:)) |
    \[/? \s* (INST|SYSTEM|/?s) \s* \] |
    (reveal|print|repeat|output|show) \s+ (me \s+ )? (your|the) \s+ (system \s+ )? (prompt|instructions?|rules) |
    (add|put) \s+ .{0,30} \s* (to \s+ the \s+ cart|free) |
    (set|make) \s+ .{0,20} price \s+ to |
    100\s*% \s+ (off|discount) |
    developer \s+ mode | jailbreak
    """
)


def strip_untrusted(text: str, max_chars: int = 400) -> str:
    """Catalog free text (`body_html`, `description.html`) is untrusted input.
    Prompt injection arrives through catalog data, not just through the user."""
    if not text:
        return ""

    # Unescape first: &lt;system&gt; is a role marker too. Then tags become segment
    # breaks, not spaces — an injection lives in its own <p>, and collapsing that
    # boundary makes the surrounding real copy collateral damage.
    raw = html.unescape(str(text))
    raw, role_blocks = _ROLE_BLOCK.subn("\n", raw)
    plain = _TAG.sub("\n", raw)

    kept, removed = [], []
    if role_blocks:
        removed.append(f"<{role_blocks} role-marked block(s)>")
    for part in re.split(r"(?<=[.!?])\s+|\n+", plain):
        part = _WS.sub(" ", part).strip()
        if not part:
            continue
        (removed if _INJECTION.search(part) else kept).append(part)

    out = _WS.sub(" ", " ".join(kept)).strip()
    truncated = len(out) > max_chars
    if truncated:
        out = out[:max_chars].rsplit(" ", 1)[0] + "…"

    if removed or truncated:
        emit(
            "guardrail.untrusted_text",
            {"removed": [r[:120] for r in removed], "truncated": truncated},
            "guardrail",
        )
    return out


_DASHES = {0x2212: "-", 0x2013: "-", 0x2014: "-", 0x2010: "-", 0x2011: "-"}

_CLAIM_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("temperature", re.compile(r"(?i)-?\s?\d+(?:\.\d+)?\s*(?:°\s*)?(?:c|f)\b(?!\w)")),
    ("temperature", re.compile(r"(?i)-?\s?\d+(?:\.\d+)?\s*degrees?\s*(?:celsius|fahrenheit|c|f)?")),
    (
        "temperature",
        re.compile(
            r"(?i)\b(?:rated|comfort[- ]rated|good)\s+(?:down\s+)?to\s+"
            r"(?P<key>-?\s?\d+(?:\.\d+)?\s*(?:°\s*)?(?:celsius|fahrenheit|c|f)?)\b"
        ),
    ),
    ("capacity", re.compile(r"(?i)\b\d+(?:\.\d+)?\s*(?:l\b|litre|liter)s?")),
    ("waterproof", re.compile(r"(?i)\b\d[\d,]*\s*(?:mm|k)\s*(?:hydrostatic|water\s*column)?\b(?=\s*(?:hydrostatic|waterproof|water|rating|membrane|shell|[.,;]|$))")),
    ("waterproof", re.compile(r"(?i)\b(?:fully\s+)?(?:seam[- ]sealed|taped\s+seams?|gore[- ]?tex|waterproof|windproof|breathable|water[- ]?resistant)\b")),
    ("material", re.compile(r"(?i)\b(?:merino|goose\s+down|duck\s+down|down\s+fill|ripstop|cordura|primaloft|polyester|nylon|leather|fleece)\b")),
    ("material", re.compile(r"(?i)\b\d+\s*(?:fill\s*power|fp)\b")),
    ("weight", re.compile(r"(?i)\b\d+(?:\.\d+)?\s*(?:kg|kgs|g|grams?|lbs?|pounds?|oz|ounces?)\b")),
    ("price", re.compile(r"\$\s?\d[\d,]*(?:\.\d{1,2})?")),
    # Unbacked BY CONSTRUCTION, not merely unbacked by this kit: the feed's
    # `compare_at_price` and MCP's `list_price` are deliberately unmapped, so no
    # pre-discount number can reach the model at all. The NH500 really is $100 from
    # $149 — we still must not say so, because nothing in the pipeline sourced it.
    ("discount", re.compile(r"(?i)\b\d+\s*%\s*(?:off|discount|reduction|savings?)\b")),
    ("discount", re.compile(r"(?i)\b(?:was|were|down\s+from|reduced\s+from|marked\s+down\s+from|rrp|msrp|list\s+price)\s*:?\s*\$?\s?\d[\d,]*(?:\.\d{1,2})?")),
    ("discount", re.compile(r"(?i)\bsave\s*(?:up\s+to\s*)?\$?\s?\d[\d,]*(?:\.\d{1,2})?")),
    ("discount", re.compile(r"(?i)\b(?:on\s+sale|clearance|discounted|half\s+price|marked\s+down)\b")),
]


def _price_minor(text: str) -> int | None:
    try:
        return round(float(text.replace("$", "").replace(",", "").strip()) * 100)
    except ValueError:
        return None


def _allowed_prices(items: Sequence[Any], extra: Iterable[int]) -> set[int]:
    """A price in prose must be one the code computed: a unit price, a line total,
    the kit total, or a figure the caller explicitly whitelists (a budget)."""
    unit: list[int] = []
    line: list[int] = []
    merged: dict[str, list[int]] = {}
    for i in items:
        price = i.get("price_minor") if isinstance(i, Mapping) else getattr(i, "price_minor", None)
        if not isinstance(price, int):
            continue
        qty = i.get("quantity", 1) if isinstance(i, Mapping) else getattr(i, "quantity", 1)
        qty = qty if isinstance(qty, int) else 1
        vid = i.get("variant_id", "") if isinstance(i, Mapping) else getattr(i, "variant_id", "")
        unit.append(price)
        line.append(price * qty)
        slot = merged.setdefault(str(vid), [price, 0])
        slot[1] += qty

    # MCP merges duplicate variant lines: two people in the same size come back as
    # one line at qty 2, so "$200 for the pair" is legitimate even when the kit
    # holds two separate quantity-1 items.
    return {*unit, *line, sum(line), *(p * q for p, q in merged.values()), *extra}


def _normalise(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).translate(_DASHES).lower()
    s = s.replace("°", "").replace("º", "")
    return _WS.sub(" ", s)


def _compact(s: str) -> str:
    """Fold to a comparison key. A minus in front of a digit is meaning, not
    punctuation — "-5C" must not compare equal to a title that says "5°C"."""
    s = re.sub(r"-(?=\d)", "neg", _normalise(s))
    return re.sub(r"[\s\-]", "", s)


# `handle` earns its place: it is a live catalog slug, so "hiking-fleeces-mid-layers"
# legitimately backs the word "fleece". `rationale` and `slot` are model-authored.
_BACKING_FIELDS = ("product_title", "title", "handle", "size_label", "product_type", "vendor", "description")


def _backing_text(items: Sequence[Any]) -> str:
    """Retrieval-derived fields ONLY. `KitItem.rationale` is model prose — including
    it would let the model back its own invention by writing it twice."""
    parts: list[str] = []
    for item in items:
        if isinstance(item, str):
            parts.append(item)
            continue
        for field in _BACKING_FIELDS:
            value = item.get(field) if isinstance(item, Mapping) else getattr(item, field, None)
            if isinstance(value, str):
                parts.append(value)
    return _compact(" | ".join(parts))


def find_unbacked_claims(
    text: str, items: Sequence[Any], *, allowed_minor: Iterable[int] = ()
) -> list[SpecClaim]:
    """Spec-shaped claims in model prose that no retrieved field backs.

    The agent will not invent products — retrieval prevents that. It invents
    *properties* of real ones. No unit conversion is attempted: "-5 °C" is unbacked
    even when a title says "23°F", because the model did not read that off the JSON.
    """
    backing = _backing_text(items)
    prices = _allowed_prices(items, allowed_minor)
    # 1:1 char substitution, so match offsets stay valid against the original text
    probe = text.translate(_DASHES)

    hits: list[SpecClaim] = []
    for kind, pattern in _CLAIM_PATTERNS:
        for m in pattern.finditer(probe):
            if kind == "price":
                # compared as a number, not a string: "$135" and "$135.00" are one price
                if _price_minor(m.group(0)) in prices:
                    continue
                hits.append(SpecClaim(text=m.group(0).strip(), kind=kind, start=m.start(), end=m.end()))
                continue
            # `key` is the measurement itself; matching the framing words too
            # ("rated to 5C") would never find backing for a spec the title states.
            if _compact(m.groupdict().get("key") or m.group(0)) in backing:
                continue
            hits.append(SpecClaim(text=text[m.start() : m.end()].strip(), kind=kind, start=m.start(), end=m.end()))

    claims: list[SpecClaim] = []
    for c in sorted(hits, key=lambda c: (c.start, -(c.end - c.start))):
        if claims and c.start < claims[-1].end:
            continue
        claims.append(c)
    return claims


def scrub_prose(text: str, items: Sequence[Any], *, allowed_minor: Iterable[int] = ()) -> str:
    """Excise unbacked spec claims from model prose. Detection is the deliverable —
    the claim phrase goes, the surrounding reasoning stays."""
    if not text:
        return ""

    claims = find_unbacked_claims(text, items, allowed_minor=allowed_minor)
    if not claims:
        return text

    out = text
    for c in sorted(claims, key=lambda c: c.start, reverse=True):
        out = out[: c.start] + out[c.end :]
    out = re.sub(r"\s+([.,;:])", r"\1", _WS.sub(" ", out))
    out = re.sub(r"^[\s,;:.]+", "", out).strip()

    emit(
        "guardrail.prose",
        {"claims": [c.model_dump() for c in claims], "kinds": sorted({c.kind for c in claims})},
        "guardrail",
    )
    return out


# Cutting here drops the condition clause. "down" must NOT be in this set: it reads
# as a preposition in "rated down to -5" but it is a product word — "rated" already
# cuts that phrase, while "down jacket" is a real query against four live collections.
_STOP_AT = {
    "for", "with", "in", "at", "on", "under", "over", "above", "below", "rated",
    "that", "which", "to", "good", "suitable", "and", "or",
}
_UNIT_WORDS = {
    "degree", "degrees", "celsius", "fahrenheit", "c", "f", "l", "litre", "litres",
    "liter", "liters", "kg", "g", "gram", "grams", "lb", "lbs", "oz", "mm", "cm",
    "person", "people", "season", "seasons", "star", "stars", "size", "sizes",
    "hour", "hours", "day", "days", "night", "nights", "week", "weeks",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
}
# "down" and "warm" are NOT filler: they are product words here. Decathlon ships
# four `*-down-jackets` collections, and "Warm" is in a quarter of live titles.
_FILLER = {
    "a", "an", "the", "some", "any", "i", "me", "my", "we", "our", "us", "you", "your",
    "it", "is", "are", "please", "need", "needs", "want", "looking", "get", "buy",
    "recommend", "something", "best", "cheap",
}


def _drop(t: str) -> bool:
    return any(ch.isdigit() for ch in t) or t in _UNIT_WORDS or t in _FILLER


def check_query_shape(q: str) -> str:
    """Keyword search returns ZERO for descriptive queries (SPEC.md §3.3):
    "sleeping bag" -> 3 products, "sleeping bag 0 degrees celsius" -> 0."""
    tokens = re.findall(r"[A-Za-z0-9']+", _normalise(q))

    kept: list[str] = []
    for t in tokens:
        if t in _STOP_AT:
            break
        if not _drop(t):
            kept.append(t)

    # An empty query is worse than a loose one — search_catalog would be handed "".
    # Retry ignoring the cut, since the head noun can sit behind a stop word.
    if not kept:
        kept = [t for t in tokens if t not in _STOP_AT and not _drop(t)]

    shaped = " ".join(kept[-3:])
    if shaped != _normalise(q).strip():
        emit("guardrail.query_shape", {"original": q, "shaped": shaped, "empty": not shaped}, "guardrail")
    return shaped
