"""One run, rendered as text you can paste into an AI.

The audit panel renders `summarise()`, which clamps every payload value at 120
characters and the whole line at 300 — right for a panel read over your shoulder,
useless for debugging afterwards. This renders the SAME events with their payloads
intact, plus the conversation and the kit and cart that came out, so the paste needs
no further explanation.

Deliberate: the cart's `continue_url` is not redacted. It is a working link to a real
cart, which is exactly what you need when debugging one, and the header says so.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from concierge.domain.models import minor_to_display

# Above this a payload reads better as an indented block than as one long line.
INLINE_MAX = 160
_GUTTER = " " * 14


@dataclass(frozen=True)
class RunSnapshot:
    stamp: str = ""
    mode: str = "live"
    gated: bool = False
    lane: str = "reserved"
    messages: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)
    unservable: list[str] = field(default_factory=list)
    budget_minor: int | None = None
    cart: dict[str, Any] | None = None


def _json(value: Any, indent: int | None = None) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, indent=indent)


def _payload_block(payload: dict[str, Any]) -> str:
    if not payload:
        return f"{_GUTTER}{{}}"
    compact = _json(payload)
    if len(compact) <= INLINE_MAX:
        return f"{_GUTTER}{compact}"
    return "\n".join(f"{_GUTTER}{line}" for line in _json(payload, indent=2).splitlines())


def _header(snap: RunSnapshot) -> list[str]:
    events = snap.events
    turns = sum(1 for m in snap.messages if m.get("role") == "user")
    levels = [e.get("level", "info") for e in events]
    counts = f"{len(events)}"
    tally = [
        f"{levels.count(name)} {name}" for name in ("guardrail", "error") if levels.count(name)
    ]
    if tally:
        counts += f" ({', '.join(tally)})"

    lines = [
        f"# DecaBot run bundle — {snap.stamp}",
        f"mode={snap.mode}  gate={'on' if snap.gated else 'off'}  "
        f"lane={snap.lane}  turns={turns}  events={counts}",
    ]
    if snap.cart and snap.cart.get("url"):
        lines.append("NOTE: contains a live Decathlon cart link.")
    return lines


def _conversation(snap: RunSnapshot) -> list[str]:
    lines = ["", "## Conversation"]
    if not snap.messages:
        lines.append("(nothing said yet)")
        return lines

    turn = 0
    for message in snap.messages:
        role = message.get("role", "?")
        if role == "user":
            turn += 1
        lines.append(f"[{turn} {role}] {message.get('content', '')}")
        cites = message.get("citations") or []
        if cites:
            lines.append("     cite " + "  ".join(str(c) for c in cites))
    return lines


def _kit(snap: RunSnapshot) -> list[str]:
    if not snap.items:
        lines = ["", "## Kit", "(no kit built)"]
        if snap.unservable:
            lines.append("unservable: " + ", ".join(snap.unservable))
        return lines

    total = sum(int(i.get("price_minor", 0)) * int(i.get("quantity", 1)) for i in snap.items)
    count = sum(int(i.get("quantity", 1)) for i in snap.items)
    head = f"## Kit — {count} items · {minor_to_display(total)}"
    if snap.budget_minor is not None:
        delta = total - snap.budget_minor
        verdict = (
            f"OVER by {minor_to_display(delta)}"
            if delta > 0
            else f"under by {minor_to_display(-delta)}"
        )
        head += f" · budget {minor_to_display(snap.budget_minor)} · {verdict}"

    lines = ["", head]
    for item in snap.items:
        flag = "  [SIZE SUBSTITUTED]" if item.get("size_substituted") else ""
        lines.append(
            f"- {item.get('slot', '?')} · {item.get('product_title', '?')} · "
            f"{item.get('size_label', '?')} · qty {item.get('quantity', 1)} · "
            f"{minor_to_display(int(item.get('price_minor', 0)))}{flag}"
        )
        for detail in (item.get("variant_id"), item.get("product_url")):
            if detail:
                lines.append(f"  {detail}")
        if item.get("rationale"):
            lines.append(f"  why: {item['rationale']}")
    if snap.unservable:
        lines.append("unservable: " + ", ".join(snap.unservable))
    return lines


def _cart(snap: RunSnapshot) -> list[str]:
    cart = snap.cart
    if not cart:
        return ["", "## Cart", "(no cart created)"]

    parts = [
        str(cart.get("cart_id", "?")),
        f"{cart.get('line_count', 0)} lines",
        minor_to_display(int(cart.get("total_minor", 0))),
    ]
    if cart.get("expires_at"):
        parts.append(f"expires {cart['expires_at']}")
    lines = ["", "## Cart", "  ·  ".join(parts)]
    if cart.get("url"):
        lines.append(str(cart["url"]))
    return lines


def _trace(snap: RunSnapshot) -> list[str]:
    lines = ["", "## Trace"]
    if not snap.events:
        lines.append("(no events)")
        return lines

    origin = snap.events[0].get("ts") or 0.0
    for event in snap.events:
        offset = float(event.get("ts") or origin) - origin
        lines.append(
            f"{event.get('seq', 0):>4}  +{offset:.3f}s  "
            f"{event.get('level', 'info'):<9}  {event.get('event', '?')}"
        )
        lines.append(_payload_block(event.get("payload") or {}))
    return lines


def render(snap: RunSnapshot) -> str:
    lines: list[str] = []
    for section in (_header, _conversation, _kit, _cart, _trace):
        lines.extend(section(snap))
    return "\n".join(lines) + "\n"
