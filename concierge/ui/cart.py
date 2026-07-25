"""Human-in-the-loop cart confirmation.

The button below is the only route to `confirm_cart`. The model cannot reach it.
"""

from __future__ import annotations

import reflex as rx

from concierge.state import FIXTURE_MODE, State
from concierge.ui.theme import ACCENT, BORDER, DANGER, MUTED, PANEL_2, TEXT


def confirm_bar() -> rx.Component:
    return rx.cond(
        State.awaiting_confirmation & ~State.has_cart,
        rx.vstack(
            rx.hstack(
                rx.icon("shield-check", size=20, color=ACCENT),
                rx.text(
                    "Nothing has been bought yet. I only create a cart when you say so.",
                    size="2",
                    color=TEXT,
                    line_height="1.6",
                ),
                spacing="2",
                align="center",
            ),
            rx.button(
                rx.hstack(
                    rx.icon("shopping-cart", size=20),
                    rx.text(f"Build my cart — {State.total_display}", size="3", weight="bold"),
                    spacing="2",
                    align="center",
                ),
                on_click=State.confirm_cart,
                disabled=State.is_thinking,
                size="4",
                width="100%",
                cursor="pointer",
            ),
            spacing="3",
            width="100%",
            padding="1.15rem",
            background="rgba(61,220,151,0.08)",
            border=f"1px solid {ACCENT}",
            border_radius="14px",
        ),
    )


def cart_block() -> rx.Component:
    return rx.cond(
        State.has_cart,
        rx.vstack(
            rx.hstack(
                rx.icon("circle-check-big", size=22, color=ACCENT),
                rx.text(
                    "Cart created at Decathlon",
                    size="4",
                    weight="bold",
                    color=ACCENT,
                ),
                spacing="2",
                align="center",
            ),
            rx.flex(
                rx.vstack(
                    rx.text("CART TOTAL", size="1", color=MUTED, letter_spacing="0.08em"),
                    rx.text(State.cart_total_display, size="6", weight="bold", color=TEXT),
                    spacing="0",
                    align="start",
                ),
                rx.vstack(
                    rx.text("LINES", size="1", color=MUTED, letter_spacing="0.08em"),
                    rx.text(State.cart_line_count, size="6", weight="bold", color=TEXT),
                    spacing="0",
                    align="start",
                ),
                gap="2.5rem",
                wrap="wrap",
            ),
            rx.link(
                rx.hstack(
                    rx.icon("external-link", size=22),
                    rx.text("Open my cart on Decathlon", size="4", weight="bold"),
                    spacing="3",
                    align="center",
                    justify="center",
                ),
                href=State.cart_url,
                is_external=True,
                width="100%",
                padding="1.1rem",
                background=ACCENT,
                color="#04150d",
                border_radius="12px",
                text_decoration="none",
                text_align="center",
                _hover={"opacity": "0.9"},
            ),
            rx.text(
                State.cart_url,
                size="1",
                color=MUTED,
                font_family="monospace",
                word_break="break-all",
                line_height="1.5",
            ),
            rx.cond(
                State.cart_expires_at != "",
                rx.text(f"Expires {State.cart_expires_at}", size="1", color=MUTED),
            ),
            spacing="3",
            width="100%",
            padding="1.3rem",
            background=PANEL_2,
            border=f"2px solid {ACCENT}",
            border_radius="14px",
        ),
    )


def error_block() -> rx.Component:
    return rx.cond(
        State.error != "",
        rx.hstack(
            rx.icon("circle-alert", size=18, color=DANGER),
            rx.text(State.error, size="2", color=TEXT, line_height="1.6"),
            spacing="2",
            align="center",
            width="100%",
            padding="0.9rem 1rem",
            background="rgba(255,107,94,0.12)",
            border=f"1px solid {DANGER}",
            border_radius="12px",
        ),
    )


def fixture_ribbon() -> rx.Component:
    # A module constant, not a Var: this is the first thing rendered on the page
    # and there is no reason to make it wait on state hydration.
    if not FIXTURE_MODE:
        return rx.fragment()
    return rx.hstack(
        rx.icon("flask-conical", size=15, color=MUTED),
        rx.text(
            "FIXTURE MODE — replaying a catalog snapshot, not calling Decathlon live. "
            "Unset CONCIERGE_FIXTURE_MODE for the real loop.",
            size="1",
            color=MUTED,
        ),
        spacing="2",
        align="center",
        width="100%",
        padding="0.5rem 0.8rem",
        background=PANEL_2,
        border=f"1px dashed {BORDER}",
        border_radius="8px",
    )
