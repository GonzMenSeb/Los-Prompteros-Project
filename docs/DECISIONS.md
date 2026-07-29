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

### 2026-07-29 · Ask for the size, and keep asking until it is given

A live run went out with a US 7 boot for a 9.5 foot. The rate limit was the trigger,
not the fault. `_continue` assigned `session.profile` before `_plan_slots`, so a 429 on
the taxonomy left the session half-built: the retry took the "user is answering" branch,
skipped the question stage entirely, and `_choose_size(requested=None)` did what it is
documented to do — took the first available variant. Nothing flagged it, because
`size_substituted` is False when no size was ever asked for.

Two changes, and the split matters. The state bug is fixed at the root: `profile` and
`slots` are committed to the session together, so a failure in either leaves the session
untouched and the next turn re-enters the question stage. That alone would have prevented
this run. It is not enough on its own — the question stage can legitimately return an
empty list, and the model is free to skip the size question — so the guarantee lives in
`check_size_confirmation`, a new `KitItem.size_confirmed` flag set from
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
