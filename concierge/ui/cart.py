"""Human-in-the-loop cart confirmation.

The button below is the only route to `confirm_cart`. The model cannot reach it.
"""

from __future__ import annotations

import reflex as rx

from concierge.state import FIXTURE_MODE, State
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


def _eyebrow(label, color: str = MUTED) -> rx.Component:
    return rx.text(label, size="1", weight="bold", color=color, letter_spacing=TRACK_EYEBROW)


def _stat(label: str, value, color: str = TEXT) -> rx.Component:
    return rx.vstack(
        _eyebrow(label),
        rx.text(
            value,
            size="6",
            weight="bold",
            color=color,
            letter_spacing=TRACK_TIGHT,
            line_height="1.1",
            class_name="db-num",
        ),
        spacing="1",
        align="start",
        min_width="5.5rem",
    )


def confirm_bar() -> rx.Component:
    return rx.cond(
        State.awaiting_confirmation & ~State.has_cart,
        rx.vstack(
            rx.hstack(
                rx.icon("shield-check", size=18, color=BRAND, flex_shrink="0"),
                rx.text(
                    "Nothing has been bought. DecaBot only creates a cart when you click.",
                    size="2",
                    weight="medium",
                    color=TEXT,
                    line_height="1.6",
                ),
                spacing="2",
                align="center",
            ),
            # Not a gate on the cart button — DECISIONS, 29 Jul.
            rx.cond(
                State.has_unconfirmed,
                rx.vstack(
                    rx.button(
                        rx.hstack(
                            rx.icon("pencil", size=17),
                            rx.text("Tell DecaBot my sizes", size="2", weight="bold"),
                            spacing="2",
                            align="center",
                        ),
                        on_click=rx.set_focus("db-composer"),
                        disabled=State.is_thinking,
                        variant="outline",
                        size="3",
                        width="100%",
                        min_height="44px",
                        cursor="pointer",
                        color=BRAND,
                        border_radius=RADIUS,
                        _hover={"background": TINT_2},
                    ),
                    rx.text(
                        State.unconfirmed_note,
                        size="1",
                        color=MUTED,
                        text_align="center",
                        width="100%",
                    ),
                    spacing="2",
                    width="100%",
                ),
            ),
            rx.button(
                rx.hstack(
                    rx.icon("shopping-cart", size=19),
                    rx.text("Build my cart at Decathlon", size="3", weight="bold"),
                    rx.text("·", size="3", opacity="0.5"),
                    rx.text(State.total_display, size="3", weight="bold", class_name="db-num"),
                    spacing="2",
                    align="center",
                ),
                on_click=State.confirm_cart,
                disabled=State.is_thinking,
                size="4",
                width="100%",
                cursor="pointer",
                background=BRAND,
                color=ON_BRAND,
                border_radius=RADIUS,
                box_shadow=SHADOW_BRAND,
                transition=f"background 160ms {EASE}, transform 160ms {EASE}",
                _hover={"background": BRAND_DARK, "transform": "translateY(-1px)"},
                _active={"transform": "translateY(0)"},
            ),
            rx.text(
                "The link opens Decathlon's own cart page. Payment happens there, never here.",
                size="1",
                color=MUTED,
                text_align="center",
                width="100%",
            ),
            spacing="3",
            width="100%",
            padding="1.15rem",
            background=f"linear-gradient(180deg, {WHITE} 0%, {TINT_1} 100%)",
            border=f"1px solid {TINT_3}",
            border_radius=RADIUS_LG,
            box_shadow=SHADOW_MD,
        ),
    )


def fixture_link_note() -> rx.Component:
    # A module constant, not a Var — same reason as fixture_ribbon below.
    if not FIXTURE_MODE:
        return rx.fragment()
    return rx.text(
        "Replayed link — it opens a real captured cart of one line, not the lines above.",
        size="1",
        color=WARN_INK,
        weight="medium",
        line_height="1.55",
    )


def cart_block() -> rx.Component:
    return rx.cond(
        State.has_cart,
        rx.vstack(
            rx.hstack(
                rx.icon("circle-check-big", size=20, color=SUCCESS, flex_shrink="0"),
                rx.text(
                    "Cart created at Decathlon",
                    size="4",
                    weight="bold",
                    color=SUCCESS,
                    letter_spacing=TRACK_TIGHT,
                ),
                spacing="2",
                align="center",
            ),
            rx.flex(
                _stat("CART TOTAL", State.cart_total_display),
                rx.box(width="1px", height="2.4rem", background=GREY_4, flex_shrink="0"),
                _stat("LINES", State.cart_line_count),
                gap="1.5rem",
                align="center",
                wrap="wrap",
            ),
            rx.link(
                rx.hstack(
                    rx.icon("external-link", size=20),
                    rx.text("Open my cart on Decathlon", size="4", weight="bold"),
                    spacing="3",
                    align="center",
                    justify="center",
                ),
                href=State.cart_url,
                is_external=True,
                width="100%",
                padding="1.05rem",
                background=BRAND,
                color=ON_BRAND,
                border_radius=RADIUS,
                box_shadow=SHADOW_BRAND,
                text_decoration="none",
                text_align="center",
                transition=f"background 160ms {EASE}, transform 160ms {EASE}",
                _hover={"background": BRAND_DARK, "transform": "translateY(-1px)"},
            ),
            rx.vstack(
                rx.text(
                    State.cart_url,
                    size="1",
                    color=MUTED,
                    font_family=MONO,
                    word_break="break-all",
                    line_height="1.6",
                ),
                rx.cond(
                    State.cart_expires_at != "",
                    rx.text(f"Expires {State.cart_expires_at}", size="1", color=MUTED, font_family=MONO),
                ),
                # The totals above are this kit's. The LINK is a replayed capture of a
                # one-line cart, and saying so here beats a judge clicking through and
                # finding the mismatch on Decathlon's own page.
                fixture_link_note(),
                spacing="1",
                align="start",
                width="100%",
                padding="0.7rem 0.8rem",
                background=TINT_1,
                border=f"1px dashed {TINT_3}",
                border_radius=RADIUS_SM,
            ),
            spacing="4",
            width="100%",
            padding="1.25rem",
            background=WHITE,
            # The cart landing is the end of the flow, so it is lifted off the page
            # rather than striped down one edge like every other callout was.
            border=f"1px solid {SUCCESS_BG}",
            border_top=f"3px solid {SUCCESS}",
            border_radius=RADIUS_LG,
            box_shadow=SHADOW_LG,
        ),
    )


def error_block() -> rx.Component:
    return rx.cond(
        State.error != "",
        rx.hstack(
            rx.center(
                rx.icon("circle-alert", size=15, color=WHITE),
                width="1.85rem",
                height="1.85rem",
                flex_shrink="0",
                background=DANGER,
                border_radius=RADIUS_SM,
            ),
            rx.text(State.error, size="2", color=TEXT, line_height="1.6"),
            spacing="3",
            align="center",
            width="100%",
            padding="0.85rem 1rem",
            background=DANGER_BG,
            border="1px solid rgba(215,3,34,0.25)",
            border_radius=RADIUS,
        ),
    )


def fixture_ribbon() -> rx.Component:
    # A module constant, not a Var: this is the first thing rendered on the page
    # and there is no reason to make it wait on state hydration.
    if not FIXTURE_MODE:
        return rx.fragment()
    return rx.hstack(
        rx.icon("flask-conical", size=15, color=INK, flex_shrink="0"),
        rx.text(
            "Fixture replay — DecaBot is reading a catalog snapshot, not calling Decathlon "
            "live. Unset CONCIERGE_FIXTURE_MODE for the real loop.",
            size="1",
            color=INK,
            line_height="1.55",
        ),
        spacing="2",
        align="center",
        width="100%",
        padding="0.55rem 0.8rem",
        background=WARN_BG,
        border=f"1px solid {WARN}",
        border_radius=RADIUS_SM,
    )
