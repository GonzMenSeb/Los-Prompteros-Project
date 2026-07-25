"""Colour tokens. Chosen for a projector: high contrast, no thin grey text."""

BG = "#0b120f"
PANEL = "#121b16"
PANEL_2 = "#18231d"
BORDER = "#26362d"
TEXT = "#eaf2ec"
MUTED = "#9db3a6"

ACCENT = "#3ddc97"
ACCENT_DIM = "#1c6b4a"
WARN = "#ffb020"
DANGER = "#ff6b5e"
GUARDRAIL = "#c9a2ff"

LEVEL_COLOR = {"info": ACCENT, "guardrail": GUARDRAIL, "error": DANGER}
LEVEL_BG = {
    "info": "rgba(61,220,151,0.06)",
    "guardrail": "rgba(201,162,255,0.12)",
    "error": "rgba(255,107,94,0.14)",
}
