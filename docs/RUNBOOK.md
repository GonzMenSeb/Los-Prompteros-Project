# RUNBOOK — demo day

Print this. Write the two tunnel URLs on it by hand.

## Preflight

```bash
make doctor      # python, .env, key valid, gemini-3.6-flash present, both endpoints reachable
make check       # offline suite
```

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

- **429 from MCP** → **do not touch the network or the tunnels.** Keep talking; the
  kit still renders from the storefront feeds, which are a separate surface and stay
  healthy. Retry the cart every ~30 s — access returns in ~4 minutes, `Retry-After`
  overstates it, and retrying does **not** extend the lockout. **Never sleep the
  advertised interval.**
- **MCP down entirely** → the live collection feeds still render the whole kit; only
  the cart link is lost. Say so and show the kit.
- **Frontend tunnel dies** → present from `localhost:3000` on the laptop screen.
- **Backend tunnel dies** → the local page is dead too, because `api_url` is now
  stale. Redo `make tunnel`, or run `reflex run` with `CONCIERGE_API_URL=http://localhost:8000`
  and present locally.
- **Total connectivity loss** → phone hotspot, then redo `make tunnel` because the
  tunnel URLs change.
- **Gemini down** → the demo is over. Keep a recorded run on disk.

## The opening and closing lines

Open on Decathlon's own `agents.md`: *"this retailer published instructions for
agents, so we built the agent it asked for."*

Close on a judge opening the cart link on their own phone.
