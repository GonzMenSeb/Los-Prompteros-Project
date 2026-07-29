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
# GREY_2 and GREY_3 are ICON AND RULE colours, never type. Measured against this
# palette's own surfaces they are 3.03:1 and 1.86:1 on white, 2.81:1 on TINT_1 —
# all under AA, and the projector at a demo is worse than any monitor. Anything
# that reads as words uses MUTED (4.95:1 white, 4.59:1 TINT_1) or darker.
GREY_2 = "#949494"
GREY_3 = "#BEBEBE"
GREY_4 = "#E1E0DF"
OFFWHITE = "#F3F3F3"
WHITE = "#FFFFFF"

SUCCESS = "#148558"
DANGER = "#D70322"
WARN = "#FFCD4E"

# SUCCESS on SUCCESS_BG measures 4.08:1 — under AA for the small bold type the
# "IN STOCK · SIZE RESOLVED" chip is set in. This is the same green darkened until
# it clears on its own tint (5.37:1). SUCCESS stays the fill and the icon colour.
SUCCESS_DEEP = "#12704A"

# WARN is a SURFACE colour. #FFCD4E as type on white is 1.6:1 — invisible. When a
# substitution has to be counted in words rather than washed behind them, this is
# the amber that survives it (5.54:1).
WARN_INK = "#8A6100"

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

# A hairline inside an already-bordered surface. GREY_4 at that job reads as a
# second frame; this sits just above the white.
HAIRLINE = "#EDECEB"

# Their brand faces are proprietary; Inter is the one they also load.
FONT = "Inter, 'Helvetica Neue', Helvetica, Arial, sans-serif"
# The audit rail is DecaBot's own instrument rather than storefront chrome, so it
# gets a real mono instead of whatever the OS hands back.
MONO = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

RADIUS = "8px"
RADIUS_SM = "4px"
RADIUS_LG = "14px"
RADIUS_PILL = "999px"

# Shadows are cast in the brand's own hue, not neutral black — on a #F5F6FC page a
# grey shadow reads as dirt.
SHADOW_XS = "0 1px 2px rgba(39,47,118,0.05)"
SHADOW_SM = "0 1px 2px rgba(39,47,118,0.05), 0 2px 6px rgba(39,47,118,0.05)"
SHADOW_MD = "0 2px 4px rgba(39,47,118,0.05), 0 10px 24px rgba(39,47,118,0.07)"
SHADOW_LG = "0 4px 10px rgba(39,47,118,0.07), 0 20px 46px rgba(39,47,118,0.11)"
SHADOW_BRAND = "0 6px 18px rgba(54,67,186,0.26)"

FOCUS_RING = "0 0 0 4px rgba(54,67,186,0.14)"

TRACK_TIGHT = "-0.02em"
TRACK_TIGHTER = "-0.03em"
TRACK_EYEBROW = "0.14em"

EASE = "cubic-bezier(0.22,0.61,0.36,1)"

CONTENT_W = "1040px"
RAIL_W = "384px"

LEVEL_COLOR = {"info": GREY_1, "guardrail": BRAND, "error": DANGER}
LEVEL_BG = {
    "info": "rgba(35,35,35,0.04)",
    "guardrail": "rgba(54,67,186,0.08)",
    "error": "rgba(215,3,34,0.07)",
}

SUCCESS_BG = "rgba(20,133,88,0.10)"
DANGER_BG = "rgba(215,3,34,0.08)"
WARN_BG = "rgba(255,205,78,0.22)"
