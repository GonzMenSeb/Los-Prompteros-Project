"""Drives the state machine the way the browser does.

`reflex export --frontend-only` proves the component tree compiles; it never runs
an event handler. This runs send_message and confirm_cart for real and asserts
every state the UI is supposed to be able to show.

    PYTHONPATH=. ./.venv/bin/python scripts/verify_ui.py
"""

from __future__ import annotations

import asyncio

from concierge.state import State, summarise, to_card


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{f'  — {detail}' if detail else ''}")
    return ok


async def main() -> int:
    state = State(_reflex_internal_init=True)
    results: list[bool] = []

    print("\nsend_message …")
    async for _ in state.send_message({"message": "Hiking Páramo de Santurbán, 2 nights"}):
        pass

    results.append(check("trace populated", len(state.trace) >= 10, f"{len(state.trace)} rows"))
    results.append(
        check(
            "guardrail rows present",
            sum(r.level == "guardrail" for r in state.trace) >= 3,
            f"{sum(r.level == 'guardrail' for r in state.trace)} guardrail",
        )
    )
    results.append(check("trace rows carry a payload summary", all(r.summary for r in state.trace)))
    results.append(check("kit populated", len(state.kit_items) > 0, f"{len(state.kit_items)} items"))
    results.append(
        check("exactly one size substitution", state.substitution_count == 1)
    )
    results.append(check("unservable slots reported", len(state.unservable_slots) == 2))
    results.append(check("over budget indicator fires", state.over_budget is True,
                         f"{state.total_display} vs {state.budget_display}"))
    results.append(check("assistant replied", len(state.messages) == 2))
    results.append(check("citations attached", len(state.messages[1].citations) == 3))
    results.append(check("awaiting confirmation", state.awaiting_confirmation is True))
    results.append(check("no cart before confirmation", state.has_cart is False))
    results.append(check("is_thinking cleared", state.is_thinking is False))

    cards = state.cards
    results.append(check("every card has a photo", all(c.image_url.startswith("http") for c in cards)))
    results.append(
        check("every card has a formatted price", all(c.price_display.startswith("$") for c in cards))
    )
    results.append(
        check(
            "every card links to a product page",
            all(c.product_url.startswith("https://www.decathlon.com/products/") for c in cards),
        )
    )

    print("\nconfirm_cart guard …")
    guarded = State(_reflex_internal_init=True)
    async for _ in guarded.confirm_cart():
        pass
    results.append(check("confirm_cart is a no-op without awaiting_confirmation", guarded.has_cart is False))

    print("\nconfirm_cart …")
    async for _ in state.confirm_cart():
        pass

    results.append(check("cart url set", state.cart_url.startswith("https://"), state.cart_url))
    results.append(check("cart id is a Cart gid", state.cart_id.startswith("gid://shopify/Cart/")))
    results.append(check("cart total formatted", state.cart_total_display.startswith("$")))
    results.append(check("awaiting_confirmation cleared", state.awaiting_confirmation is False))
    results.append(
        check("cart.created in trace", any(r.event == "cart.created" for r in state.trace))
    )
    results.append(
        check(
            "human.confirmed logged as guardrail",
            any(r.event == "human.confirmed" and r.level == "guardrail" for r in state.trace),
        )
    )

    print("\nclear …")
    state.clear()
    results.append(check("clear resets everything", not state.kit_items and not state.trace and not state.cart_url))

    print("\nsummarise() on nested payloads …")
    results.append(
        check("nested payload flattens to scalars", "b=" in summarise({"a": 1, "b": {"c": [1, 2]}}))
    )

    print(f"\n{sum(results)}/{len(results)} passed\n")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
