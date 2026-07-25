"""Rehearse the scripted demo without a browser, and time every beat.

Drives `State.run_walkthrough` — the same handler the buttons call — so what this
asserts is what the page does. Live: real Gemini, real Decathlon.

    PYTHONPATH=. ./.venv/bin/python scripts/verify_walkthrough.py            # both phases
    PYTHONPATH=. ./.venv/bin/python scripts/verify_walkthrough.py onstage    # one phase
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
import time

import dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
dotenv.load_dotenv(str(ROOT / ".env"))

from concierge import walkthrough  # noqa: E402
from concierge.domain.models import minor_to_display  # noqa: E402
from concierge.state import State  # noqa: E402


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{f'  — {detail}' if detail else ''}")
    return ok


async def run(state: State, phase: str) -> float:
    print(f"\n=== {phase or 'all'} " + "=" * (60 - len(phase or 'all')))
    t0 = time.time()
    last = t0
    seen = 0
    async for _ in state.run_walkthrough(phase):
        if state.walkthrough_step != seen and state.walkthrough_step:
            seen = state.walkthrough_step
            now = time.time()
            print(f"  +{now - t0:6.1f}s  beat {state.walkthrough_progress}  {state.walkthrough_label}")
            last = now
    del last
    return time.time() - t0


async def main() -> int:
    phase = sys.argv[1] if len(sys.argv) > 1 else ""
    state = State(_reflex_internal_init=True)
    results: list[bool] = []

    if phase in ("", "prewarm"):
        elapsed = await run(state, "prewarm")
        print(f"  prewarm wall clock: {elapsed:.1f}s")
        results.append(check("kit built", len(state.kit_items) > 0, f"{len(state.kit_items)} items"))
        results.append(check("prices resolved", state.total_minor > 0, state.total_display))
        results.append(
            check("research was grounded", any(m.citations for m in state.messages),
                  f"{sum(len(m.citations) for m in state.messages)} citations")
        )
        results.append(check("guardrail events traced", sum(r.level == 'guardrail' for r in state.trace) >= 3,
                             f"{sum(r.level == 'guardrail' for r in state.trace)}"))
        results.append(check("cart offered, not created", state.awaiting_confirmation and not state.has_cart))
        for i in state.kit_items:
            flag = "  [SUBSTITUTED]" if i.size_substituted else ""
            print(f"      {i.slot:20} {i.product_title[:38]:40} {i.size_label:22} "
                  f"{minor_to_display(i.price_minor)} x{i.quantity}{flag}")
        if state.unservable_slots:
            print(f"      unservable: {', '.join(state.unservable_slots)}")

    if phase in ("", "onstage"):
        if not state.kit_items:
            print("\n  (no kit — run the prewarm phase in the same process first)")
            return 1

        before_total = state.total_minor
        before_items = len(state.kit_items)

        elapsed = await run(state, "onstage")
        print(f"  onstage wall clock: {elapsed:.1f}s   <-- this is the on-camera slot")

        results.append(
            check("injection was gated", any(r.event == "gate.verdict" and "injection" in r.summary for r in state.trace))
        )
        results.append(
            check("injection moved nothing", state.total_minor == before_total and len(state.kit_items) == before_items,
                  f"{minor_to_display(before_total)} -> {state.total_display}")
        )
        results.append(
            check("a refusal did not retract the cart offer", state.has_cart or state.awaiting_confirmation)
        )
        results.append(check("cart created", state.has_cart, state.cart_url or state.error))
        if state.has_cart:
            results.append(check("cart url is a real Decathlon link", "decathlon" in state.cart_url))
            results.append(check("cart has lines", state.cart_line_count > 0, str(state.cart_line_count)))
            print(f"\n  CART: {state.cart_url}")
            print(f"  lines={state.cart_line_count}  total={state.cart_total_display}")

    print(f"\n  {sum(results)}/{len(results)} passed")
    print(f"  beats: {' -> '.join(b.label for b in walkthrough.beats(phase or None))}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
