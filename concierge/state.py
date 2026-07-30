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
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import reflex as rx
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# MUST run before the module-level env reads below. `agent/classify.py` also loads it,
# but that module is imported lazily inside the event handler, so at the time this
# module is imported nothing has read `.env` yet — every constant below would silently
# take its default. That is how CONCIERGE_VIP_TOKEN read as "" and the presenting
# laptop was served on the public key. Absolute path: a bare load_dotenv() resolves
# relative to the caller and finds nothing when Reflex imports us.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from concierge import walkthrough
from concierge.domain.guardrails import check_size_confirmation
from concierge.domain.models import CartResult, KitItem, minor_to_display
from concierge.obs import bundle
from concierge.obs.trace import TraceEvent, bind_sink, emit
from concierge.ui import demo_data

# Live by default — the whole claim is that this transacts for real. Set
# CONCIERGE_FIXTURE_MODE=1 to fall back to the canned run if Gemini is down.
FIXTURE_MODE = os.environ.get("CONCIERGE_FIXTURE_MODE", "0") not in ("0", "false", "")

_STEP_DELAY = 0.25
_POLL_INTERVAL = 0.15

# A backoff is the one wait the user must not read as the app hanging: catalog._get
# can sit on a retry for seconds, and "Reading the conditions…" under a spinner is a
# lie about what is happening. Driven off the trace rather than threaded back through
# run_turn, because the trace is already drained into the UI mid-turn and this needs
# to land WHILE the turn is still running.
#
# Two levels, both honest, and neither quotes a wait: still trying, and gave up on
# that request and carried on. No storefront figure is worth standing behind — its
# Retry-After says 60 s and does not honour it — and MCP's is ~48 minutes.
_RETRYING = "Decathlon is rate-limiting me — easing off and trying again…"
_DEGRADED = "Decathlon is still rate-limiting me — carrying on with what I could read…"
# Gemini backs off too, and it is the slower of the two: three 503 retries in one
# observed run cost ~30 s, ~10 s and ~18 s of silence, because `model.retry` was in
# neither map. Its own wording — the other two blame Decathlon, which had nothing to
# do with it. No figure quoted: _BACKOFF is 1/3/7 s per attempt and the real waits
# were far longer, so either number would be a lie.
_MODEL_BUSY = "The model is busy — waiting and trying again…"

# Not Decathlon-only: `model.retry` comes from concierge/agent/classify.py.
_THROTTLE_STATUS = {
    "catalog.rate_limited": _RETRYING,
    "catalog.retry": _RETRYING,
    "ucp.rate_limited": _RETRYING,
    "model.retry": _MODEL_BUSY,
    "catalog.unavailable": _DEGRADED,
    "catalog.taxonomy_stale": _DEGRADED,
    "ucp.rate_limited_paced": _DEGRADED,
    "guardrail.collection_unchecked": _DEGRADED,
}

# Turn one is ~52 s of Gemini latency (DECISIONS, 25 Jul). "Reading the conditions…"
# was set once and then never moved, so a first-time user watched a frozen caption
# under a spinner for a minute and had no way to tell working from hung. The audit
# rail was already telling the truth beside it — someone who has never seen this
# product is not reading a log to find out whether it is alive.
#
# Same mechanism as the throttle map above: driven off the drained trace, so it lands
# WHILE the turn is running. A throttle message outranks these — it is the more
# important thing to be saying.
#
# Keyed on what the LIVE pipeline emits. The first cut of this table was keyed on the
# fixture trace's vocabulary instead, so six of nine never fired outside fixture mode
# and the caption still froze through retrieval and sizing — the longest stretch of
# the turn, and the whole point. `test_it_keys_on_events_that_are_actually_emitted`
# now covers this map too.
_STAGE_STATUS = {
    "gate.verdict": "Working out what you're asking for…",
    "research.grounded": "Researching the real conditions…",
    "profile.built": "Reading the forecast and the terrain…",
    "slots.derived": "Working out what the trip demands…",
    "catalog.collection": "Searching Decathlon's live catalog…",
    "ucp.call": "Checking sizes against live stock…",
    "catalog.variant_resolved": "Checking sizes against live stock…",
    "guardrail.stock": "Checking sizes against live stock…",
    "kit.built": "Putting the kit together…",
}

# `ui/demo_data.py` replays its own event names, and the fixture is what runs on stage
# when Gemini quota is gone — so it gets the same captions under its own vocabulary.
_FIXTURE_STAGE_STATUS = {
    "intent.verdict": _STAGE_STATUS["gate.verdict"],
    "search.grounded": _STAGE_STATUS["research.grounded"],
    "catalog.retrieve": _STAGE_STATUS["catalog.collection"],
    "ucp.get_product": _STAGE_STATUS["ucp.call"],
    "variant.resolved": _STAGE_STATUS["catalog.variant_resolved"],
    "kit.assembled": _STAGE_STATUS["kit.built"],
}

_ANY_STAGE_STATUS = {**_STAGE_STATUS, **_FIXTURE_STAGE_STATUS}

# Public-load protection, for when a QR code points a room full of phones at the same
# tunnel the demo is running on.
#
# The presenting laptop opens the app with `?vip=<CONCIERGE_VIP_TOKEN>` and never
# queues. Everyone else shares CONCIERGE_PUBLIC_SLOTS concurrent turns and waits their
# turn, which is what stops N phones from each holding a 60-second generator open and
# burning the shared Gemini quota in parallel.
#
# OFF unless CONCIERGE_VIP_TOKEN is set. A misconfigured token must never be able to
# put the demo laptop in a queue — failing open is the safe direction here.
VIP_TOKEN = os.environ.get("CONCIERGE_VIP_TOKEN", "")
PUBLIC_SLOTS = max(1, int(os.environ.get("CONCIERGE_PUBLIC_SLOTS", "3")))

_public_gate = asyncio.Semaphore(PUBLIC_SLOTS)

# One shared password, no username: on a public URL what needs protecting is the Gemini
# quota and Decathlon's rate limiter, not per-visitor data. UNSET MEANS NO GATE, which is
# what leaves local dev, `make walkthrough` and the test suite untouched.
GATE_PASSWORD = os.environ.get("DECABOT_PASSWORD", "")
GATE_ON = bool(GATE_PASSWORD)
# What a returning browser presents instead of retyping. Producing it requires the
# password, so restoring `unlocked` from the cookie is a real server-side check rather
# than trusting a client-set flag.
_GATE_DIGEST = (
    hashlib.sha256(b"decabot.gate.v1:" + GATE_PASSWORD.encode()).hexdigest() if GATE_ON else ""
)
# A shared short password's only real defence is making each guess cost something.
_GATE_DELAY = 0.6

_SESSIONS: dict[str, Any] = {}


def _session_for(token: str) -> Any:
    from concierge.agent.loop import ConversationSession

    if token not in _SESSIONS:
        _SESSIONS[token] = ConversationSession()
    return _SESSIONS[token]


def _reset_session(token: str) -> None:
    _SESSIONS.pop(token, None)


class Citation(BaseModel):
    title: str
    url: str
    domain: str = ""


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
    # KitItem.image_url is `Url | None` — a real in-stock product without a photo
    # is still buyable. "" is the placeholder signal; never let None reach here.
    image_url: str = ""
    size_label: str
    quantity: int
    quantity_label: str
    price_display: str
    size_substituted: bool
    # A guessed size looked identical to a chosen one on the card, so the only
    # trace of it was a sentence in the chat log that scrolls away.
    size_confirmed: bool
    # Non-empty on the FIRST card of each person's block. The grid renders it as a
    # full-width row, which is why it rides on the card: `grid-column: 1 / -1` needs the
    # heading to be a direct child of the same grid as the cards, so every block shares
    # one set of column widths. Nesting cards under a group model is possible in Reflex
    # 0.9.7 — but do NOT name that model's list field `items`: `ObjectVar.items` shadows
    # it and `rx.foreach(group.items, …)` dies with "Unsupported type <class 'method'>".
    person_heading: str = ""
    rationale: str


def to_card(item: KitItem, heading: str = "") -> KitCard:
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
        size_confirmed=item.size_confirmed,
        person_heading=heading,
        rationale=item.rationale,
    )


def plain(value: Any) -> Any:
    """Reflex hands back state containers wrapped in `MutableProxy` (a wrapt
    ObjectProxy). `isinstance` sees through it; `json.dumps` does NOT — its encoder does
    an exact type check, misses the proxy and falls through to `default=`, which turns
    every payload into a Python repr inside a JSON string. Rebuild real containers first.
    """
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [plain(v) for v in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return str(value)
    return str(value)


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

    # The panel renders `summarise()`, which clamps values at 120 chars and the line at
    # 300. The debugging bundle needs the payloads whole, and `trace` crosses the wire on
    # every drain — so the full events live in a BACKEND-ONLY var (leading underscore),
    # which Reflex never serializes to any browser. `_last_bundle` is the same trick: a
    # successful copy then costs nothing on the wire.
    _raw_trace: list[dict[str, Any]] = []
    _last_bundle: str = ""

    # "" | "ok" | "failed". Set from what the clipboard write actually RETURNED — a green
    # tick that fires on dispatch rather than on success is a claim, not evidence.
    copy_status: str = ""
    copy_fallback: str = ""

    cart_id: str = ""
    cart_url: str = ""
    cart_total_minor: int = 0
    cart_line_count: int = 0
    cart_expires_at: str = ""

    is_thinking: bool = False
    awaiting_confirmation: bool = False
    status: str = ""
    # Styling only — `status` carries the words. Separate so the spinner can change
    # character without the UI having to string-match the message.
    throttled: bool = False
    error: str = ""

    is_vip: bool = False

    confirming_clear: bool = False

    # What the kit is still assuming about this customer, from check_open_questions.
    open_asks: list[str] = []

    # Title + size of every line in the LAST cart handed over, so a second link can
    # say what moved rather than leaving the customer to diff two Decathlon pages.
    last_cart_lines: list[str] = []

    # Every handler that spends a Gemini call or touches Decathlon re-checks this, as
    # `GATE_ON and not self.unlocked`. Conditional rendering is not a guard — the events
    # are callable over the wire whatever is on screen — exactly the reasoning behind
    # `confirm_cart` above.
    #
    # The `GATE_ON and` half is not redundant. `scripts/verify_walkthrough.py` and
    # `verify_ui.py` drive these handlers directly with no browser, so `on_page_load`
    # never runs and never opens the gate: a bare `not self.unlocked` turned
    # `make rehearse` into a silent no-op that asserted nothing.
    #
    # False unconditionally, NOT `not GATE_ON`. A state var's default is compiled INTO
    # the frontend bundle, and the image is built without DECABOT_PASSWORD set, so
    # `not GATE_ON` baked in as True: a browser that never completed the websocket
    # handshake was served the unlocked app shell. `on_page_load` opens the gate when
    # it is off, so the only thing this default decides is what an unhydrated page
    # shows — and that has to be the lock.
    unlocked: bool = False
    gate_error: str = ""
    gate_busy: bool = False
    gate_reveal: bool = False
    gate_key: str = rx.Cookie(name="decabot_gate", max_age=60 * 60 * 24 * 30, same_site="lax")

    walkthrough_phase: str = ""
    # How far the two-step script has got: 0 nothing run, 1 prewarmed, 2 finished.
    # This is what the single demo button reads to know which phase is next.
    walkthrough_stage: int = 0
    # Reflex's `initialEvents` fires on_load on every websocket RECONNECT, not just the
    # first load, so `?walkthrough=<phase>` would re-arm the script every time the tunnel
    # blinked. The in-progress guard does not cover the moment the script FINISHES —
    # which is when the kit and the cart button are on screen — so a reconnect there
    # ran clear() and wiped both. Latched once per session and never released, not even
    # by clear(): a reconnect must never be able to start the script by itself.
    walkthrough_autostarted: bool = False
    walkthrough_step: int = 0
    walkthrough_total: int = 0
    walkthrough_label: str = ""
    walkthrough_shows: str = ""

    @rx.var
    def cards(self) -> list[KitCard]:
        """Ordered so each person's block is contiguous, carrying its heading on the
        first card. A line covering two people — one variant, quantity 2 — is shared
        rather than person 1's: under a per-person heading it would read as theirs
        alone, and listing it under both would show one cart line twice."""
        owned: dict[int, list[KitItem]] = {}
        shared: list[KitItem] = []
        for item in self.kit_items:
            if len(item.person_indexes) == 1:
                owned.setdefault(item.person_indexes[0], []).append(item)
            else:
                shared.append(item)
        blocks = [(f"Person {n}", items) for n, items in sorted(owned.items())]
        if shared:
            # Nobody named means nobody to tell apart — a party of one, or a party whose
            # every line is shared — so the kit is one unheaded run instead.
            blocks.append(("Shared" if owned else "", shared))
        return [
            to_card(item, heading if n == 0 else "")
            for heading, items in blocks
            for n, item in enumerate(items)
        ]

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

    @rx.var
    def unconfirmed_count(self) -> int:
        return sum(1 for i in self.kit_items if not i.size_confirmed)

    @rx.var
    def has_unconfirmed(self) -> bool:
        return self.unconfirmed_count > 0

    @rx.var
    def unconfirmed_subject(self) -> str:
        """Both the kit-summary prompt and the confirm-bar caption open on this count,
        so the plural rule has one place to be wrong in rather than two."""
        n = self.unconfirmed_count
        return f"{n} item is" if n == 1 else f"{n} items are"

    @rx.var
    def unconfirmed_note(self) -> str:
        return f"{self.unconfirmed_subject} in a generic size because none was specified."

    @rx.var
    def walkthrough_active(self) -> bool:
        return self.walkthrough_phase != ""

    @rx.var
    def walkthrough_progress(self) -> str:
        return f"{self.walkthrough_step}/{self.walkthrough_total}"

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
            self._raw_trace.append(ev.as_dict())
            throttle = _THROTTLE_STATUS.get(ev.event)
            if throttle is not None:
                self.throttled, self.status = True, throttle
            elif not self.throttled:
                stage = _ANY_STAGE_STATUS.get(ev.event)
                if stage is not None:
                    self.status = stage
        sink.clear()
        return True

    def _cart_lines(self) -> list[str]:
        return [f"{i.product_title} — {i.size_label}" for i in self.kit_items]

    def _cart_changes(self) -> list[str]:
        """What moved between the last link and this one. Nothing on the first cart —
        there is no "changed" without a previous."""
        if not self.last_cart_lines:
            return []
        now, before = self._cart_lines(), self.last_cart_lines
        added = [x for x in now if x not in before]
        gone = [x for x in before if x not in now]
        return [f"• added: {x}" for x in added] + [f"• removed: {x}" for x in gone]

    def _remember_cart_lines(self) -> None:
        self.last_cart_lines = self._cart_lines()

    def _refresh_open_asks(self) -> None:
        """Fixture mode never reaches `_continue`, so the live path's call to
        `check_open_questions` would leave these empty in exactly the mode that runs on
        stage. Party size comes off the kit's own person ordinals — the fixture is two
        people and says so through them."""
        from concierge.domain.guardrails import check_open_questions
        from concierge.domain.models import Kit

        said = " ".join(m.content for m in self.messages if m.role == "user")
        party = max((i for it in self.kit_items for i in it.person_indexes), default=1)
        kit = Kit(
            items=list(self.kit_items),
            unservable_slots=list(self.unservable_slots),
            budget_minor=self.budget_minor,
        )
        self.open_asks = [q.ask for q in check_open_questions(kit, party, said)]

    def _apply_kit(self, kit) -> None:
        self.kit_items = list(kit.items)
        self.unservable_slots = list(kit.unservable_slots)
        self.budget_minor = kit.budget_minor

    def _reset_cart(self) -> None:
        self.cart_id = ""
        self.cart_url = ""
        self.cart_total_minor = 0
        self.cart_line_count = 0
        self.cart_expires_at = ""

    def _apply_cart(self, cart: CartResult) -> None:
        self.cart_id = cart.cart_id
        self.cart_url = cart.continue_url
        self.cart_total_minor = cart.total_minor
        self.cart_line_count = cart.line_count
        self.cart_expires_at = cart.expires_at or ""

    @rx.var
    def gate_on(self) -> bool:
        return GATE_ON

    @rx.var
    def can_copy_run(self) -> bool:
        """Binding a sink in `unlock` means a REFUSED password now puts a row in the
        trace — so a non-empty trace alone would enable the copy button for someone who
        is still locked out, and `copy_run` would then refuse in silence."""
        return bool(self.trace) and not (GATE_ON and not self.unlocked)

    def toggle_trace(self):
        self.show_trace = not self.show_trace

    def _reset_copy(self) -> None:
        self._last_bundle = ""
        self.copy_status = ""
        self.copy_fallback = ""

    def _snapshot(self) -> bundle.RunSnapshot:
        return bundle.RunSnapshot(
            stamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            mode="fixture" if FIXTURE_MODE else "live",
            gated=GATE_ON,
            lane="reserved" if self.is_vip else "public",
            messages=[
                {"role": m.role, "content": m.content, "citations": [c.url for c in m.citations]}
                for m in self.messages
            ],
            events=plain(self._raw_trace),
            items=[
                {
                    "slot": i.slot,
                    "product_title": i.product_title,
                    "product_url": i.product_url,
                    "variant_id": i.variant_id,
                    "size_label": i.size_label,
                    "quantity": i.quantity,
                    "price_minor": i.price_minor,
                    "size_substituted": i.size_substituted,
                    "rationale": i.rationale,
                }
                for i in self.kit_items
            ],
            unservable=list(self.unservable_slots),
            budget_minor=self.budget_minor,
            cart={
                "cart_id": self.cart_id,
                "url": self.cart_url,
                "total_minor": self.cart_total_minor,
                "line_count": self.cart_line_count,
                "expires_at": self.cart_expires_at,
            }
            if self.cart_url
            else None,
        )

    @rx.event
    def copy_run(self):
        """Put the whole run on the clipboard as text.

        `rx.set_clipboard` would fire on the websocket RESPONSE — one round trip after
        the click, outside its transient user activation — which Firefox and Safari
        refuse, and it reports nothing back either way. `run_script` with a callback is
        the honest form: the compiled frontend awaits the promise and hands the result to
        `copy_finished`.
        """
        if GATE_ON and not self.unlocked:
            return
        self.copy_fallback = ""
        self._last_bundle = bundle.render(self._snapshot())
        yield rx.run_script(
            f"navigator.clipboard?.writeText({json.dumps(self._last_bundle)})"
            f".then(() => true, () => false) ?? false",
            callback=State.copy_finished,
        )

    @rx.event
    def copy_finished(self, ok: bool):
        """No gate re-check here, unlike every other handler — and that is deliberate.
        This one spends nothing and reveals nothing: state is per session, and a locked
        caller's `copy_run` returned before writing `_last_bundle`, so the worst a forged
        call can do is echo this session's own empty string back to itself."""
        self.copy_status = "ok" if ok else "failed"
        # Only a refused write puts the text on the wire, and only so it can be selected
        # by hand. A working copy never pays for it.
        self.copy_fallback = "" if ok else self._last_bundle

    def toggle_reveal(self):
        self.gate_reveal = not self.gate_reveal

    @rx.event
    async def unlock(self, form_data: dict[str, Any]):
        if not GATE_ON or self.unlocked or self.gate_busy:
            return

        self.gate_busy = True
        self.gate_error = ""
        yield

        await asyncio.sleep(_GATE_DELAY)
        # Bound so these two land in THIS session's trace. Without a sink they reach only
        # the process-wide ring buffer, and the panel — and the copied bundle — would be
        # missing a guardrail verdict that did fire.
        sink: list[TraceEvent] = []
        bind_sink(sink)
        try:
            if hmac.compare_digest((form_data.get("password") or "").strip(), GATE_PASSWORD):
                self.unlocked = True
                self.gate_key = _GATE_DIGEST
                emit("gate.unlocked", {}, level="guardrail")
            else:
                self.gate_error = "That is not the password."
                emit("gate.refused", {}, level="guardrail")
            self._drain(sink)
        finally:
            bind_sink(None)

        self.gate_busy = False
        yield

    @rx.var
    def has_open_asks(self) -> bool:
        return bool(self.open_asks)

    @rx.var
    def is_presenter(self) -> bool:
        """No VIP token configured means nobody is being gated — local dev and
        `make walkthrough` must keep their controls."""
        return self.is_vip or not VIP_TOKEN

    @rx.var
    def has_anything_to_lose(self) -> bool:
        """Whether "Start over" would actually destroy something. A kit costs three
        minutes of live API calls to rebuild, and the control is icon-only below md."""
        return bool(self.messages or self.kit_items or self.trace)

    def ask_to_clear(self):
        self.confirming_clear = True

    def cancel_clear(self):
        self.confirming_clear = False

    def clear(self):
        self.confirming_clear = False
        self.open_asks = []
        self.last_cart_lines = []
        _reset_session(self.router.session.client_token)
        self.messages = []
        self.kit_items = []
        self.unservable_slots = []
        self.budget_minor = None
        self.trace = []
        self._raw_trace = []
        self._reset_copy()
        self._reset_cart()
        self.is_thinking = False
        self.awaiting_confirmation = False
        self.status = ""
        self.throttled = False
        self.error = ""
        self.draft = ""
        self.walkthrough_stage = 0

    @rx.event
    async def send_example(self, text: str):
        """The empty-state example chips. Same handler a typed message takes."""
        async for _ in self.send_message({"message": text}):
            yield

    @rx.event
    async def send_message(self, form_data: dict[str, Any]):
        text = (form_data.get("message") or self.draft or "").strip()
        if not text or self.is_thinking or (GATE_ON and not self.unlocked):
            return

        self.draft = ""
        self.error = ""
        # No timed reset: Reflex holds the session state lock for a handler's duration,
        # so sleeping to clear a badge would serialize that session's other events.
        self._reset_copy()
        self.open_asks = []
        # Sending a message is an implicit Keep. Left standing, the header sits in
        # Erase/Keep over a run the customer has since added to.
        self.confirming_clear = False
        self.messages.append(ChatMessage(role="user", content=text))
        self.is_thinking = True
        self.status = "Reading the conditions…"
        self.throttled = False
        self.awaiting_confirmation = False
        # A new turn supersedes the previous cart. Leaving these set would keep
        # `has_cart` true and permanently hide the confirm button on turn two.
        self._reset_cart()
        yield

        # The trace accumulates across turns rather than resetting: the intent
        # verdict and the grounded search happen on turn one, and those are the
        # artifacts a judge is reading for. `clear()` is the reset.
        sink: list[TraceEvent] = []
        bind_sink(sink)
        try:
            emit("turn.start", {"turn": len(self.messages) // 2 + 1, "text": text[:160]})
            self._drain(sink)
            yield

            queued = bool(VIP_TOKEN) and not self.is_vip
            if queued and _public_gate.locked():
                self.status = "The concierge is busy with the live demo — you're next in line…"
                emit("session.queued", {"slots": PUBLIC_SLOTS}, level="guardrail")
                self._drain(sink)
                yield

            if queued:
                await _public_gate.acquire()
            try:
                if FIXTURE_MODE:
                    async for _ in self._fixture_turn(sink, text):
                        yield
                else:
                    async for _ in self._live_turn(sink, text):
                        yield
            finally:
                if queued:
                    _public_gate.release()
        except Exception as exc:
            emit("turn.error", {"error": repr(exc)}, level="error")
            self._drain(sink)
            # The class name and the exception text belong in the trace, which is
            # right there and is where detail is supposed to live. On the page they
            # are a stack trace on a projector.
            self.error = "That turn failed before I could finish. The audit trail has the last step that ran."
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
            self.throttled = False
        yield

    async def _fixture_turn(self, sink: list[TraceEvent], text: str):
        # A follow-up that names a size is a size ANSWER, not a new trip. Replaying
        # the research trace and the opening kit at that point ignored the customer
        # outright: DecaBot promised "give me the sizes and I'll rebuild", and the
        # fixture handed back the same guessed sizes however many times you answered.
        if self.kit_items and self.unconfirmed_count and demo_data.sizes_in(text):
            async for _ in self._fixture_resize(sink, text):
                yield
            return

        # Same reasoning as the resize above: the fixture is what runs on stage when
        # quota is gone, so "I already have the tent" has to work there too.
        if self.kit_items and self._fixture_drop_lines(text):
            async for _ in self._fixture_drop(sink, text):
                yield
            return

        for event, payload, level in demo_data.demo_trace():
            emit(event, payload, level)
            await asyncio.sleep(_STEP_DELAY)
            self._drain(sink)
            yield

        self._apply_kit(demo_data.demo_kit())
        self._refresh_open_asks()
        # Its guardrail event is emitted after the loop above drained for the last time,
        # so without this the audit rail never gets the row. `_fixture_resize` drains
        # after its own emits for the same reason.
        self._drain(sink)
        self.messages.append(
            ChatMessage(
                role="assistant",
                content=demo_data.DEMO_MESSAGES[1][1],
                citations=[Citation(title=t, url=u, domain=d) for t, u, d in demo_data.DEMO_CITATIONS],
            )
        )
        self.awaiting_confirmation = True
        yield

    def _fixture_drop_lines(self, text: str) -> list[int]:
        """Which kit lines this message names. Reuses the live matcher rather than
        growing a second one — a fixture that behaves differently from the live path
        is how the demo starts lying again."""
        from concierge.agent.loop import _DROP_CUE, _lines_named
        from concierge.domain.models import Kit

        if not _DROP_CUE.search(text) or demo_data.sizes_in(text):
            return []
        hit = _lines_named(Kit(items=list(self.kit_items), unservable_slots=[]), text)
        # Emptying the kit is never what "I already have boots" meant.
        return [] if len(hit) == len(self.kit_items) else hit

    async def _fixture_drop(self, sink: list[TraceEvent], text: str):
        hit = set(self._fixture_drop_lines(text))
        dropped = [i for n, i in enumerate(self.kit_items) if n in hit]
        emit(
            "guardrail.lines_dropped",
            {"dropped": [i.product_title for i in dropped], "kept": len(self.kit_items) - len(hit)},
            level="guardrail",
        )
        await asyncio.sleep(_STEP_DELAY)
        self._drain(sink)
        yield

        self.kit_items = [i for n, i in enumerate(self.kit_items) if n not in hit]
        self._refresh_open_asks()
        emit("kit.assembled", {"items": len(self.kit_items), "substitutions": self.substitution_count})
        self._drain(sink)
        yield

        lines = "\n".join(f"• {i.product_title} — {i.size_label}" for i in dropped)
        plural = "s" if len(dropped) > 1 else ""
        self.messages.append(
            ChatMessage(
                role="assistant",
                content=(
                    f"Taken out of the kit, {len(dropped)} line{plural}:\n\n{lines}\n\n"
                    "Say the word if you want any of them back. Build the cart again "
                    "and you'll get a fresh link without them."
                ),
            )
        )
        self.awaiting_confirmation = True
        yield

    async def _fixture_resize(self, sink: list[TraceEvent], text: str):
        """Rebuild the demo kit with sizes the customer just gave.

        The tokens are resolved against the same dumped availability grid as the
        first pass, so a size that is not stocked stays unanswered instead of being
        invented. Whatever is still unconfirmed after this is reported, not hidden."""
        answers = demo_data.sizes_in(text)
        emit("size.answer", {"tokens": answers})
        await asyncio.sleep(_STEP_DELAY)
        self._drain(sink)
        yield

        before = {(i.slot, i.product_title): i.size_label for i in self.kit_items}
        kit = demo_data.demo_kit(tuple(answers))
        changed = [
            (i.product_title, before.get((i.slot, i.product_title)), i.size_label)
            for i in kit.items
            if before.get((i.slot, i.product_title)) not in (None, i.size_label)
        ]
        for title, was, now in changed:
            emit("variant.resolved", {"product": title, "was": was, "now": now, "source": "customer_size"})
            await asyncio.sleep(_STEP_DELAY)
            self._drain(sink)
            yield

        self._apply_kit(kit)
        self._refresh_open_asks()
        still = check_size_confirmation(self.kit_items)
        emit(
            "guardrail.size_confirmed",
            {"applied": len(changed), "still_unconfirmed": len(still)},
            level="guardrail",
        )
        emit("kit.assembled", {"items": len(kit.items), "substitutions": self.substitution_count})
        emit("human.confirmation_required", {"reason": "cart creation is never model-initiated"}, level="guardrail")
        self._drain(sink)
        yield

        if changed:
            lines = "\n".join(f"• {t}: {was} → {now}" for t, was, now in changed)
            body = f"Updated {len(changed)} line{'s' if len(changed) > 1 else ''}:\n\n{lines}"
        else:
            body = (
                "None of those sizes are stocked for the lines I was waiting on, so I have "
                "changed nothing rather than putting you in a size that does not exist."
            )
        tail = (
            "\n\nBuild the cart again and you'll get a fresh link with these lines."
            if changed
            else ""
        )
        if still:
            tail += "\n\nStill guessing on:\n" + "\n".join(still)
        self.messages.append(ChatMessage(role="assistant", content=body + tail))
        self.awaiting_confirmation = True
        yield

    async def _live_turn(self, sink: list[TraceEvent], text: str):
        # Imported inside the handler: the agent lane owns this module and it must
        # not be a module-scope import while the lanes build concurrently.
        from concierge.agent import classify, tools
        from concierge.agent.loop import run_turn
        from concierge.commerce import catalog

        # Without this the loop dispatches against agent/stubs.py and serves
        # fixture data while claiming to be live — the one failure that would
        # invalidate the whole demo.
        tools.set_backend(catalog)

        # ConversationSession carries the profile, derived slots and product cache
        # between turns, so it must outlive a single handler. Reflex state cannot
        # hold a dataclass, hence the module-level map keyed per browser session.
        session = _session_for(self.router.session.client_token)

        # Which Gemini key this turn spends. The demo laptop keeps GEMINI_API_KEY to
        # itself; a QR-code audience round-robins GEMINI_PUBLIC_KEYS. Per-project quota
        # is the one bottleneck in-app queueing cannot protect, so separate keys are the
        # only real isolation. Bound BEFORE create_task — contextvars are copied at
        # task-creation time, exactly like bind_sink above.
        classify.bind_key(None if self.is_vip else classify.next_public_key())
        # Lane only. The trace panel is on screen for anyone holding the QR code, so no
        # key material — not even a prefix — is ever emitted.
        emit("model.key_lane", {"lane": "reserved" if self.is_vip else "public"})

        task = asyncio.create_task(run_turn(text, session))
        while not task.done():
            await asyncio.sleep(_POLL_INTERVAL)
            if self._drain(sink):
                yield

        result = await task
        if self._drain(sink):
            yield

        if result.kit is not None:
            self._apply_kit(result.kit)

        self.unservable_slots = list(result.unservable_slots or self.unservable_slots)
        # Prose scrolls away; the confirm bar does not. Same reasoning as the size ask.
        if result.kit is not None:
            self.open_asks = [q.ask for q in result.open_questions]
        elif self.kit_items:
            # No kit from THIS turn is not no kit: a redirect, a rate limit or the model
            # call budget running out all leave the previous one on screen with the
            # confirm bar up, and `awaiting_confirmation` below deliberately keeps it
            # there. Dropping the asks would take them off the button that spends money
            # for the rest of the session.
            self._refresh_open_asks()
            self._drain(sink)
        self.messages.append(
            ChatMessage(
                role="assistant",
                content=result.text,
                citations=[Citation(title=c.title, url=c.uri, domain=c.domain) for c in result.citations],
            )
        )
        # A redirect, a greeting or a failed turn produces no kit at all, and must not
        # retract a standing cart offer: ask about swimming after the kit is built and
        # the confirm button would vanish for the rest of the session.
        self.awaiting_confirmation = bool(self.kit_items) and (result.offer_cart or result.kit is None)
        yield

    @rx.event
    async def confirm_cart(self):
        if not self.awaiting_confirmation or not self.kit_items or self.is_thinking:
            return
        if GATE_ON and not self.unlocked:
            return

        self.awaiting_confirmation = False
        self.is_thinking = True
        self.status = "Creating the cart at Decathlon…"
        self.throttled = False
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
                # The counts come from the kit actually being confirmed, so a rebuilt
                # kit produces a cart that agrees with what is on screen.
                cart = demo_data.demo_cart(list(self.kit_items))
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
            # The cart goes out with whatever sizes we have, but a line the customer
            # never sized is a wrong-fit return waiting to happen. Ask now, while the
            # cart is still editable, rather than letting them discover it at checkout.
            parts = ["Your cart is live — the link is beside this message."]
            # Second and later carts supersede the first, and the customer has no way
            # to tell what moved between them unless we say. Computed from the lines,
            # not narrated by the model.
            changes = self._cart_changes()
            if changes:
                parts.append("What changed since the last link:\n" + "\n".join(changes))
            self._remember_cart_lines()

            asks = check_size_confirmation(self.kit_items)
            if asks:
                parts.append("\n".join(asks))
                parts.append("Give me the sizes and I'll rebuild the kit and hand you a new link.")

            # The cart is editable at Decathlon and this is the last honest moment to
            # say so: the link is the handover point, not a receipt.
            parts.append(
                "**Please open the cart and check it before you pay** — that it has "
                "everything you want, in the sizes you want, and nothing you don't."
            )
            self.messages.append(ChatMessage(role="assistant", content="\n\n".join(parts)))
            self._drain(sink)
        except Exception as exc:
            emit("cart.error", {"error": repr(exc)}, level="error")
            self._drain(sink)
            self.error = (
                "Decathlon would not create the cart just now. Nothing was bought and the kit is "
                "untouched — press the button again, or check the audit trail for what it returned."
            )
            self.awaiting_confirmation = True
        finally:
            bind_sink(None)
            self.is_thinking = False
            self.status = ""
            self.throttled = False
        yield

    @rx.event
    async def on_page_load(self):
        """`make walkthrough` opens the page with `?walkthrough=<phase>` so the demo
        starts with no click at all.

        Gated on the query parameter rather than on the load itself: a plain visit to
        `/` must never restart the script, or a stray refresh mid-pitch would wipe a
        kit that took three minutes of live calls to build.

        Gated a second time on `walkthrough_autostarted`, because this handler runs again
        on every websocket reconnect — see that field.

        `router.url.query_parameters` — `router.page` is deprecated in 0.9.x and slated
        for removal in 1.0.
        """
        if not GATE_ON:
            self.unlocked = True
        elif not self.unlocked and hmac.compare_digest(self.gate_key, _GATE_DIGEST):
            self.unlocked = True

        params = self.router.url.query_parameters
        if VIP_TOKEN and params.get("vip", "") == VIP_TOKEN:
            self.is_vip = True
            # Same reasoning as `unlock`. Bound around this emit ONLY — `run_walkthrough`
            # below binds its own sinks per turn.
            sink: list[TraceEvent] = []
            bind_sink(sink)
            try:
                emit("session.priority", {"vip": True}, level="guardrail")
                self._drain(sink)
            finally:
                bind_sink(None)

        phase = params.get("walkthrough", "").strip().lower()
        if phase in ("prewarm", "onstage", "all") and not self.walkthrough_autostarted:
            # Latched BEFORE the first await, or a reconnect during the run re-enters here.
            self.walkthrough_autostarted = True
            async for _ in self.run_walkthrough("" if phase == "all" else phase):
                yield

    @rx.event
    async def advance_walkthrough(self):
        """The one demo button. Which phase runs is derived from the cursor, not from
        the click, so the UI cannot get out of step with the script."""
        async for _ in self.run_walkthrough("onstage" if self.walkthrough_stage == 1 else "prewarm"):
            yield

    @rx.event
    async def run_walkthrough(self, phase: str = ""):
        """The scripted demo, driven through the same handlers a human clicks.

        `phase` is "prewarm", "onstage", or "" for the whole script. Only the whole
        script and the prewarm start from a clean slate — "onstage" deliberately keeps
        the kit the prewarm built, because that kit IS the thing being probed.
        """
        if self.is_thinking or self.walkthrough_phase or (GATE_ON and not self.unlocked):
            return

        script = walkthrough.beats(phase or None)
        if not script:
            return
        if phase != "onstage":
            self.clear()

        self.walkthrough_phase = phase or "all"
        self.walkthrough_total = len(script)
        yield

        try:
            for step, beat in enumerate(script, 1):
                self.walkthrough_step = step
                self.walkthrough_label = beat.label
                self.walkthrough_shows = beat.shows
                yield
                await asyncio.sleep(walkthrough.PAUSE_SECONDS)

                if beat.message:
                    async for _ in self.send_message({"message": beat.message}):
                        yield
                elif self.awaiting_confirmation:
                    async for _ in self.confirm_cart():
                        yield
                else:
                    # The cart beat with no standing offer means an earlier beat
                    # failed. Say so rather than ending on a silent no-op.
                    self.error = (
                        "The walkthrough reached the cart step with nothing to buy — the kit "
                        "never built. Run the prewarm phase first, or check the trace panel."
                    )
                yield
            self.walkthrough_stage = 1 if phase == "prewarm" else 2
        finally:
            self.walkthrough_phase = ""
            self.walkthrough_step = 0
            self.walkthrough_total = 0
            self.walkthrough_label = ""
            self.walkthrough_shows = ""
        yield
