"""The password screen.

One field, no username. It is the whole page when the app is locked, so it carries
the identity rather than apologising for standing in the way: DecaBot's own mark on
the brand gradient, and a plain statement of why a public URL has a lock on it.
"""

from __future__ import annotations

import reflex as rx

from concierge.state import State
from concierge.ui import brand
from concierge.ui.theme import (
    BRAND,
    BRAND_DARK,
    BRAND_DEEP,
    DANGER,
    EASE,
    FOCUS_RING,
    GREY_2,
    MUTED,
    ON_BRAND,
    RADIUS,
    RADIUS_LG,
    RADIUS_PILL,
    SHADOW_LG,
    SHADOW_SM,
    TEXT,
    TINT_2,
    TINT_3,
    TRACK_EYEBROW,
    TRACK_TIGHTER,
    WHITE,
)


def _field() -> rx.Component:
    return rx.hstack(
        rx.icon("lock-keyhole", size=17, color=GREY_2, flex_shrink="0"),
        rx.input(
            name="password",
            type=rx.cond(State.gate_reveal, "text", "password"),
            placeholder="Password",
            auto_focus=True,
            disabled=State.gate_busy,
            size="3",
            width="100%",
            background="transparent",
            color=TEXT,
            font_size="1rem",
        ),
        rx.button(
            rx.icon(rx.cond(State.gate_reveal, "eye-off", "eye"), size=16),
            on_click=State.toggle_reveal,
            # A reveal toggle inside a form submits it unless it opts out.
            type="button",
            variant="ghost",
            size="2",
            cursor="pointer",
            color=GREY_2,
            flex_shrink="0",
            _hover={"color": BRAND, "background": TINT_2},
        ),
        spacing="2",
        width="100%",
        align="center",
        class_name="db-dock",
        padding="0.45rem 0.6rem 0.45rem 0.85rem",
        background=WHITE,
        # An f-string over a Var stringifies the Var object, so the whole declaration
        # has to be the branch rather than just the colour.
        border=rx.cond(State.gate_error != "", f"1px solid {DANGER}", f"1px solid {TINT_3}"),
        border_radius=RADIUS_LG,
        box_shadow=SHADOW_SM,
        transition=f"border-color 160ms {EASE}, box-shadow 160ms {EASE}",
        _focus_within={"border_color": BRAND, "box_shadow": FOCUS_RING},
    )


def _error() -> rx.Component:
    return rx.cond(
        State.gate_error != "",
        rx.hstack(
            rx.icon("circle-alert", size=14, color=DANGER, flex_shrink="0"),
            rx.text(State.gate_error, size="2", color=DANGER, weight="medium"),
            spacing="2",
            align="center",
            width="100%",
        ),
    )


def _card() -> rx.Component:
    # The animated class sits on this box, not on the form: rx.form is a Radix
    # *primitive*, and its _render does `self.class_name or ''`, which raises on a Var.
    return rx.box(
        _form(),
        width="100%",
        max_width="27rem",
        padding=["1.75rem 1.35rem", "2.25rem 2rem", "2.5rem 2.25rem"],
        background=WHITE,
        border_radius="18px",
        box_shadow=SHADOW_LG,
        class_name=rx.cond(State.gate_error != "", "db-shake", "db-rise"),
    )


def _form() -> rx.Component:
    return rx.form(
        rx.vstack(
            brand.mark(size="3.2rem", glyph=27, dot=False),
            rx.vstack(
                brand.wordmark(size="1.75rem"),
                rx.text(
                    "Decathlon expedition concierge",
                    size="1",
                    weight="bold",
                    color=MUTED,
                    letter_spacing=TRACK_EYEBROW,
                ),
                spacing="2",
                align="center",
            ),
            rx.text(
                "This demo builds real carts against Decathlon's live catalog, so it runs "
                "behind a password. Enter it to continue.",
                size="2",
                color=MUTED,
                text_align="center",
                max_width="38ch",
                line_height="1.65",
            ),
            rx.vstack(
                _field(),
                _error(),
                rx.button(
                    rx.cond(
                        State.gate_busy,
                        rx.hstack(
                            rx.spinner(size="2", color=ON_BRAND),
                            rx.text("Checking…", size="2", weight="bold"),
                            spacing="2",
                            align="center",
                        ),
                        rx.hstack(
                            rx.text("Enter", size="2", weight="bold"),
                            rx.icon("arrow-right", size=16),
                            spacing="2",
                            align="center",
                        ),
                    ),
                    type="submit",
                    size="3",
                    disabled=State.gate_busy,
                    cursor="pointer",
                    width="100%",
                    background=BRAND,
                    color=ON_BRAND,
                    border_radius=RADIUS,
                    transition=f"background 160ms {EASE}, transform 170ms {EASE}",
                    _hover={"background": BRAND_DARK, "transform": "translateY(-1px)"},
                ),
                spacing="3",
                width="100%",
            ),
            spacing="5",
            align="center",
            width="100%",
        ),
        on_submit=State.unlock,
        reset_on_submit=True,
        width="100%",
    )


def screen() -> rx.Component:
    return rx.center(
        rx.vstack(
            _card(),
            rx.hstack(
                rx.text("Los Prompteros", size="1", weight="bold", color="rgba(255,255,255,0.82)"),
                rx.box(
                    width="3px",
                    height="3px",
                    border_radius=RADIUS_PILL,
                    background="rgba(255,255,255,0.4)",
                ),
                rx.text(
                    "AgentSprint · Universidad EAFIT",
                    size="1",
                    color="rgba(255,255,255,0.62)",
                ),
                spacing="2",
                align="center",
            ),
            spacing="6",
            align="center",
            width="100%",
        ),
        width="100%",
        min_height="100vh",
        padding="1.25rem",
        # The locked page is the one surface that is not storefront chrome, so it goes
        # full brand instead of the app's near-white. The radial sits over the gradient
        # to keep the card from floating on a flat wash.
        background=(
            f"radial-gradient(1100px 620px at 50% -12%, {BRAND} 0%, transparent 62%), "
            f"linear-gradient(168deg, {BRAND_DARK} 0%, {BRAND_DEEP} 58%, #1E2459 100%)"
        ),
        background_attachment="fixed",
        letter_spacing=TRACK_TIGHTER,
    )
