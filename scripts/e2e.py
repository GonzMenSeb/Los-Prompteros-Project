"""End-to-end: description -> research -> profile -> slots -> real products -> real cart.

The real catalog is swapped in for the stubs here; nothing else changes.
"""

import asyncio
import pathlib
import sys

import dotenv

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
dotenv.load_dotenv(str(pathlib.Path(__file__).resolve().parents[1] / ".env"))

from concierge.agent import loop, tools  # noqa: E402
from concierge.commerce import cart, catalog  # noqa: E402
from concierge.domain.models import minor_to_display  # noqa: E402
from concierge.obs.trace import recent  # noqa: E402

PROMPT = sys.argv[1] if len(sys.argv) > 1 else (
    "we're hiking to Páramo de Santurbán with my girlfriend, camping two nights"
)
ANSWERS = sys.argv[2] if len(sys.argv) > 2 else (
    "Budget is about $900 total. I'm a men's US 10.5 shoe and size L top; "
    "she's a women's US 8 and size S. We already have trekking poles."
)


async def main() -> None:
    tools.set_backend(catalog)
    session = loop.ConversationSession()

    print("=" * 72)
    print("USER:", PROMPT)
    print("=" * 72)
    result = await loop.run_turn(PROMPT, session)
    print(result.text)
    print()

    if result.citations:
        print("-- citations --")
        for c in result.citations:
            print(f"   {c.title[:58]:60} {c.uri[:70]}")
        print()

    if result.questions and not (result.kit and result.kit.items):
        print("=" * 72)
        print("USER:", ANSWERS)
        print("=" * 72)
        result = await loop.run_turn(ANSWERS, session)
        print(result.text)
        print()

    if result.kit and result.kit.items:
        print("-- kit --")
        for i in result.kit.items:
            flag = "  [SIZE SUBSTITUTED]" if i.size_substituted else ""
            print(f"   {i.slot:22} {i.product_title[:44]:46} {i.size_label:20} "
                  f"{minor_to_display(i.price_minor)}{flag}")
        print(f"   {'TOTAL':22} {'':46} {'':20} {minor_to_display(result.kit.total_minor)}")
        if result.kit.unservable_slots:
            print("   unservable:", ", ".join(result.kit.unservable_slots))
        print()

        res = await cart.create_cart(result.kit.items)
        print("=" * 72)
        print("CART:", res.continue_url)
        print(f"lines={res.line_count}  total={minor_to_display(res.total_minor)}")
        print("=" * 72)
    else:
        print("(no kit this turn — awaiting answers)")
        print("awaiting_confirmation:", result.awaiting_confirmation)

    print()
    print("-- trace --")
    for ev in recent(60):
        mark = {"guardrail": "[G]", "error": "[E]"}.get(ev.level, "   ")
        print(f"  {mark} {ev.event}")

    await catalog.aclose()


if __name__ == "__main__":
    asyncio.run(main())
