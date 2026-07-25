"""Structured trace events -> UI panel + Logfire.

THE signature everything else calls:

    emit(event: str, payload: dict | None = None, level: str = "info") -> TraceEvent

`level` is one of "info" | "guardrail" | "error". Guardrail verdicts MUST use
level="guardrail" — the trace panel renders those distinctly and they are the
demonstrable artifact the Technical Checklist asks for.

Events are collected into the sink bound by `bind_sink()` if one is active
(Reflex binds a per-session list at the top of each event handler), otherwise
into a process-wide ring buffer so scripts and tests can read them too.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from itertools import count
from typing import Any, Literal

Level = Literal["info", "guardrail", "error"]

# Logfire is OPTIONAL. A missing token must never block startup, and an
# observability layer that can take down the app it observes is worse than none.
try:  # pragma: no cover - environment dependent
    import logfire

    logfire.configure(send_to_logfire="if-token-present", console=False)
    logfire.instrument_httpx()  # needs the logfire[httpx] extra
except Exception:  # pragma: no cover
    logfire = None


@dataclass
class TraceEvent:
    seq: int
    ts: float
    event: str
    payload: dict[str, Any] = field(default_factory=dict)
    level: Level = "info"

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "event": self.event,
            "payload": self.payload,
            "level": self.level,
        }


_seq = count(1)
_GLOBAL: list[TraceEvent] = []
_MAX_GLOBAL = 500
_sink: ContextVar[list[TraceEvent] | None] = ContextVar("trace_sink", default=None)


def bind_sink(sink: list[TraceEvent] | None) -> None:
    """Route subsequent emits into `sink`. Reflex calls this per event handler."""
    _sink.set(sink)


def emit(event: str, payload: dict[str, Any] | None = None, level: Level = "info") -> TraceEvent:
    ev = TraceEvent(seq=next(_seq), ts=time.time(), event=event, payload=payload or {}, level=level)

    sink = _sink.get()
    if sink is not None:
        sink.append(ev)

    _GLOBAL.append(ev)
    if len(_GLOBAL) > _MAX_GLOBAL:
        del _GLOBAL[:-_MAX_GLOBAL]

    if logfire is not None:  # pragma: no cover
        try:
            logfire.info("trace.{event}", event=event, level=level, **_flat(ev.payload))
        except Exception:
            pass
    return ev


def _flat(payload: dict[str, Any]) -> dict[str, Any]:
    """Logfire attributes must be scalar-ish; stringify anything exotic."""
    out: dict[str, Any] = {}
    for k, v in payload.items():
        out[k] = v if isinstance(v, (str, int, float, bool, type(None))) else repr(v)[:400]
    return out


def recent(limit: int = 200) -> list[TraceEvent]:
    return _GLOBAL[-limit:]


def reset() -> None:
    _GLOBAL.clear()
