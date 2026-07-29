# Visual direction brief — DecaBot

**For the agent picking this up: this file is your complete instruction set. Read it
in full before touching anything. Every constraint here was measured or decided in a
prior session; none of it is a guess you may re-derive.**

Read [`AGENTS.md`](../AGENTS.md) first — it is canonical for everything about this
repo, and it outranks this file wherever they touch the same subject. This brief only
governs **visual direction**. It never overrides the load-bearing-facts registry.

---

## 0. What DecaBot is, in five lines

A conversational agent that turns a described sporting trip into a real,
size-resolved, in-stock **Decathlon shopping cart**. It researches the trip's actual
conditions on the web, derives the gear the trip needs, retrieves live products from
Decathlon's catalog, resolves each to an in-stock size, and — only on an explicit
human click — creates a real cart. The flow ends at the cart; payment is never
automated.

It is a hackathon deliverable (Los Prompteros · AgentSprint · Universidad EAFIT,
Medellín). **It gets judged as a live demo on a projector.** That is the use scene:
someone is talking while this is on screen behind them.

---

## 1. The decision that was made, and the one that was rejected

The product owner was asked to choose between two directions and chose the first.
**Do not revisit this.**

### CHOSEN — DecaBot has its own voice

`#3643BA` (Decathlon's primary) stays as the brand anchor. On top of it, build a
visual system that is DecaBot's own: an editorial type scale, real depth and density,
a dark surface for the audit rail. It should read as a **product**, not as a page
from decathlon.com.

### REJECTED — stay literally drop-in inside decathlon.com

`concierge/ui/theme.py:1-11` currently says the pitch is that Decathlon could drop
this straight into their site. **That constraint is now retired for the visual
layer.** decathlon.com is deliberately plain and it capped how far the craft could
go. When you touch `theme.py`, update that docstring to record the new direction —
do not leave it asserting a constraint the design no longer honors.

The accepted cost, stated plainly so you do not try to have it both ways: DecaBot is
no longer literally drop-in. Keep it *harmonious* with Decathlon — same blue, same
honesty — but stop letting their flatness set the ceiling.

---

## 2. Non-negotiables

Breaking any of these breaks the build, the demo, or a guarantee the project makes.
They are not style opinions.

### 2.1 Architecture — from `AGENTS.md`, do not "fix" these

| Fact | Why |
|---|---|
| `Url = Annotated[str, AfterValidator(...)]` in `domain/models.py` | A pydantic `HttpUrl` **silently serializes to `null`** over Reflex's wire encoder. Every product photo and link would arrive empty, with no error. Never put a raw `HttpUrl` in anything that reaches the UI. |
| `rx.Base` does not exist in Reflex 0.9.7 | Use plain Pydantic v2 `BaseModel` for state vars. |
| `vite_allowed_hosts=True`, `app_module_import`, pinned ports in `rxconfig.py` | Demo-killers. Read `AGENTS.md` § "Reflex & serving" before editing `rxconfig.py` at all. |
| Never cache the catalog to disk | A local copy reads as mocked, which defeats the premise. |

### 2.2 Guarantees the UI must keep expressing

- **`create_cart` is not a model tool.** Human-in-the-loop is enforced by its
  *absence* from the tool list. `State.confirm_cart` re-checks `awaiting_confirmation`
  because conditional rendering is not a guard. Do not add any other route to it.
- **Specifications render from data, never from model prose.** The agent will not
  invent products — retrieval prevents that — but it *will* invent properties of real
  ones ("rated to −5 °C", "60 litres"). Every factual attribute on a card must come
  from a `KitItem` field. Model prose lives in `rationale` and nowhere else. If your
  redesign adds a spec row, it renders fields that exist or it does not ship.
- **`KitItem.available: Literal[True]`** — an out-of-stock item cannot exist in a
  `Kit`. The "IN STOCK" claim is structural. Do not weaken it into a promise.
- **Honesty affordances must stay unmissable**: `SIZE SUBSTITUTED`,
  `WHAT SIZE ARE YOU?`, unservable slots, over-budget. You may redesign how they look.
  You may not make any of them quieter or easier to scroll past.

### 2.3 Accessibility — landed in PR #4, must not regress

Verified and measured. Re-breaking any of this is a regression, not a trade-off.

- **`GREY_2` and `GREY_3` are icon and rule colours and NEVER set type.** Measured:
  `GREY_2 #949494` is 3.03:1 on white and 2.81:1 on `TINT_1`; `GREY_3` is 1.86:1.
  Anything that reads as words uses `MUTED #707070` (4.95:1 / 4.59:1) or darker.
- `SUCCESS_DEEP #12704A` exists because `SUCCESS` on `SUCCESS_BG` is 4.08:1.
  `WARN_INK #8A6100` exists because `WARN` as type is 1.6:1 — `WARN` is a **surface**.
- Body and placeholder text **≥4.5:1**, large text ≥3:1. On coloured surfaces, tint
  secondary text from that hue or the foreground — never grey. **Measure, do not
  eyeball.** A helper is in §6.
- Keep: `role="banner"` / `role="main"` / `role="complementary"`, the `db-skip` skip
  link, the visually hidden persistent `<h1>` in `app.py` (the empty state's heading
  is an `h2` and unmounts — it cannot be the `h1`), `aria-live` on the transcript and
  the status row, accessible names on every icon-only button whose label hides below
  `md`, and 44px minimum touch targets.
- `prefers-reduced-motion` must keep an intentional path. The current global
  `0.001ms` kill in `assets/decabot.css` is itself a finding — **fix it** as part of
  work package D rather than preserving it.

### 2.4 Tests and process

- `make check` must stay green. Baseline: **210 passed, 12 deselected**.
- `make verify` (live suite) is only needed if `commerce/` changes. Your work should
  not touch `commerce/` at all.
- Append to `docs/DECISIONS.md`; it is **append-only**, never edit a past entry.
- Comments: **absolutely minimal**, only where a fact is genuinely counterintuitive.
  No docstring on every function. This repo's style is terse and load-bearing.

---

## 3. Diagnosis — why it currently reads flat

Run against Impeccable's craft floor. These are **category defaults**, not bugs: the
UI reaches for the same handful of moves every generic product UI reaches for, which
is exactly why it reads as competent-but-anonymous.

### 3.1 The eyebrow above a heading — a ban, not a preference

The craft floor bans this outright: *"The heading carries its own weight; delete the
label and let the heading speak."*

| Location | Text | Verdict |
|---|---|---|
| `ui/product.py:168` | slot label above the product title | **True kicker. Must go** — but the slot is real information the title does not carry. Re-express it as data, not as a label. |
| `ui/product.py:384` | `THE KIT` | Section kicker. Remove or absorb. |
| `ui/product.py:268` | `SLOTS DECABOT COULD NOT FILL` | Same. |
| `ui/chat.py:117` | `SOURCES · GROUNDED WEB SEARCH` | Same. |
| `ui/chat.py:340` | `OR START FROM ONE OF THESE` | Same. |
| `ui/chat.py:136,156` | `YOU` / `DECABOT` | Speaker attribution in a transcript. Judgement call — attribution is not a kicker, but two ALL-CAPS labels per exchange is noise. |
| `ui/cart.py:73`, `ui/product.py:290` | stat labels above values | **Not a kicker.** A stat label is not a heading. These may stay. |

### 3.2 The hero-metric template

`ui/product.py:377-425` (`kit_summary`) is the flagged pattern exactly: big number,
small label, supporting stats, accent colour. This is the moment a shopper decides to
spend $1,300 — it deserves a form with more conviction than a dashboard tile row.

### 3.3 One structural device doing seven different jobs

`border_left: 3px solid <colour>` appears at `cart.py:216,235,260`,
`chat.py:192`, `product.py:282,325,340,374`. The craft floor names a coloured
`border-left` above 1px as a surface habit. Here it is worse than a habit: a chat
bubble, an error, a budget line, a success cart and a size prompt are all *the same
shape in a different colour*. Nothing in the page has structural hierarchy — only hue.

### 3.4 Identical cards as page structure

The three empty-state examples (`ui/chat.py:287-316`) are same-size cards of icon +
heading + text. Flagged as the lazy container.

### 3.5 No authored motion

`db-rise` (`assets/decabot.css:92-105`) fires identically on chat bubbles
(`chat.py:147,194`) and trace rows (`trace_panel.py:173`). The craft floor asks for
**one authored moment**, not the same entrance everywhere.

### 3.6 No editorial type contrast

One family (Inter), a narrow weight band, near-uniform sizes. Nothing sits at display
scale except the empty-state heading. Tracking floor available: `-0.04em`.

---

## 4. Work packages

Four packages, all four in scope. Ship them as **one branch, one PR**.

Global rules for all four:
- **Commit, then clarify.** Make one decisive move per package completely, then quiet
  everything around it. If every element gets louder, the page got flatter.
- **Amplify what the system owns.** `#3643BA` is the anchor. Do not introduce a
  second brand hue. New neutrals and surfaces are allowed and expected.
- **Skeleton test:** strip the copy out of your planned section. Does the bare
  structure still say what the section is and why it matters? If it only works once
  the words return, the boldness is in the font size, not the design.

---

### Package A — Empty state / first impression

**File:** `concierge/ui/chat.py` (`empty_state`, `_example`, `EXAMPLES`)

**Current:** centred bot mark → `h2` at ~32px → paragraph → eyebrow → three identical
cards. It is the first thing on the projector and it is doing nothing.

**Required outcome**
- A genuine hero moment. Display type at full strength (craft floor: display max
  `6rem`, tracking floor `-0.04em`, balanced headings).
- The three examples must stop being three equal cards. One primary path plus two
  secondary is the suggested shape; any structure that breaks the equal-weight grid
  is acceptable.
- The examples remain **functional buttons** (`rx.button`, so Enter and Space work)
  and keep their exact prompt strings — each is a trip Decathlon genuinely stocks
  for, and an example that dead-ends is worse than no example.
- Body measure stays 65–75ch.

**Done when:** the skeleton test passes, the `h2` is still an `h2`, all three examples
still fire `State.send_example`, and it holds up at 1440px and 414px.

---

### Package B — The kit and the product cards

**Files:** `concierge/ui/product.py`, and `KitCard` in `concierge/state.py` if you
need a new render-ready field

**Current:** `kit_summary` is the hero-metric template; `product_card` is a standard
e-commerce card with a kicker above the title.

**Required outcome**
- Replace the hero-metric row with a form that reads as **closing a purchase**.
- Kill the kicker at `product.py:168`. The slot (`WATERPROOF BOOTS`) is real
  information — re-express it as data rather than as a label above the title.
- Establish hierarchy between summary, cards, and callouts by **structure and
  weight**, not by seven differently-coloured left borders.
- `size_substituted` (amber) and `size_confirmed=False` (brand blue) must stay
  visually distinct and unmissable. The colour split is deliberate: a substitution is
  a fault already committed; an unconfirmed size is an open question. Do not merge
  them. See `docs/DECISIONS.md`, entry dated 2026-07-29.
- Zero-value stats stay hidden (`SIZE SWAPS`, `SIZES TO CONFIRM` render only when > 0).
- Grid columns: `initial="1", sm="2", lg="2", xl="3"`. **Do not restore three at
  `lg`** — that is the same breakpoint the 384px audit rail moves beside the column,
  which left ~200px per card.

**Done when:** every factual attribute still comes from a `KitItem` field, all four
honesty affordances survive, and `make check` is green.

---

### Package C — The audit panel

**File:** `concierge/ui/trace_panel.py`, plus `LEVEL_COLOR` / `LEVEL_BG` in `theme.py`

**Current:** a generic log viewer on white.

**Why it matters more than it looks:** this panel *is* the technical claim. The
project's thesis is "a guardrail written in the prompt is a suggestion; a guardrail
written in Python is a guarantee" — every check emits a trace event at
`level="guardrail"`, and this rail is where a judge watches them fire. It should read
as an **instrument**, not as console output.

**Required outcome**
- A dark surface is explicitly sanctioned here and is the recommended move. It gives
  the page a second register and makes the rail read as instrumentation.
- Monospace is **earned** here — this is real log data and measurement, not a costume.
  Keep it.
- Guardrail rows must remain unmistakably distinct from routine `info` rows. That
  distinction is the point of the panel. Errors likewise.
- Contrast on a dark surface must be re-measured from scratch. The light-surface
  tokens do not transfer. Tint secondary text from the surface hue — never grey.
- Keep `role="complementary"`, the `aria-label`, `aria-expanded`/`aria-controls`, the
  44px targets, and the collapsed-state toggle.

**Done when:** contrast is measured and passing on the new surface, and a guardrail
row is identifiable at a glance from three metres away.

---

### Package D — Motion

**Files:** `assets/decabot.css`, and the `class_name` call sites

**Current:** `db-rise` on every bubble and every trace row; `db-halo` on the presence
dot; `db-sweep` on the walkthrough bar. Scattered, not authored.

**Required outcome**
- **One authored moment.** Choose the one thing worth animating and make it excellent.
  Strong candidate: the kit arriving — that is the payoff beat of the whole demo, and
  right now it just appears.
- Exponential ease-out **from an already-visible default**. Nothing may be invisible
  waiting for JS.
- Reach past transform and opacity where it stays smooth: blur, `backdrop-filter`,
  `clip-path`, `mask`, shadow.
- Do **not** animate layout properties.
- **Fix `prefers-reduced-motion`.** The current global `0.001ms` kill
  (`decabot.css:274-281`) destroys useful feedback. Reduced motion needs an
  intentional alternative that preserves state change and hierarchy, not a blanket off
  switch.

**Done when:** one moment is clearly authored, reduced-motion has a real alternative
path, and nothing animates layout.

---

## 5. What you must NOT do

- Do not touch `concierge/commerce/`, `concierge/agent/`, or `concierge/domain/`
  logic. `state.py` may gain render-ready fields on `KitCard` and computed `rx.var`s;
  it may not gain business rules.
- Do not add a JS charting or animation library. The stack is Reflex + one CSS file.
- Do not add a second brand hue.
- Do not restore any pattern §3 names as a default.
- Do not add a dependency without saying why a few lines could not do it.
- Do not fabricate product data, prices, or specs for the sake of a nicer card.
- Do not use `AskUserQuestion` to re-open §1. It is decided.

---

## 6. How to run and verify

```powershell
# Fixture mode: full kit, real product data, no Gemini quota spent.
$env:CONCIERGE_FIXTURE_MODE="1"; .\.venv\Scripts\reflex.exe run
```

Open `http://localhost:3000`, click **"Two nights in the páramo"**. In ~8 seconds you
get the complete demo kit, which deliberately triggers every honesty affordance: a
real size substitution (women's NH900, asked 7, got 6.5), an unconfirmed size (men's
NH500 fleece — no size requested, ten in stock), two unservable slots, and over
budget by $405.99.

**Tests**

```powershell
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe -m pytest tests/ -q
```

**Contrast — measure, never eyeball**

```python
def lum(h):
    h = h.lstrip("#"); c = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    c = [v/12.92 if v <= 0.03928 else ((v+0.055)/1.055)**2.4 for v in c]
    return 0.2126*c[0] + 0.7152*c[1] + 0.0722*c[2]

def ratio(a, b):
    la, lb = lum(a), lum(b)
    return round((max(la, lb) + 0.05) / (min(la, lb) + 0.05), 2)
```

**Inspection protocol — bounded, not a loop.** Build all four packages fully. Then
inspect **once** in a batched round covering desktop and mobile together. Fix
everything that round shows in **one** batch. Confirm with at most one more round,
then stop. Open-ended self-QA burns money doing worse what a review does better.

**Detector**

```bash
node <impeccable-skill-dir>/scripts/detect.mjs --json assets/decabot.css concierge/ui concierge/app.py
```

Known false positive, already adjudicated: `overused-font: Inter`. Inter stays — it is
the face Decathlon loads, it is the brand anchor's companion, and the brief outranks a
saturation warning. **Do not swap the font to satisfy the detector.** If you want a
second face for display type only, that is a legitimate proposal — argue it in the PR
rather than doing it silently.

---

## 7. Deliverables

1. **Branch** off `ui-accessibility-and-size-affordance` (this brief assumes PR #4 is
   in your history — `KitCard.size_confirmed` and the a11y work come from it). Name it
   something like `visual-direction-decabot-voice`.
2. **One PR**, all four packages. Body must contain:
   - before/after for each package, in words
   - the contrast table for any new surface, with measured ratios
   - which §3 defaults you removed and what replaced each
   - the detector output and your adjudication of any finding
   - confirmation that `make check` is green with the pass count
3. **`docs/DECISIONS.md`** — one appended entry recording the direction change (own
   voice over drop-in), what it cost, and any token added with the measured reason.
4. **`concierge/ui/theme.py`** — docstring updated so it no longer asserts the retired
   drop-in constraint.
5. **Screenshots** at 1440px and 414px of: empty state, full kit, audit panel, cart
   created.

## 8. Acceptance

- [ ] `make check` green, 210+ passed
- [ ] Every §2 non-negotiable intact — spot-check the a11y list explicitly
- [ ] Every §3 default either removed or explicitly argued for in the PR
- [ ] Contrast measured, not eyeballed, on every new surface
- [ ] All four honesty affordances still unmissable
- [ ] Skeleton test passes for packages A, B, C
- [ ] Runs clean at 1440px and 414px
- [ ] Unmistakably the same brand — only far more sure of itself
