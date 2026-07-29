"""The audit rail. A judge reads this while DecaBot works, so every step the loop
takes has to arrive here live and guardrail verdicts have to be unmissable.
"""

from __future__ import annotations

import reflex as rx

from concierge.state import State, TraceRow
from concierge.ui.theme import (  # noqa: F401
    ACCENT,
    ACCENT_DIM,
    BG,
    BORDER,
    BRAND,
    BRAND_DARK,
    BRAND_DEEP,
    CONTENT_W,
    DANGER,
    DANGER_BG,
    EASE,
    FOCUS_RING,
    FONT,
    GREY_1,
    GREY_2,
    GREY_3,
    GREY_4,
    GUARDRAIL,
    HAIRLINE,
    INK,
    LEVEL_BG,
    LEVEL_COLOR,
    MONO,
    MUTED,
    OFFWHITE,
    ON_BRAND,
    PANEL,
    PANEL_2,
    RADIUS,
    RADIUS_LG,
    RADIUS_PILL,
    RADIUS_SM,
    RAIL_BG,
    RAIL_BG_2,
    RAIL_DANGER,
    RAIL_GUARDRAIL,
    RAIL_INK,
    RAIL_LINE,
    RAIL_MUTED,
    RAIL_W,
    SHADOW_BRAND,
    SHADOW_LG,
    SHADOW_MD,
    SHADOW_SM,
    SHADOW_XS,
    SUCCESS,
    SUCCESS_BG,
    SUCCESS_DEEP,
    TEXT,
    TINT_1,
    TINT_2,
    TINT_3,
    TRACK_EYEBROW,
    TRACK_TIGHT,
    TRACK_TIGHTER,
    WARN,
    WARN_BG,
    WARN_INK,
    WHITE,
)


# Quiet ink -> brand blue -> danger red. GUARDRAIL and ACCENT both alias BRAND,
# so colouring info rows with ACCENT would make a guardrail verdict look identical
# to a routine step — and the guardrail rows are the point of this panel.
def _level_color(row: TraceRow):
    return rx.match(
        row.level,
        ("guardrail", LEVEL_COLOR["guardrail"]),
        ("error", LEVEL_COLOR["error"]),
        RAIL_INK,
    )


def _level_bg(row: TraceRow):
    return rx.match(
        row.level,
        ("guardrail", LEVEL_BG["guardrail"]),
        ("error", LEVEL_BG["error"]),
        LEVEL_BG["info"],
    )


# A verdict is an OBJECT on the rail; a routine step is a LINE on it. That is the
# distinction doing the work at three metres — the hue only confirms it. Colouring
# both and calling the difference a border makes every row the same shape.
def _level_edge(row: TraceRow):
    return rx.match(
        row.level,
        ("guardrail", "1px solid rgba(154,163,245,0.34)"),
        ("error", "1px solid rgba(255,139,150,0.34)"),
        "1px solid transparent",
    )


def _level_icon(row: TraceRow):
    return rx.match(row.level, ("error", "circle-alert"), "shield-check")


def trace_row(row: TraceRow) -> rx.Component:
    color = _level_color(row)
    return rx.hstack(
        rx.text(
            row.seq,
            size="1",
            color=RAIL_MUTED,
            font_family=MONO,
            width="1.5rem",
            flex_shrink="0",
            text_align="right",
            line_height="1.5",
            opacity="0.75",
        ),
        rx.vstack(
            rx.hstack(
                rx.cond(
                    row.level != "info",
                    rx.icon(_level_icon(row), size=13, color=color, flex_shrink="0"),
                ),
                rx.text(
                    row.event,
                    size="2",
                    weight="bold",
                    color=color,
                    font_family=MONO,
                    letter_spacing="-0.01em",
                    min_width="0",
                    word_break="break-word",
                ),
                rx.spacer(),
                rx.cond(
                    row.level != "info",
                    rx.text(
                        row.level.upper(),
                        size="1",
                        weight="bold",
                        # Dark ink on the light pill. ON_BRAND here is 1.8:1 — the
                        # pill inverts on a dark surface or it stops being readable.
                        color=RAIL_BG,
                        font_family=MONO,
                        letter_spacing="0.08em",
                        background=color,
                        padding="0.05rem 0.4rem",
                        border_radius=RADIUS_PILL,
                        flex_shrink="0",
                    ),
                ),
                width="100%",
                align="center",
                spacing="2",
                # The rail is 384px and event names run long. Without wrapping, the
                # pill squeezed the name until it broke mid-word — `guardrail.slot_
                # unserva / ble`. Let the pill drop to its own line instead.
                wrap="wrap",
            ),
            rx.cond(
                row.summary != "",
                rx.text(
                    row.summary,
                    size="1",
                    color=RAIL_MUTED,
                    font_family=MONO,
                    white_space="pre-wrap",
                    word_break="break-word",
                    line_height="1.55",
                ),
            ),
            spacing="1",
            align="start",
            width="100%",
            min_width="0",
        ),
        spacing="2",
        align="start",
        width="100%",
        padding="0.5rem 0.6rem",
        background=_level_bg(row),
        border=_level_edge(row),
        border_radius=RADIUS_SM,
    )


def trace_body() -> rx.Component:
    return rx.cond(
        State.trace.length() > 0,
        rx.vstack(
            rx.foreach(State.trace, trace_row),
            spacing="1",
            width="100%",
            align="start",
        ),
        rx.vstack(
            rx.icon("activity", size=22, color=RAIL_GUARDRAIL, opacity="0.7"),
            rx.text(
                "No steps yet. Send a message and every planning step, tool call, "
                "grounding result and guardrail verdict lands here as it happens.",
                size="2",
                color=RAIL_MUTED,
                line_height="1.65",
                text_align="center",
                max_width="34ch",
            ),
            spacing="3",
            align="center",
            width="100%",
            padding="2.5rem 1rem",
        ),
    )


def trace_header() -> rx.Component:
    return rx.hstack(
        rx.icon("activity", size=16, color=RAIL_GUARDRAIL),
        rx.text("AUDIT TRAIL", size="2", weight="bold", color=RAIL_INK, letter_spacing=TRACK_EYEBROW),
        rx.text(
            State.trace.length(),
            size="1",
            weight="bold",
            color=RAIL_BG,
            font_family=MONO,
            background=RAIL_GUARDRAIL,
            padding="0.1rem 0.45rem",
            border_radius=RADIUS_PILL,
        ),
        rx.spacer(),
        rx.cond(State.is_thinking, rx.spinner(size="1", color=RAIL_GUARDRAIL)),
        rx.button(
            rx.icon("chevron-right", size=15),
            on_click=State.toggle_trace,
            variant="ghost",
            # size="1" rendered a ~24px hit area. 44px is the floor for a touch
            # target, and this is the control an audience on phones reaches for.
            size="2",
            min_width="44px",
            min_height="44px",
            cursor="pointer",
            color=RAIL_MUTED,
            aria_label="Hide the audit trail",
            aria_expanded="true",
            aria_controls="decabot-trace",
            _hover={"background": RAIL_BG_2, "color": RAIL_INK},
        ),
        width="100%",
        align="center",
        spacing="2",
        padding="0.8rem 0.9rem",
        border_bottom=f"1px solid {RAIL_LINE}",
        background=RAIL_BG,
        position="sticky",
        top="0",
        z_index="2",
    )


def trace_panel() -> rx.Component:
    return rx.cond(
        State.show_trace,
        rx.box(
            rx.vstack(
                trace_header(),
                rx.box(
                    trace_body(),
                    class_name="db-scroll",
                    padding="0.6rem",
                    width="100%",
                    overflow_y="auto",
                    flex="1",
                ),
                spacing="0",
                height="100%",
                width="100%",
            ),
            id="decabot-trace",
            role="complementary",
            aria_label="Audit trail — every step, tool call and guardrail verdict",
            width=["100%", "100%", "100%", RAIL_W],
            min_width=["auto", "auto", "auto", RAIL_W],
            height=["24rem", "24rem", "24rem", "calc(100vh - 4.5rem)"],
            position=["static", "static", "static", "sticky"],
            top="4.5rem",
            background=RAIL_BG,
            border=f"1px solid {RAIL_BG_2}",
            border_radius=[RADIUS, RADIUS, RADIUS, "0"],
            overflow="hidden",
            flex_shrink="0",
            class_name="db-rail",
        ),
        rx.box(
            rx.button(
                rx.icon("activity", size=15),
                rx.text("Audit trail", size="1", weight="bold", letter_spacing="0.06em"),
                on_click=State.toggle_trace,
                size="2",
                min_height="44px",
                cursor="pointer",
                # The collapsed control wears the rail's own surface, so what it
                # opens is legible before it opens.
                color=RAIL_INK,
                background=RAIL_BG,
                border_radius=RADIUS_PILL,
                padding_x="0.9rem",
                aria_expanded="false",
                aria_controls="decabot-trace",
                _hover={"background": RAIL_BG_2},
            ),
            padding="1rem 0.9rem",
            flex_shrink="0",
        ),
    )
