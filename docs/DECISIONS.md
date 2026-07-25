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

### 2026-07-25 · `ucp.py` latches into paced mode on the first 429

Re-measuring the rate limit produced a different answer from the first probe:
recovery is **~48 minutes, not ~4**, `Retry-After` is honest and counts down in
real time, and a single call succeeding proves nothing because single calls
succeed throughout a lockout. So the old advice — poll one cheap call every
30–45 s and wait it out — was wrong twice over.

What the measurement does support is that a **trickle is served mid-lockout while
a burst of 3–4 re-trips it instantly.** Pacing is therefore the only useful
response: the first `429` serialises every later call and spaces it by
`PACE_SECONDS`, `call_ucp` retries once at that spacing, and `UcpRateLimited` now
means *even a trickle was refused*. Pacing never un-latches on a success, because
a success is not recovery.

### 2026-07-25 · `resolve_variant` resolves off the storefront feed, not MCP

The three-call grid walk (`labels` → partial-selection grid → full selection) is
correct and was verified live, but it fires **3 MCP calls per product**, and a
kit is 6–8 products. That ~24-request burst is what tripped the rate limiter
during a live end-to-end run on 25 Jul — the kit died at the last slot and
recovery was 25 minutes.

The walk turned out to be unnecessary. The collection feed already carries every
variant's id, title, price and stock flag; the registry already recorded that its
`available` cross-checks against `get_product` exactly; and the feed's numeric
variant id **is** the MCP variant GID — verified in both dumped fixtures, now
pinned by `test_the_feed_variant_id_is_the_mcp_variant_gid`. So resolution runs
off data already in hand, at **zero MCP calls**, and `create_cart` is the only MCP
call left in a demo run. Turn 2 loses ~10 s and the kit stops depending on a
surface that can lock us out for 48 minutes.

`_resolve_via_mcp` is kept, unchanged, for a product the feed hands over with no
variants. It encodes the `available: null` behaviour that makes a non-empty
partial selection mandatory, and that knowledge is expensive to rediscover.

Two things the feed forced into the open. A variant `title` is the option values
joined by `" / "`, but an option *value* may itself contain a slash — the MT500
bag has two options and three parts — so positional splitting is trusted only
when the part count equals the option count. And because the same size exists in
several colours, an exact available match in a later colour is preferred over the
nearest size in the first one; otherwise the agent discloses a substitution that
never happened.

### 2026-07-25 · The scripted walkthrough is two phases, not one

The pitch is two minutes, so the demo gets about thirty seconds on camera. A real
run does not fit: measured, turn one alone is **52 s** of Gemini latency
(classify 12.5, research 9.8, profile 14.2, slots 11.5, questions 4.1). Squeezing
it would mean cutting the grounded research or the questions — both scored — or
replaying a recording, which is what `CONCIERGE_FIXTURE_MODE` already is and what
the whole project exists not to do.

So `walkthrough.SCRIPT` is split. **Prewarm** (trip description, answers) runs the
slow real work while the pitch is still on the problem statement. **Onstage**
(injection blocked, honest refusal, cart click) is fast — the intent gate
short-circuits before research and `create_cart` is one call — and is what the
audience watches happen. The kit being probed was built live, in the same
session, minutes earlier.

This surfaced a real bug: a redirect turn produced no kit and
`awaiting_confirmation` was recomputed from `result.offer_cart` alone, so asking
about swimming after the kit was built retracted the cart offer for the rest of
the session. A turn that produces no kit at all now leaves a standing offer alone.

### 2026-07-25 · Pre-build research is archived under `docs/research/`, not deleted

The technical assessment and stack spec were the founding documents — they carry the
measurements behind every stack choice, and deleting them would throw away the answer
to "how do you know?". But leaving them loose at the repo root, undated and
unqualified, made them read as current documentation, and **several of their claims
were overturned during the build**: rate-limit recovery is ~48 minutes rather than ~4,
the UI became Reflex rather than Streamlit, retrieval moved to collection feeds, and
`previous_interaction_id` turned out not to exist on `generate_content`.

That is precisely the hazard `AGENTS.md` exists to prevent — a confident, plausible,
breaking "fix" made in good faith against a stale source. So they move to
`docs/research/`, each gets a banner naming the claims that no longer hold, and the
folder's own README states the precedence rule: **where the research and `AGENTS.md`
disagree, `AGENTS.md` wins.** Archived, labelled, and outranked — rather than trusted
or lost.
