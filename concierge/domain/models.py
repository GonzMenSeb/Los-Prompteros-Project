"""Domain model. Strict by construction — see SPEC.md §5.

Two deliberate choices, do not "simplify" them:
  * `KitItem.available: Literal[True]` — an out-of-stock item cannot be
    represented in a Kit at all. The stock guardrail is enforced by the type
    system, not by a check somebody might forget.
  * every optional field carries an explicit default. In Pydantic v2 `X | None`
    without a default is a REQUIRED field that happens to accept None.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, HttpUrl, TypeAdapter, field_validator, model_validator

_http_url = TypeAdapter(HttpUrl)


def _must_be_url(v: str) -> str:
    _http_url.validate_python(v)
    return v


# A `str` that is validated as an HttpUrl but STORED as a str.
#
# Do not "restore" this to a bare `HttpUrl`. Reflex 0.9.7's wire encoder
# serialises a pydantic HttpUrl to `null` — silently, with no error — so every
# product link and product photo would arrive at the browser empty. Verified
# against reflex.utils.format.json_dumps on 25 Jul 2026.
Url = Annotated[str, AfterValidator(_must_be_url)]

Environment = Literal[
    "alpine", "forest", "desert", "coastal", "open_water", "pool", "road", "indoor", "mixed"
]
Precipitation = Literal["none", "light", "heavy", "persistent"]
Humidity = Literal["arid", "moderate", "humid", "saturated"]
Priority = Literal["essential", "recommended", "optional"]
Provenance = Literal["search", "assumed", "user"]

Intent = Literal[
    "activity_kit", "clarify", "greeting", "off_topic", "out_of_scope", "safety_critical", "injection"
]


class GroundedValue(BaseModel):
    """Every environmental fact carries its provenance."""

    value: float | str
    unit: str | None = None
    source: Provenance = "assumed"
    citation: Url | None = None

    @model_validator(mode="after")
    def search_requires_citation(self):
        if self.source == "search" and not self.citation:
            raise ValueError("a searched value must carry its citation")
        return self


class GearSlot(BaseModel):
    name: str
    rationale: str
    collection_handles: list[str] = Field(default_factory=list)
    per_person: bool = True
    priority: Priority = "recommended"


class ActivityProfile(BaseModel):
    discipline: str
    environment: Environment
    party_size: int = 1
    elevation_m: GroundedValue | None = None
    temp_min_c: GroundedValue
    temp_max_c: GroundedValue
    precipitation: Precipitation
    humidity: Humidity
    duration_hours: float
    overnight: bool
    terrain: list[str] = Field(default_factory=list)
    hazards: list[str] = Field(default_factory=list)
    gear_slots: list[GearSlot] = Field(default_factory=list)

    @field_validator("temp_min_c", "temp_max_c")
    @classmethod
    def plausible_temperature(cls, v: GroundedValue) -> GroundedValue:
        try:
            celsius = float(v.value)
        except (TypeError, ValueError):
            raise ValueError("temperature must be numeric")
        if not -60 <= celsius <= 60:
            raise ValueError("implausible temperature — check unit (C vs F)")
        return v


class KitItem(BaseModel):
    slot: str
    product_title: str
    product_url: Url
    image_url: Url | None = None  # a real in-stock product without a photo is still buyable
    variant_id: str
    size_label: str
    price_minor: int
    quantity: int = 1
    available: Literal[True]
    size_substituted: bool = False
    # False means the size was NOT asked for — `_choose_size` fell through to
    # "first available", which is how a 9.5 foot got a 7. Distinct from
    # `size_substituted`, which is a size that WAS asked for and was sold out.
    size_confirmed: bool = True
    # Who this line is for, on a per-person slot in a party of more than one. A LIST
    # because `_merge_variants` folds two people onto one line when they take the same
    # variant — a single label would have to be dropped or silently overwritten there.
    # Empty means shared kit (a tent) or a party of one: nobody to distinguish.
    person_labels: list[str] = Field(default_factory=list)
    rationale: str = ""

    @field_validator("variant_id")
    @classmethod
    def must_be_a_variant_gid(cls, v: str) -> str:
        if not v.startswith("gid://shopify/ProductVariant/"):
            raise ValueError(
                "variant_id must be a gid://shopify/ProductVariant/... — a bare id or a "
                "Product gid will be rejected by create_cart (AGENTS.md load-bearing facts)"
            )
        return v


class Kit(BaseModel):
    items: list[KitItem] = Field(default_factory=list)
    unservable_slots: list[str] = Field(default_factory=list)
    budget_minor: int | None = None

    @property
    def total_minor(self) -> int:
        return sum(i.price_minor * i.quantity for i in self.items)


class CatalogVariant(BaseModel):
    """One size/colour of a product, normalised from the storefront feed."""

    variant_gid: str
    size_label: str
    price_minor: int
    available: bool

    @field_validator("variant_gid")
    @classmethod
    def must_be_a_variant_gid(cls, v: str) -> str:
        if not v.startswith("gid://shopify/ProductVariant/"):
            raise ValueError("variant_gid must be gid://shopify/ProductVariant/...")
        return v


class CatalogProduct(BaseModel):
    """A storefront-feed product after the §4.3 field mapping. The ONLY shape
    the agent loop and the UI ever see — raw feed dicts stop at catalog.py."""

    product_gid: str
    handle: str
    title: str
    product_url: Url
    image_url: Url | None = None
    product_type: str = ""
    vendor: str = ""
    option_names: list[str] = Field(default_factory=list)
    variants: list[CatalogVariant] = Field(default_factory=list)

    @property
    def min_price_minor(self) -> int | None:
        prices = [v.price_minor for v in self.variants if v.available]
        return min(prices) if prices else None


class ResolvedVariant(BaseModel):
    """Output of resolve_variant() — an in-stock variant confirmed via get_product."""

    variant_gid: str
    size_label: str
    price_minor: int
    available: Literal[True]
    substituted: bool = False
    requested_size: str | None = None


class CartResult(BaseModel):
    """What create_cart() hands back. `continue_url` is the demo's proof —
    it 301-redirects to https://www.decathlon.com/cart/c/<token>?key=<key>."""

    cart_id: str
    continue_url: Url
    total_minor: int
    currency: str = "USD"
    line_count: int = 0
    expires_at: str | None = None


class IntentVerdict(BaseModel):
    intent: Intent
    discipline: str | None = None
    reason: str = ""


class Question(BaseModel):
    """A single slot-filling question. PII minimisation: sizes and budget only."""

    key: Literal["budget", "party_size", "sizes", "existing_kit"]
    text: str


class SlotPlan(BaseModel):
    slots: list[GearSlot] = Field(default_factory=list)


def minor_to_display(minor: int, currency: str = "USD") -> str:
    """5000 -> '$50.00'. The ONLY place minor units become human text."""
    symbol = "$" if currency == "USD" else f"{currency} "
    return f"{symbol}{minor / 100:,.2f}"


def major_string_to_minor(price: str | float) -> int:
    """Storefront feed gives a decimal STRING in MAJOR units ('50.00'). MCP gives
    a minor-units integer (5000). Convert at the boundary — SPEC.md §3.3."""
    return round(float(price) * 100)
