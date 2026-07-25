"""Decathlon's own design tokens, read off www.decathlon.com on 25 Jul 2026.

The pitch is that Decathlon could drop this concierge straight into their site,
so the palette is theirs. #3643BA is their primary — it appears on their page as
`--color-background: rgb(54 67 186)`, not as an incidental hex.

#7AFFA7 is their `--color-accent`, but it is a promotional/sale green. Using it
for "in stock" makes the kit read as a discount banner; SUCCESS is #148558.

Names are kept stable — every component imports from here.
"""

BRAND = "#3643BA"
BRAND_DARK = "#2E3998"
BRAND_DEEP = "#272F76"

TINT_1 = "#F5F6FC"
TINT_2 = "#E7E8F7"
TINT_3 = "#D3D8F7"

INK = "#232323"
GREY_1 = "#707070"
GREY_2 = "#949494"
GREY_3 = "#BEBEBE"
GREY_4 = "#E1E0DF"
OFFWHITE = "#F3F3F3"
WHITE = "#FFFFFF"

SUCCESS = "#148558"
DANGER = "#D70322"
WARN = "#FFCD4E"

BG = TINT_1
PANEL = WHITE
PANEL_2 = OFFWHITE
BORDER = GREY_4
TEXT = INK
MUTED = GREY_1
ACCENT = BRAND
ACCENT_DIM = TINT_3
GUARDRAIL = BRAND
ON_BRAND = WHITE

# Their brand faces are proprietary; Inter is the one they also load.
FONT = "Inter, 'Helvetica Neue', Helvetica, Arial, sans-serif"

RADIUS = "8px"
RADIUS_SM = "4px"

LEVEL_COLOR = {"info": GREY_1, "guardrail": BRAND, "error": DANGER}
LEVEL_BG = {
    "info": "rgba(35,35,35,0.04)",
    "guardrail": "rgba(54,67,186,0.08)",
    "error": "rgba(215,3,34,0.07)",
}

SUCCESS_BG = "rgba(20,133,88,0.10)"
DANGER_BG = "rgba(215,3,34,0.08)"
WARN_BG = "rgba(255,205,78,0.22)"
