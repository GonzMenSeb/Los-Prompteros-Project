# AGENTS.md — Expedition Concierge

Canonical instructions for any AI assistant working in this repo.
Team: **Los Prompteros** · AgentSprint, Universidad EAFIT, Medellín.

## What this is

A conversational agent that turns a described sporting expedition into a **real,
size-resolved, in-stock Decathlon shopping cart**. The user describes an activity
in natural language; the agent researches the real conditions on the web, asks a
short set of targeted questions, derives the gear the trip actually requires,
retrieves real products from Decathlon's live catalog, resolves each to an
in-stock size, presents them with photos and a running budget, and — **only on an
explicit human click** — creates a real Decathlon cart and hands over a live link.

The flow **ends at the cart**. We never automate payment. That is both the honest
stopping point and the one Decathlon's own `agents.md` prescribes.

## Load-bearing facts — the "do not fix these" registry

Every line below was executed against the live services on **24–25 Jul 2026**.
**These look like bugs and are not.** Anything here that gets "corrected" breaks
the build. If live behaviour really changed, update this registry and
`tests/test_contracts.py` **together**, in the same commit.

### UCP / MCP  (`concierge/commerce/ucp.py`)

- Endpoint `POST https://www.decathlon.com/api/ucp/mcp`, `Content-Type: application/json`.
  No auth, no key, no OAuth.
- **`tools/list` and `initialize` ALWAYS fail** with `-32001 UCP discovery failed`.
  Call tools directly by name. **Do not add an MCP SDK. Do not add a handshake step.**
  An off-the-shelf MCP client cannot connect to this endpoint.
- **The agent profile goes inside `arguments.meta`** — not `params`, not an HTTP header:
  `arguments.meta["ucp-agent"].profile = "https://shopify.dev/ucp/agent-profiles/examples/2026-04-08/valid-with-capabilities.json"`.
  This is Shopify's public example profile: a **public capability declaration, not a
  credential**. There is no secret in it. The server really fetches it, so it must be
  publicly reachable — `localhost` will never work.
- **Cart lines are `cart.line_items[].item.id`** — not `merchandise_id`, not a bare id.
- **MCP prices are MINOR UNITS.** A variant price is a nested object
  `{"amount": 10000, "currency": "USD"}` → `10000` means `$100.00`.
  Cart `totals` is a **list**: `[{"type":"subtotal","amount":…},{"type":"total","amount":…}]`.
- **Responses are double-encoded.** The real body is a JSON *string* inside
  `result.content[0].text` — `json.loads()` it a second time. Every response also
  echoes a large `ucp` capability block; strip it before it reaches the model.
- **Schema errors arrive as `result.isError: true` with HTTP 200**, not as JSON-RPC
  errors. Naive error handling treats a rejected call as success.
- **`get_product` with no `selected` returns `available: null` for every option value.**
  You must pass a **non-empty partial** selection (e.g. the Color) to get a usable
  availability grid, then a **full** selection to obtain the variant GID.
- Open with no auth: `search_catalog`, `lookup_catalog`, `get_product`, `create_cart`,
  `get_cart`, `update_cart`, `create_checkout`, `update_checkout`.
  JWT-gated and out of scope: `complete_checkout`, `get_order`.
- **The US store will not ship to Colombia.** `create_checkout` with
  `address_country: "CO"` returns `delivery_no_delivery_available_for_merchandise_line`.
  `decathlon.com.co` is a different site: 403, no `agents.md`, no `.well-known/ucp`.
  The agent-commerce layer exists **only** on the US store, in USD.
- `continue_url` comes back on `decathlon-usa.myshopify.com` and **301-redirects** to
  `https://www.decathlon.com/cart/c/<token>?key=<key>`. This is the demo's proof.

### Rate limits

Re-measured **25 Jul 2026**, and the numbers moved. `SPEC.md §3.2` and
`tests/test_contracts.py` carry the same corrected figures — the first probe's
"~4 minutes" was wrong.

- Clean at **20 sequential** and **40 concurrent** (~0.5 s each) from a rested bucket.
- **100 concurrent trips it**: 85 % return `429`.
- **Recovery is ~48 MINUTES, not ~4.** Plan the demo around 48. A trip is expensive
  enough that the rate-limit contract tests deliberately never induce one.
- **`Retry-After` is honest.** It counts down in real time to a fixed unlock instant.
  It does not overstate recovery — that earlier claim was an artifact of believing
  recovery took 4 minutes. There is still nothing to sleep for: 48 minutes.
- **A single call succeeds throughout the lockout**, so a one-call poll proves only
  that the bucket holds one token — **it is not a readiness signal.** Never use one
  to decide the lockout has cleared.
- Mid-lockout a **burst of 3–4 re-trips it instantly**; a **trickle ~1.5 s apart is
  served normally.** `ucp.py` therefore latches into paced mode on the first `429`
  (serialised, `PACE_SECONDS` apart) and **never un-latches on a success** — a
  success is not recovery. One spaced retry happens inside `call_ucp`, so
  `UcpRateLimited` means *even a trickle was refused*.
- Retrying during lockout does **not** extend it.
- The **storefront JSON endpoints are a separate surface** and stay healthy through
  an MCP lockout. They carry the catalog and stock flags, but **not variant GIDs the
  cart accepts** — `resolve_variant` needs MCP `get_product`, so a lockout degrades
  the kit to trickle speed rather than leaving it untouched.
- **The storefront has its own limiter, and it is not MCP's.** Observed **28 Jul
  2026**: `GET /collections.json?limit=250` returned **429 with no MCP lockout in
  play**, and it killed the turn — `get_taxonomy` called `raise_for_status()` naked,
  so `profile.built` was followed straight by `turn.error`.
- **When the storefront does 429 it says `Retry-After: 60`, and that 60 is not a
  recovery time.** Measured 28 Jul: a pooled client kept getting 429 with that same
  header after 75 s — and after 25 minutes — of complete quiet. Never sleep it and
  never treat it as a countdown. `catalog._get` backs off on a budget we chose
  instead — ≤`MAX_ATTEMPTS`, `RETRY_BUDGET_SECONDS` **total** per request,
  exponential with jitter — and a hint longer than that budget is **reported, never
  slept**, which at 60 s means one attempt then degrade. The ladder runs only when no
  hint is sent. **All of this is now the unhappy path, not the normal one** (see the
  connection-reuse entry below): unpooled, we are not being limited at all.
- **It is a rate limiter, NOT a block, and we are inside Decathlon's stated rules.**
  The 429 body is the 18-byte `text/plain` string **`local_rate_limited`**, with
  `Retry-After: 60` and **no `cf-mitigated` header** — no challenge, no 403, no WAF
  page. Their own `/agents.md` explicitly lists `GET /collections/{handle}/products.json`
  under "Read-Only Browsing (No Authentication Required)" and instructs agents to
  *"Respect rate limits… Back off on 429 responses"*, which is exactly what
  `catalog._get` now does. `robots.txt` is `User-agent: * / Allow: /`; its only
  `Disallow`s are faceted-navigation patterns (`sort_by`, `filter`, `+`) that we never
  request. **Nobody is banning us — do not go looking for a way around a block, there
  isn't one to route around.** Note their agents.md scopes its per-IP claim to the
  *MCP* endpoint; the storefront limiter is undocumented, which matches it not being
  IP-keyed here.
- **THE STOREFRONT REFUSES REUSED CONNECTIONS. This is the whole finding.**
  Measured 28 Jul 2026, the same 24-feed burst at 6 concurrent, minutes apart from
  one machine and one IP:

  | client | connections | result |
  |---|---|---|
  | `urllib` | fresh per request | **24/24 OK**, 9.3 req/s |
  | `requests`, no Session | fresh per request | **24/24 OK**, 11.4 req/s |
  | `requests`, shared `Session` | pooled keep-alive | **4/24 OK**, 6.4 req/s |
  | `httpx` (pools by design) | pooled | **always 429**, even idle and single-shot |

  It is **faster unpooled and clean, slower pooled and refused** — so it is neither
  a rate limit nor the HTTP library. Two consecutive full turns through
  `requests`-with-no-Session: 24/24 feeds, 92 products, 3.2 s each, zero 429s.
  **`catalog.client()` therefore returns the `requests` MODULE, not a Session, and
  `_send` opens one connection per request.** The TLS handshake per request is what
  makes the feed work at all; it costs ~2 s across a whole turn. Do not "optimise"
  it into a Session — that does not speed the feed up, it stops it working.
- **`ucp.py` stays on `httpx`.** The MCP endpoint is a separate limiter and is
  unaffected — `get_product` verified working the same hour the storefront was
  refusing every pooled request. Two clients in `commerce/` is deliberate, and
  `trace.py` instruments both.
- **Residual unknown:** a single `httpx.get()` from a rested state is refused too,
  which connection *reuse* alone does not explain — that request has nothing to
  reuse. So the mechanism is not fully nailed; what is nailed, and reproducible, is
  the fix. A JA3/JA4 capture is still the way to close it out, and it is no longer
  on the critical path.
- **Earlier readings of this that are now SUPERSEDED** — do not resurrect them from
  git history: "recovery is unmeasured", "a penalty box our own bursts earned",
  "httpx is fingerprinted and singled out", and the storefront limiting on rate.
  Each was consistent with the evidence available at the time and each is wrong.

### Catalog & retrieval  (`concierge/commerce/catalog.py`)

- **Retrieval is live. NEVER cache the catalog to disk** — a local copy reads as
  mocked, which defeats the entire premise. `fixtures/` is for offline development
  only and is never read by the running app.
- `GET /collections.json?limit=250` → **228 collections**, ~0.8 s. Slimmed to
  handle+title it fits in a prompt.
- `GET /collections/{handle}/products.json?limit=N` → `title`, `handle`,
  `product_type`, `vendor`, `images[]`, and `variants[]` with `id`, size `title`,
  `price` and `available`.
- **The storefront feed's `price` is a decimal STRING in MAJOR units (`"50.00"`)**,
  whereas MCP returns a **minor-units integer** (`5000`). Two sources, two
  representations — convert at the boundary and store minor units internally.
  Getting this wrong is the easiest way to break the cart.
- **The collection feed's `available` is trustworthy** — cross-checked against MCP
  `get_product`, exact agreement. The storewide `/products.json` returns
  `available: null`; only the **collection-scoped** feed carries it.
- **Collection handles must be validated against a live `collections.json`.** The
  model hallucinates them — observed: it invented `rain-shells`; the real handle is
  `apparel-for-the-rain`.
- **A collection can exist and be empty.** `bike-helmet` is real and returns zero
  products. Empty result → slot marked **unservable**, never silently dropped.
- **Keyword search returns zero for descriptive queries.** `"sleeping bag"` → 3
  products; `"sleeping bag 0 degrees celsius"` → **0**. Keyword fallback must use
  1–3 word noun phrases; conditions and specifications belong in the *selection*
  step, never in the query.
- **The feed's numeric variant id IS the MCP variant GID.** Verified in both dumped
  fixtures: the feed's `41919445434430` / `"Dark Cinnamon / 6.5"` is `get_product`'s
  `gid://shopify/ProductVariant/41919445434430` / `"Dark Cinnamon / 6.5"`. Pinned by
  `test_the_feed_variant_id_is_the_mcp_variant_gid` — **if that test ever fails,
  feed-first resolution is invalid and must revert to the grid walk.**
- **`resolve_variant` therefore resolves off the feed at ZERO MCP calls.** The feed
  already carries every variant's id, title, price and a trustworthy stock flag, so
  the three-call grid walk bought nothing and cost the demo: 3 calls × 8 slots is a
  ~24-request burst, and **that is what tripped the rate limiter on 25 Jul.**
  `_resolve_via_mcp` is kept for a product the feed hands over with no variants at
  all, because it is the path proven against live `available: null` behaviour.
  **`create_cart` is now the only MCP call in a demo run.**
- **Sizes arrive phrased the way the customer said them** — `"US 10.5"`, `"men's L"`,
  `"size 8"` — while feed labels are bare (`"10.5"`, `"L"`). `_clean_request` strips
  that noise before matching. Without it nothing matched and `_choose_size` fell
  through to its last resort, "first available, flagged as a substitution": observed
  live on 25 Jul handing a **US 10.5 request a 6.5 while 10.5 was in stock**, and
  flagging in-stock exact matches as substitutions. Numbers are extracted from
  anywhere in the *request* (`_num_in`) but a *label* counts as numeric only when it
  is nothing but a number (`_num`) — otherwise `"Dark Cinnamon / 6.5"` reads as 6.5.
- **A feed variant `title` is the option values joined by `" / "`** in `option_names`
  order — but **an option VALUE may itself contain a slash.** The MT500 bag has two
  options and three parts: `"Smoked Black / M / 5'2\"–5'5\""`. Positional splitting is
  trusted **only when part count equals option count**; otherwise match the whole
  title. Slicing blindly matches a size request against a height range.

### Gemini  (`concierge/agent/`)

- Model `gemini-3.6-flash`.
- **`tools=` must be a list of `types.Tool`.** A bare list of `FunctionDeclaration`
  raises `AttributeError: 'FunctionDeclaration' object has no attribute
  'function_declarations'` *before* any HTTP call. Wrap:
  `tools=[types.Tool(function_declarations=[...])]`.
- **`grounding_metadata` is Optional and is `None`** when the model answers without
  searching. `gm.grounding_chunks` on a `None` raises `AttributeError`. Guard it.
- **Search never shares a request with anything else.** Built-in + custom tools in
  one request requires `tool_config.include_server_side_tool_invocations=True` or you
  get `400 INVALID_ARGUMENT` — and even then `grounding_metadata` comes back empty
  and search lands as opaque `tool_call` / `tool_response` parts.
  **This is why the pipeline is phased. Do not merge search into the tool loop.**
- **`previous_interaction_id` does not exist** on `client.models.generate_content` —
  its parameters are `model`, `contents`, `config` only. History is threaded
  client-side as a `list[types.Content]`.
- `response_schema=<PydanticModel>` with `response_mime_type="application/json"`
  works and returns a typed instance on `response.parsed`, nested models included.
  Verified directly against `ActivityProfile` — no intermediate wire schema needed.

### Reflex & serving  (`rxconfig.py`, `concierge/app.py`)

- **`rx.Base` does not exist in Reflex 0.9.7.** Use a plain Pydantic v2 `BaseModel`;
  it works as a state var and `rx.foreach` + attribute access works on it.
- **A pydantic `HttpUrl` field silently serializes to `null`** over Reflex's wire
  encoder — no error, just an empty image and a dead link. `domain/models.py` defines
  `Url = Annotated[str, AfterValidator(...)]`: validated as a URL, **stored as a
  `str`**. Never put a raw `HttpUrl` in anything that reaches the UI.
- **`app_module_import="concierge.app"`.** Reflex otherwise resolves the app module
  as `app_name + "." + app_name` → `concierge.concierge` → `ModuleNotFoundError`.
- **`vite_allowed_hosts=True`.** It defaults to `False`, which allows localhost only,
  and a quick-tunnel URL then returns `403 Blocked request. This host is not
  allowed.` **This is the demo-killer; it is not optional.**
- **`api_url` is compiled INTO the frontend bundle.** Change it → recompile. Restart
  the backend tunnel → new random URL → recompile. Symptom of getting this wrong:
  a page that renders perfectly and does nothing at all.
- Reflex needs **two** ports — frontend `3000`, backend `8000` — and the browser must
  reach the backend directly over WebSocket, so **both must be publicly tunnelled**.
  **Pin the ports**, or Reflex's "next available port if taken" behaviour silently
  moves the frontend and desyncs the tunnel.
- `cors_allowed_origins` defaults to `("*",)`, so CORS needs no work.
- **`rx.set_clipboard` fires on the websocket RESPONSE — outside the click's user
  activation — and reports nothing back.** Chromium usually allows it because it
  auto-grants `clipboard-write` to the focused tab; Firefox and Safari raise
  `NotAllowedError`, and either way there is no success signal, so a "Copied ✓" badge
  driven by it is a claim rather than evidence. `copy_run` therefore uses
  `rx.run_script(js, callback=State.copy_finished)`: the compiled frontend **awaits the
  promise** before invoking the callback (`.web/utils/state.js`), so the badge reports
  what the write actually returned. **Do not "simplify" this back to `set_clipboard`** —
  it silently reintroduces a green tick over a failed copy.
- **Reflex hands state containers back wrapped in `MutableProxy` (a `wrapt.ObjectProxy`),
  and `json.dumps` does not see through it.** `isinstance(proxy, dict)` is True, but the
  encoder's exact type check misses the proxy and falls through to `default=`, so every
  payload serialises as a **Python repr inside a JSON string** — `"{'turn': 1}"` instead
  of `{"turn": 1}`. `state.plain()` rebuilds real containers before anything is dumped.
  This is invisible to handler tests that only assert substrings, and was caught only by
  pasting a real bundle out of a browser.

### Container deployment  (`Dockerfile`, hosted at `decabot.web.vespiridion.org`)

Executed against the live host on **28 Jul 2026**. The Reflex/serving entries above
describe `reflex run` in DEV and remain correct there — **everything here is about
`--env prod`, where the port and `api_url` rules genuinely differ.** Neither section
overrides the other; check which mode you are in first.

- **PROD IS ONE PORT.** `_run` errors with *"In production, frontend and backend must run
  on the same port"* if they differ, and `_run_prod` mounts the compiled frontend onto the
  backend's own ASGI app. So `8000` serves the page **and** `/_event`. The
  "Reflex needs two ports … both must be publicly tunnelled" entry above is a **dev/tunnel**
  fact. `--single-port` exists as a CLI flag and is **never forwarded to `_run`** — it is a
  no-op in 0.9.7; prod is already single-port.
- **`api_url` must stay `http://localhost:8000` in the image.** `state.js`
  `getBackendURL()` rewrites any `SAME_DOMAIN_HOSTNAMES` host — `localhost`, `0.0.0.0`,
  `::` — to `window.location.hostname`, upgrades `ws:`→`wss:` and **clears the port** when
  the page is https. Baking the real hostname in would need one image per domain and buys
  nothing. **This is why the image is domain-agnostic. Do not "fix" it to the public URL.**
- **`REFLEX_SKIP_COMPILE` and `REFLEX_MOUNT_FRONTEND_COMPILED_APP` are declared
  `internal=True`, which prefixes the real env var with `__`.** `__REFLEX_SKIP_COMPILE`,
  `__REFLEX_MOUNT_FRONTEND_COMPILED_APP`. Without the underscores they are silently ignored.
- **`.web/backend/stateful_pages.json` must be copied into the runtime image.**
  `compile_app()` takes a no-write fast path only when that marker already exists;
  otherwise a skip-compile boot still tries to *create* `.web/backend` and dies with
  `PermissionError` as the non-root user. `[]` is the correct content for this app.
- Static frontend lives at **`.web/build/client`** (`Dirs.STATIC = build/client`).
- **`reflex.lock/` is committed, and must stay committed.** The `Dockerfile` does
  `COPY reflex.lock/ ./reflex.lock/` and `.dockerignore` explicitly un-ignores it, so a
  clean clone that lacks it cannot build the image — `failed to compute cache key:
  "/reflex.lock": not found`. It was in `.gitignore` until 29 Jul, which nobody noticed
  because every manual build ran from a working tree that already had it; the first CI
  build from a fresh clone failed instantly. It is `bun.lock` + `package.json`, the
  frontend dependency pin — a lockfile, which belongs in git anyway.
- **Granian, not uvicorn.** Reflex ships granian and no uvicorn/gunicorn, so
  `should_use_granian()` is what its own prod path takes. `get_num_workers()` returns
  **1** without Redis — which is what keeps `_SESSIONS` and the `_public_gate` semaphore
  (both process-local) correct. **Do not add Redis or raise the worker count** without
  moving those out of module scope.
- `state_manager_mode` is **DISK**, so `./.states` must be writable by the container user.
- **Zot rejects Docker v2 manifests with `415`.** It accepts OCI only, so a plain
  `docker push` fails at the manifest step with `manifest invalid` *after* every layer
  uploads successfully. Push with
  `docker buildx build --provenance=false --sbom=false --output type=image,oci-mediatypes=true,push=true`.
- **A WebSocket probe must force `--http1.1`.** Traefik negotiates h2 with curl, and
  `Connection: Upgrade` is an HTTP/1.1 mechanism, so over h2 granian answers
  `400 Invalid websocket upgrade` on a completely healthy app.

## Module boundaries — enforced socially, and worth it

- **Nothing calls the MCP endpoint except `concierge/commerce/ucp.py`.**
- **Nothing constructs a cart line except `concierge/commerce/cart.py`.**
- **`create_cart` is never exposed as a model tool.** Human-in-the-loop is enforced
  by its *absence* from the tool list, not by a prompt instruction. Only a user
  click may create a cart.

Two files to debug when the demo misbehaves instead of six.

## Guardrail principle

**A guardrail written in the prompt is a suggestion; a guardrail written in Python
is a guarantee.** Every check is deterministic code between the model and the world,
and every one emits a trace event at `level="guardrail"`.

`KitItem.available: Literal[True]` means an out-of-stock item cannot be represented
in a `Kit` at all — the stock guardrail is enforced by the type system rather than by
a check somebody might forget. Every optional field carries an explicit default,
because in Pydantic v2 `X | None` without a default is a *required* field that
happens to accept `None`.

**Attribute invention is the likeliest way to be embarrassed live.** The agent will
not invent *products* — retrieval prevents that. It will invent *properties* of real
products: "rated to −5 °C", "fully seam-sealed", "60 litres". The JSON says none of
that. The structural fix is to render specs from data and let prose carry only
reasoning.

## Conventions

- **Comments: absolutely minimal.** Only where a fact is genuinely counterintuitive.
  No docstring on every function; no comment restating the code.
- **Never guess an API or a payload shape.** Read the fixture, run the call, or read
  the library source. Unfounded assumptions are the one unforgivable sin here.
- Python 3.12, `from __future__ import annotations`, type-annotated.
- Run everything as `PYTHONPATH=. ./.venv/bin/python …`.

## Maintenance contract

| If you change… | You must also update… |
|---|---|
| `commerce/ucp.py` | this facts registry + `tests/test_contracts.py` |
| any tool schema | `agent/tools.py`, the system prompt, and the trace event names |
| a rate-limit trace event NAME | `state.py`'s `_THROTTLE_STATUS` — the throttled loading message is keyed by event string, so a rename silently strips it. Pinned by `test_it_keys_on_events_that_are_actually_emitted`. |
| a guardrail | the guardrail table + its test + the trace event |
| `rxconfig.py` | recompile the frontend; note the new URL in `docs/RUNBOOK.md` |
| the build's state | tick it off in `docs/HANDOFF.md` — another agent resumes from there |
| an architectural choice | append to `docs/DECISIONS.md` — never edit a past entry |
| `Dockerfile` or anything the container reads | nothing — merging to `main` rebuilds, re-pushes and redeploys. `docs/DEPLOY.md` covers the by-hand path and the Jenkins job |
| the touched-path gate in `infra/jenkins/Jenkinsfile` | `docs/DEPLOY.md` § Ship a change — it lists which paths ship and which do not |

**PR checklist:** facts registry still accurate · `make check` green · `make verify`
green if `commerce/` changed · `DECISIONS.md` appended if architectural.

## Where the documentation lives

| | |
|---|---|
| [`SPEC.md`](SPEC.md) | Full technical specification. Cited by section number throughout the code. |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Demo-day sequence and contingencies. |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | The hosted instance: how to ship a change, rotate the password, verify. |
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | State of the build — resume from this file alone. |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Append-only architectural log. |
| [`docs/research/`](docs/research/) | **Archived pre-build research. Outranked by this file.** |

`docs/research/` is provenance, not documentation. It records what was measured before
the build, and several of its claims were overturned during it — rate-limit recovery,
the UI framework, the retrieval path, `previous_interaction_id`. **Where it and this
file disagree, this file wins.** Never "correct" working code to match it.
