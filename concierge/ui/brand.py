"""The DecaBot identity: one mark, one wordmark, reused everywhere.

The mark carries a presence dot — green when DecaBot is idle on live data, amber
on a fixture replay, brand blue with a halo while a turn is actually running. That
is the only ambient animation in the app.
"""

from __future__ import annotations

import reflex as rx

from concierge.state import FIXTURE_MODE, State
from concierge.ui.theme import (
    BRAND,
    BRAND_DEEP,
    INK,
    ON_BRAND,
    RADIUS_PILL,
    SHADOW_BRAND,
    SUCCESS,
    TRACK_TIGHTER,
    WARN,
    WHITE,
)

IDLE_DOT = WARN if FIXTURE_MODE else SUCCESS


def _dot(color: str, halo: bool) -> rx.Component:
    return rx.box(
        position="absolute",
        right="-2px",
        bottom="-2px",
        width="10px",
        height="10px",
        border_radius=RADIUS_PILL,
        background=color,
        border=f"2px solid {WHITE}",
        class_name="db-halo" if halo else "",
    )


def mark(size: str = "2.5rem", glyph: int = 21, dot: bool = True) -> rx.Component:
    return rx.box(
        rx.icon("bot", size=glyph, color=ON_BRAND),
        rx.cond(
            State.is_thinking,
            _dot(BRAND, halo=True),
            _dot(IDLE_DOT, halo=False),
        )
        if dot
        else rx.fragment(),
        position="relative",
        display="flex",
        align_items="center",
        justify_content="center",
        flex_shrink="0",
        width=size,
        height=size,
        background=f"linear-gradient(152deg, {BRAND} 0%, {BRAND_DEEP} 100%)",
        border_radius="11px",
        box_shadow=SHADOW_BRAND,
    )


def wordmark(size: str = "1.4rem") -> rx.Component:
    return rx.hstack(
        rx.text("Deca", color=INK),
        rx.text("Bot", color=BRAND),
        spacing="0",
        align="baseline",
        font_size=size,
        font_weight="800",
        letter_spacing=TRACK_TIGHTER,
        line_height="1.1",
    )
