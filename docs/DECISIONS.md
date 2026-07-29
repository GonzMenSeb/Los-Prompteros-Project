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

### 2026-07-25 · AGPL-3.0, chosen over MIT because DecaBot is a hosted app

The repo shipped with no licence at all, which means default copyright and all rights
reserved — the most restrictive outcome, arrived at by omission rather than intent.

The brief was "a little more restrictive than MIT". The honest finding is that for a
**network-served application** the licences that are only slightly more restrictive do
not restrict the thing worth protecting. Apache-2.0 adds a patent grant and an
attribution duty; MPL-2.0 adds file-level copyleft that triggers on *distribution*.
Under either, a third party can host a modified DecaBot commercially and owe nothing,
because hosting is not distribution. That is the SaaS loophole, and among OSI licences
only the AGPL closes it: §13 extends the source obligation to users who interact with
the program *over a network*.

So the real choice was cosmetic protection or actual protection, not a dial of
strictness. AGPL-3.0 keeps the project OSI-approved open source — reading, forking,
self-hosting and private modification are all unrestricted, so judges, recruiters and
learners are unaffected — while requiring reciprocity from anyone who runs it as a
service. The accepted cost is that many companies refuse AGPL code internally, which
effectively ends corporate reuse; for a hackathon deliverable that is a feature.

Licence text is the verbatim FSF original from gnu.org, diffed against the SPDX
canonical copy and identical apart from line-wrapping and `http`→`https` on the FSF URL.
Copyright line is **Los Prompteros**, matching the README credit.

Not done, and required if a modified fork is ever deployed publicly: AGPL §13 obliges
the running UI to offer its users the Corresponding Source. Today's UI carries no such
link, which is fine for the original — we publish the source — but a fork must add one.

### 2026-07-25 · MIT after all, superseding the AGPL entry above

Sebastián's call: MIT. The AGPL reasoning in the previous entry still describes the
trade-off accurately, but it was solving a problem this project does not have. DecaBot
is a hackathon deliverable, not a product with a competitor worth fencing out, and the
cost of AGPL is real — plenty of companies refuse to touch AGPL code, which makes the
repo less useful as something to show people.

`LICENSE` is the SPDX MIT text with the copyright line filled in as Los Prompteros;
verified identical to the canonical copy apart from that line. The AGPL §13 note in the
previous entry no longer applies: MIT asks nothing of anyone who deploys a fork.

Leaving the AGPL entry above in place rather than deleting it, per the append-only rule.
A later reader should be able to see that AGPL was considered and why it was dropped.

### 2026-07-28 · Hosted permanently at decabot.web.vespiridion.org, behind an in-app password

The demo was tunnel-only: `make tunnel` mints two Cloudflare quick-tunnel URLs per run,
and `api_url` is compiled into the frontend bundle, so every restart invalidated any QR
code already in the wild. That is fine for a rehearsal and bad for anything a judge or a
recruiter might open a week later. It now also runs as a container on the team's own VPS
under Ansible management (`vps-infrastructure`, role `decabot`), on the same Traefik +
Let's Encrypt plane as the other services there. The tunnel path is untouched and stays
the demo-day primary — it needs no VPS and no DNS propagation.

**One port, not two.** Reflex needs two in dev (frontend 3000, backend 8000), which is
why `make tunnel` has to tunnel both. In `--env prod` it mounts the compiled frontend
onto the backend's own ASGI app, so a single 8000 serves the page *and* the `/_event`
websocket. That collapses the two-tunnel problem into one Traefik router with no
path-based split to get wrong.

**`api_url` stays at `http://localhost:8000` in the image, on purpose.** The compiled
bundle rewrites any `SAME_DOMAIN_HOSTNAMES` value — localhost, 0.0.0.0, :: — to whatever
origin actually served the page, upgrading `http`→`https` and `ws`→`wss` and dropping the
port. So the registry's "api_url is compiled INTO the bundle" fact still holds exactly as
written; it just means the *correct* baked value for a reverse-proxied deployment is
localhost, and the image carries no domain and needs no rebuild to move hosts.

**Auth is a password gate in the app, not Traefik basicauth.** The thing being protected
is the Gemini quota and Decathlon's MCP rate limiter — a lockout is ~48 minutes — not
per-visitor data, so a shared password is the right shape and a username would be
theatre. Traefik's basicauth was the cheaper build and was rejected: a browser credential
dialog cannot be styled, and the URL has to be handable to a judge with nothing to
explain but one password. The gate is enforced in Python inside every handler that spends
a call, per the guardrail principle — `rx.cond` decides what renders, and renders nothing
that isn't also refused server-side.

`unlocked` defaults to a literal `False` rather than `not GATE_ON`. A state var's default
is compiled into the bundle and the image is built with no password set, so the derived
version baked in as `True` and served the unlocked app shell to any browser whose
websocket never completed. Fail-closed is the only safe direction for a default that
ships to the client.

Rejected: building the frontend at container start. It would let one image serve any
`api_url`, at the cost of bun plus 277 MB of `node_modules` in the runtime image and a
multi-minute boot before the first request. The rewrite above makes it unnecessary.

## The audit trail is copyable, and the copy button does not lie

The panel renders `summarise()`, which clamps each payload value at 120 characters and
the whole line at 300. That is right for something a judge reads over your shoulder while
the agent works, and useless afterwards: debugging a failed run with an AI meant
screenshotting a panel whose payloads were already truncated. One button in the audit
header now puts the whole run on the clipboard — conversation, trace with **full**
payloads, kit, budget and cart — as text that needs no explanation when pasted.

**The full payloads live in a backend-only var.** `trace` crosses the websocket on every
drain, so widening `TraceRow` would have made every run more expensive to watch in order
to make a rare copy richer. `_raw_trace` (leading underscore → never serialized to any
browser) mirrors it with the events intact. `_last_bundle` is the same trick: the
rendered text stays server-side, and only a *refused* copy publishes it to the client so
it can be selected by hand.

**The confirmation reports what happened, not what was attempted.** `rx.set_clipboard`
was rejected: it fires on the websocket response, one round trip after the click and
outside its transient user activation, which Firefox and Safari refuse — and it returns
no result, so the green tick would have appeared over a failed copy. `run_script` with a
callback gets the promise's actual result back, and a blocked write renders the text for
manual selection instead of a lie. Consistent with the guardrail principle: a check
written in Python is a guarantee, a badge written in hope is not.

**`gate.unlocked`, `gate.refused` and `session.priority` were emitted with no sink bound**
and so had never reached `State.trace` at all — only the process-wide ring buffer. They
now bind a sink like every other handler, which fixes the panel as well as the bundle.
Reading `trace.recent()` instead was rejected outright: `_GLOBAL` is process-wide, and on
the public URL it would splice other visitors' sessions into one user's bundle.

**The cart's `continue_url` is not redacted**, deliberately. It resolves to a working
`/cart/c/<token>?key=<key>`, which is frequently the thing being debugged; the cart
carries no payment and the README already publishes such links. The bundle header says so
rather than leaving it a surprise.

Found only in a browser: Reflex returns state containers as `MutableProxy`, which
`json.dumps` misses, so payloads first came out as Python reprs inside JSON strings.
Handler tests asserting substrings all passed. `state.plain()` fixes it and
`verify_ui.py` now asserts real JSON — the class of bug that only a real round trip
exposes.
