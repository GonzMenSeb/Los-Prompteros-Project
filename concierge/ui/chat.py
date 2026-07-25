from __future__ import annotations

import reflex as rx

from concierge.state import ChatMessage, State
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


def citation_link(c) -> rx.Component:
    return rx.link(
        rx.hstack(
            rx.icon("link", size=13, color=ACCENT),
            rx.text(c.title, size="1", color=ACCENT, no_of_lines=1),
            spacing="1",
            align="center",
        ),
        href=c.url,
        is_external=True,
        text_decoration="none",
        padding="0.3rem 0.6rem",
        border=f"1px solid {BORDER}",
        border_radius=RADIUS_SM,
        background=PANEL_2,
        _hover={"border_color": ACCENT},
    )


def citations(m) -> rx.Component:
    return rx.cond(
        m.citations.length() > 0,
        rx.vstack(
            rx.text(
                "SOURCES — GROUNDED WEB SEARCH",
                size="1",
                weight="bold",
                color=MUTED,
                letter_spacing="0.08em",
            ),
            rx.flex(
                rx.foreach(m.citations, citation_link),
                wrap="wrap",
                gap="0.4rem",
            ),
            spacing="2",
            align="start",
            width="100%",
            margin_top="0.9rem",
            padding_top="0.9rem",
            border_top=f"1px solid {BORDER}",
        ),
    )


def bubble(m: ChatMessage) -> rx.Component:
    is_user = m.role == "user"
    return rx.box(
        rx.vstack(
            rx.text(
                rx.cond(is_user, "YOU", "CONCIERGE"),
                size="1",
                weight="bold",
                letter_spacing="0.1em",
                color=rx.cond(is_user, MUTED, ACCENT),
            ),
            # The research and presentation stages answer in markdown — headings, bold,
            # bullet lists — and `rx.text` renders the syntax literally, so the
            # conditions report reached the demo screen as "### ... **Elevation**".
            #
            # User content is never handed to rx.markdown. Reflex's markdown pulls in
            # rehype-raw, so passing untrusted text through it would let a typed
            # <img onerror=...> reach the DOM. Plain text for the user, markdown only
            # for our own model output.
            #
            # Known, benign: rx.markdown carries `useContext`, and rx.foreach hoists
            # each bubble's hooks into the list render, so appending a message changes
            # the parent's hook COUNT and React dev mode logs "change in the order of
            # Hooks". Verified across a full walkthrough — 6 messages, 10 product cards,
            # a created cart — with no render breakage. Reverting to rx.text silences it
            # at the cost of literal "### " and "**" on the demo screen.
            rx.cond(
                is_user,
                rx.text(m.content, size="3", color=TEXT, white_space="pre-wrap", line_height="1.65"),
                rx.box(
                    rx.markdown(m.content),
                    color=TEXT,
                    width="100%",
                    font_size="var(--font-size-3)",
                    line_height="1.65",
                ),
            ),
            citations(m),
            spacing="2",
            align="start",
            width="100%",
        ),
        width="100%",
        padding="1rem 1.15rem",
        border_radius=RADIUS,
        background=rx.cond(is_user, PANEL_2, PANEL),
        border=f"1px solid {BORDER}",
        border_left=rx.cond(is_user, f"1px solid {BORDER}", f"3px solid {ACCENT}"),
    )


def thinking() -> rx.Component:
    return rx.cond(
        State.is_thinking,
        rx.hstack(
            rx.spinner(size="2"),
            rx.text(State.status, size="2", color=MUTED),
            spacing="3",
            align="center",
            padding="0.9rem 1.15rem",
            border_radius=RADIUS,
            background=PANEL,
            border=f"1px solid {BORDER}",
            width="100%",
        ),
    )


def composer() -> rx.Component:
    return rx.form(
        rx.hstack(
            rx.input(
                name="message",
                placeholder="Hiking to Páramo de Santurbán with my girlfriend, camping two nights…",
                size="3",
                width="100%",
                disabled=State.is_thinking,
                background=PANEL_2,
                color=TEXT,
            ),
            rx.button(
                rx.icon("send-horizontal", size=18),
                type="submit",
                size="3",
                disabled=State.is_thinking,
                cursor="pointer",
                background=BRAND,
                color=ON_BRAND,
                border_radius=RADIUS_SM,
                _hover={"background": BRAND_DARK},
            ),
            spacing="2",
            width="100%",
        ),
        on_submit=State.send_message,
        reset_on_submit=True,
        width="100%",
    )


def empty_state() -> rx.Component:
    return rx.cond(
        State.messages.length() == 0,
        rx.vstack(
            rx.icon("mountain-snow", size=44, color=ACCENT),
            rx.heading("Describe the expedition.", size="6", color=TEXT),
            rx.text(
                "Where you are going, who is going, and how long for. I research the "
                "conditions, work out what the trip demands, and fill each slot with a "
                "real Decathlon product that is in stock in your size — or tell you "
                "plainly when it is not.",
                size="3",
                color=MUTED,
                text_align="center",
                max_width="46ch",
                line_height="1.7",
            ),
            spacing="3",
            align="center",
            padding="3rem 1rem",
            width="100%",
        ),
    )


def chat_panel() -> rx.Component:
    return rx.vstack(
        empty_state(),
        rx.foreach(State.messages, bubble),
        thinking(),
        spacing="3",
        width="100%",
        align="start",
    )
