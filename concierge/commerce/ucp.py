"""The ONE wrapper around Decathlon's UCP/MCP endpoint.

NOTHING else in the codebase may call this endpoint. See concierge/commerce/AGENTS.md.

Load-bearing facts encoded here (SPEC.md §3.1) — these look like bugs and are not:
  * `tools/list` and `initialize` ALWAYS fail with -32001. Call tools by name.
    Do NOT add an MCP SDK. Do NOT add a handshake step.
  * The agent profile goes inside `arguments.meta`, not `params`, not a header.
  * Responses are DOUBLE-ENCODED: the real body is a JSON string inside
    result.content[0].text. json.loads() it a second time.
  * Schema errors arrive as `result.isError: true` with HTTP 200.
  * Prices from MCP are MINOR UNITS integers (5000 == $50.00).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from concierge.obs.trace import emit

EP = "https://www.decathlon.com/api/ucp/mcp"
PROF = "https://shopify.dev/ucp/agent-profiles/examples/2026-04-08/valid-with-capabilities.json"

# Clean at 40 concurrent from a rested bucket; 100 trips a ~48 MINUTE lockout.
SEM = asyncio.Semaphore(8)

# Once a 429 has been seen, every later call is serialised and spaced by this much
# for the rest of the process. Measured 25 Jul 2026: mid-lockout a burst of 3-4
# re-trips the limiter instantly, while a trickle ~1.5s apart is served normally.
# Pacing is the difference between a dead demo and a slow one. Never un-pace on a
# success — single calls succeed THROUGHOUT a lockout, so a success is not recovery.
PACE_SECONDS = 1.5

CONTEXT = {"address_country": "US", "currency": "USD"}

_client: httpx.AsyncClient | None = None
_paced = False
_pace_lock = asyncio.Lock()
_last_send = 0.0


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            headers={"Content-Type": "application/json"},
            timeout=httpx.Timeout(45.0),
            limits=httpx.Limits(max_connections=16),
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


class UcpRateLimited(Exception):
    """429 that survived a spaced retry. `Retry-After` is honest — it counts down in
    real time to a fixed unlock ~48 minutes out — so there is nothing useful to sleep
    for. Never poll to detect recovery either: a single call succeeds throughout the
    lockout, so a success proves the bucket holds one token and nothing more."""

    def __init__(self, retry_after: str | None = None):
        super().__init__(f"UCP rate limited (Retry-After: {retry_after})")
        self.retry_after = retry_after


class UcpToolError(Exception):
    """A JSON-RPC error, or an HTTP 200 carrying result.isError."""


def _engage_pacing() -> None:
    global _paced
    _paced = True


async def _send(payload: dict[str, Any]) -> httpx.Response:
    global _last_send
    if not _paced:
        async with SEM:
            return await client().post(EP, json=payload)

    # Serialised, not merely slowed: concurrency is what re-trips the limiter.
    async with _pace_lock:
        wait = PACE_SECONDS - (time.monotonic() - _last_send)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            return await client().post(EP, json=payload)
        finally:
            _last_send = time.monotonic()


async def call_ucp(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool,
            "arguments": {"meta": {"ucp-agent": {"profile": PROF}}, **args},
        },
    }

    r = await _send(payload)

    if r.status_code == 429:  # never sleep on Retry-After: it is ~48 minutes out
        first = not _paced
        _engage_pacing()
        emit(
            "ucp.rate_limited",
            {"tool": tool, "retry_after": r.headers.get("Retry-After"), "pacing_engaged": first},
            "error",
        )
        r = await _send(payload)  # spaced, and a trickle is served mid-lockout
        if r.status_code == 429:
            emit("ucp.rate_limited_paced", {"tool": tool, "retry_after": r.headers.get("Retry-After")}, "error")
            raise UcpRateLimited(r.headers.get("Retry-After"))
    r.raise_for_status()

    body = r.json()
    if "error" in body:
        emit("ucp.error", {"tool": tool, "error": body["error"]}, "error")
        raise UcpToolError(body["error"])

    content = body["result"]["content"][0]["text"]
    if body["result"].get("isError"):  # HTTP 200 + isError
        emit("ucp.error", {"tool": tool, "error": str(content)[:400]}, "error")
        raise UcpToolError(content)

    data = json.loads(content)  # second decode
    data.pop("ucp", None)  # strip the capability echo before it reaches the model
    emit("ucp.call", {"tool": tool, "keys": ",".join(sorted(data.keys()))})
    return data
