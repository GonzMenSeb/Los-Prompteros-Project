# Demo readiness — where a low-context user breaks this

Findings from a review on **2026-07-29**, framed by one question: *this is judged as
a live demo, and the people using it have never seen it before. Where does that go
wrong?*

Every finding below was measured against the code or the running app. File and line
references are to the tree at the time of review. Nothing here is a style opinion —
each item is a place where **the system knows something it does not tell the user.**

This is a findings report, not a plan. Nothing here has been fixed. `DECISIONS.md`
records calls that were made; this records ones that have not been.

---

## P0 — visible on the projector, breaks the demo

### 1. An exhausted Gemini quota prints a raw exception on screen

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
    self.error = f"{type(exc).__name__}: {exc}"
```

`cart.error_block` renders `State.error` verbatim. The audience reads
`ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': ...}}`.

**Why this one first:** the project's own README and `HANDOFF.md` name the Gemini
quota as *the* bottleneck. This is the single most likely failure of the day, and it
is the worst-presented one. The Decathlon path proves the team already knows how to
handle a rate limit well — Gemini just was not added to the same list.

**Shape of a fix:** recognise the quota error, say what happened in a sentence, and
name the operator's escape hatch (fixture mode). Raw exception strings should never
reach `State.error`; the trace panel is where the detail belongs.

### 2. The status line freezes for the whole longest wait

`state.py` sets it once per turn:

```python
self.status = "Reading the conditions…"
```

After that it only changes if `_drain` sees an event in `_THROTTLE_STATUS` — seven
rate-limit and degradation events. A healthy turn hits none of them.

Turn one measures **52 s** of Gemini latency (`DECISIONS.md`, 25 Jul: classify 12.5,
research 9.8, profile 14.2, slots 11.5, questions 4.1). So a first-time user watches
a spinner under a caption that does not move, for the better part of a minute, on
their very first interaction.

The audit rail *is* updating live — but a person who has never seen this product is
not reading a log to find out whether it is alive.

**Shape of a fix:** the events already flow through `_drain`. Deriving the status
line from them costs one mapping and no new plumbing.

### 3. The budget silently vanishes on the most natural phrasing

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

**Shape of a fix:** widen the pattern, and — more important than any regex — emit a
guardrail when a number that looks like money is seen but *cannot* be anchored, so
the failure is loud instead of silent.

---

## P1 — makes a first-timer stumble

### 4. Four questions, one free-text field, never asked again

`prompts.py`:

```
* AT MOST 4 questions, all in this one turn. Never ask again later.
```

`_render_questions` numbers them into one markdown block, and `_continue` sets
`session.questions_asked = True` permanently. A user who answers two of four loses
the other two silently — which is precisely how a kit arrives with unconfirmed sizes.

PR #4 added a "Tell DecaBot my sizes" button, so *sizes* now have a route back.
Party size, existing kit and budget do not.

### 5. Presenter controls sit above the product for every user

`app.py` renders `walkthrough.walkthrough_bar()` unconditionally. Measured on a
414×896 phone at first load:

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

### 6. Nothing sets a time expectation

Neither the hero nor the composer says the first answer takes about a minute.
Combined with finding 2, a first-timer's evidence is: a static caption, a spinner,
and no idea whether waiting is correct behaviour.

### 7. "Start over" destroys a live run with no confirmation

`State.clear` wipes `messages`, `kit_items`, `trace`, the cart and the walkthrough
stage. The control is icon-only below `md`. One mis-tap on a phone ends a run that
took three minutes of live API calls — during a two-minute pitch.

---

## P2 — smaller risk

### 8. The model-call budget ends a conversation with no way back

`MAX_MODEL_CALLS = 25`. A judge who explores conversationally can reach it, and the
only offer is to start a fresh conversation — losing the kit they were looking at.

### 9. The residue of an English-only surface

The English UI is **correct and not a finding**: the agent-commerce layer exists only
on Decathlon's US store, in USD, so an English product is the honest one.

What remains is narrower: the **parsers** are keyed to English words. A Spanish-
speaking judge in Medellín typing `presupuesto 900` gets no budget, and the size
tokenizer only recognises Latin letter sizes and numbers. The cheap mitigation is to
add the Spanish keywords to those two patterns and leave the interface in English.

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

1. **Finding 1** — highest likelihood × worst presentation.
2. **Finding 3** — a judge can disable an honesty affordance by accident.
3. **Finding 2** — the cheapest of the three; the data is already flowing.

Findings 1 and 3 are the two a judge can trigger without meaning to.
