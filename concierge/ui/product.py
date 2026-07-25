"""Product card and kit summary.

Every factual attribute on this card is read from a KitItem field. Model prose
lives in `rationale` and nowhere else — a specification the JSON does not carry
does not get rendered.
"""

from __future__ import annotations

import reflex as rx

from concierge.state import KitCard, State
from concierge.ui.theme import (  # noqa: F401
    ACCENT,
    ACCENT_DIM,
    BG,
    BORDER,
    BRAND,
    BRAND_DARK,
    BRAND_DEEP,
    DANGER,
    DANGER_BG,
    FONT,
    GREY_1,
    GREY_2,
    GREY_3,
    GREY_4,
    GUARDRAIL,
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
    RADIUS_SM,
    SUCCESS,
    SUCCESS_BG,
    TEXT,
    TINT_1,
    TINT_2,
    TINT_3,
    WARN,
    WARN_BG,
    WHITE,
)


def substituted_badge(item: KitCard) -> rx.Component:
    return rx.cond(
        item.size_substituted,
        rx.hstack(
            rx.icon("triangle-alert", size=14, color=INK),
            rx.text("SIZE SUBSTITUTED", size="1", weight="bold", color=INK),
            spacing="1",
            align="center",
            background=WARN,
            padding="0.3rem 0.6rem",
            border_radius=RADIUS_SM,
        ),
    )


def spec_row(label: str, value) -> rx.Component:
    return rx.hstack(
        rx.text(label, size="1", color=MUTED, letter_spacing="0.06em"),
        rx.spacer(),
        rx.text(value, size="2", weight="medium", color=TEXT),
        width="100%",
        align="center",
    )


def product_card(item: KitCard) -> rx.Component:
    return rx.vstack(
        rx.box(
            rx.cond(
                item.image_url != "",
                rx.image(
                    src=item.image_url,
                    alt=item.product_title,
                    width="100%",
                    height="100%",
                    object_fit="contain",
                    loading="lazy",
                ),
                rx.center(
                    rx.vstack(
                        rx.text(
                            "NO PHOTO IN CATALOG",
                            size="1",
                            weight="bold",
                            color=MUTED,
                            letter_spacing="0.1em",
                        ),
                        rx.text(
                            item.product_title,
                            size="2",
                            weight="medium",
                            color=TEXT,
                            text_align="center",
                            line_height="1.4",
                        ),
                        spacing="2",
                        align="center",
                    ),
                    width="100%",
                    height="100%",
                    padding="0.75rem",
                ),
            ),
            width="100%",
            height="210px",
            # The card is already white, so a photo needs no fill. The no-photo
            # branch does, or an empty white box reads as a broken image.
            background=rx.cond(item.image_url != "", WHITE, PANEL_2),
            border=rx.cond(
                item.image_url != "", f"1px solid {BORDER}", f"1px dashed {GREY_3}"
            ),
            border_radius=RADIUS_SM,
            overflow="hidden",
            padding="0.5rem",
        ),
        rx.text(
            item.slot_label,
            size="1",
            weight="bold",
            color=ACCENT,
            letter_spacing="0.1em",
        ),
        rx.link(
            rx.text(
                item.product_title,
                size="3",
                weight="bold",
                color=TEXT,
                line_height="1.35",
            ),
            href=item.product_url,
            is_external=True,
            text_decoration="none",
            _hover={"text_decoration": "underline"},
        ),
        substituted_badge(item),
        rx.vstack(
            # This is a shop: the price is the headline, not a spec row.
            rx.text(item.price_display, size="7", weight="bold", color=INK),
            spec_row("SIZE", item.size_label),
            spec_row("QTY", item.quantity_label),
            spacing="1",
            width="100%",
            padding_top="0.6rem",
            border_top=f"1px solid {BORDER}",
        ),
        rx.cond(
            item.rationale != "",
            rx.text(
                item.rationale,
                size="2",
                color=MUTED,
                line_height="1.6",
                font_style="italic",
            ),
        ),
        rx.link(
            rx.hstack(
                rx.text("View on Decathlon", size="2", weight="medium"),
                rx.icon("external-link", size=14),
                spacing="1",
                align="center",
            ),
            href=item.product_url,
            is_external=True,
            color=ACCENT,
            text_decoration="none",
            margin_top="auto",
            padding_top="0.5rem",
        ),
        spacing="2",
        align="start",
        padding="0.9rem",
        background=PANEL,
        border=f"1px solid {BORDER}",
        border_radius=RADIUS,
        height="100%",
        width="100%",
        _hover={"border_color": BRAND},
    )


def unservable_notice() -> rx.Component:
    return rx.cond(
        State.has_unservable,
        rx.vstack(
            rx.hstack(
                # The yellow is the surface, never the type: #FFCD4E text on a
                # pale-yellow wash is illegible on a projector.
                rx.icon("circle-slash", size=18, color=INK),
                rx.text(
                    "SLOTS I COULD NOT FILL",
                    size="2",
                    weight="bold",
                    color=INK,
                    letter_spacing="0.08em",
                ),
                spacing="2",
                align="center",
            ),
            rx.foreach(
                State.unservable_slots,
                lambda slot: rx.text(slot, size="2", color=TEXT, line_height="1.65"),
            ),
            spacing="2",
            align="start",
            width="100%",
            padding="1rem 1.15rem",
            background=WARN_BG,
            border=f"1px solid {WARN}",
            border_radius=RADIUS,
        ),
    )


def stat(label: str, value, color: str = TEXT) -> rx.Component:
    return rx.vstack(
        rx.text(label, size="1", color=MUTED, letter_spacing="0.08em"),
        rx.text(value, size="6", weight="bold", color=color),
        spacing="0",
        align="start",
    )


def budget_line() -> rx.Component:
    return rx.cond(
        State.has_budget,
        rx.cond(
            State.over_budget,
            rx.hstack(
                rx.icon("trending-up", size=18, color=DANGER),
                rx.text(
                    f"Over your {State.budget_display} budget by {State.budget_delta_display}. "
                    "Nothing has been swapped down to hit the number — tell me what to cut.",
                    size="2",
                    color=TEXT,
                    line_height="1.6",
                ),
                spacing="2",
                align="center",
                width="100%",
                padding="0.75rem 1rem",
                background=DANGER_BG,
                border=f"1px solid {DANGER}",
                border_radius=RADIUS,
            ),
            rx.hstack(
                rx.icon("check", size=18, color=SUCCESS),
                rx.text(
                    f"{State.budget_delta_display} under your {State.budget_display} budget.",
                    size="2",
                    color=TEXT,
                ),
                spacing="2",
                align="center",
                width="100%",
                padding="0.75rem 1rem",
                background=SUCCESS_BG,
                border=f"1px solid {SUCCESS}",
                border_radius=RADIUS,
            ),
        ),
    )


def kit_summary() -> rx.Component:
    return rx.vstack(
        rx.flex(
            stat("KIT TOTAL", State.total_display, INK),
            stat("ITEMS", State.item_count),
            stat("SIZE SUBSTITUTIONS", State.substitution_count, INK),
            rx.cond(State.has_budget, stat("BUDGET", State.budget_display, MUTED)),
            gap="2.5rem",
            wrap="wrap",
            width="100%",
        ),
        budget_line(),
        spacing="3",
        width="100%",
        padding="1.15rem",
        background=WHITE,
        border=f"1px solid {BORDER}",
        border_radius=RADIUS,
    )


def kit_grid() -> rx.Component:
    return rx.cond(
        State.has_kit,
        rx.vstack(
            kit_summary(),
            unservable_notice(),
            rx.grid(
                rx.foreach(State.cards, product_card),
                columns=rx.breakpoints(initial="1", sm="2", lg="3"),
                gap="1rem",
                width="100%",
            ),
            spacing="4",
            width="100%",
        ),
    )
