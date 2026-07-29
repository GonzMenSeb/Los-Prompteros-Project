"""One §3 fact per test. These exist so that a Decathlon-side change is reported
as a named contract break, not as a mystery outage during the demo.

Every live probe runs once, sequentially, inside a single module-scoped event loop
(`live`). Do not add `asyncio.gather` to this file — Dev A owns that surface and a
lockout stops the whole team.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
import requests

from concierge.commerce.ucp import CONTEXT, EP, PROF, UcpRateLimited, UcpToolError, aclose, call_ucp
from concierge.domain.models import major_string_to_minor
from tests.conftest import PRODUCT_GID, VARIANT_GID, load

FACTS = 'AGENTS.md "load-bearing facts" (SPEC.md §3)'
BASE = "https://www.decathlon.com"

# Measured 25 Jul 2026, and it contradicts SPEC.md §3.2: recovery from a trip is
# ~48 MINUTES, not ~4, and Retry-After counts DOWN in real time to a fixed unlock
# rather than overstating it. A single call succeeds throughout the lockout, so a
# one-call poll proves only that the bucket holds one token — it is NOT a readiness
# signal. A burst of 3-4 re-trips instantly; a trickle is tolerated.
_SPACING = 1.5

SHIPPED_HANDLES = [
    "hiking-boots",
    "hiking-womens-boots",
    "mens-hiking-boots",
    "apparel-for-the-rain",
    "hiking-jackets",
    "base-layers",
    "backpacking-packs",
    "camping-tents-2-3-person",
    "sleeping-bags",
    "hiking-fleeces-mid-layers",
    "kiprun-trail-running-shoes",
    "running-belts-hydration-vests",
    "bike-helmet",
]


def _rpc(tool: str, args: dict[str, Any], *, profile_in_params: bool = False) -> dict:
    if profile_in_params:
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "meta": {"ucp-agent": {"profile": PROF}}, "arguments": args},
        }
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": {"meta": {"ucp-agent": {"profile": PROF}}, **args}},
    }


async def _probe() -> dict[str, Any]:
    out: dict[str, Any] = {"rate_limited": False, "storefront_status": None}
    catalog_arg = {"catalog": {"id": PRODUCT_GID, "context": CONTEXT}}

    async with httpx.AsyncClient(timeout=45, headers={"Content-Type": "application/json"}) as raw:

        async def post(payload: dict) -> httpx.Response:
            """Space the calls out. A burst of 3-4 re-trips the limiter while a
            trickle is tolerated, and a trip costs ~48 minutes (measured), so the
            few seconds this adds are the cheapest insurance in the repo."""
            await asyncio.sleep(_SPACING)
            resp = await raw.post(EP, json=payload)
            if resp.status_code == 429:
                out["rate_limited"] = True
            return resp

        r = await post(_rpc("get_product", catalog_arg))
        out["get_product_status"] = r.status_code
        out["get_product_envelope"] = None if out["rate_limited"] else r.json()

        r = await post(_rpc("get_product", catalog_arg, profile_in_params=True))
        out["bad_profile_status"] = r.status_code
        out["bad_profile_body"] = r.json()

        bad_line = {"cart": {"line_items": [{"merchandise_id": VARIANT_GID, "quantity": 1}], "context": CONTEXT}}
        r = await post(_rpc("create_cart", bad_line))
        out["bad_cart_status"] = r.status_code
        out["bad_cart_body"] = r.json()

    # The storefront feed is a SEPARATE surface that stays healthy through an MCP
    # lockout, so it is fetched unconditionally and its tests take `storefront` rather
    # than `mcp` — they still run when the MCP half is locked out.
    #
    # FETCHED WITH `requests`, NO SESSION, DELIBERATELY — the same transport
    # commerce/catalog.py ships. decathlon.com's storefront 429s REUSED connections,
    # so probing it over the httpx client above would skip these three tests forever
    # while the app itself works fine. A contract test has to exercise the transport
    # we actually ship, or it is testing a configuration nobody runs.
    for key, url in (
        ("collections", f"{BASE}/collections.json?limit=250"),
        ("empty_collection", f"{BASE}/collections/bike-helmet/products.json?limit=12"),
        ("stocked_collection", f"{BASE}/collections/hiking-boots/products.json?limit=12"),
    ):
        fr = requests.get(url, timeout=30)
        if fr.status_code >= 400:
            out["storefront_status"] = fr.status_code
            break
        out[key] = fr.json()

    if out["rate_limited"]:
        return out

    async def tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(_SPACING)
        return await call_ucp(name, args)

    try:
        # created at quantity 2 so the update below can prove REPLACE, not a no-op
        good_line = {"cart": {"line_items": [{"item": {"id": VARIANT_GID}, "quantity": 2}], "context": CONTEXT}}
        out["cart"] = await tool("create_cart", good_line)
        cart_id = out["cart"]["id"]
        out["get_cart"] = await tool("get_cart", {"id": cart_id, "context": CONTEXT})
        out["update_cart"] = await tool(
            "update_cart",
            {
                "id": cart_id,
                "cart": {"line_items": [{"item": {"id": VARIANT_GID}, "quantity": 1}], "context": CONTEXT},
            },
        )
        out["search_short"] = await tool(
            "search_catalog", {"catalog": {"query": "sleeping bag", "context": CONTEXT, "pagination": {"limit": 10}}}
        )
        out["search_long"] = await tool(
            "search_catalog",
            {"catalog": {"query": "sleeping bag 0 degrees celsius", "context": CONTEXT, "pagination": {"limit": 10}}},
        )
    except UcpRateLimited:
        out["rate_limited"] = True
    finally:
        await aclose()

    return out


@pytest.fixture(scope="module")
def live() -> dict[str, Any]:
    return asyncio.run(_probe())


@pytest.fixture(scope="module")
def storefront(live) -> dict[str, Any]:
    """The storefront half. Separate from `mcp` so an MCP lockout does not hide the
    catalog facts, and from `live` so the storefront's own limiter reports as a skip."""
    if live["storefront_status"] is not None:
        pytest.skip(
            f"storefront returned HTTP {live['storefront_status']} — its own limiter, not a "
            "contract violation. This probe already uses the shipped transport (requests, no "
            "Session, one connection per request), so if it is 429 the app is too. Retry-After "
            "says 60 and is not a recovery time; MCP's 48 minutes does not transfer. See "
            "AGENTS.md: the storefront refuses REUSED connections."
        )
    return live


@pytest.fixture(scope="module")
def mcp(live) -> dict[str, Any]:
    if live["rate_limited"]:
        pytest.skip(
            "UCP rate limited — a lockout is not a contract violation. Recovery is ~48 minutes "
            "(measured; SPEC.md §3.2's '~4 minutes' is wrong). Do NOT poll with a single call to "
            "decide it has cleared: one call succeeds throughout the lockout."
        )
    return live


@pytest.mark.live
def test_profile_must_be_in_arguments_meta(mcp):
    assert mcp["get_product_status"] == 200, (
        f"The agent profile in arguments.meta stopped working. {FACTS} says the profile goes in\n"
        f"  params.arguments.meta['ucp-agent'].profile — not params, not an HTTP header.\n"
        f"  Got HTTP {mcp['get_product_status']}."
    )
    assert "error" not in mcp["get_product_envelope"], mcp["get_product_envelope"].get("error")

    err = mcp["bad_profile_body"].get("error", {})
    assert err.get("code") == -32001, (
        f"Profile placement no longer matters. {FACTS} says the profile in params (rather than\n"
        f"  arguments.meta) fails with -32001 'UCP discovery failed'. Got: {mcp['bad_profile_body']}\n"
        f"  If Decathlon really loosened this, update AGENTS.md and this test together."
    )


@pytest.mark.live
def test_response_is_double_encoded(mcp):
    envelope = mcp["get_product_envelope"]
    text = envelope["result"]["content"][0]["text"]
    assert isinstance(text, str), (
        f"Response is no longer double-encoded. {FACTS} says the real body is a JSON *string*\n"
        f"  inside result.content[0].text and must be json.loads()'d a second time.\n"
        f"  Got {type(text).__name__}. commerce/ucp.py decodes twice and will now break."
    )
    inner = json.loads(text)
    assert "product" in inner
    assert "ucp" in inner, (
        f"The `ucp` capability echo is gone from the response. {FACTS} says every response echoes it\n"
        f"  and that commerce/ucp.py strips it before it reaches the model. Harmless if truly removed —\n"
        f"  but verify nothing else moved, then update AGENTS.md and this test together."
    )


@pytest.mark.live
def test_mcp_prices_are_minor_units(mcp):
    product = json.loads(mcp["get_product_envelope"]["result"]["content"][0]["text"])["product"]
    amount = product["price_range"]["min"]["amount"]
    assert isinstance(amount, int) and not isinstance(amount, bool), (
        f"MCP price is no longer an integer (got {amount!r}). {FACTS} says MCP prices are MINOR\n"
        "  UNITS integers and that a price is a NESTED object {'amount': 10000, 'currency': 'USD'}.\n"
        "  If it is now a major-unit decimal, every total in the app is off by 100x."
    )
    assert amount >= 100, f"{amount} looks like major units. {FACTS}: 5000 means $50.00."
    price = mcp["cart"]["line_items"][0]["item"]["price"]
    assert isinstance(price, int) and price >= 100


@pytest.mark.live
def test_cart_line_shape_is_item_id(mcp):
    line = mcp["cart"]["line_items"][0]
    assert "item" in line and "id" in line["item"], (
        f"Cart line shape changed. {FACTS} says cart.line_items[].item.id — NOT merchandise_id,\n"
        f"  not a bare id. If Decathlon really changed their schema, update AGENTS.md and this\n"
        f"  test together. Got keys: {sorted(line)}"
    )
    assert line["item"]["id"] == VARIANT_GID
    assert isinstance(mcp["cart"]["totals"], list), (
        f"Cart totals is not a list. {FACTS} says totals is a LIST of\n"
        "  {'type': 'subtotal'|'total', 'amount': int, 'display_text': str} — not a mapping."
    )
    assert {t["type"] for t in mcp["cart"]["totals"]} >= {"subtotal", "total"}
    assert mcp["cart"]["continue_url"].startswith("http")


def _total(cart: dict, kind: str = "total") -> int:
    return next(t["amount"] for t in cart["totals"] if t["type"] == kind)


@pytest.mark.live
def test_get_cart_takes_a_flat_id_not_a_nested_cart(mcp):
    fetched = mcp["get_cart"]
    assert {li["item"]["id"] for li in fetched["line_items"]} == {VARIANT_GID}, (
        f"get_cart's argument shape changed. {FACTS} says get_cart is FLAT —\n"
        '  {"id": cart_id, "context": CONTEXT} — unlike create_cart, which nests under "cart".\n'
        '  Nesting it returns "Missing required arguments: id".'
    )


@pytest.mark.live
def test_update_cart_replaces_line_items_and_is_not_a_no_op(mcp):
    """update_cart wants BOTH nestings — {"id": ..., "cart": {"line_items": [...]}} —
    and REPLACES the lines.

    The 2 -> 1 quantity change is load-bearing, do not "simplify" it to 1 -> 1.
    1 -> 1 catches an append (it would total unit x2) but CANNOT catch a silent
    no-op: the cart would sit at unit x1 and the assertion would pass green.
    Starting at 2 forces the total to change, so append and no-op both fail.
    """
    unit = mcp["cart"]["line_items"][0]["item"]["price"]
    assert _total(mcp["cart"]) == unit * 2, "setup: cart must be created with quantity 2"

    updated = mcp["update_cart"]
    assert _total(updated) == unit, (
        f"update_cart is no longer replace-in-place. {FACTS} says it REPLACES line_items:\n"
        f"  a cart of 2 updated to a single quantity-1 line must total {unit}, not {_total(updated)}.\n"
        f"  {unit * 3} means it appended — every edit silently doubles the customer's cart.\n"
        f"  {unit * 2} means the update did nothing at all."
    )
    assert sum(li["quantity"] for li in updated["line_items"]) == 1


@pytest.mark.live
def test_schema_errors_arrive_as_isError_with_http_200(mcp):
    assert mcp["bad_cart_status"] == 200, (
        f"A schema error no longer returns HTTP 200. {FACTS} says schema errors arrive as\n"
        f"  result.isError: true WITH HTTP 200, which is why naive error handling reads a\n"
        f"  rejected call as success. Got HTTP {mcp['bad_cart_status']}."
    )
    result = mcp["bad_cart_body"]["result"]
    assert result.get("isError") is True, (
        f"merchandise_id was accepted. {FACTS} says the cart line key is item.id and that\n"
        f"  merchandise_id is rejected. Got: {json.dumps(mcp['bad_cart_body'])[:300]}"
    )
    assert "item" in result["content"][0]["text"]


@pytest.mark.live
def test_get_product_without_selection_returns_null_availability(mcp):
    product = json.loads(mcp["get_product_envelope"]["result"]["content"][0]["text"])["product"]
    values = [v for o in product["options"] for v in o["values"]]
    assert values
    assert all(v.get("available") is None for v in values), (
        f"get_product with NO `selected` now returns availability. {FACTS} says it returns\n"
        f"  available: null for every option value, which is why resolve_variant() must send a\n"
        f"  non-empty PARTIAL selection to get a usable grid (SPEC.md §4.3). If this is genuinely\n"
        f"  fixed, the extra round-trip can go — update AGENTS.md and this test together."
    )
    graded = load("get_product_variant")["product"]["options"]
    assert any(v.get("available") is not None for o in graded for v in o["values"]), (
        "fixtures/get_product_variant.json no longer shows a graded availability grid"
    )


@pytest.mark.live
def test_long_query_returns_zero(mcp):
    short = mcp["search_short"]["products"]
    long = mcp["search_long"]["products"]
    assert short, (
        f"Keyword search returns nothing for a 2-word noun phrase. {FACTS} says 'sleeping bag'\n"
        "  returns 3 products. Retrieval is via collections, but the fallback is now dead."
    )
    assert not long, (
        f"Keyword search now tolerates descriptive queries ({len(long)} hits for\n"
        f"  'sleeping bag 0 degrees celsius'). {FACTS} says it returns ZERO — conditions and\n"
        f"  specifications belong in the selection step, never in the query. guardrails.\n"
        f"  check_query_shape() exists because of this; confirm before relaxing it."
    )


@pytest.mark.live
def test_collection_handles_resolve(storefront):
    handles = {c["handle"] for c in storefront["collections"]["collections"]}
    assert len(handles) >= 200, f"Collection count collapsed to {len(handles)}. {FACTS} says 228."

    missing = [h for h in SHIPPED_HANDLES if h not in handles]
    assert not missing, (
        f"Collection handles we ship no longer exist: {missing}.\n"
        f"  {FACTS} says handles must be validated against a live collections.json, and every\n"
        f"  handle above was confirmed live. Replace them in SPEC.md §4.3 and AGENTS.md together."
    )
    assert "rain-shells" not in handles, (
        "'rain-shells' now exists. It is the documented hallucination — the model invented it and\n"
        f"  the real handle is 'apparel-for-the-rain'. {FACTS}"
    )


@pytest.mark.live
def test_empty_collection_is_legal(storefront):
    assert storefront["empty_collection"]["products"] == [], (
        f"'bike-helmet' now returns products. {FACTS} says a collection can exist and be empty,\n"
        "  which is why check_coverage() marks the slot unservable instead of erroring. Pick another\n"
        "  reliably-empty handle for this test rather than deleting it."
    )


@pytest.mark.live
def test_feed_prices_are_major_unit_strings(storefront):
    variants = [v for p in storefront["stocked_collection"]["products"] for v in p["variants"]]
    assert variants
    for v in variants[:20]:
        assert isinstance(v["price"], str), (
            f"Storefront feed price is no longer a string ({v['price']!r}). {FACTS} says the feed\n"
            "  gives a decimal STRING in MAJOR units ('50.00') while MCP gives a minor-units\n"
            "  integer (5000) — two sources, two representations. major_string_to_minor() converts\n"
            "  at the boundary; if this changed, every feed-derived price is now 100x wrong."
        )
        assert "." in v["price"]
        assert major_string_to_minor(v["price"]) >= 1

    assert all("available" in v for v in variants), (
        f"The collection feed dropped `available`. {FACTS} says the collection-scoped feed's\n"
        "  `available` is trustworthy (cross-checked against MCP get_product) and that only the\n"
        "  storewide /products.json returns null. Stock filtering depends on it."
    )


def test_tools_must_be_wrapped_in_Tool():
    """Deliberately NOT marked live: it raises before any HTTP call, so it costs
    nothing and belongs in the fast suite."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key="contract-test-no-network")
    fd = types.FunctionDeclaration(
        name="get_collection", description="x", parameters=types.Schema(type="OBJECT", properties={})
    )

    with pytest.raises(AttributeError, match="function_declarations"):
        client.models.generate_content(
            model="gemini-3.6-flash",
            contents="hi",
            config=types.GenerateContentConfig(tools=[fd]),
        )

    wrapped = types.GenerateContentConfig(tools=[types.Tool(function_declarations=[fd])])
    assert wrapped.tools[0].function_declarations[0].name == "get_collection", (
        f"{FACTS}: `tools=` must be a list of types.Tool. A bare list of FunctionDeclaration\n"
        "  raises AttributeError before any HTTP call — wrap it:\n"
        "    tools=[types.Tool(function_declarations=[...])]"
    )


def test_ucp_wrapper_still_puts_the_profile_in_arguments_meta():
    """Offline mirror of the live check: guards the wrapper itself against an
    edit that moves the profile back to params or to a header."""
    import inspect

    from concierge.commerce import ucp

    src = inspect.getsource(ucp.call_ucp)
    assert '"arguments": {"meta": {"ucp-agent": {"profile": PROF}}' in src, (
        f"commerce/ucp.py moved the agent profile out of arguments.meta. {FACTS}: wrong placement\n"
        "  returns -32001 UCP discovery failed. The profile is a public capability declaration,\n"
        "  not a credential."
    )
    assert "tools/call" in src and "tools/list" not in src, (
        f"{FACTS}: tools/list and initialize ALWAYS fail with -32001. Call tools by name;\n"
        "  do not add an MCP SDK or a handshake step."
    )
