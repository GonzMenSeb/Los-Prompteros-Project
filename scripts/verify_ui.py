"""Drives the state machine the way the browser does.

`reflex export --frontend-only` proves the component tree compiles; it never runs
an event handler. This runs send_message and confirm_cart for real and asserts
every state the UI is supposed to be able to show.

    PYTHONPATH=. ./.venv/bin/python scripts/verify_ui.py
"""

from __future__ import annotations

import asyncio

from concierge.state import State, TraceRow, summarise, to_card


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

    print("\nsecond turn after a cart exists …")
    trace_before = len(state.trace)
    async for _ in state.send_message({"message": "swap the tent for the cheaper one"}):
        pass
    results.append(check("stale cart cleared", state.has_cart is False))
    results.append(check("confirm button reachable again", state.awaiting_confirmation is True))
    results.append(
        check("trace accumulates across turns", len(state.trace) > trace_before,
              f"{trace_before} -> {len(state.trace)}")
    )
    results.append(
        check("turn.start separates turns", sum(r.event == "turn.start" for r in state.trace) == 2)
    )
    results.append(
        check("turn-one grounding still visible",
              any(r.event == "search.grounded" for r in state.trace))
    )

    print("\ncopy_run …")
    results.append(
        check(
            "_raw_trace mirrors the panel rows",
            len(state._raw_trace) == len(state.trace),
            f"{len(state._raw_trace)} raw vs {len(state.trace)} rows",
        )
    )
    # The panel row carries `summarise()` — a flat string. The mirror has to carry the
    # structure itself, or the bundle is just the screenshot with extra steps.
    results.append(
        check(
            "raw events carry structured payloads, not flattened strings",
            all(isinstance(e["payload"], dict) for e in state._raw_trace),
        )
    )
    results.append(
        check(
            "raw events keep native value types the summary stringifies",
            any(
                isinstance(v, (int, float, bool))
                for e in state._raw_trace
                for v in e["payload"].values()
            ),
        )
    )
    for _ in state.copy_run():
        pass
    text = state._last_bundle
    results.append(check("bundle built", len(text) > 0, f"{len(text)} chars"))
    results.append(check("bundle carries the conversation", "swap the tent for the cheaper one" in text))
    results.append(check("bundle carries a guardrail event", "guardrail" in text))
    results.append(check("bundle carries the kit", "## Kit" in text and "gid://shopify/" in text))
    # Reflex hands state containers back as MutableProxy, which json.dumps misses — the
    # payloads then arrive as Python reprs inside a JSON string. Caught in a browser, not
    # by any handler test, because only a real round trip stores them through Reflex.
    results.append(
        check('payloads are real JSON, not Python reprs', '"turn": 1' in text and "{'turn':" not in text)
    )
    results.append(
        check("nothing is on the wire until a copy fails", state.copy_fallback == "")
    )

    print("\ncopy_finished …")
    state.copy_finished(True)
    results.append(check("a confirmed write shows ok", state.copy_status == "ok"))
    results.append(check("a confirmed write publishes no fallback", state.copy_fallback == ""))
    state.copy_finished(False)
    results.append(check("a refused write shows failed", state.copy_status == "failed"))
    results.append(
        check("a refused write publishes the text to select", state.copy_fallback == text)
    )

    print("\ncopy_run behind a closed gate …")
    # The event is callable over the wire whatever is on screen — same reasoning as
    # confirm_cart. Patched rather than mocked: GATE_ON is read at module import.
    import concierge.state as state_mod

    locked = State(_reflex_internal_init=True)
    # Exactly the state a refused password leaves behind: one guardrail row, still locked.
    locked.trace = [TraceRow(seq=1, event="gate.refused", level="guardrail", summary="")]
    locked._raw_trace = [
        {"seq": 1, "ts": 0.0, "event": "gate.refused", "payload": {}, "level": "guardrail"}
    ]
    was_on = state_mod.GATE_ON
    state_mod.GATE_ON = True
    try:
        for _ in locked.copy_run():
            pass
    finally:
        state_mod.GATE_ON = was_on
    results.append(check("copy_run is a no-op while locked", locked._last_bundle == ""))
    # A refused password now drains a row into `trace`, so "trace is non-empty" alone
    # would light the button up for someone still locked out — and clicking it would do
    # nothing at all.
    state_mod.GATE_ON = True
    try:
        results.append(check("the button stays disabled while locked", locked.can_copy_run is False))
        locked.unlocked = True
        results.append(check("unlocking enables it", locked.can_copy_run is True))
    finally:
        state_mod.GATE_ON = was_on

    print("\nclear …")
    state.clear()
    results.append(check("clear resets everything", not state.kit_items and not state.trace and not state.cart_url))
    results.append(
        check(
            "clear empties the raw mirror and the copy state",
            not state._raw_trace and not state._last_bundle and state.copy_status == "",
        )
    )

    print("\nKitItem without a photo …")
    # No fixture product lacks an image, so this path is only reachable from live
    # retrieval. It must degrade to one placeholder card, not kill the turn.
    from concierge.domain.models import KitItem

    photoless = KitItem(
        slot="tent",
        product_title="A real in-stock product that has no photo",
        product_url="https://www.decathlon.com/products/x",
        variant_id="gid://shopify/ProductVariant/1",
        size_label="One Size",
        price_minor=1000,
        available=True,
    )
    results.append(check("KitItem.image_url defaults to None", photoless.image_url is None))
    card = to_card(photoless)
    results.append(check("to_card does not raise on a None photo", card.image_url == ""))
    results.append(
        check("placeholder card keeps its title", card.product_title == photoless.product_title)
    )

    print("\nsummarise() on nested payloads …")
    results.append(
        check("nested payload flattens to scalars", "b=" in summarise({"a": 1, "b": {"c": [1, 2]}}))
    )

    print(f"\n{sum(results)}/{len(results)} passed\n")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
