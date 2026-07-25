"""Reflex state for the Expedition Concierge.

Two things here are load-bearing and look like over-engineering:

  * `bind_sink()` is called BEFORE `asyncio.create_task()`. contextvars are
    copied at task-creation time, so that ordering is what routes the agent
    loop's `emit()` calls into this session's trace list rather than the
    process-wide ring buffer.
  * `confirm_cart` re-checks `awaiting_confirmation`. Conditional rendering is
    not a guard — the event is callable over the wire whatever is on screen.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import reflex as rx
from pydantic import BaseModel, Field

from concierge.domain.models import CartResult, KitItem, minor_to_display
from concierge.obs.trace import TraceEvent, bind_sink, emit
from concierge.ui import demo_data

# Live by default — the whole claim is that this transacts for real. Set
# CONCIERGE_FIXTURE_MODE=1 to fall back to the canned run if Gemini is down.
FIXTURE_MODE = os.environ.get("CONCIERGE_FIXTURE_MODE", "0") not in ("0", "false", "")

_STEP_DELAY = 0.25
_POLL_INTERVAL = 0.15


class Citation(BaseModel):
    title: str
    url: str


class ChatMessage(BaseModel):
    role: str
    content: str
    citations: list[Citation] = Field(default_factory=list)


class TraceRow(BaseModel):
    seq: int
    event: str
    level: str
    summary: str


class KitCard(BaseModel):
    """Render-ready view of a KitItem. `minor_to_display()` is a Python function
    and cannot be called on a Var inside a component, so prices are formatted
    here — backend-side — and the card renders strings it is handed."""

    slot_label: str
    product_title: str
    product_url: str
    image_url: str
    size_label: str
    quantity: int
    quantity_label: str
    price_display: str
    size_substituted: bool
    rationale: str


def to_card(item: KitItem) -> KitCard:
    return KitCard(
        slot_label=item.slot.replace("_", " ").upper(),
        product_title=item.product_title,
        product_url=item.product_url,
        image_url=item.image_url or "",  # KitItem.image_url is optional; "" -> placeholder
        size_label=item.size_label,
        quantity=item.quantity,
        quantity_label=(
            f"{item.quantity}  ({minor_to_display(item.price_minor * item.quantity)})"
            if item.quantity > 1
            else "1"
        ),
        price_display=minor_to_display(item.price_minor),
        size_substituted=item.size_substituted,
        rationale=item.rationale,
    )


def summarise(payload: dict[str, Any]) -> str:
    """Trace payloads come from four different lanes with arbitrary nesting.
    Flatten to one scalar line so the panel never has to walk an unknown shape."""
    if not payload:
        return ""
    parts = []
    for key, value in payload.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            text = str(value)
        else:
            text = json.dumps(value, default=str, ensure_ascii=False)
        parts.append(f"{key}={text[:120]}")
    return "  ".join(parts)[:300]


class State(rx.State):
    messages: list[ChatMessage] = []
    draft: str = ""

    kit_items: list[KitItem] = []
    unservable_slots: list[str] = []
    budget_minor: int | None = None

    trace: list[TraceRow] = []
    show_trace: bool = True

    cart_id: str = ""
    cart_url: str = ""
    cart_total_minor: int = 0
    cart_line_count: int = 0
    cart_expires_at: str = ""

    is_thinking: bool = False
    awaiting_confirmation: bool = False
    status: str = ""
    error: str = ""

    @rx.var
    def cards(self) -> list[KitCard]:
        return [to_card(i) for i in self.kit_items]

    @rx.var
    def total_minor(self) -> int:
        return sum(i.price_minor * i.quantity for i in self.kit_items)

    @rx.var
    def total_display(self) -> str:
        return minor_to_display(self.total_minor)

    @rx.var
    def item_count(self) -> int:
        return sum(i.quantity for i in self.kit_items)

    @rx.var
    def has_kit(self) -> bool:
        return len(self.kit_items) > 0

    @rx.var
    def has_budget(self) -> bool:
        return self.budget_minor is not None

    @rx.var
    def budget_display(self) -> str:
        return minor_to_display(self.budget_minor or 0)

    @rx.var
    def over_budget(self) -> bool:
        return self.budget_minor is not None and self.total_minor > self.budget_minor

    @rx.var
    def budget_delta_display(self) -> str:
        if self.budget_minor is None:
            return ""
        return minor_to_display(abs(self.total_minor - self.budget_minor))

    @rx.var
    def has_unservable(self) -> bool:
        return len(self.unservable_slots) > 0

    @rx.var
    def has_cart(self) -> bool:
        return self.cart_url != ""

    @rx.var
    def cart_total_display(self) -> str:
        return minor_to_display(self.cart_total_minor)

    @rx.var
    def substitution_count(self) -> int:
        return sum(1 for i in self.kit_items if i.size_substituted)

    def _drain(self, sink: list[TraceEvent]) -> bool:
        if not sink:
            return False
        for ev in sink:
            self.trace.append(
                TraceRow(
                    seq=ev.seq,
                    event=ev.event,
                    level=ev.level,
                    summary=summarise(ev.payload),
                )
            )
        sink.clear()
        return True

    def _apply_kit(self, kit) -> None:
        self.kit_items = list(kit.items)
        self.unservable_slots = list(kit.unservable_slots)
        self.budget_minor = kit.budget_minor

    def _apply_cart(self, cart: CartResult) -> None:
        self.cart_id = cart.cart_id
        self.cart_url = cart.continue_url
        self.cart_total_minor = cart.total_minor
        self.cart_line_count = cart.line_count
        self.cart_expires_at = cart.expires_at or ""

    def toggle_trace(self):
        self.show_trace = not self.show_trace

    def clear(self):
        self.messages = []
        self.kit_items = []
        self.unservable_slots = []
        self.budget_minor = None
        self.trace = []
        self.cart_id = ""
        self.cart_url = ""
        self.cart_total_minor = 0
        self.cart_line_count = 0
        self.cart_expires_at = ""
        self.is_thinking = False
        self.awaiting_confirmation = False
        self.status = ""
        self.error = ""
        self.draft = ""

    @rx.event
    async def send_message(self, form_data: dict[str, Any]):
        text = (form_data.get("message") or self.draft or "").strip()
        if not text or self.is_thinking:
            return

        self.draft = ""
        self.error = ""
        self.messages.append(ChatMessage(role="user", content=text))
        self.is_thinking = True
        self.status = "Reading the conditions…"
        self.trace = []
        self.awaiting_confirmation = False
        yield

        sink: list[TraceEvent] = []
        bind_sink(sink)
        try:
            if FIXTURE_MODE:
                async for _ in self._fixture_turn(sink):
                    yield
            else:
                async for _ in self._live_turn(sink, text):
                    yield
        except Exception as exc:
            emit("turn.error", {"error": repr(exc)}, level="error")
            self._drain(sink)
            self.error = f"{type(exc).__name__}: {exc}"
            self.messages.append(
                ChatMessage(
                    role="assistant",
                    content="That turn failed before I could finish a kit. The trace "
                    "panel has the last step that ran.",
                )
            )
        finally:
            bind_sink(None)
            self.is_thinking = False
            self.status = ""
        yield

    async def _fixture_turn(self, sink: list[TraceEvent]):
        for event, payload, level in demo_data.demo_trace():
            emit(event, payload, level)
            await asyncio.sleep(_STEP_DELAY)
            self._drain(sink)
            yield

        self._apply_kit(demo_data.demo_kit())
        self.messages.append(
            ChatMessage(
                role="assistant",
                content=demo_data.DEMO_MESSAGES[1][1],
                citations=[Citation(title=t, url=u) for t, u in demo_data.DEMO_CITATIONS],
            )
        )
        self.awaiting_confirmation = True
        yield

    async def _live_turn(self, sink: list[TraceEvent], text: str):
        # Imported inside the handler: the agent lane owns this module and it must
        # not be a module-scope import while the lanes build concurrently.
        from concierge.agent.loop import run_turn

        history = [(m.role, m.content) for m in self.messages[:-1]]
        task = asyncio.create_task(run_turn(text, history=history))

        while not task.done():
            await asyncio.sleep(_POLL_INTERVAL)
            if self._drain(sink):
                yield

        result = await task
        if self._drain(sink):
            yield

        kit = getattr(result, "kit", None)
        if kit is not None:
            self._apply_kit(kit)

        self.messages.append(
            ChatMessage(
                role="assistant",
                content=getattr(result, "reply", "") or "",
                citations=[
                    Citation(
                        title=getattr(c, "title", "") or str(c),
                        url=getattr(c, "url", "") or str(c),
                    )
                    for c in (getattr(result, "citations", None) or [])
                ],
            )
        )
        self.awaiting_confirmation = bool(self.kit_items) and bool(
            getattr(result, "awaiting_confirmation", True)
        )
        yield

    @rx.event
    async def confirm_cart(self):
        if not self.awaiting_confirmation or not self.kit_items or self.is_thinking:
            return

        self.awaiting_confirmation = False
        self.is_thinking = True
        self.status = "Creating the cart at Decathlon…"
        self.error = ""
        yield

        sink: list[TraceEvent] = []
        bind_sink(sink)
        try:
            emit(
                "human.confirmed",
                {"line_items": len(self.kit_items), "total_minor": self.total_minor},
                level="guardrail",
            )
            self._drain(sink)
            yield

            if FIXTURE_MODE:
                emit("ucp.create_cart", {"tool": "create_cart", "source": "fixture"})
                await asyncio.sleep(_STEP_DELAY * 2)
                cart = demo_data.demo_cart()
            else:
                from concierge.commerce.cart import create_cart

                cart = await create_cart(self.kit_items)

            self._apply_cart(cart)
            emit(
                "cart.created",
                {
                    "cart_id": cart.cart_id,
                    "line_count": cart.line_count,
                    "total_minor": cart.total_minor,
                    "continue_url": cart.continue_url,
                },
            )
            self._drain(sink)
        except Exception as exc:
            emit("cart.error", {"error": repr(exc)}, level="error")
            self._drain(sink)
            self.error = f"Cart creation failed — {type(exc).__name__}: {exc}"
            self.awaiting_confirmation = True
        finally:
            bind_sink(None)
            self.is_thinking = False
            self.status = ""
        yield
