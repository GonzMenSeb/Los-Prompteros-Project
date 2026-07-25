# Decisions

Append-only. One short entry per architectural call, with its reason.
**Never edit a past entry** — a later reader needs to know what was believed then.

---

### 2026-07-25 · Spike before building

Ran the verified `create_cart` path end-to-end before writing any application
code: storefront feed → product → `get_product` grid → full selection → variant
GID → `create_cart`. It returned a real `continue_url`. Everything downstream was
built on a proven transaction rather than on a hoped-for one.

### 2026-07-25 · Contract layer written serially, then four parallel lanes

`domain/models.py`, `obs/trace.py`, `commerce/ucp.py` and `rxconfig.py` were
written first and frozen. Four lanes (commerce, agent loop, UI, guardrails) then
worked concurrently against them with disjoint file ownership. **Reason:** those
four files are the shared contract; parallel authors would otherwise invent four
incompatible versions and burn the integration window renegotiating interfaces.

### 2026-07-25 · Only one lane may call the MCP endpoint during the build

100 concurrent MCP requests trigger a ~4-minute lockout. With four agents each
probing live, a self-inflicted lockout could stop the whole team at the worst
moment. Commerce owns that surface; everyone else works from `fixtures/`. The
storefront feed is a separate surface and stayed safe for all lanes.

### 2026-07-25 · `Url = Annotated[str, AfterValidator(...)]` instead of `HttpUrl`

A pydantic `HttpUrl` field serializes to `null` through Reflex 0.9.7's wire
encoder — silently, with no error. Every product photo and product link would
have arrived at the browser empty, and the failure would have surfaced only at
integration. The alias keeps strict URL validation while storing a plain `str`.
**Do not revert this.** Verified against `reflex.utils.format.json_dumps`.

### 2026-07-25 · No intermediate "wire schema" for Gemini structured output

Considered giving the model a loosened schema and validating into the strict
domain model afterwards. Tested instead: `response_schema=ActivityProfile` works
directly — nested models, the `float | str` union, the `Url` fields and the
`model_validator` all round-trip, and `response.parsed` returns a typed instance.
The extra layer would have been cost with no benefit.

### 2026-07-25 · `KitItem.image_url` is optional

It began as required. `CatalogProduct.image_url` was already optional, so the
seam didn't line up — and a real, in-stock, buyable product would have been
dropped from the kit purely for lacking a photo in the feed. The UI renders a
placeholder instead.

### 2026-07-25 · `create_cart` is not a model tool

Human-in-the-loop is enforced by its **absence** from the function-declaration
list, not by a prompt instruction. Prompt-level guardrails degrade as context
grows; an absent tool cannot be called at all. Only a user click reaches
`commerce/cart.py`.

### 2026-07-25 · Reflex `app_module_import="concierge.app"`

SPEC.md §3.5 says `"app"`, which describes a flat layout with `rxconfig.py` beside
`app.py`. Our layout (§8) puts the app at `concierge/app.py` with `rxconfig.py` at
the root, under which `app` is not importable and `concierge.app` is. Resolved
empirically with a `reflex run` smoke test.

### 2026-07-25 · Session-record analytics deferred

`SPEC-SESSION-RECORD.md` (conversation intake + SQLModel/SQLite analytics) is a
clean bolt-on: a new `analytics/` package plus one hook at session close. It is
not on the demo's critical path, so it lands after the working end-to-end demo
is committed.
