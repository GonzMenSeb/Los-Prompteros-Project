# HANDOFF — state of the build

Living checklist. Update it as you go; another agent should be able to resume
from this file alone. Read [`AGENTS.md`](../AGENTS.md) first — its
load-bearing-facts registry is what stops an assistant "fixing" working code.

## How to run anything

```bash
PYTHONPATH=. ./.venv/bin/python <script>      # venv is at ./.venv, python 3.12
make check          # offline suite  (pytest -m "not live")
make verify         # live contract tests against Decathlon + Gemini
make doctor         # preflight — currently ALL GREEN
make dev            # reflex run (ports 3000 frontend / 8000 backend, pinned)
make tunnel         # both cloudflare tunnels in the order that works
PYTHONPATH=. ./.venv/bin/python scripts/e2e.py        # full CLI end-to-end
PYTHONPATH=. ./.venv/bin/python scripts/spike_cart.py hiking-boots --size 10.5
PYTHONPATH=. ./.venv/bin/python scripts/verify_walkthrough.py   # rehearse, no browser
```

---

## Running the demo

The pitch is two minutes, so the demo gets about **thirty seconds on camera**. A real
run does not fit in thirty seconds — measured, turn one alone is **52 s** of Gemini
latency — so `concierge/walkthrough.py` splits the script in two. Both phases are
live; neither is mocked. `CONCIERGE_FIXTURE_MODE` is the fake and it says so on screen.

```bash
make walkthrough                 # prewarm: kills strays, waits for compile, opens the
                                 # browser, and the script starts on its own
make walkthrough PHASE=onstage   # the on-camera phase
make walkthrough PHASE=all       # end to end
make rehearse                    # same script, no browser, asserts every beat
```

`make walkthrough` opens `localhost:3000/?walkthrough=<phase>`, and **the query
parameter is what starts it** — a plain visit to `localhost:3000` will not restart the
script, so a stray refresh mid-pitch cannot wipe a kit that took three minutes of live
calls to build.

1. **`1 · Prewarm the trip`** — hit it while the pitch is still on the problem
   statement. **~2.8 min.** Swim refusal, grounded research with citations, targeted
   questions, then a real kit: 10 items, ~$1,160, photos, resolved sizes, running
   budget, substitutions disclosed, two slots honestly marked unservable.
2. **`2 · Go live`** — hit it when the audience is looking. Injection blocked with the
   kit and every price unmoved, then the real cart.
3. **Open the cart link.** That is the proof. Hand the phone over.

Rehearse the whole thing headless with `scripts/verify_walkthrough.py`; it asserts
every beat and prints the wall clock per phase.

**Killing a stale dev server needs two patterns.** The frontend is a detached
`react-router dev` node process under `.web/` that survives killing the reflex
supervisor and keeps port 3000. And never type a `pkill -f 'reflex run'` inline — the
pattern matches the invoking shell's own command line and kills the caller.

---

## DONE — verified, not assumed

- [x] **Spike.** Live `create_cart` proven before any code was written.
- [x] **Contract layer** frozen first: `domain/models.py`, `obs/trace.py`,
      `commerce/ucp.py`, `rxconfig.py`. Everything else was built against it.
- [x] **Commerce lane.** `catalog.py` (live taxonomy, handle validation, §4.3
      field mapping, `resolve_variant`) + `cart.py`. Verified live on two
      products: one with Color+Size, one Color-only.
- [x] **Agent lane.** Four-call sequence, intent gate, `types.Tool`-wrapped
      declarations, client-side history, call counters.
- [x] **Guardrails lane.** `domain/guardrails.py` + 131 offline tests green.
- [x] **UI lane.** Chat, product cards, kit summary, trace panel, cart confirm.
- [x] **End-to-end, CLI.** Santurbán prompt → grounded research (3,000–4,290 m,
      sub-zero lows) → `ActivityProfile` → 8 slots → live products → sizes
      resolved → **real cart, 5 lines, $1,004.98**.
- [x] **End-to-end, browser.** Message sent through the running app; trace panel
      streamed `turn.start` → `tools.backend=concierge.commerce.catalog` →
      `gate.verdict[GUARDRAIL]`. WebSocket over the pinned ports works.
- [x] **Two integration bugs found by driving the real app** (no test caught
      either): `run_turn()` called with a non-existent `history=` kwarg, and the
      loop still pointed at `agent/stubs.py` so the UI would have served fixture
      data while claiming to be live.
- [x] **Secrets audited.** `.env` never tracked; the key value never appears in
      any commit. `doctor.py` now actually checks this (it previously ran the
      search and discarded the result, passing unconditionally).
- [x] `AGENTS.md`, `commerce/AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`.
- [x] **Decathlon-native restyle** (`d49f2dd`, `100b9ce`, `ad10af1`). Their real
      tokens live in `concierge/ui/theme.py` and everything imports from there —
      BRAND `#3643BA`, light theme, Inter, squarer radii, `#148558` for "in stock"
      because their `#7AFFA7` is a *promotional* green and reads as a sale badge.
      The bot is **DecaBot**: two-tone wordmark, presence dot green on live catalog
      and amber on a fixture replay.
- [x] **Feed-first variant resolution** (`e5bb954`). `resolve_variant` runs off the
      storefront feed at **zero MCP calls**; `create_cart` is the only MCP call in a
      demo run. The old three-call grid walk is what tripped the rate limiter.
- [x] **Two-phase scripted walkthrough** (`e5bb954`, `ad10af1`) — prewarm + onstage,
      both live, driven by `?walkthrough=<phase>`.
- [x] **Reconnect no longer wipes the kit** (`ad10af1`). Reflex re-fires `on_load` on
      every websocket *reconnect*, which re-armed the whole script whenever the
      tunnel blinked. `walkthrough_autostarted` latches it once per session.
      Verified in the browser: cart, 12 product cards, kit total and transcript all
      survive a re-fired `on_load`.
- [x] **Tunnels brought up end to end** via `make tunnel` — backend tunnel, compile
      against it, frontend tunnel, judge URL printed. `make reload` re-compiles
      without minting new URLs, so a QR code already in the wild stays valid.
- [x] **Repo organised and docs refreshed**. Pre-build research archived
      under `docs/research/` with superseded-facts banners; `README.md` rewritten to
      describe the app rather than the two recon reports it used to ship.
- [x] **Full walkthrough driven end to end in a browser, 25 Jul.** Both phases, live,
      zero errors. Swim refusal → grounded research with **7 citations** (3,000–4,290 m,
      overnight lows to −15 °C) → 8 slots → **12 items, $1,203.97, 6 size swaps** →
      over-budget reported honestly → sleeping-bag slot left unfilled and named →
      injection blocked with prices unmoved → **real cart, 12 lines**, `continue_url`
      confirmed 301-redirecting to `www.decathlon.com/cart/c/…`. Screenshots in
      `docs/images/`, embedded in the README.

## KNOWN ISSUES — both will show on camera

- [ ] **Prices inside model prose render as LaTeX.** `rx.markdown` treats `$…$` as inline
      math, so *"$1,203.97 is $303.97 over the $900.00 budget"* renders as
      `1,203.97is303.97` in a serif math font. Only affects **markdown-rendered model
      prose** — the kit summary, product cards and cart block are styled components and
      are unaffected. Fix by escaping `$` before it reaches `rx.markdown` in
      `concierge/ui/chat.py:174`, or by disabling the math plugin. Visible in
      `docs/images/07-injection.png` below the fold, which is why that frame is cropped.
- [ ] **`GEMINI_API_KEY2` — the public-lane key — is quota-exhausted** (`429
      RESOURCE_EXHAUSTED`, confirmed 25 Jul). `GEMINI_API_KEY` (reserved/VIP lane) is
      fine. Every non-VIP session round-robins the public pool, so **a QR-code audience
      currently gets errors** while the presenting laptop works. Before demoing: either
      top up / replace `GEMINI_API_KEY2`, or empty the pool so it falls back to the
      reserved key (`public_keys()` in `agent/classify.py` already does that when no
      other key is configured). The walkthrough above was run with the pool emptied.

## NOT DONE — highest value first

- [ ] **Phone test over the tunnel.** `make tunnel`, then open the judge URL **from a
      phone, not the build laptop**, and send one message. A reply is the only
      positive proof the WebSocket reached the tunnelled backend. The tunnels have
      been up; this specific proof has not been recorded.
- [ ] **Rehearse the four judge checks** in `docs/RUNBOOK.md` §"four judge
      checks" — cart link, product click-through, out-of-stock size, absurd
      budget. Plus swimming-gear refusal and prompt injection.
- [ ] **Session-record analytics** — `SPEC-SESSION-RECORD.md`, deliberately
      deferred as non-core. A clean bolt-on: new `analytics/` package,
      SQLModel + SQLite, one hook at session close. Needs `sqlmodel` added to
      `requirements.txt`.
- [ ] Stretch, in priority order: host our own UCP agent profile on GitHub Pages;
      inline citations beside each gear rationale; expose the concierge itself
      as an MCP server.

**Dropped.** A reference design was shared as a Claude artifact
(`faa6d28e-17ef-4a59-b010-b96b00db3fa0`, "Expedition Concierge Integration"). It was
never readable — the fetch fails with *"served to you as a public (non-member)
reader"* — and the restyle shipped from Decathlon's own scraped tokens instead, which
is the stronger provenance anyway. Only revisit if the owner re-publishes it.

## Traps that will cost you an hour if you "fix" them

Full list in [`AGENTS.md`](../AGENTS.md). The five worst:

1. `tools/list` and `initialize` always fail. **Do not add an MCP SDK.**
2. The agent profile lives in `arguments.meta`, not `params`, not a header.
3. Responses are **double-encoded** — `json.loads()` twice.
4. `get_product` with **no** `selected` returns `available: null` for everything.
   A non-empty *partial* selection is required.
5. A pydantic `HttpUrl` serializes to **`null`** through Reflex's wire encoder,
   silently. `models.py` uses `Url = Annotated[str, AfterValidator(...)]`.
   Reverting that empties every product photo and link.
