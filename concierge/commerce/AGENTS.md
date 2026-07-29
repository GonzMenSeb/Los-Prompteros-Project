# commerce/ — the fragile knowledge lives here

Read [`/AGENTS.md`](../../AGENTS.md) first. This file is the scoped reminder for
the two modules that touch Decathlon.

## Rules

1. **`ucp.py` is the ONLY caller of `https://www.decathlon.com/api/ucp/mcp`.**
   If you need a new MCP tool, add it through `call_ucp()`. Never post to that
   URL from anywhere else.
2. **`cart.py` is the ONLY place a cart line is constructed.**
3. **`create_cart` is never exposed as a model tool.** Only a user click reaches it.
4. **Never cache the catalog to disk.** `fixtures/` is development scaffolding; the
   running app always retrieves live. A local copy reads as mocked and destroys the
   premise of the demo.

## The five things that will look like bugs

| Looks wrong | Is correct | Break it and… |
|---|---|---|
| No `initialize`, no `tools/list` | Both always return `-32001`. Tools are called directly by name. | You add an MCP SDK, it can't connect, you lose an hour |
| Profile buried in `arguments.meta` | Not `params`, not a header. It is a public capability declaration, not a credential. | `-32001 UCP discovery failed` |
| `json.loads()` called twice | Responses are double-encoded: the body is a JSON string inside `result.content[0].text` | `TypeError: string indices must be integers` |
| `result.isError` checked on an HTTP 200 | Schema errors arrive as 200 + `isError`, not as JSON-RPC errors | A rejected call is treated as success |
| `line_items[].item.id` | Not `merchandise_id`, not a bare id | Cart creation fails schema validation |

## The two-price trap

| Source | Representation | Example |
|---|---|---|
| Storefront feed `variants[].price` | decimal **string**, **MAJOR** units | `"50.00"` |
| MCP variant `price` | nested object, **MINOR** units | `{"amount": 5000, "currency": "USD"}` |

Convert at the boundary with `major_string_to_minor()` and **store minor units
internally**. All budget arithmetic is integer arithmetic in minor units, computed
in code, never by the model.

## `resolve_variant` — the one non-obvious algorithm

`get_product` with **no** `selected` returns `available: null` for every option
value. It is useless. You need two calls:

1. **partial** selection (first value of every non-Size option) → the availability
   grid, `values[] = {label, available, exists}`
2. normalise the requested size against `values[].label` — exact, then numeric-equal
   ignoring formatting, then case-insensitive
3. if that label is `available: false`, walk the grid **outward by index** to the
   nearest `available: true`
4. **full** selection (every option supplied) → `product.variants[0]` → the variant GID

Return `substituted: bool`. **When it is true the agent must say so** — never
silently swap a size. That disclosure is the single best adversarial test a judge
can run against us.

## Rate limits

`asyncio.Semaphore(8)`. Clean at 20 sequential / 40 concurrent from a rested bucket;
**100 concurrent trips a ~48 MINUTE lockout** (re-measured 25 Jul 2026 — `SPEC.md
§3.2`'s "~4 minutes" is the superseded first probe).

The first `429` latches `ucp.py` into **paced mode** for the rest of the process:
serialised, `PACE_SECONDS` (1.5 s) apart, because mid-lockout a burst of 3–4 re-trips
the limiter instantly while a trickle is served normally. `call_ucp` retries once at
that spacing, so **`UcpRateLimited` means even a trickle was refused.** Pacing never
un-latches on a success — a single call succeeds throughout a lockout, so a success
is not recovery, and neither is a one-call poll. `Retry-After` is honest and ~48
minutes out: there is nothing worth sleeping for.

The storefront feeds are a separate surface and stay healthy throughout — and since
`resolve_variant` now resolves off the feed, **a lockout no longer costs the kit at
all.** `create_cart` is the only MCP call left in a demo run, so a lockout costs the
cart link and nothing else.

**The storefront has its own limiter.** `collections.json` returned 429 on 28 Jul 2026
with no MCP lockout in play, and `get_taxonomy`'s naked `raise_for_status()` turned it
into a dead turn. `_get()` now owns every storefront request: `SEM(6)`, ≤`MAX_ATTEMPTS`
tries on 429/5xx/transport error, exponential backoff with jitter inside a
**`RETRY_BUDGET_SECONDS` TOTAL** — total, because `_tax_lock` is held for the whole
sequence and every session queues behind it. A `Retry-After` we cannot outwait is
reported, never slept. 4xx other than 429 is not retried.

**`Retry-After: 60` is what it sends, and it is NOT honest** — httpx was still 429 after
75 s of total quiet, so the bucket is penalty-shaped rather than a rolling 60-second
window. Since 60 s > the budget, the live path is **one attempt then degrade**; the
backoff ladder only runs when no hint arrives. None of MCP's numbers apply. The 429
response *shape* is borrowed from the measured MCP surface: serialise and space out.
Unlike `ucp.py` the latch **decays** after `COOLDOWN_SECONDS`, because `_prefetch` is
~24 calls every turn where `create_cart` is one per demo.

**The storefront refuses REUSED connections (28 Jul).** Same 24-feed burst at 6
concurrent, minutes apart: `urllib` 24/24 (9.3 req/s), `requests` with no Session
24/24 (11.4 req/s), `requests` with a shared `Session` 4/24 (6.4 req/s), `httpx`
always 429. Faster unpooled and clean, slower pooled and refused — not rate, not the
library. So `client()` returns the `requests` **module** and every call opens and
closes its own connection. **Do not turn it into a Session.** `ucp.py` stays on
`httpx`: different limiter, verified unaffected. Residual unknown — a single idle
`httpx.get()` is refused too, which reuse alone does not explain.

## Why resolution is feed-first

The feed's numeric variant id **is** the MCP variant GID (verified in both fixtures:
`41919445434430` / `"Dark Cinnamon / 6.5"`), and the collection feed's `available`
cross-checks against `get_product` exactly. The three-call grid walk therefore bought
nothing and cost everything: 3 calls × 8 slots is a ~24-request burst, and that is
what tripped the limiter on 25 Jul. `_resolve_via_mcp` survives for a product the feed
hands over with no variants — do not delete it; it encodes the `available: null`
behaviour that makes a non-empty partial selection mandatory.
