"""Reflex State — smoke stub. Dev C replaces this with the real state."""

import reflex as rx


class State(rx.State):
    status: str = "boot ok"

    def ping(self):
        self.status = "pong"
