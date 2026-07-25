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
```

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

## IN PROGRESS

- [ ] **Decathlon-native restyle.** The client wants this to look like it belongs
      inside decathlon.com. Their real tokens, scraped from their live homepage:

      BRAND       #3643BA   primary (their --color-background: rgb(54 67 186))
      BRAND_DARK  #2E3998 · BRAND_DEEP #272F76
      TINT_1      #F5F6FC (page) · TINT_2 #E7E8F7 · TINT_3 #D3D8F7
      INK         #232323 · GREY #707070 / #949494 / #BEBEBE / #E1E0DF
      OFFWHITE    #F3F3F3 · WHITE #FFFFFF
      SUCCESS     #148558 · DANGER #D70322 · WARN #FFCD4E

      Font: their 'Decathlon Brand/Display/Text' are proprietary — use **Inter**
      (they load it too) with a sans-serif fallback.
      **Light theme, not dark.** White cards on a pale-blue wash, squarer radii
      (4–8px), price as prominent bold ink, solid blue primary buttons.
      `#7AFFA7` is their *promotional* green — do NOT use it for "in stock", it
      reads as a sale badge. Use `#148558`.

      Files: `concierge/ui/theme.py` (token source, everything imports from it)
      plus hardcoded rgba values in `ui/product.py`, `ui/cart.py`,
      `ui/trace_panel.py`, and `appearance="dark"` in `concierge/app.py`.

- [ ] **A reference design was provided** as a shared Claude artifact,
      `https://claude.ai/code/artifact/faa6d28e-17ef-4a59-b010-b96b00db3fa0`
      ("Expedition Concierge Integration"). **It could not be read** — the fetch
      fails with *"served to you as a public (non-member) reader, and reading
      public artifacts that way is not enabled yet"*, both directly and via the
      shared-artifact list. To use it, get the HTML into the repo (save it under
      `docs/design-reference.html`) or have the owner re-publish it.

## NOT DONE — highest value first

- [ ] **Click "Build my cart" in the browser.** The single most important
      untested path: `confirm_cart` → `commerce.cart.create_cart` →
      `_apply_cart` → `cart_block` rendering a live `continue_url`. Every step
      upstream is verified; this click never has been. Do it on a *fresh*
      `reflex run` (the dev server hot-reloads across edits and its module state
      goes stale).
- [ ] **Tunnels + phone test.** `make tunnel`, then open the judge URL **from a
      phone, not the build laptop**, and send one message. A reply is the only
      positive proof the WebSocket reached the tunnelled backend.
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
