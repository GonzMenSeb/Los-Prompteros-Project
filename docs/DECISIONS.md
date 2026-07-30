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
## Backing off the storefront, and treating a rate limit as a pause — 28 Jul 2026

A live turn died with `HTTPStatusError: 429` on `GET /collections.json?limit=250`. The
trace read `profile.built` → `turn.error` → `turn.done stage=error`: `get_taxonomy()`
called `raise_for_status()` with nothing around it, `_plan_slots` was the caller, and
the generic handler in `run_turn` turned a rate limit into "Something broke."

**The storefront's limiter is its own.** The registry's "storefront stays healthy
through an MCP lockout" is still true and was left standing — this 429 arrived with no
MCP lockout in play, which is a different fact.

What we then measured, and it is worse than the incident suggested. The storefront sends
`Retry-After: 60` on every 429, **and that hint is not honest**: httpx was still 429
after 75 s of complete quiet. So the bucket is penalty-shaped rather than a rolling
window, and neither 60 s nor MCP's 48 minutes is a recovery figure worth acting on.
`catalog._get()` therefore backs off on a budget **we** chose — ≤4 attempts, ~12 s
total, exponential with jitter — and never on a number Decathlon supplied. Because 60 s
exceeds that budget, the live path is *one attempt then degrade*; the ladder only runs
when no hint arrives. That is deliberate: 60 s inside `_tax_lock` is precisely the stall
we refused, and a stalled turn is worse than a short kit.

**Unexplained, and left unexplained on purpose.** From this machine and one IP,
interleaved over ~45 minutes: `curl`, Python `urllib` and `requests`/`urllib3` all
returned 200 while `httpx` returned 429 every time. The decisive reading is three
requests inside two seconds — `06:44:34 httpx → 429`, `06:44:35 requests → 200` (228
collections), `06:44:36 httpx → 429`. That rules out a volume bucket, a per-IP bucket
and a time window in one shot, and `httpx` was still 429 after 25 minutes of total
quiet. Ruled out at the application layer: User-Agent; `Accept`/`Accept-Encoding`/
`Connection` values (curl sending httpx's exact header set got 200, httpx sending
urllib's exact set got 429); **header order** (httpx sending requests' exact headers in
requests' exact order still got 429); HTTP version; ALPN; address family. Whatever this
is, it lives at TLS or below.

**We did not move the storefront off httpx, and the reason is sharper than "we don't
know why".** The tempting read is "httpx is fingerprinted, so use requests." The problem
is that httpx is also *the only stack that has ever fired `_prefetch`'s ~24-request
bursts from this machine* — curl, urllib and requests have only ever made single-shot
probes here. "httpx is singled out" and "httpx is the one we burned" predict everything
we observed, and separating them requires deliberately burning a second client, which
spends the one known-good fallback we have. Under the second reading a swap buys one
clean run and then re-earns the same state on the replacement, with the burst prevention
dropped because the problem looks solved. It would also cost `logfire.instrument_httpx()`
and split the two commerce surfaces onto different client idioms. Backoff, pacing and
graceful degradation are the correct response under *both* readings; that is the
tiebreaker.

A stack swap therefore stands as a **demo-day contingency, untested under burst load** —
`requests` is already in the venv and verifiably serves the feed — alongside
`CONCIERGE_FIXTURE_MODE=1`. If it is ever taken, the pacing and backoff must travel with
it. Probing was stopped deliberately: seven probes each eliminated a hypothesis without
converging, and the next real step is a JA3/JA4 capture from a rested bucket, which is
its own task.

The budget is a **total**, not per-attempt, because `_tax_lock` is held across the whole
sequence. Holding it is right — one queue against a limiter beats a thundering herd,
and with one Granian worker every session waits on it — but that makes lock-held time
equal to the retry budget, and the UI has no signal for a 30-second stall.

**The latch decays here and does not in `ucp.py`.** Same shape, opposite lifetime, and
the discriminator is request volume rather than confidence: `create_cart` is the only
MCP call in a demo run, so `ucp.py`'s permanent latch costs 1.5 s, while `_prefetch`
fires ~24 storefront requests every turn, where a permanent latch would charge every
later turn ~36 s for one transient 429.

**"Could not read" is not "not in stock."** The subtler half of the bug: `_prefetch`
dropped a failed handle with `continue`, and `_retrieve` computed `empty = planned -
stocked`, so a 429'd handle arrived at the model as "This collection is live but
currently has no products in stock — say so, do not substitute." That is a fabricated
inventory claim assembled from a request that never completed, which is the precise
failure the guardrail principle exists to prevent. Unchecked now travels separately from
empty through `_prefetch`, both retrieval and presentation prompts, and `_disclosures`.

**A rate limit pauses the conversation instead of ending it.** `run_turn` reports
`stage="rate_limited"`, keeps everything the turn earned on the session, and `_continue`
re-enters at whichever stage did not finish rather than falling through to `_retrieve`
with no slots and presenting an empty kit. The message quotes no wait time — we have no
storefront figure worth standing behind, and MCP's is 48 minutes. On a resume turn the
user's message is a retry, not an answer, so it is kept out of `session.answers`, where
`_plan_slots` and `_select` would read it as a size.

**The wait got its own loading state, driven off the trace.** A backoff is the one wait
that reads as a hang: `_get` can hold a request for seconds while the spinner still says
"Reading the conditions…", which is untrue and, on a demo, indistinguishable from a
crash. `_drain` already walks every trace event into the UI mid-turn, so mapping the
rate-limit events to a status there (`_THROTTLE_STATUS`) is what lets the message land
*while the turn is still running* — a field on `TurnResult` would arrive only once the
turn was over, which is exactly too late for a loading message. Two levels, because
"still trying" and "gave up on that one and carried on" are different facts the user is
entitled to, and neither quotes a number. It is warn-toned rather than merely reworded:
the point is that a judge watching the screen can tell at a glance that we are waiting
on Decathlon rather than broken. The coupling this creates — status keyed by event
*name* — is pinned by a test and recorded in the maintenance contract, because a rename
in `catalog.py` would otherwise strip the message with nothing failing.

Rejected: escalating `ucp.py`'s spaced retry to 2–3 attempts while we were here. Nothing
in the incident implicated MCP; 1.5 s is measured and 3 s / 6 s would have been invented;
and `UcpRateLimited`'s documented meaning — "even a trickle was refused" — is depended on
by `tools.py` and pinned by a test. Its mitigation is already the measured-correct one.

## Correction: the storefront refuses reused connections — 28 Jul 2026

The entry above concluded "do not swap the storefront off httpx" and left the cause
open between a TLS-fingerprint bucket and a penalty box our own bursts earned. A
deliberate experiment settled it, and then a second one overturned the conclusion we
drew from the first. Both are recorded because the sequence is the point.

**Experiment 1 — burn an expendable client.** The two hypotheses were indistinguishable
by any test that did not involve bursting a second client, so we bursted the one we
would never ship: stdlib `urllib`, 24 collection feeds at 6 concurrent, one turn's
worth. It returned **24/24 at 9.3 req/s**, and immediately afterwards `requests`
returned 200 while `httpx` returned 429 in the same second. The penalty-box hypothesis
died there: a client that had just bursted was fine, a client idle for hours was
refused. On that evidence the swap was approved and made.

**Experiment 2 — the swap failed, which was the useful part.** `requests` behind a
thread-local `Session` gave **17 of 24 feeds 429** on the first real turn. Adding rate
spacing made it *worse* (4/24 at 6.4 req/s), while `urllib` re-ran clean at 9.3 req/s
minutes later. Rate was therefore exonerated. The one remaining difference was
connection reuse — `urllib` pools nothing, `Session` and `httpx` both do — and
`requests` with **no** Session returned **24/24 at 11.4 req/s**. Faster unpooled and
clean, slower pooled and refused. It is not rate and it is not the library.

So `catalog.client()` returns the `requests` **module**, never a Session, and the TLS
handshake per request is the price of the feed working at all — about 2 s across a
whole turn, against two consecutive verification turns of 24/24 feeds and 92 products
in 3.2 s each with zero 429s. `ucp.py` stays on `httpx`: the MCP endpoint is a separate
limiter, verified working the same hour, and `create_cart` is the demo's proof.

**What we got wrong, in order:** "recovery is unmeasured" (it was measurable), "a
penalty box our own bursts earned" (disproved by experiment 1), "httpx is fingerprinted
and singled out" (too narrow — every pooled client is refused), and "the storefront
limits on rate" (disproved by 11.4 req/s clean). Each was the honest reading of the
evidence then available. The registry carries only the surviving version, and lists the
superseded ones by name so they are not rediscovered from git history.

**Still open:** a single `httpx.get()` from rest is refused too, and that request has no
connection to reuse. So reuse cannot be the whole mechanism. A JA3/JA4 capture would
close it out; it is no longer on the critical path, because the fix is measured,
reproducible, and does not depend on knowing why.

Rejected again, and now on better grounds: `curl_cffi` or any browser-impersonation
transport. Decathlon's `agents.md` explicitly permits the endpoints we read and asks
only that we back off on 429 — which we do. The fix that worked is "open a fresh
connection", not "look like a browser", and that distinction is worth keeping.

### 2026-07-29 · Ask for the size, and keep asking until it is given

A live run went out with a US 7 boot for a 9.5 foot. The rate limit was the trigger,
not the fault. `_continue` assigned `session.profile` before `_plan_slots`, so a 429 on
the taxonomy left the session half-built: the retry took the "user is answering" branch,
skipped the question stage entirely, and `_choose_size(requested=None)` did what it is
documented to do — took the first available variant. Nothing flagged it, because
`size_substituted` is False when no size was ever asked for.

Two changes, and the split matters — but only one of them landed here. The state bug is
fixed at the root by the rate-limit entry above, which merged first: `_continue` now
skips a stage only if that stage actually completed, so a 429 in `_plan_slots` leaves
the session resumable and the next turn re-plans the slots **and** re-enters the question
stage. This branch carried its own answer to the same root cause — committing `profile`
and `slots` together — and it was dropped during the rebase rather than merged, because
two fixes for one bug is one too many and the resumable form also spares a re-run of the
research and profile calls.

What this entry contributes is the half the root-cause fix does not provide. Re-entering
the question stage is not enough on its own: the stage can legitimately return an empty
list, and the model is free to skip the size question. So the guarantee lives in
`check_size_confirmation`, driven by a new `KitItem.size_confirmed` flag set from
`ResolvedVariant.requested_size`. Prompt-level asking is a suggestion; the flag is code.

`size_confirmed` is deliberately distinct from `size_substituted`. Substituted means the
size WAS given and was sold out — a different sentence, and one the customer has already
half-expected. Unconfirmed means we guessed. Conflating them would have let this failure
hide inside a disclosure that already existed.

Simón's call on the flow: the cart is NOT blocked on unconfirmed sizes. The link goes out
with the confirmed lines plus the guessed ones, and the ask is repeated after the link.
The reasoning is that seeing the products is what makes the size question answerable, and
a blocked button on a demo stage is worse than a wrong size on an editable cart. The cost
is real and accepted: a customer who ignores both asks checks out in a guessed size.
Revisit if that ever happens to someone who is not us.

### 2026-07-29 · The palette has ink colours and it has icon colours, and they are not the same list

An accessibility pass measured every foreground/background pair this theme actually
produces. Four failed AA, and all four failed the same way: a grey chosen for how it
looked next to a border was then used to set type.

- `GREY_2 #949494` — 3.03:1 on white, 2.81:1 on `TINT_1`. It was setting the "YOU"
  eyebrow, "NO PHOTO IN CATALOG", the trace sequence numbers and the cart expiry.
- the composer placeholder `#a3a3a3` — 2.52:1.
- `SUCCESS` on `SUCCESS_BG` — 4.08:1, under AA for the small bold type of the
  in-stock chip.

The fix is a rule rather than a new set of tokens: **`GREY_2` and `GREY_3` are icon
and rule colours and never set type.** Anything that reads as words uses `MUTED`
(4.95:1 on white) or darker. Two tokens were added only where the rule left a real
gap — `SUCCESS_DEEP` for green type on its own tint, and `WARN_INK` because `WARN`
is a surface at 1.6:1 and there was no amber that could be written with.

Also recorded, because it will look like a regression to anyone reading the diff:
the empty state's heading is now an `h2`. It was the page's only `h1`, and it
unmounts the moment the first message lands — so every screen after the first had a
document with no top-level heading. `app.py` owns a visually hidden `h1` instead.

The audit's one remaining detector finding — "Inter is an overused font" — is a
verified false positive and stays. Inter is the face Decathlon themselves load, and
the entire pitch is that this drops into their site unnoticed. The brief outranks
the saturation warning.

### 2026-07-29 · The guessed size gets a way to answer it, and a name attached to it

The badge told you a size had been guessed and then left you to work out what to do
about it — the ask was a sentence in the transcript, above a kit several thousand pixels
long. There is now a "Tell DecaBot my sizes" button in the confirm bar that focuses the
composer, under a grey line counting what is still generic.

It does **not** gate the cart button. That is the entry above, unchanged: seeing the
products is what makes the size question answerable, and the cart stays editable. This
adds the route to answering, not a blocker on the way.

**`KitItem.person_indexes` is a list of ordinals, not a name.** `_merge_variants` folds
two people onto one cart line when they take the same variant — it exists because
`create_cart` merges identical variants into one line, and `len(kit.items)` has to keep
agreeing with `line_count`. A scalar would have had to be dropped at that merge, and the
card would then have read as person 1's alone. Ordinals rather than rendered `"Person N"`
strings so the wording lives in one UI formatter instead of being minted in the agent
loop and again in the fixture — and so ordering is numeric: sorted as strings,
`Person 10` lands between `Person 1` and `Person 2`. Empty means shared kit or a party
of one.

**The person counter runs per slot, not per pick.** A party of two splits across two
picks for one slot — a women's boot and a men's one — not across two sizes inside one
pick, which is what a per-pick index would have assumed. The labels are positional
(`Person 1`, `Person 2`) and their stability across slots depends on the model emitting
picks in a consistent order; it usually does, because it works the slot list in order.
A wrong-but-consistent grouping is still better than a kit where two people's gear is
interleaved with nothing saying which is which, but this is the weak point to revisit
if the model is ever seen shuffling picks within a slot.

Recorded because it will look like a bug to anyone reading the diff: the kit grid is one
flat `rx.grid` whose person headings are cards carrying a `person_heading`, spanning
every column via `grid-column: 1 / -1`. That is what keeps every block on one shared set
of column widths — a grid per group would let the columns drift between people.

**And a trap worth the paragraph, because the first attempt here recorded the wrong
cause.** The obvious shape — a group model holding `items: list[KitCard]`, nested
`rx.foreach` — dies at component construction with `TypeError: Unsupported type
<class 'method'>`. It is tempting to conclude Reflex cannot type a list reached through
a foreach loop variable. It can. **`ObjectVar` defines its own `items`** (an alias of
`entries`), so `group.items` hands back a bound method instead of the field. Rename the
field to `cards` and the identical nested shape renders fine on 0.9.7. Anyone who
believes the first diagnosis will flatten a model that never needed flattening.

That failure shipped green: every state-level assertion passed while the page was dead,
and the app has one route, so nothing rendered at all. `make check` never built a
component. `test_the_kit_grid_still_builds` now does.

### 2026-07-29 · DecaBot gets its own voice, and stops being a drop-in

Two directions were put to the product owner: keep the UI literally drop-in inside
decathlon.com, or build a visual system that is DecaBot's own on top of Decathlon's
blue. He chose the second. `theme.py`'s docstring had asserted the drop-in
constraint since 25 Jul; it now records the change.

The cost is real and accepted: **this is no longer literally drop-in.** The pitch
loses the line "Decathlon could paste this into their site tomorrow." What it buys
is a ceiling. decathlon.com is deliberately flat, and matching that flatness is why
the UI had one surface, one weight band, and hierarchy carried entirely by hue —
the page had a colour for every kind of message and a shape for none of them. The
anchor does not move: `#3643BA` is still the only brand hue, and no second one was
introduced.

Four defaults were removed, each replaced by structure rather than by a new colour.

**The coloured `border-left`.** Eight places — a chat bubble, an error, an
over-budget line, an under-budget line, a size prompt, an unfilled-slot notice, a
created cart and every trace row — were the same 3px stripe in a different hue.
Nothing had structural hierarchy, only saturation. Callouts are now one
`_disclosure` form (a filled icon medallion on the row's own surface), DecaBot's
bubbles are told from the user's by elevation, the cart landing is lifted on a top
edge and a deeper shadow, and a trace verdict is a bordered object where a routine
step is a bare line. The 2px rule on a product's `rationale` stays: that one is a
blockquote, which is what it looks like.

**The eyebrow above a heading.** `THE KIT`, `SLOTS DECABOT COULD NOT FILL`,
`OR START FROM ONE OF THESE` and `SOURCES · GROUNDED WEB SEARCH` are gone or
absorbed into the sentence they were labelling. `YOU`/`DECABOT` stayed — a
transcript needs attribution — but as sentence case, because two ALL-CAPS labels per
exchange is noise. Stat labels above values stayed; a stat label is not a heading.
The slot kicker above each product title was the one that cost something to remove:
the slot is real information the title does not carry, so it moved down into the
card's chip row to stand as data alongside the size and the quantity.

**The hero-metric tile row.** `kit_summary` was big-number-plus-supporting-stats,
which is a dashboard, at the moment someone decides to spend four figures. It is now
the bill: the total at display scale, the counts as a ledger strip beneath it, and
every caveat that qualifies that total — unfilled slots, guessed sizes, an overrun —
pulled inside the same object instead of scattered down the column. The cards below
are the line items.

**The same entrance on everything.** `db-rise` fired identically on every chat
bubble and every trace row, which is a default, not motion design. It is deleted.
One moment is authored instead — the kit arriving, the payoff beat of the demo —
resolving out of blur under a `clip-path` wipe on an exponential ease-out, from an
already-visible default state.

One token group was added, and every value in it was measured, not chosen by eye:
the audit rail's dark surface. The rail is where a judge watches guardrails fire, so
it now reads as an instrument rather than as console output. None of the
light-surface tokens survive the move — `BRAND` is 2.1:1 on the new surface and
`DANGER` is 2.8:1 — so the rail carries its own set, tinted from the surface hue
rather than greyed:

| Pair | Ratio |
|---|---|
| `RAIL_INK #E8EAF7` on `RAIL_BG #151833` | 14.49:1 |
| `RAIL_MUTED #A9AFD8` on `RAIL_BG` | 8.11:1 |
| `RAIL_GUARDRAIL #9AA3F5` on `RAIL_BG` | 7.38:1 |
| `RAIL_DANGER #FF8B96` on `RAIL_BG` | 7.75:1 |
| `RAIL_MUTED` on `RAIL_BG_2 #1C2044` | 7.32:1 |
| `RAIL_BG` on `RAIL_GUARDRAIL` (level pill) | 7.38:1 |

The level pill had to invert: it was white type on the level colour, which is 1.8:1
once the level colour is a light blue on a dark panel.

Also recorded because it reads as a regression in the diff: the
`prefers-reduced-motion` block no longer sets `animation-duration: 0.001ms` on
everything. That blanket kill was itself the bug — it took out the "DecaBot is
working" pulse, the running-demo progress bar and the kit's arrival, leaving a
reduced-motion user unable to tell a working app from a frozen one. Reduced motion
means no vestibular triggers, not no information: the halo becomes a steady ring,
the progress sweep breathes in place instead of travelling, the kit fades instead of
rising, and hover/focus transitions are shortened rather than removed.

The detector's one finding — "Inter is an overused font" — remains the same
adjudicated false positive it was on 25 Jul. Inter is the face Decathlon load, and
it is the brand anchor's companion. No second face was added: the display register
is Inter at 800 with `-0.04em`, which costs no extra font request on a projector.

### 2026-07-29 · The fixture stops replaying a kit that ignores you

Found by testing the demo the way a judge would: build the kit, take the cart link,
then answer the size question DecaBot just asked. Nothing happened. Answering again
produced a byte-identical turn — same trace, same kit, same guessed sizes.

`_fixture_turn` took no `text` argument. It replayed `demo_trace()` and `demo_kit()`,
both constants, then appended the same canned message. Meanwhile `confirm_cart`
appends "Give me the sizes and I'll rebuild the kit and hand you a new link" after
**both** the fixture and the live branch. So the one mode that runs on stage without
Gemini quota was making a promise it structurally could not keep.

**The live path was never broken.** `_continue` appends the message to
`session.answers` (`loop.py`), and `answers` is threaded into `SELECT_PROMPT`, which
produces `pick.sizes` for `resolve_variant`. The route to a second cart was not
blocked either: `send_message` calls `_reset_cart()` on every turn, with a comment
already anticipating exactly this failure. Only the fixture lied.

The fix is not to soften the promise but to keep it. A follow-up naming a size now
routes to `_fixture_resize` instead of replaying the opening turn, and `demo_kit()`
takes the answers. **Nothing here fabricates stock:** the tokens resolve through the
same `_kit_item` path and the same dumped availability grid as the first pass, so
`XL` fits the fleece that stocks it, `9.5` matches nothing on an apparel line and is
dropped, and a size nobody stocks leaves the line unconfirmed and says so. Answering
"9.5 and XL" moves one line and reports the other as still guessed — which is the
honest outcome, not a failure to handle.

Recorded because it looks like a regression in the diff: **the fixture cart no longer
reports the numbers in its own dump.** `fixtures/create_cart.json` is a real capture
of a ONE-line $100 test cart, so rendering its totals printed
"CART TOTAL $100.00 · LINES 1" directly beneath a $1,305.99 kit — and the visual work
had just put that kit total at display scale, which made the contradiction louder.
`demo_cart()` now derives the count and total from the kit that was actually
confirmed. The id, the link and the expiry still come from the real capture, because
that link being real is the point of it. The gap that leaves — a genuine link that
opens one line — is stated in the cart block under fixture mode rather than left for
a judge to discover on Decathlon's own page.

Turn numbering in `turn.start` reads `turn=3` for the second exchange
(`len(messages) // 2 + 1` counts an assistant message the fixture appends twice).
Cosmetic, in the trace only, left alone.

### 2026-07-29 · Merging to `main` deploys, and every image says which commit it is

The trigger was a bug report that was not a bug. A live turn died on
`429 Too Many Requests` from `/collections.json?limit=250` on 29 Jul — the exact failure
`2d8a591` had fixed eight hours earlier. The fix was in `main` and had never been built:
the host was still running the 28 Jul image. The only way to establish that was noticing
the traceback named `HTTPStatusError`, which is **httpx's** class, and the shipped
`catalog.py` is on `requests` and cannot raise it. A deployment whose contents can only
be identified by forensics on an exception type is not a deployment.

So: Jenkins job `decabot-deploy` on `*/main`, `infra/jenkins/Jenkinsfile` here, the job
and its deploy-key credential in `vps-infrastructure`'s `casc.yml.j2`. This is the
miplata/categorizer house pattern, and it fills a hole the infra repo already described
— `roles/decabot/tasks/main.yml` used to end with "There is no Jenkins job for this
service: build and push it by hand."

**Every image is tagged `:<git-short-sha>` as well as `:latest`, and carries
`org.opencontainers.image.revision`.** That label is the point of the whole change: it
makes "which commit is live" a `docker inspect` away instead of an inference. It is also
the rollback target — the deploy stage reads it off the running image before replacing
it, and the health gate restores it if the new revision fails.

**The path gate is on stages, not on tests.** The obvious reading of "only run what was
touched" is per-test-file selection; measured, the offline suite is **276 tests in
4.88 s**, of which ~0.6 s per file is interpreter startup. Selecting files saves about
two seconds and risks the cross-module contract tests that pin the facts registry. The
minutes are in the image build, so that is what is gated: a merge touching only `*.md`,
`docs/`, `LICENSE` or `.github/` builds nothing and does not restart the live instance —
three of the twelve commits before this one were exactly that. `tests/`, `fixtures/`,
`scripts/` and `Makefile` run the suite and stop, because the `Dockerfile` does not copy
them.

**The build stage does not look like the sibling repos', and must not be made to.**
miplata and categorizer use `docker build` + `docker push`; this one uses the `buildx`
invocation from `DEPLOY.md` with `oci-mediatypes=true` and provenance/SBOM off. Zot
rejects Docker v2 manifests with `415`, and it does so *after* every layer has uploaded,
so the failure reads like a network problem rather than a format one. Whether the
sibling repos get away with it on the same registry is unresolved and deliberately not
relied upon here.

**`pytest -m live` is a `booleanParam`, off by default.** The live suite hits Decathlon,
and MCP recovery is ~48 minutes; the registry says the rate-limit tests are written to
never induce one, and a per-merge live run would eventually contradict that.

**Post-deploy verification is inline `curl`, not `tests/health-check.yml`.** The infra
playbook already asserts `/ping` and the websocket for decabot, but running it would
mean cloning `vps-infrastructure` and handing the vault password to a job that otherwise
needs neither. The two checks are copied instead — including `--http1.1`, without which
Traefik negotiates h2 and a healthy app answers `400 Invalid websocket upgrade`.

**PR checks are GitHub Actions, and that is not a second deploy path.** A Jenkins job on
`*/main` first sees a bad commit after it has landed, and merges happen in PRs. The
offline suite needs no network and no secrets — verified by running it green in a clean
clone with no `.env` — so a public-repo runner costs nothing and no VPS credential
leaves our infrastructure. Deploy stays entirely on Jenkins.

### 2026-07-29 · Answering a question must not change the answer to a different one

A live run: the customer typed *"My size is XL in both"*. They got a **hiking** jacket
where a cycling jacket had been, a jersey where the base layer had been, and $248.99
where $99.99 had been. They asked for a size and were handed a different kit.

`_continue` ran `_retrieve` and `_select` unguarded on every turn, and `_select` asks
the model to pick from scratch. Nothing anchored the new selection to the old one, so
supplying a size re-rolled the whole kit.

`_resize` is a deterministic fast path: when this turn is unambiguously a size answer,
re-resolve the **variants** of the products already chosen and change nothing else.
Zero model calls — the first turn that reaches `stage="kit"` without one. Six
conditions must all hold, and **every doubt returns `None`** and falls through to the
old path, which is slow and sometimes re-picks but has never looked broken on stage.

Two rules inside it are load-bearing and easy to get backwards. `unservable_slots` is
**copied**, never recomputed — recomputing turns "we could not read that collection"
into "not stocked", an inventory claim we have not earned. `budget_minor` **is**
recomputed, because the follow-up was appended to `answers` first and may itself carry
a budget.

The trigger cannot be "contains a size token": the tokenizer would read "make it 3
people" and "2 nights" as sizes and silently suppress a legitimate rebuild. It reuses
the budget parser's `_NOT_A_UNIT` lookahead, requires the intent gate to have said
`clarify`, requires the kit to actually have something unconfirmed, and rejects any
change-intent word. `agent/` deliberately does **not** import `ui.demo_data.sizes_in`
— that would put the fixture module on the live path — and the loop's tokenizer has to
be narrower anyway.

Same run, same customer: they asked for **XL** and were handed **S**. `_nearest_available`
walked outward with no ceiling. The fix is in `_choose_size` and is measured in ladder
steps, not list index, because the feed groups by colour and the reported XL → S was
**one index away**. Details and the calibration numbers are in the facts registry.

Over the ceiling the slot goes unservable, which on its own makes a card vanish from
the kit mid-demo with no explanation. So the refusal carries its reason up through a
contextvar collector — the same shape as `obs.trace.bind_sink`, reached by name
through the tools adapter so `agent/` still does not depend on `commerce/` — and
`_select` writes a sentence into `unservable_slots` instead of a bare slot name.

Recorded because implementing it surfaced a defect the design did not predict: applying
a token to **every** line means a token that is not on a product's ladder at all
("XL" against trousers sized `W24 L30`) falls through to first-available, returns the
line we already had, and would have flagged an untouched line as a substitution the
customer never caused. A substitution is now only accepted when it actually moves the
label. Caught by replaying the bug report, not by a test — which is the argument for
replaying it.

Also: `model.retry` was in neither status map, so three Gemini 503 backoffs cost ~30 s,
~10 s and ~18 s of silence in that same run. It is a throttle, not a stage, and gets
its own wording — the other two blame Decathlon, which had nothing to do with it.


### 2026-07-29 · The guided-demo controls belong to the presenter, not the audience

`walkthrough_bar` rendered for everyone. Measured at 414px, the panel ran from 224px to
about 560px and the product did not explain itself until 582px — so a third of a phone
screen was a control panel for a scripted demo the viewer is not running, captioned
"Step 1 of 2 · refusal · grounded research · live kit". With it gated, the hero starts
at **319px**.

Gated on `is_presenter`, which is `is_vip or not VIP_TOKEN`: the presenting laptop
already identifies itself with `?vip=<token>`, and with no token configured nobody is
being gated at all, so local dev and `make walkthrough` keep their button. The RUNNING
banner still shows to everyone — an audience watching a scripted demo is entitled to
see that it is scripted.

Three smaller ones from the same review, all of them the same shape: **the system knew
something and did not say it.**

"Start over" wiped messages, kit, trace and cart on one click, from a control that is
icon-only below `md` — a mis-tap ending three minutes of live API calls mid-pitch. It
now asks, but **only when there is something to lose**: `has_anything_to_lose` keeps a
fresh page clearing in one click, so the confirmation never becomes furniture people
learn to click through.

Nothing said how long the first answer takes. It is ~52 s of measured model latency and
ran 80 s in one live bundle, so the only evidence a first-timer had that waiting was
correct behaviour was a spinner.

`_BudgetExceeded` told the customer to "start a fresh conversation" — but `result.kit`
stays None on that path, so state keeps the kit already on screen and the cart button
still works. The text was sending people to destroy a working kit for nothing.

And the question stage runs once and never asks again, so a customer who answered some
of it lost the rest in silence. Sizes already had a way back. A budget did not: the kit
said "No budget set." — a fact, with no offer of the way out. `_disclosures` now adds
one. Party size and existing kit still have no route back, and nothing re-runs the
question stage; recorded as partly closed rather than closed.

Recorded because it corrects an earlier entry in this file: the "parsers are keyed to
English" finding was **already closed** when it was written up. `presupuesto`, `hasta`,
`dólares` and `tallas?` were all present. It was written from reading the code once and
not checked; checking it is what showed otherwise. Now pinned by tests so it stays true.

### 2026-07-29 · Ask what is still unknown, every turn, and stop when it is answered

The question stage runs once. `questions_asked` latches, and `QUESTION_PROMPT` says so
in as many words: *"AT MOST 4 questions, all in this one turn. Never ask again later."*
So a customer who answered two of four had the other two assumed, silently, forever.

The obvious fix — let the model ask again — is the wrong shape twice over. It spends a
model call to re-derive something already knowable, and a prompt instruction to ask
"only if still missing" is a suggestion, which this project does not accept as a
guardrail.

`check_open_questions` is the deterministic version. It takes the kit, the party size,
and **everything the customer typed**, and returns what is still being assumed. It runs
on every turn that produces a kit, so an ask that is answered simply stops appearing —
which is what keeps a standing offer from becoming a nag, without any state tracking
which question was asked when.

`party_size` is the one that needed the customer's own words rather than the model's
output. `ActivityProfile.party_size` defaults to **1**, so an assumed 1 and a stated 1
are byte-identical in the profile. The only evidence a default was chosen rather than
defaulted is that they said so, hence the cue scan over `trip_message + answers`.

Bias is deliberately toward silence: a loose match counts as ANSWERED. Under-asking is
a smaller harm than pestering somebody who already replied. That is why the live
bundle's *"I have no clothes for that"* closes the existing-kit question — it is an
answer, and a stricter matcher would have gone on asking.

Recorded because it is the same trap a teammate caught in `_STAGE_STATUS` earlier the
same day, and I nearly walked into it again: **fixture mode never reaches `_continue`**,
so wiring this only into the live path would have left it dead in exactly the mode that
runs on stage without Gemini quota. `_refresh_open_asks` covers the fixture, deriving
party size from the kit's own person ordinals.

The asks also reach the confirm bar, not just the prose — same reasoning as the size
ask before them: prose scrolls away and the button that spends money does not.

### 2026-07-29 · A cue has to be about the thing, not merely contain a common word

Review of the entry above. The bias toward silence is right and stays; the cues that
implemented it were not cues. `_PARTY_CUE` matched a bare `both`, and *"My size is XL in
both"* is a verbatim live message from earlier the same day — recorded higher up this
file. A customer answering the size question therefore silenced the party question, for
the rest of the conversation, with the words the size question asked for.

`_OWNED_CUE` matched a bare `have`, `has`, `got`, `already`, `nothing`. So *"what do I
have to buy?"* read as *"I already own things"* — the exact opposite of what was said.
`"I have a trip to the páramo"`, `"I have never camped before"`, `"I already booked the
flights"` and `"nothing fancy, just something warm"` all closed the existing-kit
question too. `said` is every message the customer has ever sent, so the longer someone
talks the likelier an accidental cue, and the asks quietly stop for good.

An ownership verb now needs something ownable within three words (`_GEAR`, or
`nothing`/`nada`), `already` needs a verb after it, and `both` became `both of us` /
`us both`. `we|us|our` stay loose on purpose: `_refresh_open_asks` derives party size
from `person_indexes`, which `models.py` documents as empty for a party of one **or a
shared kit**, so a three-person all-shared kit derives 1 and the cue scan is the only
thing standing between that and a wrong ask.

Two wiring holes from the same review:

**`result.kit is None` does not mean there is no kit.** It means this turn did not build
one. A redirect, a rate limit, and the model-call budget stop all leave the previous kit
on screen, and `awaiting_confirmation` deliberately keeps the confirm bar up — the same
`_BudgetExceeded` path that now says *"the kit above is still good"*. The asks were
cleared at the start of the turn and never restored, so the button that spends money
stopped disclosing what it assumed. It falls back to `_refresh_open_asks`.

**The fixture emitted its guardrail event after the last drain of the turn**, so
`guardrail.open_questions` never reached the trace panel in the mode that runs on stage.
`_fixture_resize` drains after its own emits; `_fixture_turn` did not.

A third, found by re-checking a claim rather than a line of code: the **injection reply
computed the asks and threw them away.** It sets `result.kit = session.kit` and
`offer_cart`, so it is a kit turn with the confirm bar standing — but it passed
`_open_questions(...)` straight into `_disclosures` without ever assigning
`result.open_questions`, which `_live_turn` is what reads. The prose listed all three
assumptions and the button that spends money listed none. Assigned once and reused, so
the two cannot drift apart again.

### 2026-07-29 · The last three from the live bundle: ask, do not guess; fail loudly, not silently

Three items noted in the run bundle and left unfixed because none had an obvious safe
answer. All three turned out to have one.

**A party of one was handed a Women's cycling jacket and a Men's base layer.** Retrieval
guarantees the products are REAL; nothing guaranteed they were for the same person. The
tempting fix — drop the odd one out on a title match — throws away a good product over a
word, so this became an open question instead: it asks, and the ask disappears when the
kit stops being mixed. `\b` is the whole defence in the matcher, because "Women's"
contains "men's"; there is a test for exactly that.

**`set_backend(stubs)` ran at module import and emitted.** So every live run opened with
`tools.backend backend=concierge.agent.stubs`, and a real decision was indistinguishable
in the trace from a fallback nobody chose. Worse, the fallback was SILENT: forget
`set_backend(catalog)` and the loop builds a kit out of fixture data while claiming to be
live — which `AGENTS.md` calls the one failure that would invalidate the demo. The
fallback stays, because tests and scripts rely on it, but it no longer announces itself
as a choice, and using it without choosing it now emits `guardrail.backend_not_chosen` at
error level the first time a tool actually serves data.

**Citations rendered as opaque `vertexaisearch` redirects.** `GroundingChunkWeb` carries
a `domain` alongside `title`, and it was being dropped. The title now falls back to the
domain rather than to an empty chip, and the domain renders beside it — the `href` is a
redirect, so naming the destination is the only way a customer can see where a link goes
before clicking it. That is a trust fix, not decoration.

Review of the entry above, three things:

**The gender matcher missed the products it was written for.** `\b` was the documented
defence and it is correct — but the pattern was keyed to `'` (U+0027) alone, and
Decathlon sends both apostrophes. `Quechua Men’s MH500 Half-Zip Hiking Fleece` and
`Quechua Men’s MH500 Warm Water-Repellent Hiking Fleece Jacket` are in
`fixtures/collection_hiking-fleeces-mid-layers.json` exactly as the feed returns them,
with U+2019, and both read as **unisex**. So a Men’s fleece beside a Women's jacket did
not flag. Swept all 60 fixture titles before and after: men's 30 → **32**, women's 20,
matching **both** still 0, women's-read-as-men's still 0. The `\b` test now uses one of
those real titles, since a test built from a hand-typed title is what let this through.

**The fixture dropped the citation domain.** `DEMO_CITATIONS` was `(title, url)`, so
every fixture chip had `domain=""` and the new label rendered on the live path only —
in the mode that runs on stage once Gemini quota is gone. The same trap
`_refresh_open_asks` exists to avoid, one PR later. It is a 3-tuple now, with one
consumer updated and a test pinning it.

**Two tests asserted source text where the behaviour was directly observable.** The
backend one checked `"if not chosen:" in src and "return" in src` — `return` is in
almost every function — and now asserts that an unchosen `_bind` emits no
`tools.backend` while `set_backend` emits exactly one. The citation one asserted that a
pydantic field round-trips; the actual claim, that a chunk with no title falls back to
its domain and then to `"source"`, had no test and now has one driven through
`_research` with real `types.GroundingChunkWeb` objects. Both were coverage gaps, not
defects — the code was already right.

### 2026-07-30 · A correction has to reach the profile, and the kit has to be able to shrink

From a live run. The customer said *"I wanna start to make running with a 10 kilometers
race"* and got back a research report on **Edmonton, Alberta**, with elevation, forecast
and seven citations. They never mentioned Canada. `RESEARCH_PROMPT` told the model to
find *"where this actually is"* with no way to answer "they did not say", so it picked
somewhere.

They corrected it: *"I aint searching a race in Canada"*. The trace for that turn has no
`research.grounded`, no `profile.built`, no `slots.derived` — `_continue` only researches
`if session.profile is None`, and it never becomes None again. **The kit came back still
sized to Edmonton's summer**: the correction was agreed with in prose and changed nothing.

So the gate now returns `corrects_premise`, and a true verdict throws the profile, the
slots and the research away and rebuilds. It is capped at two per session: a rebuild is
three model calls and about forty seconds. The correction is APPENDED to the trip rather
than replacing it — "not in Canada" is not a trip on its own.

The prompt is also told, first thing, not to name a place the customer did not: research
the ACTIVITY and give ranges. That is a suggestion, not a guarantee, which is why the
`corrects_premise` rebuild exists behind it.

Same run, second complaint: the reply was a wall. Five sourced sections — elevation,
temperature, rainfall, terrain, hazards — in front of someone who had asked one question
and was about to be asked three back. The research prompt now leads with a ≤45-word
paragraph and only that reaches the chat; `_headline` falls back to a hard truncation
rather than to the whole report, because a model that ignores the format rule must not
be able to dump five sections into the conversation.

Two smaller ones from the same bundle. `scrub_prose` excised a claim and left the
preposition that introduced it — *"a wide temperature jump from to"*, on a projector; the
connector that pointed AT the claim now goes with it. And a pair of running shorts
arrived in **3XL** with nothing said, because one available variant sets `sized=False`,
which suppresses the size question. No question was owed — there was no choice — but the
fact was still theirs, so `sole_size` now carries it to a disclosure.

Finally, the kit could only ever grow. There was no way to say "I already have shoes" or
"drop the hat". `_drop` is the mirror of `_resize`: deterministic, zero model calls,
removes only what the message actually names. A token shared by most of the kit
("running") identifies nothing and is discarded before matching, or "drop the running
belt" would empty the cart; a message that would empty the kit falls through instead,
because that is never what "I already have shoes" meant.

And because a second link supersedes the first with no way to tell what moved,
`confirm_cart` now diffs the lines against the last cart and says so, then closes by
telling the customer to open the cart and check it before paying. The link is the
handover, not a receipt.


### 2026-07-30 · Left out is not sold out, and it had already met you

From the run of 02:29Z. Three things, and the one the customer did not report is the
worst.

**It invented an inventory fact to explain its own choice.** The customer said *"only
t-shirt and shoes"*. `_select` picked two, and every OTHER slot fell through
`for slot in session.slots: if slot.name not in filled: unservable.append(...)` — and
`_disclosures` renders that list as **"Not stocked right now"**. So the reply said
Decathlon does not stock running socks, while the same socks were in the previous kit
and came back in the next one. There are three different facts here and they are now
kept apart all the way to the page: **not stocked** (evidence: an empty collection, a
`no_stock` pick, or the size ceiling), **could not check** (rate-limited), and **not
chosen** (nobody picked it — usually because the customer narrowed the kit). Only the
first is an inventory claim, and it is now the only one that makes one.

**It greeted the customer on every single message.** *"Welcome to running, Simon!"*
opened three consecutive replies. The prompt now carries the kit number and a rule, but
the rule is a suggestion — `_strip_greeting` is the part that holds, and it iterates,
because the observed opening was two greetings in a row (*"Hi Simon! Welcome to
running."*). It only ever removes a LEADING greeting sentence, so "Hi-vis is not needed"
mid-paragraph survives.

**A size answer that named its lines fell through to a rebuild.** *"Send me the link
with the same shoes and t-shirt in L siza please"* carries a size and points straight at
the kit, but the cue word was a typo and the sentence was long, so `_wants_resize`
rejected it — and the full rebuild then re-added two products the customer had just
narrowed away. Naming a kit line is now a third way in, alongside the cue word and the
sizes-and-nothing-else test.

Recorded because it settles an argument this file has been having with itself: in the
run before this one, the *same* research prompt that invented "the Edmonton 10K" instead
opened with *"No specific geographic location is provided."* Same prompt, same model,
opposite behaviour, one night apart. That is what a prompt is worth on its own, and why
every one of these has a deterministic half behind it.

Review of the two entries above.

**`_drop` is the one path that removes from the cart, so its cue has to mean "do not
add this".** `i (?:have|own|got)` did not. *"I have shoes but they are worn out"*,
*"I have shoes that are falling apart"* and *"my old socks give me blisters, I have
socks but they are bad"* all dropped the line — the rest of each sentence is the reason
they need a new one, and the system deleted exactly what they were asking for. The
Spanish side had already drawn the line correctly: `ya tengo` is a cue and a bare
`tengo` is not. English now matches it — "already", or an explicit object ("I have my
own boots"), and a bare "I have X" falls through to the model.

**The mender repaired prose that was never cut.** `_mend` ran its patterns over the
whole text, so *"conditions you should plan around."* lost its "around" and *"the range
you are training at."* lost its "at" — valid sentences nowhere near an excision, in the
guardrail whose entire job is not leaving broken grammar on a projector. Each excision
now leaves a `\x00` marker and a connector is only removed when the marker is inside the
match. Every repair in the entry above still fires; none of the false strips do.

**The rebuild cap went quiet.** Past `MAX_REBUILDS` the correction was dropped with no
event and no sentence — the customer says the premise is wrong for a third time and the
kit comes back unchanged, which is the exact failure the `corrects_premise` work was
about. It now emits `guardrail.premise_change_refused` and says the trip was left as it
stands.

**"Hi-vis" is a product category.** `\b` sits between "Hi" and the hyphen, so a reply
OPENING on *"Hi-vis matters on these roads."* — a Decathlon running category, in a
conversation about running — read as a greeting and lost the whole sentence. The
existing test put "Hi-vis" in the second sentence, which is the one position the
leading-anchored pattern can never reach. `(?![-\w])` instead of `\b`.

Registered in SPEC.md §6.1: `check_sole_sizes`, `_drop`, and the premise rebuild.
`check_sole_sizes` also joins `test_all_guardrails_emit_at_guardrail_level`, whose
exact-set assertion is the real registry and did not know it existed.
