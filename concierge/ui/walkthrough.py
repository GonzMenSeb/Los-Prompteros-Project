"""Controls for the scripted demo. The script itself is `concierge/walkthrough.py`.

One button, not three. The script is a two-step sequence and the button simply says
which step is next: prewarm while the pitch is still on the problem statement, then
go live when the audience is looking. `State.walkthrough_stage` is the cursor.
"""

from __future__ import annotations

import reflex as rx

from concierge.state import State
from concierge.ui.theme import (
    BORDER,
    BRAND,
    BRAND_DARK,
    EASE,
    GREY_4,
    HAIRLINE,
    INK,
    MONO,
    MUTED,
    ON_BRAND,
    RADIUS,
    RADIUS_PILL,
    RADIUS_SM,
    SHADOW_BRAND,
    SHADOW_SM,
    SUCCESS,
    TEXT,
    TINT_1,
    TRACK_EYEBROW,
    TRACK_TIGHT,
    WHITE,
)

# Measured, not guessed: prewarm ran 166 s and the onstage phase 34 s. Do not round
# these down — the presenter paces the pitch off them, and prewarm finishing late is
# what makes a demo look broken.
STEPS = (
    ("Research the trip", "refusal · grounded research · live kit", "~3 min"),
    ("Go live on camera", "injection blocked · real Decathlon cart", "~25 s"),
)


def _cta_label():
    return rx.match(
        State.walkthrough_stage,
        (0, "Run the demo"),
        (1, "Go live"),
        "Run it again",
    )


def _cta_detail():
    return rx.match(
        State.walkthrough_stage,
        (0, f"Step 1 of 2 · {STEPS[0][1]} · {STEPS[0][2]}"),
        (1, f"Step 2 of 2 · {STEPS[1][1]} · {STEPS[1][2]}"),
        f"From a clean slate · {STEPS[0][2]}",
    )


def _step(index: int, title: str) -> rx.Component:
    done = State.walkthrough_stage > index
    active = State.walkthrough_stage == index
    return rx.hstack(
        rx.box(
            rx.cond(
                done,
                rx.icon("check", size=11, color=ON_BRAND),
                rx.text(
                    str(index + 1),
                    size="1",
                    weight="bold",
                    color=rx.cond(active, ON_BRAND, MUTED),
                    font_family=MONO,
                ),
            ),
            display="flex",
            align_items="center",
            justify_content="center",
            width="1.2rem",
            height="1.2rem",
            flex_shrink="0",
            border_radius=RADIUS_PILL,
            background=rx.cond(done, SUCCESS, rx.cond(active, BRAND, GREY_4)),
        ),
        rx.text(
            title,
            size="1",
            weight="medium",
            color=rx.cond(done | active, TEXT, MUTED),
        ),
        spacing="2",
        align="center",
    )


def _controls() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("play", size=14, color=BRAND),
            rx.text("GUIDED DEMO", size="1", weight="bold", letter_spacing=TRACK_EYEBROW, color=BRAND),
            rx.text(
                "automated, not mocked — every beat runs through the live agent",
                size="1",
                color=MUTED,
            ),
            spacing="2",
            align="center",
            wrap="wrap",
        ),
        rx.flex(
            rx.button(
                rx.hstack(
                    rx.icon("play", size=17),
                    rx.vstack(
                        rx.text(_cta_label(), size="3", weight="bold", line_height="1.2"),
                        # The detail line is a single unbroken run of "·"-joined
                        # phrases. Left unwrapped it forced the button wider than the
                        # card it sits in, and at 414px it bled to the viewport edge.
                        rx.text(
                            _cta_detail(),
                            size="1",
                            opacity="0.85",
                            line_height="1.3",
                            white_space="normal",
                        ),
                        spacing="1",
                        align="start",
                        min_width="0",
                    ),
                    spacing="3",
                    align="center",
                    width="100%",
                ),
                on_click=State.advance_walkthrough,
                disabled=State.is_thinking,
                cursor="pointer",
                height="auto",
                max_width="100%",
                padding="0.7rem 1.1rem",
                background=BRAND,
                color=ON_BRAND,
                border_radius=RADIUS,
                box_shadow=SHADOW_BRAND,
                letter_spacing=TRACK_TIGHT,
                transition=f"background 160ms {EASE}, transform 160ms {EASE}",
                _hover={"background": BRAND_DARK, "transform": "translateY(-1px)"},
                _active={"transform": "translateY(0)"},
            ),
            rx.vstack(
                _step(0, STEPS[0][0]),
                _step(1, STEPS[1][0]),
                spacing="2",
                align="start",
                padding_left="1.1rem",
                border_left=f"1px solid {HAIRLINE}",
            ),
            gap="1.1rem",
            align="center",
            wrap="wrap",
        ),
        spacing="3",
        align="start",
        width="100%",
        padding="0.9rem 1.1rem",
        background=WHITE,
        border=f"1px solid {BORDER}",
        border_radius=RADIUS,
        box_shadow=SHADOW_SM,
    )


def _banner() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.spinner(size="3", color=ON_BRAND),
            rx.vstack(
                rx.hstack(
                    rx.text("RUNNING", size="1", weight="bold", letter_spacing=TRACK_EYEBROW, color=ON_BRAND),
                    rx.text(
                        State.walkthrough_progress,
                        size="1",
                        weight="bold",
                        color=ON_BRAND,
                        font_family=MONO,
                        opacity="0.85",
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.text(
                    State.walkthrough_label,
                    size="4",
                    weight="bold",
                    color=ON_BRAND,
                    line_height="1.3",
                    letter_spacing=TRACK_TIGHT,
                ),
                rx.text(State.walkthrough_shows, size="2", color=ON_BRAND, opacity="0.85", line_height="1.45"),
                spacing="1",
                align="start",
            ),
            spacing="4",
            align="center",
            width="100%",
            padding="1rem 1.2rem",
        ),
        rx.box(
            class_name="db-track",
            width="100%",
            height="3px",
            background="rgba(255,255,255,0.22)",
        ),
        spacing="0",
        width="100%",
        background=BRAND,
        border_radius=RADIUS,
        box_shadow=SHADOW_BRAND,
        overflow="hidden",
    )


def walkthrough_bar() -> rx.Component:
    return rx.cond(State.walkthrough_active, _banner(), _controls())
