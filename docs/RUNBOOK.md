# RUNBOOK — demo day

Print this. Write the two tunnel URLs on it by hand.

## Preflight

```bash
make doctor      # python, .env, key valid, gemini-3.6-flash present, both endpoints reachable
make check       # offline suite
make rehearse    # the scripted walkthrough, live, no browser — asserts every beat
```

## The scripted walkthrough

The pitch is two minutes; the demo gets about **thirty seconds on camera**. A real run
does not fit — turn one alone is **52 s** of Gemini latency — so the script has two
phases and you choose when the second one fires. Both are live.

```bash
make walkthrough                 # locally: fresh server, browser opened, script running
make walkthrough PHASE=onstage
```

**Run `1 · Prewarm the trip` while you are still on the problem statement.** ~3 min:
swim refusal, grounded research with citations, targeted questions, then a real kit —
10 items, photos, resolved sizes, running budget, substitutions disclosed, slots
honestly marked unservable. **Hit `2 · Go live` when the audience is looking.** ~25 s:
injection blocked with every price unmoved, then the real cart. Then open the link.

Prewarming is not cheating: the kit on screen was built live, in the same session,
minutes earlier. What happens on camera happens as they watch.

Under tunnels, use `make tunnel` (below) and click the buttons on the judge URL —
`make walkthrough` restarts the server and would invalidate the compiled `api_url`.

## Bring the demo up — ORDER IS CRITICAL

`api_url` is compiled **into** the frontend bundle, and quick-tunnel URLs are
random per restart. Wrong order gives a page that renders perfectly and does
nothing at all.

```bash
make tunnel      # backend tunnel -> reflex run (compiled against it) -> frontend tunnel
```

It prints the **judge URL**. Then:

> **PROVE IT FROM A PHONE, NOT THE BUILD LAPTOP.**
> Open the judge URL and send one message. A reply is the only positive proof
> the WebSocket reached the tunnelled backend. Silence means `api_url` is stale.

Bring both tunnels up **once, early**, and leave them running.

### The hosted instance is the fallback, and the link that outlives the day

**https://decabot.web.vespiridion.org** — same app, permanent URL, one shared password
(`vault_decabot_password` in `vps-infrastructure/vault.yml`). It does not move when a
tunnel restarts, so it is what a judge or a recruiter can open next week.

Tunnels stay the demo-day primary: no VPS in the path, no DNS, and no password to read
out on camera. Use the hosted URL if the tunnels will not come up, and hand it out
afterwards either way. Full detail in [`DEPLOY.md`](DEPLOY.md).

| | URL |
|---|---|
| Backend (`:8000`) | ________________________________ |
| Frontend — **judge link** (`:3000`) | ________________________________ |

## The four judge checks — rehearse these out loud, twice

1. **Open the cart link.** The final message carries a live `decathlon.com` cart
   URL. The judge opens it on their own device and sees the same items, sizes and
   prices. *Proves the transaction is real.*
2. **Click a product through to its page.** Price and size options match what the
   agent showed, because both came from the same live call. *Proves catalog grounding.*
3. **Demand an out-of-stock size.** The agent must refuse and offer the nearest
   in-stock size **while saying it substituted**. *The single best adversarial test.*
4. **Impose an absurd budget** — *"kit us both out for $40."* It must report that
   nothing fits rather than inventing a $12 tent. *Proves it is retrieving, not generating.*

Two more to welcome: **ask for swimming gear** (declines honestly, naming the
towels as all that exists) and **attempt prompt injection** (`injection` appears
in the trace panel, the agent carries on unbothered).

## Contingencies

- **429 from MCP** → **do not touch the network or the tunnels, and do not stall
  waiting for it to clear — a lockout is ~48 minutes, not ~4** (re-measured 25 Jul;
  the old 4-minute figure was wrong). `ucp.py` latches into paced mode on the first
  `429` and retries once, spaced, and **spaced calls are served mid-lockout** — so
  keep going and narrate that it is deliberately slowing itself down. Retrying does
  **not** extend the lockout. Never sleep `Retry-After`, and never treat one
  successful call as proof it cleared: single calls succeed throughout.
- **MCP down entirely** → the live collection feeds still render the whole kit; only
  the cart link is lost. Say so and show the kit.
- **Frontend tunnel dies** → present from `localhost:3000` on the laptop screen.
- **Backend tunnel dies** → the local page is dead too, because `api_url` is now
  stale. Redo `make tunnel`, or run `reflex run` with `CONCIERGE_API_URL=http://localhost:8000`
  and present locally.
- **Total connectivity loss** → phone hotspot, then redo `make tunnel` because the
  tunnel URLs change.
- **Gemini `429 RESOURCE_EXHAUSTED` ("quota exhausted")** → the *key quota*, not the MCP
  limit and not a bug. Symptom: `lane=public` turns 429 while the swim-refusal turn still
  passes (it only spends the cheap gate call). **Stop resending** — each turn's 3 retries burn
  ~3× the quota. The fix is billing, not waiting: keep the demo laptop's `GEMINI_API_KEY` on a
  billed project with prepay credit ([aistudio.google.com/billing](https://aistudio.google.com/billing)
  → Buy credits, US$10 min, minutes to land). Postpay is Tier-3-gated and disabled — prepay only.
- **Gemini down** → the demo is over. Keep a recorded run on disk.

## The opening and closing lines

Open on Decathlon's own `agents.md`: *"this retailer published instructions for
agents, so we built the agent it asked for."*

Close on a judge opening the cart link on their own phone.
