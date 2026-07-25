"""Controls for the scripted demo. The script itself is `concierge/walkthrough.py`.

Two buttons rather than one, because the on-camera slot is 30 seconds and a real
grounded-research pass is not. Prewarm while the pitch is still on the problem
statement; go live when the audience is looking.
"""

from __future__ import annotations

import reflex as rx

from concierge.state import State
from concierge.ui.theme import (
    BORDER,
    BRAND,
    BRAND_DARK,
    MONO,
    MUTED,
    ON_BRAND,
    RADIUS,
    RADIUS_SM,
    TINT_2,
    WHITE,
)


def _button(title: str, detail: str, phase: str, primary: bool) -> rx.Component:
    return rx.button(
        rx.vstack(
            rx.text(title, size="2", weight="bold", line_height="1.2"),
            rx.text(detail, size="1", opacity="0.8", line_height="1.2"),
            spacing="1",
            align="start",
        ),
        on_click=State.run_walkthrough(phase),
        disabled=State.is_thinking,
        cursor="pointer",
        height="auto",
        padding="0.6rem 0.9rem",
        background=BRAND if primary else WHITE,
        color=ON_BRAND if primary else BRAND,
        border=f"1px solid {BRAND}",
        border_radius=RADIUS_SM,
        _hover={"background": BRAND_DARK if primary else TINT_2},
    )


def _controls() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("play", size=15, color=BRAND),
            rx.text("SCRIPTED WALKTHROUGH", size="1", weight="bold", letter_spacing="0.1em", color=BRAND),
            rx.text(
                "automated, not mocked — every beat runs through the live agent",
                size="1",
                color=MUTED,
            ),
            spacing="2",
            align="center",
            wrap="wrap",
        ),
        rx.flex(
            # Measured, not guessed: prewarm ran 166 s and the onstage phase 34 s with
            # three beats. Do not round these down — the presenter paces the pitch off
            # them, and prewarm finishing late is what makes a demo look broken.
            _button("1 · Prewarm the trip", "research + kit · ~3 min · run during the intro", "prewarm", False),
            _button("2 · Go live", "probe + real cart · ~25 s · the on-camera slot", "onstage", True),
            _button("Run all", "end to end, for rehearsal", "", False),
            gap="0.6rem",
            wrap="wrap",
        ),
        spacing="2",
        align="start",
        width="100%",
        padding="0.8rem 1rem",
        background=WHITE,
        border=f"1px solid {BORDER}",
        border_radius=RADIUS,
    )


def _banner() -> rx.Component:
    return rx.hstack(
        rx.spinner(size="3"),
        rx.vstack(
            rx.hstack(
                rx.text("WALKTHROUGH", size="1", weight="bold", letter_spacing="0.12em", color=ON_BRAND),
                rx.text(State.walkthrough_progress, size="1", weight="bold", color=ON_BRAND, font_family=MONO),
                spacing="2",
                align="center",
            ),
            rx.text(State.walkthrough_label, size="4", weight="bold", color=ON_BRAND, line_height="1.3"),
            rx.text(State.walkthrough_shows, size="2", color=ON_BRAND, opacity="0.88", line_height="1.4"),
            spacing="1",
            align="start",
        ),
        spacing="4",
        align="center",
        width="100%",
        padding="1rem 1.2rem",
        background=BRAND,
        border_radius=RADIUS,
    )


def walkthrough_bar() -> rx.Component:
    return rx.cond(State.walkthrough_active, _banner(), _controls())
