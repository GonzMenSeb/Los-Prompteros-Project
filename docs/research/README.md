# Pre-build research — archived

Two self-contained HTML reports, written **before the build** on 24–25 Jul 2026. No
build step and no dependencies — open either in a browser (both adapt to light/dark
and carry a theme toggle).

| | |
|---|---|
| [`tech-assessment.html`](tech-assessment.html) | Feasibility. The UCP handshake solved, all ten MCP tools probed, the conversation flow mapped call by call, rate limits measured, and the four hazards found. |
| [`stack-spec.html`](stack-spec.html) | The decisions taken off that assessment, plus the collection-feed retrieval finding and the per-discipline catalog coverage survey. |

## These are provenance, not documentation

They are kept because they record **what was measured and why the stack was chosen** —
useful when someone asks "how do you know?". They are **not** a description of the
shipped system, and several of their claims were overturned during the build.

**Where these files and [`AGENTS.md`](../../AGENTS.md) disagree, `AGENTS.md` wins.** It
carries the load-bearing-facts registry, re-verified against live services and pinned by
`tests/test_contracts.py`. Each file states this in a banner at the top, along with the
specific claims that no longer hold.

The headline reversals, in case you only read this file:

- **Rate-limit recovery is ~48 minutes, not ~4**, `Retry-After` is honest, and a single
  successful call proves nothing because single calls succeed throughout a lockout.
- **The UI is Reflex**, not Streamlit.
- **Variant resolution runs off the storefront feed at zero MCP calls.** `create_cart`
  is the only MCP call in a demo run.
- **`previous_interaction_id` does not exist** on `generate_content`; history is
  threaded client-side.

Do not "correct" working code to match anything in this folder.
