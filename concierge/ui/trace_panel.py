"""The trace panel. A judge reads this while the agent works, so every step the
loop takes has to arrive here live and guardrail verdicts have to be unmissable.
"""

from __future__ import annotations

import reflex as rx

from concierge.state import State, TraceRow
from concierge.ui.theme import (
    ACCENT,
    BG,
    BORDER,
    DANGER,
    GUARDRAIL,
    MUTED,
    PANEL,
    PANEL_2,
    TEXT,
)


def _level_color(row: TraceRow):
    return rx.match(
        row.level,
        ("guardrail", GUARDRAIL),
        ("error", DANGER),
        ACCENT,
    )


def _level_bg(row: TraceRow):
    return rx.match(
        row.level,
        ("guardrail", "rgba(201,162,255,0.10)"),
        ("error", "rgba(255,107,94,0.13)"),
        "transparent",
    )


def trace_row(row: TraceRow) -> rx.Component:
    color = _level_color(row)
    return rx.vstack(
        rx.hstack(
            rx.text(
                row.seq,
                size="1",
                color=MUTED,
                font_family="monospace",
                min_width="2.2rem",
            ),
            rx.text(
                row.event,
                size="2",
                weight="bold",
                color=color,
                font_family="monospace",
            ),
            rx.spacer(),
            rx.cond(
                row.level != "info",
                rx.badge(
                    row.level.upper(),
                    color_scheme=rx.match(row.level, ("error", "red"), "purple"),
                    variant="solid",
                    size="1",
                ),
            ),
            width="100%",
            align="center",
            spacing="2",
        ),
        rx.cond(
            row.summary != "",
            rx.text(
                row.summary,
                size="1",
                color=MUTED,
                font_family="monospace",
                white_space="pre-wrap",
                word_break="break-word",
                line_height="1.5",
                padding_left="2.2rem",
            ),
        ),
        spacing="1",
        align="start",
        width="100%",
        padding="0.55rem 0.7rem",
        background=_level_bg(row),
        border_left=f"2px solid {color}",
        border_radius="0 6px 6px 0",
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
        rx.text(
            "No steps yet. Send a message and every planning step, tool call, "
            "grounding result and guardrail verdict lands here as it happens.",
            size="2",
            color=MUTED,
            line_height="1.6",
            padding="0.7rem",
        ),
    )


def trace_header() -> rx.Component:
    return rx.hstack(
        rx.icon("activity", size=17, color=ACCENT),
        rx.text("AGENT TRACE", size="2", weight="bold", color=TEXT, letter_spacing="0.1em"),
        rx.badge(State.trace.length(), color_scheme="jade", variant="soft", size="1"),
        rx.spacer(),
        rx.cond(State.is_thinking, rx.spinner(size="1")),
        rx.button(
            rx.cond(State.show_trace, rx.icon("chevron-right", size=16), rx.icon("chevron-left", size=16)),
            on_click=State.toggle_trace,
            variant="ghost",
            size="1",
            cursor="pointer",
        ),
        width="100%",
        align="center",
        spacing="2",
        padding="0.85rem 0.9rem",
        border_bottom=f"1px solid {BORDER}",
        background=PANEL_2,
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
                    padding="0.7rem",
                    width="100%",
                    overflow_y="auto",
                    flex="1",
                ),
                spacing="0",
                height="100%",
                width="100%",
            ),
            width=["100%", "100%", "100%", "400px"],
            min_width=["auto", "auto", "auto", "400px"],
            height=["24rem", "24rem", "24rem", "100vh"],
            position=["static", "static", "static", "sticky"],
            top="0",
            background=PANEL,
            border=f"1px solid {BORDER}",
            border_radius=["14px", "14px", "14px", "0"],
            overflow="hidden",
            flex_shrink="0",
        ),
        rx.box(
            rx.button(
                rx.icon("activity", size=16),
                on_click=State.toggle_trace,
                variant="soft",
                size="2",
                cursor="pointer",
            ),
            padding="0.6rem",
            background=BG,
        ),
    )
