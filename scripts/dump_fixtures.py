"""Dump live fixtures so the UI/agent/guardrail lanes can work offline.

Fixtures are for DEVELOPMENT ONLY. The running app always retrieves live —
a cached catalog reads as mocked, which defeats the premise (SPEC.md §3.3).
"""

import asyncio
import json
import pathlib
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from concierge.commerce.ucp import CONTEXT, call_ucp  # noqa: E402

BASE = "https://www.decathlon.com"
OUT = pathlib.Path(__file__).resolve().parents[1] / "fixtures"
HANDLES = [
    "hiking-boots",
    "backpacking-packs",
    "apparel-for-the-rain",
    "camping-tents-2-3-person",
    "sleeping-bags",
    "hiking-fleeces-mid-layers",
    "base-layers",
    "kiprun-trail-running-shoes",
    "bike-helmet",
]


async def main() -> None:
    OUT.mkdir(exist_ok=True)
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{BASE}/collections.json?limit=250")
        cols = [{"handle": x["handle"], "title": x["title"]} for x in r.json()["collections"]]
        (OUT / "collections.json").write_text(json.dumps(cols, indent=1))
        print(f"collections.json  {len(cols)} collections")

        for h in HANDLES:
            r = await c.get(f"{BASE}/collections/{h}/products.json?limit=12")
            prods = r.json().get("products", [])
            (OUT / f"collection_{h}.json").write_text(json.dumps(prods, indent=1))
            print(f"collection_{h}.json  {len(prods)} products")

    boots = json.loads((OUT / "collection_hiking-boots.json").read_text())
    if not boots:
        print("!! hiking-boots empty, cannot probe MCP")
        return
    p = boots[0]
    gid = f"gid://shopify/Product/{p['id']}"
    print(f"\nprobe product: {p['title']}  {gid}")
    print("options:", [o["name"] for o in p.get("options", [])])

    grid = await call_ucp("get_product", {"catalog": {"id": gid, "context": CONTEXT}})
    (OUT / "get_product_grid.json").write_text(json.dumps(grid, indent=1))
    opts = grid.get("product", {}).get("options", [])
    for o in opts:
        vals = [(v.get("label"), v.get("available")) for v in o.get("values", [])]
        print(f"  {o.get('name')}: {vals[:8]}")

    selected = [{"name": o["name"], "label": o["values"][0]["label"]} for o in opts if o.get("values")]
    full = await call_ucp("get_product", {"catalog": {"id": gid, "selected": selected, "context": CONTEXT}})
    (OUT / "get_product_variant.json").write_text(json.dumps(full, indent=1))
    variants = full.get("product", {}).get("variants", [])
    print(f"  full selection {selected} -> {len(variants)} variant(s)")
    if not variants:
        print("!! no variant resolved")
        return
    v = variants[0]
    print(f"  variant id={v.get('id')} price={v.get('price')} avail={v.get('availability')}")

    cart = await call_ucp(
        "create_cart",
        {"cart": {"line_items": [{"item": {"id": v["id"]}, "quantity": 1}], "context": CONTEXT}},
    )
    (OUT / "create_cart.json").write_text(json.dumps(cart, indent=1))
    print("\n=== CART CREATED ===")
    print("continue_url:", cart.get("cart", cart).get("continue_url") or cart.get("continue_url"))


if __name__ == "__main__":
    asyncio.run(main())
