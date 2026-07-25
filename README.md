# DecaBot — Expedition Concierge

**Los Prompteros** · AgentSprint (ReshapeX AI-agent hackathon), Universidad EAFIT, Medellín.

A conversational agent that turns a described sporting expedition into a **real,
size-resolved, in-stock Decathlon shopping cart** — grounded end to end in Decathlon's
own agent-commerce protocol (UCP/MCP), which they published for exactly this.

> *"Voy a subir al Páramo de Santurbán con mi novia, acampamos dos noches."*

The agent researches the real conditions on the web with citations, asks a short set of
targeted questions, derives the gear the trip actually requires, retrieves real products
from Decathlon's live catalog, resolves each to an in-stock size, presents them with
photos and a running budget, and — **only on an explicit human click** — creates a real
Decathlon cart and hands over a live link.

The flow **ends at the cart**. Payment is never automated. That is both the honest
stopping point and the one Decathlon's own `agents.md` prescribes.

## Quick start

```bash
make setup     # venv (python 3.12), deps, .env from .env.example, fetch cloudflared
#              then paste your GEMINI_API_KEY into .env
make doctor    # preflight: key valid, model resolves, both endpoints reachable
make check     # offline suite — 205 tests
make dev       # reflex run → http://localhost:3000
```

For the demo itself — the two-phase scripted walkthrough, the tunnel bring-up order,
and the contingencies — see **[`docs/RUNBOOK.md`](docs/RUNBOOK.md)**.

```bash
make walkthrough                 # fresh server, browser opened, script running
make walkthrough PHASE=onstage   # the on-camera phase
make rehearse                    # same script, headless, asserts every beat
make tunnel                      # both cloudflare tunnels, in the order that works
```

## How it works

Four Gemini calls per turn, deliberately **phased** — search never shares a request
with the tool loop, because combining them costs the structured citations:

| | |
|---|---|
| **1 · intent gate** | Structured, no tools. Off-topic, out-of-scope, unservable, safety-critical and prompt-injection each get a distinct answer. |
| **2 · grounded research** | `google_search` **only**. Citations exist here and nowhere else. |
| **3 · profile extraction** | Structured, no tools → a validated `ActivityProfile` + gear slots. |
| **4..n · tool dispatch** | Tools only. Live collection feeds → real products → resolved variants. |

Retrieval is **live on every request** — nothing is pre-downloaded and nothing is cached
to disk. Products come from Decathlon's 228 merchandised collections rather than keyword
search, which returns zero for the descriptive queries an LLM writes by default.

**Guardrails are Python, not prompt text.** A guardrail written in the prompt is a
suggestion; one written in code is a guarantee. Every check sits deterministically
between the model and the world and emits a trace event the judges can watch in the
audit rail. `create_cart` is not in the model's tool list at all — human-in-the-loop is
enforced by its *absence*, not by an instruction.

## Layout

```
concierge/
  app.py            Reflex app + theme          state.py   the single State
  walkthrough.py    the two-phase demo script
  agent/            loop · tools · prompts · classify · stubs
  commerce/         ucp.py (the ONLY caller of MCP) · catalog.py · cart.py
  domain/           models.py (strict by construction) · guardrails.py
  obs/              trace.py → audit rail + optional Logfire
  ui/               chat · product · cart · trace_panel · brand · theme · walkthrough
scripts/            doctor · e2e · spike_cart · tunnel.sh · walkthrough.sh · reload.sh
tests/              205 offline + live contract tests
fixtures/           dumped feeds for OFFLINE DEV ONLY — never read by the running app
```

## Documentation

| | |
|---|---|
| **[`AGENTS.md`](AGENTS.md)** | **Read this first.** Canonical instructions, and the load-bearing-facts registry — verified behaviour that *looks like bugs and is not*. "Fixing" any of it breaks the build. |
| [`SPEC.md`](SPEC.md) | Full technical specification. Cited by section number throughout the code (`SPEC.md §3.3`). |
| [`SPEC-SESSION-RECORD.md`](SPEC-SESSION-RECORD.md) | Conversation-intake & analytics spec. Deferred, not built. |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Demo day: bring-up order, the four judge checks, contingencies. |
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | State of the build. Resume from this file alone. |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Append-only architectural log. Never edit a past entry. |
| [`docs/research/`](docs/research/) | Pre-build research, archived for provenance. **Superseded where it conflicts with `AGENTS.md`** — each file says so at the top. |
| [`concierge/commerce/AGENTS.md`](concierge/commerce/AGENTS.md) | Scoped rules for the fragile surface. |

## Before changing anything

This codebase's most important facts look like mistakes. Responses are double-encoded;
`tools/list` always fails; prices are minor units from one source and decimal strings
from the other; a pydantic `HttpUrl` silently serializes to `null` through Reflex's wire
encoder. Each is load-bearing, each is written down in [`AGENTS.md`](AGENTS.md), and each
is pinned by `tests/test_contracts.py` with a failure message that points back at the
registry line.

If live behaviour really changed, update the registry and the test **together, in the
same commit**.
