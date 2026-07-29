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
    TRACK_DISPLAY,
    TRACK_EYEBROW,
    TRACK_TIGHT,
    TRACK_TIGHTER,
    WARN,
    WARN_BG,
    WARN_INK,
    WHITE,
)


def _eyebrow(label, color: str = MUTED, **props) -> rx.Component:
    return rx.text(label, size="1", weight="bold", color=color, letter_spacing=TRACK_EYEBROW, **props)


def _chip(icon: str, label, fg: str = TEXT, bg: str = TINT_1, border: str = TINT_2) -> rx.Component:
    return rx.hstack(
        rx.icon(icon, size=12, color=fg, flex_shrink="0"),
        rx.text(label, size="1", weight="bold", color=fg, class_name="db-num"),
        spacing="1",
        align="center",
        padding="0.25rem 0.55rem",
        background=bg,
        border=f"1px solid {border}",
        border_radius=RADIUS_PILL,
        flex_shrink="0",
    )


def _photo_badge(icon: str, label: str, fg: str, bg: str) -> rx.Component:
    return rx.hstack(
        rx.icon(icon, size=12, color=fg, flex_shrink="0"),
        rx.text(label, size="1", weight="bold", color=fg, letter_spacing="0.06em"),
        spacing="1",
        align="center",
        position="absolute",
        top="0.55rem",
        left="0.55rem",
        # Bounded, not stretched. `right` would over-constrain the box and paint a
        # full-width banner across the photo instead of a badge.
        max_width="calc(100% - 1.1rem)",
        z_index="1",
        background=bg,
        padding="0.25rem 0.5rem",
        border_radius=RADIUS_PILL,
        box_shadow=SHADOW_SM,
    )


def size_badge(item: KitCard) -> rx.Component:
    """Sits on the photo, because the size is the one thing on this card a buyer
    must not be able to scroll past.

    Two different states, deliberately two different colours. A SUBSTITUTION is a
    fault we already committed — amber, the warning surface. An UNCONFIRMED size is
    an open question we are asking — brand blue, the same hue as every other thing
    DecaBot wants an answer about. Painting both amber would tell the customer we
    got something wrong when all we did was not know yet.

    They are mutually exclusive by construction: `size_substituted` can only be
    true when a size WAS requested, which is exactly when `size_confirmed` is true.
    """
    return rx.cond(
        item.size_substituted,
        _photo_badge("triangle-alert", "SIZE SUBSTITUTED", INK, WARN),
        rx.cond(
            ~item.size_confirmed,
            _photo_badge("circle-help", "WHAT SIZE ARE YOU?", ON_BRAND, BRAND),
        ),
    )


def product_card(item: KitCard) -> rx.Component:
    return rx.vstack(
        rx.box(
            size_badge(item),
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
                        rx.icon("image-off", size=20, color=GREY_3),
                        _eyebrow("NO PHOTO IN CATALOG", MUTED),
                        spacing="2",
                        align="center",
                    ),
                    width="100%",
                    height="100%",
                    padding="0.75rem",
                ),
            ),
            position="relative",
            width="100%",
            height="196px",
            # A tint behind the photo instead of a second border: the card already
            # has a frame, and an empty white box reads as a broken image.
            background=TINT_1,
            border_radius=RADIUS_SM,
            overflow="hidden",
            padding="0.6rem",
            flex_shrink="0",
        ),
        rx.link(
            rx.text(
                item.product_title,
                size="4",
                weight="bold",
                color=TEXT,
                line_height="1.3",
                letter_spacing=TRACK_TIGHT,
                class_name="db-clamp-2",
                min_height="2.6em",
            ),
            href=item.product_url,
            is_external=True,
            text_decoration="none",
            width="100%",
            padding_top="0.15rem",
            _hover={"color": BRAND},
        ),
        # The slot used to sit above the title as a kicker. It is real information —
        # which requirement of the trip this product answers — so it moved down to
        # stand with the card's other facts as one more piece of data, instead of
        # announcing the heading.
        rx.flex(
            _chip("shapes", item.slot_label, BRAND, TINT_1, TINT_2),
            # The chip changes state rather than moving: a guessed size sits in
            # exactly the same place as a chosen one, tinted brand instead of
            # neutral, so scanning a grid of cards shows which rows are answered.
            rx.cond(
                item.size_confirmed,
                _chip("ruler", item.size_label),
                _chip("ruler", item.size_label, BRAND, TINT_2, TINT_3),
            ),
            rx.cond(item.quantity > 1, _chip("x", item.quantity_label)),
            gap="0.35rem",
            wrap="wrap",
            width="100%",
        ),
        rx.hstack(
            # This is a shop: the price is the headline, not a spec row.
            rx.text(
                item.price_display,
                size="7",
                weight="bold",
                color=INK,
                letter_spacing=TRACK_TIGHTER,
                class_name="db-num",
                line_height="1",
            ),
            width="100%",
            align="center",
            padding_top="0.7rem",
            border_top=f"1px solid {HAIRLINE}",
        ),
        rx.cond(
            item.rationale != "",
            rx.text(
                item.rationale,
                size="2",
                color=MUTED,
                line_height="1.6",
                padding_left="0.7rem",
                border_left=f"2px solid {TINT_3}",
            ),
        ),
        rx.link(
            rx.hstack(
                rx.text("View on Decathlon", size="2", weight="bold"),
                rx.icon("arrow-up-right", size=14),
                spacing="1",
                align="center",
            ),
            href=item.product_url,
            is_external=True,
            color=ACCENT,
            text_decoration="none",
            margin_top="auto",
            padding_top="0.6rem",
            _hover={"text_decoration": "underline"},
        ),
        spacing="3",
        align="start",
        padding="0.75rem 0.9rem 0.9rem",
        background=PANEL,
        border=f"1px solid {BORDER}",
        border_radius=RADIUS,
        box_shadow=SHADOW_XS,
        height="100%",
        width="100%",
        transition=f"transform 180ms {EASE}, box-shadow 180ms {EASE}, border-color 180ms {EASE}",
        _hover={"border_color": TINT_3, "box_shadow": SHADOW_MD, "transform": "translateY(-3px)"},
    )


# Every caveat that qualifies the total is one of these. A filled medallion plus
# the row's own surface carries the tone — five differently-coloured left borders
# gave a substitution, an error and a budget line the same shape in a new hue, so
# nothing on the page had structure, only colour.
def _disclosure(icon: str, fg: str, medallion: str, bg: str, body: rx.Component) -> rx.Component:
    return rx.hstack(
        rx.center(
            rx.icon(icon, size=15, color=fg),
            width="1.85rem",
            height="1.85rem",
            flex_shrink="0",
            background=medallion,
            border_radius=RADIUS_SM,
        ),
        body,
        spacing="3",
        align="start",
        width="100%",
        padding="0.7rem 0.85rem",
        background=bg,
        border_radius=RADIUS_SM,
    )


def unservable_notice() -> rx.Component:
    return rx.cond(
        State.has_unservable,
        _disclosure(
            # The yellow is the surface, never the type: #FFCD4E text on a
            # pale-yellow wash is illegible on a projector.
            "circle-slash",
            INK,
            WARN,
            WARN_BG,
            rx.vstack(
                rx.text(
                    "DecaBot could not fill every slot.",
                    size="2",
                    weight="bold",
                    color=INK,
                    line_height="1.5",
                ),
                rx.foreach(
                    State.unservable_slots,
                    lambda slot: rx.text(slot, size="2", color=TEXT, line_height="1.6"),
                ),
                spacing="1",
                align="start",
                width="100%",
            ),
        ),
    )


def stat(label: str, value, color: str = TEXT) -> rx.Component:
    return rx.vstack(
        _eyebrow(label),
        rx.text(
            value,
            size="5",
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


def budget_line() -> rx.Component:
    return rx.cond(
        State.has_budget,
        rx.cond(
            State.over_budget,
            _disclosure(
                "trending-up",
                WHITE,
                DANGER,
                DANGER_BG,
                rx.text(
                    f"Over your {State.budget_display} budget by {State.budget_delta_display}. "
                    "Nothing has been swapped down to hit the number — tell me what to cut.",
                    size="2",
                    color=TEXT,
                    line_height="1.6",
                ),
            ),
            _disclosure(
                "check",
                WHITE,
                SUCCESS,
                SUCCESS_BG,
                rx.text(
                    f"{State.budget_delta_display} under your {State.budget_display} budget.",
                    size="2",
                    color=TEXT,
                    line_height="1.6",
                ),
            ),
        ),
    )


def size_prompt() -> rx.Component:
    """The kit-level counterpart to the per-card badge. `check_size_confirmation`
    already says this in prose, but prose scrolls away and the cart button does not."""
    return rx.cond(
        State.has_unconfirmed,
        _disclosure(
            "ruler",
            ON_BRAND,
            BRAND,
            TINT_2,
            rx.text(
                State.unconfirmed_subject,
                " in a size I picked for you. "
                "Tell me your size and I'll swap it — the cart can still change.",
                size="2",
                color=TEXT,
                line_height="1.6",
            ),
        ),
    )


def kit_summary() -> rx.Component:
    """The bill, not a dashboard tile row.

    This is the moment a shopper decides to spend four figures, so the total is
    set at display scale and everything else is subordinate to it: the counts read
    as a ledger strip underneath, and every caveat that qualifies the number —
    unfilled slots, guessed sizes, an overrun — sits inside the same object rather
    than scattered down the page. The cards below are the line items.
    """
    return rx.vstack(
        rx.vstack(
            rx.hstack(
                _eyebrow("KIT TOTAL"),
                rx.spacer(),
                # Every KitItem is `available: Literal[True]` and size-resolved by
                # the time it reaches here, so this claim is structural, not a
                # promise. SUCCESS_DEEP, not SUCCESS: on its own 10% tint the
                # brighter green is 4.08:1, under AA for type this small.
                _chip("circle-check-big", "IN STOCK", SUCCESS_DEEP, SUCCESS_BG, "transparent"),
                width="100%",
                align="center",
            ),
            rx.text(
                State.total_display,
                size="9",
                weight="bold",
                color=INK,
                letter_spacing=TRACK_DISPLAY,
                line_height="1",
                class_name="db-num",
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        rx.flex(
            stat("ITEMS", State.item_count),
            # These two were rendered unconditionally and read 0 on almost every
            # run. A stat that is always zero trains people to stop reading the row,
            # which is the opposite of what a disclosure is for — so each appears
            # only when it has something to disclose.
            rx.cond(
                State.substitution_count > 0,
                stat("SIZE SWAPS", State.substitution_count, WARN_INK),
            ),
            rx.cond(
                State.has_unconfirmed,
                stat("SIZES TO CONFIRM", State.unconfirmed_count, BRAND),
            ),
            rx.cond(State.has_budget, stat("BUDGET", State.budget_display, MUTED)),
            gap="0.9rem 2.2rem",
            align="start",
            wrap="wrap",
            width="100%",
            padding_top="0.95rem",
            border_top=f"1px solid {BORDER}",
        ),
        rx.vstack(
            unservable_notice(),
            size_prompt(),
            budget_line(),
            spacing="2",
            width="100%",
        ),
        spacing="4",
        width="100%",
        padding="1.35rem 1.4rem",
        background=WHITE,
        border=f"1px solid {BORDER}",
        border_radius=RADIUS_LG,
        box_shadow=SHADOW_MD,
    )


def _card_with_heading(card: KitCard) -> rx.Component:
    """`rx.fragment` leaves no DOM node, so the heading and the card both land as direct
    children of the grid — the heading spanning every column, which starts the next
    person on a fresh row."""
    return rx.fragment(
        rx.cond(
            card.person_heading != "",
            rx.hstack(
                rx.icon("user", size=14, color=GREY_3, flex_shrink="0"),
                # nowrap because the separator's flex_grow otherwise takes the row and
                # breaks a two-word label over two lines.
                _eyebrow(card.person_heading, white_space="nowrap", flex_shrink="0"),
                rx.separator(flex_grow="1"),
                spacing="2",
                align="center",
                width="100%",
                grid_column="1 / -1",
                padding_top="0.35rem",
            ),
        ),
        product_card(card),
    )


def kit_grid() -> rx.Component:
    return rx.cond(
        State.has_kit,
        rx.vstack(
            kit_summary(),
            rx.grid(
                rx.foreach(State.cards, _card_with_heading),
                # `lg` is the same breakpoint at which the 384px audit rail moves
                # beside this column, so three cards here were being asked to share
                # what was left of a 1024px viewport — roughly 200px each, with the
                # product title clamped to two lines of nothing. Three columns wait
                # for xl, where the space actually exists.
                columns=rx.breakpoints(initial="1", sm="2", lg="2", xl="3"),
                gap="0.9rem",
                width="100%",
            ),
            spacing="4",
            width="100%",
            class_name="db-kit",
        ),
    )
