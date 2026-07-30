# Demo readiness — where a low-context user breaks this

Findings from a review on **2026-07-29**, framed by one question: *this is judged as
a live demo, and the people using it have never seen it before. Where does that go
wrong?*

Every finding below was measured against the code or the running app. File references
are to `e766720`, the tree this review was run against. Nothing here is a style
opinion — each item is a measured place where a first-time user loses something the
system already had.

`DECISIONS.md` records calls that were made; this records ones that had not been.

**Status.** The three P0s were fixed in `tell-the-user-what-broke`. Every item below
carries its own status in its heading.

P1 and P2 were then closed in `polish-for-a-first-timer`, except **#4**, which is only
partly closed: sizes and budget each have a way back now, but party size and existing
kit do not, and nothing re-runs the question stage. Measured effect of #5: the hero
moved from 582px to **319px** on a 414px phone. **#9 turned out to be already closed** —
`presupuesto`, `hasta`, `dólares` and `tallas?` were all in the parsers; it was written
up as open without checking, and checking it is what showed otherwise.

A later live run exposed three more, all agent-side and all fixed in
`answer-a-size-not-a-new-kit`: answering a size question rebuilt the whole kit with
different products, substitution had no distance ceiling (XL was handed an S), and a
30-second Gemini retry was completely silent. See `DECISIONS.md`, 29 Jul.

---

## P0 — visible on the projector, breaks the demo

### 1. An exhausted Gemini quota prints a raw exception on screen — FIXED

`agent/loop.py`

```python
_RATE_LIMITED = {"CatalogUnavailable", "UcpRateLimited"}

def _rate_limited(exc: BaseException) -> bool:
    return type(exc).__name__ in _RATE_LIMITED
```

Those are **Decathlon's** rate limits, and they get a written, calm, actionable
message. A Gemini `429 RESOURCE_EXHAUSTED` is a `ClientError` — it matches neither
name, so it falls through to the generic handler in `state.py`:

```python
except Exception as exc:
    emit("turn.error", {"error": repr(exc)}, level="error")
    self._drain(sink)
    self.error = f"{type(exc).__name__}: {exc}"
```

`concierge/ui/cart.py`'s `error_block` renders `State.error` verbatim. The audience
reads `ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': ...}}`.

**Why this one first:** `HANDOFF.md` names the Gemini quota as *the* bottleneck, and
records it already being hit on 26 Jul. This is the single most likely failure of the
day, and it is the worst-presented one. The Decathlon path proves the team already
knows how to handle a rate limit well — Gemini just was not added to the same list.

**Fixed.** Quota is recognised **by status — 429 — not by class name**, which matters
because `_RATE_LIMITED` matches `type(exc).__name__` and `ClientError` also covers
400s and auth failures that must not get a "switch to fixture mode" message. It has
its own wording naming the fixture escape hatch, and `State.error` no longer carries a
class name on any path — the detail belongs in the trace panel.

One correction to the first attempt, which claimed quota died at the intent gate and
wrapped `classify()` in a second handler: it does not. `classify()` catches `Exception`
itself and returns a fail-safe verdict, so quota never escapes it — it surfaces on the
next model call, inside the try that already had a written answer. The extra handler
could only fire if `classify` were replaced, which is what its test did. Removed.

### 2. The status line freezes for the whole longest wait — FIXED

`state.py` sets it once per turn:

```python
self.status = "Reading the conditions…"
```

After that it only changes if `_drain` sees an event in `_THROTTLE_STATUS` — seven
rate-limit and degradation events. A healthy turn hits none of them.

Turn one measures **52 s** of Gemini latency (`DECISIONS.md`, 25 Jul, has the
per-call breakdown). So a first-time user watches a spinner under a caption that does
not move, for the better part of a minute, on their very first interaction.

The audit rail *is* updating live — but a person who has never seen this product is
not reading a log to find out whether it is alive.

**Fixed.** Derived from the trace already being drained mid-turn. A throttle message
still outranks the routine captions.

The first attempt did not work outside fixture mode: the table was keyed on
`ui/demo_data.py`'s event vocabulary, so six of its nine keys had no live emitter and
the caption still froze through retrieval and sizing — the longest stretch of the turn,
and the whole point. It is now keyed on what the live pipeline emits (`gate.verdict`,
`research.grounded`, `catalog.collection`, `ucp.call`, `catalog.variant_resolved`,
`kit.built`), with the fixture names kept as explicit aliases so the on-stage replay
still moves. `test_it_keys_on_events_that_are_actually_emitted` now covers both tables
and ignores `_fixture_*` bodies, which is what let two of the dead keys look alive.

### 3. The budget silently vanishes on the most natural phrasing — FIXED

Measured by calling the real `_budget_minor` with a session stub:

| Input | Parsed |
|---|---|
| `my budget is $900` | ✅ 90000 |
| `$900 budget` | ✅ 90000 |
| `budget 900 dollars` | ✅ 90000 |
| `I can spend 900 dollars` | ✅ 90000 |
| `my budget is 900` | ❌ **None** |
| `keep it under 900` | ❌ None |
| `up to 900` | ❌ None |
| `900 dollars max` | ❌ None |
| `no more than 900 dollars` | ❌ None |
| `I have 900 dollars` | ❌ None |

Without a `$`, the second pattern requires a currency **word after the number**, and
the anchor keyword **before** it. `my budget is 900` satisfies neither.

What actually happens when it misses — stated precisely, because the first draft of
this review got it wrong: `check_budget` **does** still emit a `guardrail.budget`
event, with `"No budget set."`. So the trace is honest. **The UI is silent.**
`has_budget` is false, so the `BUDGET` stat does not render and neither the
over-budget nor the under-budget disclosure appears. The customer stated a budget,
the kit ignored it, and the only trace of that is a log row they will not read.

That matters more than a parsing miss normally would: **over-budget is one of the
four honesty affordances the product is judged on**, and this is a way to switch it
off by accident, by typing English.

**Fixed**, with a trap worth recording. Widening the anchors made the *opposite*
failure real, and that direction is worse: a miss is silent, but a false positive
makes the kit disclose an overrun against a figure the customer never gave.

The first attempt fought it with a unit blocklist inside the regex — `m|km|mi|ft|kg|
lb|people|nights|…`. That cannot close the hole, because it has to name every unit
anyone might type: `around 3800 meters` still parsed as **$3800**, `about 45 litres`
as **$45**, `about 30 litre pack` as **$30**. Small ones only escaped notice because
the pre-existing under-$20 floor swallowed them.

The scope was the actual bug. Only the keyword pattern is loose enough to be fooled,
and it only needed the trip description because it was reading it — so it now runs
over `session.answers` alone, while the three currency-marked patterns still read the
trip. No blocklist. Both directions are pinned, including the units that defeated the
list. One honest regression: a bare `budget around 900` in the *opening* message now
returns `None`; the same figure parses with a `$` or the word `dollars`, or said as an
answer. A bare number is still not a budget, and an unanchorable money mention emits a
guardrail instead of nothing.

---

## P1 — makes a first-timer stumble

### 4. Four questions, one free-text field, never asked again — PARTLY FIXED

`prompts.py`:

```
* AT MOST 4 questions, all in this one turn. Never ask again later.
```

In `agent/loop.py`, `_render_questions` numbers them into one markdown block, and
`_continue` sets `session.questions_asked = True` permanently. A user who answers two
of four loses the other two silently — which is precisely how a kit arrives with
unconfirmed sizes.

PR #4 added a "Tell DecaBot my sizes" button, so *sizes* now have a route back.
Party size, existing kit and budget do not.

### 5. Presenter controls sit above the product for every user — FIXED

`app.py` renders `concierge/ui/walkthrough.py`'s `walkthrough_bar()` unconditionally.
Measured on a 414×896 phone at first load:

| | top |
|---|---|
| fixture ribbon | 119 px |
| GUIDED DEMO panel | 224 px |
| "Run the demo" button | 303 px |
| **hero heading — what this product IS** | **582 px** |
| primary example button | 863 px |

So the first ~560 px of a phone screen is a ribbon plus a control panel for a
scripted demo the viewer is not running, before the product introduces itself. The
copy is operator jargon: *"Step 1 of 2 · refusal · grounded research · live kit ·
~3 min."*

This is the right UI for the presenter on the build laptop. It is the wrong UI for
the audience holding the QR code, and both get it.

### 6. Nothing sets a time expectation — FIXED

Neither the hero nor the composer says the first answer takes about a minute. With
finding 2, that leaves a first-timer no way to tell whether waiting is correct
behaviour.

### 7. "Start over" destroys a live run with no confirmation — FIXED

`State.clear` wipes `messages`, `kit_items`, `trace`, the cart and the walkthrough
stage. The control is icon-only below `md`. One mis-tap on a phone ends a run that
took three minutes of live API calls — during a two-minute pitch.

---

## P2 — smaller risk

### 8. The model-call budget ends a conversation with no way back — FIXED

`MAX_MODEL_CALLS = 25`. A judge who explores conversationally can reach it, and the
only offer is to start a fresh conversation — losing the kit they were looking at.

### 9. The parsers are keyed to English words — ALREADY CLOSED

**The paragraph below was wrong when it was written, and is kept only so the correction
has something to point at.** `_budget_minor` already had `presupuesto`, `hasta` and
`dólares`, and `_SIZE_CUE` already had `tallas?`. It was written from reading the code
once without running it. Tests now pin all four.

~~A Spanish-speaking judge in Medellín typing `presupuesto 900` gets no budget, and the
size tokenizer only recognises Latin letter sizes and numbers.~~

The English UI itself is **correct and not a finding**: the agent-commerce layer
exists only on Decathlon's US store, in USD, so an English product is the honest one.
It is only the parsers behind it that are narrower than the room.

**Shape of a fix:** finding 3's general half already covers the budget half of this —
a guardrail on an unanchorable money-number tells the `presupuesto 900` user too.
Adding Spanish keywords to the two patterns is the cheap mitigation on top; the
interface stays English either way.

---

## Checked and found fine

Recorded so nobody re-investigates them:

- **Hero above the fold on mobile.** Suspected it was pushed under; measured, it is
  not — 582 px on a 896 px viewport, with the primary example at 863 px.
- **The cart is reset between turns.** `send_message` calls `_reset_cart()`, so a
  rebuilt kit can always reach a second cart link.
- **`create_cart` is still absent from the model's tool list**, and `confirm_bar` is
  its only route.
- **Substitution vs. unconfirmed stays split** — amber for a fault already committed,
  brand blue for an open question.

---

## Suggested order

The three P0s are one problem wearing three hats: **the system knows, and does not
say.** They are also all small, and independent of each other.

1. **Finding 1** — the raw exception on screen.
2. **Finding 3** — the vanishing budget.
3. **Finding 2** — the frozen status line.

Findings 1 and 3 are the two a judge can trigger without meaning to. All three are
now closed; P1 and P2 are not.
