import reflex as rx

from concierge.state import State
from concierge.ui import cart, chat, product, trace_panel
from concierge.ui.theme import ACCENT, BG, BORDER, MUTED, PANEL_2, TEXT


def header() -> rx.Component:
    return rx.hstack(
        rx.icon("tent-tree", size=26, color=ACCENT),
        rx.vstack(
            rx.heading("Expedition Concierge", size="5", color=TEXT),
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
            variant="soft",
            size="2",
            cursor="pointer",
        ),
        width="100%",
        align="center",
        spacing="3",
        padding="0.9rem 1.2rem",
        background=PANEL_2,
        border_bottom=f"1px solid {BORDER}",
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
        appearance="dark",
        accent_color="jade",
        gray_color="sage",
        radius="large",
        scaling="100%",
    ),
    style={"background": BG, "color": TEXT},
)
app.add_page(index, route="/", title="Expedition Concierge")
