"""Product card and kit summary.

Every factual attribute on this card is read from a KitItem field. Model prose
lives in `rationale` and nowhere else — a specification the JSON does not carry
does not get rendered.
"""

from __future__ import annotations

import reflex as rx

from concierge.state import KitCard, State
from concierge.ui.theme import (
    ACCENT,
    BORDER,
    DANGER,
    MUTED,
    PANEL,
    PANEL_2,
    TEXT,
    WARN,
)


def substituted_badge(item: KitCard) -> rx.Component:
    return rx.cond(
        item.size_substituted,
        rx.hstack(
            rx.icon("triangle-alert", size=14, color="#1a1200"),
            rx.text("SIZE SUBSTITUTED", size="1", weight="bold", color="#1a1200"),
            spacing="1",
            align="center",
            background=WARN,
            padding="0.3rem 0.6rem",
            border_radius="6px",
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
            height="200px",
            # White only behind a real cutout photo; an empty white box reads as a
            # broken image rather than a product that has none.
            background=rx.cond(item.image_url != "", "#ffffff", PANEL_2),
            border=rx.cond(item.image_url != "", "none", f"1px dashed {BORDER}"),
            border_radius="10px",
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
            spec_row("SIZE", item.size_label),
            spec_row("QTY", item.quantity_label),
            spec_row("PRICE", item.price_display),
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
        border_radius="14px",
        height="100%",
        width="100%",
    )


def unservable_notice() -> rx.Component:
    return rx.cond(
        State.has_unservable,
        rx.vstack(
            rx.hstack(
                rx.icon("circle-slash", size=18, color=WARN),
                rx.text(
                    "SLOTS I COULD NOT FILL",
                    size="2",
                    weight="bold",
                    color=WARN,
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
            background="rgba(255,176,32,0.09)",
            border=f"1px solid {WARN}",
            border_radius="12px",
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
                background="rgba(255,107,94,0.12)",
                border=f"1px solid {DANGER}",
                border_radius="10px",
            ),
            rx.hstack(
                rx.icon("check", size=18, color=ACCENT),
                rx.text(
                    f"{State.budget_delta_display} under your {State.budget_display} budget.",
                    size="2",
                    color=TEXT,
                ),
                spacing="2",
                align="center",
                width="100%",
                padding="0.75rem 1rem",
                background="rgba(61,220,151,0.10)",
                border=f"1px solid {ACCENT}",
                border_radius="10px",
            ),
        ),
    )


def kit_summary() -> rx.Component:
    return rx.vstack(
        rx.flex(
            stat("KIT TOTAL", State.total_display, ACCENT),
            stat("ITEMS", State.item_count),
            stat("SIZE SUBSTITUTIONS", State.substitution_count, WARN),
            rx.cond(State.has_budget, stat("BUDGET", State.budget_display, MUTED)),
            gap="2.5rem",
            wrap="wrap",
            width="100%",
        ),
        budget_line(),
        spacing="3",
        width="100%",
        padding="1.15rem",
        background=PANEL_2,
        border=f"1px solid {BORDER}",
        border_radius="14px",
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
