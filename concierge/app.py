"""Reflex app — smoke stub. Dev C replaces this with the real chat page."""

import reflex as rx

from concierge.state import State


def index() -> rx.Component:
    return rx.vstack(
        rx.heading("Expedition Concierge"),
        rx.text(State.status),
        rx.button("ping", on_click=State.ping),
        padding="2rem",
    )


app = rx.App()
app.add_page(index, route="/")
