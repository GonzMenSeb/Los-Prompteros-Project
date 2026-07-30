from __future__ import annotations

import reflex as rx

from concierge.state import ChatMessage, State
from concierge.ui import brand
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

# Three openings a judge can click instead of typing. Each is a trip Decathlon
# genuinely stocks for — an example that dead-ends is worse than no example.
EXAMPLES: tuple[tuple[str, str, str], ...] = (
    (
        "mountain-snow",
        "Two nights in the páramo",
        "we're hiking to Páramo de Santurbán with my girlfriend, camping two nights",
    ),
    (
        "footprints",
        "First trail half-marathon",
        "I'm training for a 21k trail race in Medellín, running four mornings a week",
    ),
    (
        "bike",
        "Rainy bike commute",
        "I want to start bike-commuting 8km each way in Medellín, rain included",
    ),
)


def _attribution(label: str, color: str = MUTED) -> rx.Component:
    """Who is speaking. Not an eyebrow — sentence case, no tracking: a transcript
    needs attribution, but two ALL-CAPS labels per exchange is just noise."""
    return rx.text(label, size="1", weight="bold", color=color)


def citation_link(c) -> rx.Component:
    return rx.link(
        rx.hstack(
            rx.icon("link", size=12, color=ACCENT),
            rx.text(c.title, size="1", color=ACCENT, weight="medium", no_of_lines=1),
            spacing="1",
            align="center",
        ),
        href=c.url,
        is_external=True,
        text_decoration="none",
        padding="0.3rem 0.65rem",
        border=f"1px solid {TINT_3}",
        border_radius=RADIUS_PILL,
        background=TINT_1,
        transition=f"background 160ms {EASE}, border-color 160ms {EASE}",
        _hover={"background": TINT_2, "border_color": BRAND},
    )


def citations(m) -> rx.Component:
    return rx.cond(
        m.citations.length() > 0,
        rx.vstack(
            # The provenance claim is real and stays, but it is a caption on the
            # chips below it, not a heading over a section.
            rx.text("Grounded on live web search", size="1", color=MUTED),
            rx.flex(
                rx.foreach(m.citations, citation_link),
                wrap="wrap",
                gap="0.4rem",
            ),
            spacing="2",
            align="start",
            width="100%",
            margin_top="1rem",
            padding_top="0.9rem",
            border_top=f"1px solid {HAIRLINE}",
        ),
    )


def _user_bubble(m: ChatMessage) -> rx.Component:
    return rx.box(
        rx.vstack(
            _attribution("You"),
            rx.text(m.content, size="3", color=TEXT, white_space="pre-wrap", line_height="1.65"),
            spacing="2",
            align="start",
            width="100%",
        ),
        width="100%",
        padding="0.9rem 1.1rem",
        border_radius=RADIUS,
        background=TINT_1,
        border=f"1px solid {TINT_2}",
    )


def _bot_bubble(m: ChatMessage) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                brand.mark(size="1.3rem", glyph=13, dot=False),
                _attribution("DecaBot", BRAND),
                spacing="2",
                align="center",
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
            rx.box(
                rx.markdown(m.content),
                class_name="db-md",
                color=TEXT,
                width="100%",
                font_size="var(--font-size-3)",
            ),
            citations(m),
            spacing="3",
            align="start",
            width="100%",
        ),
        width="100%",
        padding="1.1rem 1.25rem",
        border_radius=RADIUS,
        # DecaBot speaks from a raised white panel, the user from a flat tint. The
        # two roles are told apart by elevation now — the blue stripe down the edge
        # was the same device the errors, the budget and the cart were all using.
        background=PANEL,
        border=f"1px solid {BORDER}",
        box_shadow=SHADOW_SM,
    )


def bubble(m: ChatMessage) -> rx.Component:
    return rx.cond(m.role == "user", _user_bubble(m), _bot_bubble(m))


def _waiting(accent: str, background: str, border: str, note: str = "") -> rx.Component:
    # WARN is #FFCD4E — it carries the rule and the wash; the words stay on TEXT/MUTED,
    # which is the only way it passes contrast.
    lines = [rx.text(State.status, size="2", color=TEXT, weight="medium")]
    if note:
        lines.append(rx.text(note, size="1", color=MUTED))
    return rx.hstack(
        rx.spinner(size="2", color=accent),
        rx.vstack(*lines, spacing="1", align="start"),
        # A turn runs for a minute or more and `status` changes several times
        # inside it. Without a live region that whole minute is silent.
        role="status",
        aria_live="polite",
        spacing="3",
        align="center",
        padding="0.85rem 1.15rem",
        border_radius=RADIUS,
        background=background,
        border=f"1px solid {border}",
        border_left=f"3px solid {accent}",
        box_shadow=SHADOW_SM,
        width="100%",
    )


def thinking() -> rx.Component:
    """The throttled variant exists because a backoff is a wait the user must not read
    as a hang: `catalog._get` can sit on a retry for seconds, and a spinner still
    saying "Reading the conditions…" is a lie about what the app is doing. It also
    promises nothing — no countdown — because neither Decathlon surface gives us a
    wait time worth quoting (AGENTS.md, rate limits)."""
    return rx.cond(
        State.is_thinking,
        rx.cond(
            State.throttled,
            _waiting(WARN, WARN_BG, WARN, "Still working — this just takes longer."),
            _waiting(BRAND, WHITE, TINT_3),
        ),
    )


def composer() -> rx.Component:
    return rx.form(
        rx.hstack(
            rx.input(
                name="message",
                id="db-composer",
                placeholder="Describe the trip — where, who with, how long…",
                size="3",
                width="100%",
                disabled=State.is_thinking,
                background="transparent",
                color=TEXT,
                font_size="1rem",
                # A placeholder is not a label: it disappears the moment you type,
                # and a screen reader announces the field as unnamed.
                aria_label="Describe the trip — where, who with, how long",
            ),
            rx.button(
                rx.icon("send-horizontal", size=17),
                # The word is hidden below md, which left an unnamed icon button on
                # exactly the viewport where a demo audience holds the QR code.
                rx.text("Send", size="2", weight="bold", display=["none", "none", "block"]),
                aria_label="Send",
                type="submit",
                size="3",
                disabled=State.is_thinking,
                cursor="pointer",
                background=BRAND,
                color=ON_BRAND,
                border_radius=RADIUS,
                padding_x="1.1rem",
                flex_shrink="0",
                transition=f"background 160ms {EASE}",
                _hover={"background": BRAND_DARK},
            ),
            spacing="2",
            width="100%",
            align="center",
        ),
        on_submit=State.send_message,
        reset_on_submit=True,
        width="100%",
        class_name="db-dock",
        padding="0.5rem 0.5rem 0.5rem 0.65rem",
        background=WHITE,
        border=f"1px solid {GREY_3}",
        border_radius=RADIUS_LG,
        box_shadow=SHADOW_SM,
        transition=f"border-color 160ms {EASE}, box-shadow 160ms {EASE}",
        _focus_within={"border_color": BRAND, "box_shadow": FOCUS_RING},
    )


def _primary_example(icon: str, label: str, prompt: str) -> rx.Component:
    # rx.button rather than a clickable box: Enter and Space have to work.
    return rx.button(
        rx.hstack(
            rx.icon(icon, size=26, color=ON_BRAND, flex_shrink="0"),
            rx.vstack(
                rx.text(label, size="5", weight="bold", color=ON_BRAND, line_height="1.25"),
                # TINT_3 on BRAND is 5.6:1. Secondary type on a coloured surface is
                # tinted from that surface, never greyed.
                rx.text(prompt, size="2", color=TINT_3, line_height="1.5"),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.icon("arrow-right", size=20, color=ON_BRAND, flex_shrink="0"),
            spacing="4",
            align="center",
            width="100%",
        ),
        on_click=State.send_example(prompt),
        disabled=State.is_thinking,
        cursor="pointer",
        width="100%",
        height="auto",
        justify_content="flex-start",
        padding="1.15rem 1.3rem",
        text_align="left",
        background=f"linear-gradient(140deg, {BRAND} 0%, {BRAND_DEEP} 100%)",
        border_radius=RADIUS_LG,
        box_shadow=SHADOW_BRAND,
        transition=f"transform 200ms {EASE}, box-shadow 200ms {EASE}",
        _hover={"box_shadow": SHADOW_LG, "transform": "translateY(-3px)"},
        _active={"transform": "translateY(0)"},
    )


def _example(icon: str, label: str, prompt: str) -> rx.Component:
    return rx.button(
        rx.vstack(
            rx.icon(icon, size=17, color=BRAND, flex_shrink="0"),
            rx.text(label, size="2", weight="bold", color=TEXT, line_height="1.3"),
            rx.text(prompt, size="1", color=MUTED, line_height="1.45", no_of_lines=2),
            spacing="2",
            align="start",
            width="100%",
        ),
        on_click=State.send_example(prompt),
        disabled=State.is_thinking,
        cursor="pointer",
        width="100%",
        height="auto",
        justify_content="flex-start",
        padding="0.85rem 0.95rem",
        text_align="left",
        background=WHITE,
        border=f"1px solid {BORDER}",
        border_radius=RADIUS,
        box_shadow=SHADOW_XS,
        transition=f"transform 170ms {EASE}, box-shadow 170ms {EASE}, border-color 170ms {EASE}",
        _hover={"border_color": BRAND, "box_shadow": SHADOW_MD, "transform": "translateY(-2px)"},
    )


def empty_state() -> rx.Component:
    return rx.cond(
        State.messages.length() == 0,
        rx.vstack(
            brand.mark(size="3.4rem", glyph=28),
            rx.vstack(
                rx.heading(
                    "Describe the expedition.",
                    # h2, not the default h1. This block is unmounted the moment the
                    # first message lands, so as an h1 it took the page's only
                    # top-level heading with it. app.py owns the persistent h1.
                    as_="h2",
                    color=TEXT,
                    font_size=["2.5rem", "3rem", "4.25rem"],
                    font_weight="800",
                    line_height="0.98",
                    letter_spacing=TRACK_DISPLAY,
                    class_name="db-balance",
                ),
                rx.text(
                    "Where you are going, who is going, and how long for. DecaBot researches "
                    "the conditions, works out what the trip demands, and fills each slot with "
                    "a real Decathlon product that is in stock in your size — or says plainly "
                    "when it is not.",
                    size="3",
                    color=MUTED,
                    max_width="68ch",
                    line_height="1.7",
                ),
                # Turn one is ~52 s of measured model latency and ran 80 s in one live
                # bundle. Nothing said so, so the only evidence a first-timer had that
                # waiting was correct behaviour was a spinner.
                rx.hstack(
                    rx.icon("clock", size=14, color=MUTED, flex_shrink="0"),
                    rx.text(
                        "The first answer takes about a minute — it researches the real "
                        "conditions before it picks anything.",
                        size="2",
                        color=MUTED,
                        line_height="1.5",
                    ),
                    spacing="2",
                    align="center",
                ),
                spacing="4",
                align="start",
                width="100%",
            ),
            # One primary path and two alternates. Three equal cards made the choice
            # look like a menu with no recommendation; the páramo trip is the one
            # that exercises every honesty affordance, so it leads.
            rx.vstack(
                _primary_example(*EXAMPLES[0]),
                rx.grid(
                    *[_example(*e) for e in EXAMPLES[1:]],
                    columns=rx.breakpoints(initial="1", sm="2"),
                    gap="0.7rem",
                    width="100%",
                ),
                spacing="3",
                align="start",
                width="100%",
            ),
            spacing="6",
            align="start",
            width="100%",
            padding=["1.5rem 0", "1.5rem 0", "2.5rem 0 1rem"],
        ),
    )


def chat_panel() -> rx.Component:
    return rx.vstack(
        empty_state(),
        rx.vstack(
            rx.foreach(State.messages, bubble),
            # The reply arrives asynchronously — nothing else on the page announces
            # it. `log` rather than `polite`: this is an ordered running transcript,
            # and it must not interrupt whatever the status region is saying.
            role="log",
            aria_live="polite",
            aria_label="Conversation with DecaBot",
            spacing="3",
            width="100%",
            align="start",
        ),
        thinking(),
        spacing="3",
        width="100%",
        align="start",
    )
