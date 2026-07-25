"""Acceptance test for the commerce lane: handle -> collection -> variant -> real cart.

    PYTHONPATH=. ./.venv/bin/python scripts/spike_cart.py hiking-boots --size 10.5
    PYTHONPATH=. ./.venv/bin/python scripts/spike_cart.py apparel-for-the-rain \
        --product-id 4171195908158 --size S
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from concierge.commerce import cart as cart_mod  # noqa: E402
from concierge.commerce import ucp  # noqa: E402
from concierge.commerce.catalog import (  # noqa: E402
    NoStockError,
    UnknownHandle,
    aclose,
    get_collection,
    resolve_variant,
)
from concierge.domain.models import KitItem, minor_to_display  # noqa: E402
from concierge.obs.trace import recent  # noqa: E402


async def run(args: argparse.Namespace) -> int:
    try:
        products = await get_collection(args.handle, limit=args.limit)
    except UnknownHandle as e:
        print(f"UnknownHandle: {e.handle}\n  suggestions: {e.suggestions}")
        return 2

    print(f"{args.handle}: {len(products)} products")
    if not products:
        print("  empty collection -> slot unservable (this is a legitimate result)")
        return 0

    if args.product_id:
        wanted = f"gid://shopify/Product/{args.product_id}"
        picked = next((p for p in products if p.product_gid == wanted), None)
        if picked is None:
            print(f"  {wanted} not in this collection")
            return 2
    else:
        picked = products[args.index]

    print(f"  -> {picked.title}")
    print(f"     {picked.product_gid}  options={picked.option_names}")
    print(f"     {picked.product_url}")
    print(f"     image={picked.image_url}")

    try:
        variant = await resolve_variant(picked, args.size)
    except NoStockError as e:
        print(f"NoStockError: {e}\n  grid: {e.grid}")
        return 3

    print(f"\nresolved: {variant.size_label}  {variant.variant_gid}")
    print(f"  price={minor_to_display(variant.price_minor)}  substituted={variant.substituted}"
          f"  requested={variant.requested_size!r}")

    item = KitItem(
        slot=args.handle,
        product_title=picked.title,
        product_url=picked.product_url,
        image_url=picked.image_url,
        variant_id=variant.variant_gid,
        size_label=variant.size_label,
        price_minor=variant.price_minor,
        quantity=args.quantity,
        available=True,
        size_substituted=variant.substituted,
    )

    result = await cart_mod.create_cart([item])
    print("\n=== CART ===")
    print(f"  id       {result.cart_id}")
    print(f"  lines    {result.line_count}")
    print(f"  total    {minor_to_display(result.total_minor, result.currency)}")
    print(f"  expires  {result.expires_at}")
    print(f"  CONTINUE {result.continue_url}")

    if args.get_cart:
        fetched = await cart_mod.get_cart(result.cart_id)
        print(f"\nget_cart -> keys={sorted(fetched.keys())} lines={len(fetched.get('line_items') or [])}")

    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("--size", default=None)
    ap.add_argument("--product-id", default=None)
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--quantity", type=int, default=1)
    ap.add_argument("--get-cart", action="store_true")
    ap.add_argument("--trace", action="store_true")
    args = ap.parse_args()

    async def go() -> int:
        try:
            return await run(args)
        finally:
            if args.trace:
                print("\n--- trace ---")
                for ev in recent():
                    print(f"  [{ev.level}] {ev.event} {ev.payload}")
            await aclose()
            await ucp.aclose()

    sys.exit(asyncio.run(go()))


if __name__ == "__main__":
    main()
