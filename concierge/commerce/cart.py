"""The transaction. Nothing else in the repo constructs a cart line.

Line shape is `line_items[].item.id` — not `merchandise_id`, not a bare id
(SPEC.md §3.1) — and every line goes in ONE create_cart call.
"""

from __future__ import annotations

from typing import Any

from concierge.commerce.ucp import CONTEXT, call_ucp
from concierge.domain.models import CartResult, KitItem
from concierge.obs.trace import emit


def cart_line(variant_gid: str, quantity: int = 1) -> dict[str, Any]:
    return {"item": {"id": variant_gid}, "quantity": quantity}


def _total(cart: dict[str, Any], kind: str) -> int | None:
    for t in cart.get("totals") or []:
        if t.get("type") == kind:
            return t.get("amount")
    return None


async def create_cart(items: list[KitItem]) -> CartResult:
    if not items:
        raise ValueError("create_cart called with no items")

    lines = [cart_line(i.variant_id, i.quantity) for i in items]
    cart = await call_ucp("create_cart", {"cart": {"line_items": lines, "context": CONTEXT}})

    returned = {(li.get("item") or {}).get("id") for li in cart.get("line_items") or []}
    missing = [i.variant_id for i in items if i.variant_id not in returned]
    if missing:
        emit(
            "cart.lines_dropped",
            {"missing": ",".join(missing), "requested": len(items), "returned": len(returned)},
            "guardrail",
        )

    expected = sum(i.price_minor * i.quantity for i in items)
    subtotal = _total(cart, "subtotal")
    if subtotal is not None and subtotal != expected and not missing:
        emit(
            "cart.total_mismatch",
            {"expected_minor": expected, "subtotal_minor": subtotal},
            "guardrail",
        )

    total = _total(cart, "total")
    result = CartResult(
        cart_id=cart["id"],
        continue_url=cart["continue_url"],
        total_minor=total if total is not None else expected,
        currency=cart.get("currency") or "USD",
        line_count=len(cart.get("line_items") or []),
        expires_at=cart.get("expires_at"),
    )
    emit(
        "cart.created",
        {
            "cart_id": result.cart_id,
            "lines": result.line_count,
            "total_minor": result.total_minor,
            "continue_url": result.continue_url,
        },
    )
    return result


# get_cart / update_cart do NOT take create_cart's argument shape (verified live):
# get_cart is flat, update_cart wants the id at top level AND a cart object, and it
# REPLACES the lines rather than adding to them.
async def get_cart(cart_id: str) -> dict[str, Any]:
    cart = await call_ucp("get_cart", {"id": cart_id, "context": CONTEXT})
    emit("cart.fetched", {"cart_id": cart_id, "lines": len(cart.get("line_items") or [])})
    return cart


async def update_cart(cart_id: str, line_items: list[dict[str, Any]]) -> dict[str, Any]:
    cart = await call_ucp(
        "update_cart", {"id": cart_id, "cart": {"line_items": line_items, "context": CONTEXT}}
    )
    emit("cart.updated", {"cart_id": cart_id, "lines": len(cart.get("line_items") or [])})
    return cart
