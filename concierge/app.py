import reflex as rx

from concierge.state import State
from concierge.ui import cart, chat, product, trace_panel
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


def header() -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.icon("tent-tree", size=22, color=ON_BRAND),
            background=BRAND,
            padding="0.45rem",
            border_radius=RADIUS_SM,
            line_height="0",
        ),
        rx.vstack(
            rx.heading("Expedition Concierge", size="5", color=TEXT, weight="bold"),
            rx.text(
                "Describe the trip. Get a real, in-stock Decathlon cart.",
                size="2",
                color=MUTED,
            ),
            spacing="0",
            align="start",
        ),
        rx.spacer(),
        rx.button(
            rx.icon("rotate-ccw", size=16),
            on_click=State.clear,
            variant="outline",
            size="2",
            cursor="pointer",
            color=BRAND,
        ),
        width="100%",
        align="center",
        spacing="3",
        padding="0.85rem 1.2rem",
        background=WHITE,
        border_bottom=f"3px solid {BRAND}",
        position="sticky",
        top="0",
        z_index="5",
    )


def main_column() -> rx.Component:
    return rx.vstack(
        cart.fixture_ribbon(),
        chat.chat_panel(),
        cart.error_block(),
        product.kit_grid(),
        cart.confirm_bar(),
        cart.cart_block(),
        rx.box(height="1rem"),
        chat.composer(),
        spacing="4",
        width="100%",
        max_width="1100px",
        padding=["1rem", "1rem", "1.5rem"],
        align="start",
    )


def index() -> rx.Component:
    return rx.box(
        header(),
        rx.flex(
            rx.box(main_column(), flex="1", min_width="0", width="100%"),
            trace_panel.trace_panel(),
            direction=rx.breakpoints(initial="column", lg="row"),
            width="100%",
            align="start",
            gap="0",
        ),
        width="100%",
        min_height="100vh",
        background=BG,
    )


app = rx.App(
    theme=rx.theme(
        appearance="light",
        accent_color="indigo",
        gray_color="gray",
        radius="small",
        scaling="100%",
        # Radix sets font-family on `.radix-themes` itself, which outranks a
        # body-level App(style=...). Setting it here is what actually applies Inter.
        font_family=FONT,
    ),
    # Decathlon's own faces are proprietary; Inter is the one they also load.
    stylesheets=["https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"],
    style={"background": BG, "color": TEXT, "font_family": FONT},
)
app.add_page(index, route="/", title="Expedition Concierge")
