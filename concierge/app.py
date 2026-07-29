import reflex as rx

from concierge.state import FIXTURE_MODE, State
from concierge.ui import brand, cart, chat, gate, product, trace_panel, walkthrough
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


def source_chip() -> rx.Component:
    """Which world DecaBot is talking to. Load-bearing honesty, not decoration."""
    live = not FIXTURE_MODE
    return rx.hstack(
        rx.icon("zap" if live else "flask-conical", size=12, color=SUCCESS if live else INK),
        rx.text(
            "LIVE CATALOG" if live else "FIXTURE REPLAY",
            size="1",
            weight="bold",
            color=SUCCESS if live else INK,
            letter_spacing="0.1em",
        ),
        spacing="1",
        align="center",
        padding="0.3rem 0.6rem",
        background=SUCCESS_BG if live else WARN_BG,
        border_radius=RADIUS_PILL,
    )


def header() -> rx.Component:
    return rx.hstack(
        brand.mark(),
        rx.vstack(
            brand.wordmark(),
            rx.text(
                "Decathlon expedition concierge",
                size="1",
                color=MUTED,
                weight="medium",
            ),
            spacing="1",
            align="start",
        ),
        rx.spacer(),
        source_chip(),
        rx.button(
            rx.icon("rotate-ccw", size=15),
            rx.text("Start over", size="2", weight="medium", display=["none", "none", "block"]),
            on_click=State.clear,
            # Same trap as the composer's Send: the label is hidden below md.
            aria_label="Start over",
            variant="outline",
            size="2",
            cursor="pointer",
            color=BRAND,
            border_radius=RADIUS_PILL,
            padding_x="0.9rem",
            _hover={"background": TINT_2},
        ),
        role="banner",
        width="100%",
        align="center",
        spacing="3",
        padding=["0.7rem 1rem", "0.7rem 1rem", "0.85rem 1.4rem"],
        background=WHITE,
        border_bottom=f"1px solid {BORDER}",
        box_shadow=SHADOW_XS,
        position="sticky",
        top="0",
        z_index="20",
    )


def main_column() -> rx.Component:
    return rx.vstack(
        cart.fixture_ribbon(),
        walkthrough.walkthrough_bar(),
        chat.chat_panel(),
        cart.error_block(),
        product.kit_grid(),
        cart.confirm_bar(),
        cart.cart_block(),
        # The composer sticks to the bottom of the viewport instead of sitting at
        # the end of the column. With a kit on screen the column runs several
        # thousand pixels; the reply to "what size are you?" was below all of it.
        rx.box(
            chat.composer(),
            position="sticky",
            bottom="0",
            z_index="10",
            width="100%",
            padding_top="0.9rem",
            padding_bottom="0.6rem",
            background=f"linear-gradient(180deg, rgba(245,246,252,0) 0%, {BG} 42%)",
        ),
        spacing="5",
        width="100%",
        max_width=CONTENT_W,
        padding=["1rem", "1rem", "1.6rem 1.4rem 1.4rem"],
        align="start",
    )


def skip_link() -> rx.Component:
    """First tab stop on the page. Without it a keyboard user walks the whole
    header and, once a kit is up, every card link before reaching the composer."""
    return rx.link(
        "Skip to the conversation",
        href="#decabot-main",
        class_name="db-skip",
    )


def index() -> rx.Component:
    return rx.cond(State.unlocked, app_shell(), gate.screen())


def app_shell() -> rx.Component:
    return rx.box(
        skip_link(),
        # The only h1 on the page. The empty state's heading used to be it, and it
        # unmounts as soon as the conversation starts — leaving a document with no
        # top-level heading for the rest of the session.
        rx.heading("DecaBot — Decathlon expedition concierge", as_="h1", class_name="db-sr-only"),
        header(),
        rx.flex(
            rx.flex(
                main_column(),
                id="decabot-main",
                role="main",
                flex="1",
                min_width="0",
                width="100%",
                justify="center",
            ),
            trace_panel.trace_panel(),
            direction=rx.breakpoints(initial="column", lg="row"),
            width="100%",
            align="start",
            gap="0",
        ),
        width="100%",
        min_height="100vh",
        # A soft fade out of the header rather than a flat wash — the page reads as
        # one surface with the chrome sitting on top of it.
        background=f"linear-gradient(180deg, {WHITE} 0, {BG} 260px)",
        background_attachment="fixed",
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
    # Decathlon's own faces are proprietary; Inter is the one they also load. The mono
    # is for the audit rail only. One request, both families.
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800"
        "&family=JetBrains+Mono:wght@400;500;700&display=swap",
        "/decabot.css",
    ],
    style={"background": BG, "color": TEXT, "font_family": FONT},
)
app.add_page(
    index,
    route="/",
    title="DecaBot — Decathlon expedition concierge",
    description="Describe an expedition. DecaBot researches it, builds the kit from Decathlon's live catalog, and hands you a real in-stock cart.",
    on_load=State.on_page_load,
)
