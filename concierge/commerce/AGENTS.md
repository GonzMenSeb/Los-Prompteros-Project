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

`asyncio.Semaphore(8)`. Clean at 20 sequential / 40 concurrent; **100 concurrent
trips a ~4 minute lockout**. On `UcpRateLimited`, **never sleep for `Retry-After`** —
it overstates recovery by minutes. Poll one cheap call every 30–45 s and keep
rendering from the storefront feeds, which are a separate surface and stay healthy.
