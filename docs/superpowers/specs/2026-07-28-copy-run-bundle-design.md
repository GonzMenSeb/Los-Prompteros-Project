# Copy the run — a one-click debugging bundle

**Date:** 2026-07-28 · **Status:** approved, ready to implement

## The problem

When a run misbehaves, the audit rail on screen shows *that* a step happened but not
enough of *what* it carried. `summarise()` flattens each payload to `key=value` pairs,
clamps every value at 120 characters and the whole line at 300. That is the right call
for a panel a judge reads over your shoulder mid-demo, and the wrong one for handing a
failure to an AI afterwards. Today the only way to debug a run with an AI is to
screenshot the panel or retype it, and either way the payloads arrive already truncated.

## What we are building

A button in the `AUDIT TRAIL` header that puts the whole run on the clipboard as text:
the conversation, the trace with **full untruncated payloads**, and the kit, budget and
cart that came out. Self-contained, so pasting it into an AI needs no further
explanation.

## Architecture

### `concierge/obs/bundle.py` — new module

One pure render function. No Reflex import, so `tests/test_bundle.py` can build a
snapshot literally and assert on a string. It does import `minor_to_display` from
`domain/models.py` — that function is documented there as *"the ONLY place minor units
become human text"*, and the convention outranks keeping this module import-free.

```python
@dataclass(frozen=True)
class RunSnapshot:
    stamp: str                 # ISO-8601 UTC
    mode: str                  # "live" | "fixture"
    gated: bool
    lane: str                  # "reserved" | "public"
    messages: list[dict]       # role, content, citations[]
    events: list[dict]         # seq, ts, event, level, payload
    items: list[dict]          # slot, title, url, variant_id, size, qty, price_minor, substituted
    unservable: list[str]
    budget_minor: int | None
    cart: dict | None          # cart_id, url, total_minor, line_count, expires_at

def render(snap: RunSnapshot) -> str: ...
```

Output shape:

```
# DecaBot run bundle — 2026-07-28T19:04:11Z
mode=live  gate=on  lane=reserved  turns=2  events=47 (9 guardrail, 1 error)
NOTE: contains a live Decathlon cart link.

## Conversation
[1 user] Hiking Páramo de Santurbán, 2 nights, budget $300
[1 assistant] Here's what the conditions actually demand…
     cite https://…  https://…

## Kit — 6 items · $412.50 · budget $300.00 · OVER by $112.50
- TENT · Quechua MH100 · One Size · qty 1 · $89.99  [SIZE SUBSTITUTED]
  gid://shopify/ProductVariant/41919445434430
  https://www.decathlon.com/products/…
unservable: bike_helmet, gaiters

## Cart
gid://shopify/Cart/…  ·  6 lines  ·  $412.50  ·  expires 2026-07-29T…
https://www.decathlon.com/cart/c/…?key=…

## Trace
   1  +0.000s  info       turn.start
              {"turn": 1, "text": "Hiking Páramo de Santurbán, 2 nights"}
   2  +0.412s  guardrail  intent.verdict
              {"intent": "expedition", "confidence": 0.94}
```

Payloads render as compact JSON below ~160 characters and `indent=2` above it — never
through `summarise()`. The `+Ns` column is each event's `ts` relative to the first, which
makes a slow step visible without reading timestamps.

### State — a backend-only mirror

`TraceRow` keeps carrying only the summary, because it is what the panel renders and it
crosses the websocket on every drain. The full payloads live beside it:

- **`_raw_trace: list[dict]`** — the leading underscore makes it a *backend-only var*
  (`reflex_base/utils/types.py:849`): it is never serialized to any browser. `_drain()`
  appends to it alongside each `TraceRow`; `clear()` empties it.
- **`_last_bundle: str`** — also backend-only. Holds the rendered text between the copy
  and its result, so a successful copy costs nothing on the wire.
- **`copy_status: str`** — `""` | `"ok"` | `"failed"`, drives the button's icon.
- **`copy_fallback: str`** — published *only* when the clipboard write is refused.

`copy_run()` re-checks `GATE_ON and not self.unlocked` before building anything. Same
reasoning as `confirm_cart`: the event is callable over the wire whatever is on screen,
so conditional rendering is not a guard.

The copy emits no trace event of its own. It would pollute the artifact it is copying.

### The clipboard write, and not lying about it

`rx.set_clipboard` fires on the **websocket response**, one round trip after the click,
which is outside the click's transient user activation. Chromium generally allows it
because it auto-grants `clipboard-write` to the focused tab; Firefox and Safari throw
`NotAllowedError`. Worse, it returns no success signal, so a green *Copied ✓* would
appear even when the write was blocked — a claim rather than evidence.

`run_script(js, callback=…)` exists in Reflex 0.9.7, and the compiled frontend **awaits
the promise** before invoking the callback (`.web/utils/state.js:335-357`, verified). So:

```python
yield rx.run_script(
    f"navigator.clipboard?.writeText({json.dumps(text)}).then(() => true, () => false) ?? false",
    callback=State.copy_finished,
)
```

`json.dumps` with the default `ensure_ascii=True` escapes every non-ASCII character,
which also disposes of U+2028/U+2029. Optional chaining short-circuits the whole
expression to `undefined` when `navigator.clipboard` is absent — an insecure context —
and `?? false` turns that into an honest failure rather than a silent one.

`copy_finished(ok: bool)` sets `copy_status` from the real result and, on failure only,
copies `_last_bundle` into `copy_fallback` so the panel can show the text for manual
selection.

The badge is **not** reset on a timer: Reflex holds the per-session state lock for the
duration of a handler, so a `sleep` there would serialize that session's other events.
It clears on the next `send_message` or `clear`.

### Three guardrail events that never reached the panel

`unlock()` emits `gate.unlocked` / `gate.refused` and `on_page_load()` emits
`session.priority`, all at `level="guardrail"`, with no sink bound — so they land only in
the process-wide ring buffer and never in `State.trace`. The bundle would inherit that
gap. Each gets the local-sink-and-drain pattern already used by `send_message` and
`confirm_cart`. In `on_page_load` the bind wraps only the `session.priority` emit, before
the walkthrough branch, because `run_walkthrough` binds its own sinks.

Reading `trace.recent()` instead was rejected: `_GLOBAL` is process-wide, so on the
public URL it would splice other visitors' sessions into one user's bundle.

Side effect, and an improvement: those guardrail rows now appear in the live panel too.

### UI

A ghost icon-button in `trace_header()`, left of the collapse chevron: `copy`, becoming
`check` in `SUCCESS` on a confirmed write and `circle-alert` in `DANGER` on a blocked
one. Disabled while the trace is empty. When blocked, a selectable block appears at the
top of the panel body with the text and a plain instruction to copy it by hand.

## Deliberate inclusions

The bundle carries the cart's `continue_url` unredacted. Per the facts registry that
resolves to `…/cart/c/<token>?key=<key>` — a working link to a real cart. This is a
decision, not an oversight: the cart has no payment attached, the README already
publishes such links, and the URL is frequently the thing you need to debug. The header
says so so nobody pastes one somewhere public unaware. `turn.error` and `cart.error`
payloads carry `repr(exc)`, and an httpx exception repr embeds the request URL; same
reasoning applies.

## Verification

- `tests/test_bundle.py` — sections present, payloads untruncated, relative offsets,
  empty run, no cart, over-budget line, unicode survives.
- `scripts/verify_ui.py` — `_raw_trace` mirrors `trace`, the built bundle contains the
  user's message and a guardrail event, the gate blocks `copy_run`, `clear()` empties the
  mirror.
- The component tree compiles, and a real browser click actually fills the clipboard.
  A passing handler test does not prove the clipboard write survived the round trip.

**What the browser caught that nothing else did:** Reflex returns state containers wrapped
in `MutableProxy`, and `json.dumps` misses it — its encoder does an exact type check, so
every payload came out as a Python repr inside a JSON string. Every handler test passed,
because they asserted substrings. `state.plain()` rebuilds real containers, and
`verify_ui.py` now asserts real JSON rather than presence.

## Documentation

`docs/DECISIONS.md` gets an append. `docs/HANDOFF.md` gets a tick. One new entry joins
the AGENTS.md Reflex registry: **`rx.set_clipboard` fires outside user activation and
reports nothing** — without it, someone eventually "simplifies" this back into a silent
failure.

No facts-registry change beyond that, no `test_contracts.py`, no `commerce/`. `make
check` green is the bar.
