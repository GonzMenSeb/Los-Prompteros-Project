from __future__ import annotations

import pytest
from pydantic import BaseModel, HttpUrl, ValidationError
from reflex.utils.format import json_dumps

from concierge.domain.models import (
    ActivityProfile,
    GroundedValue,
    Kit,
    KitItem,
    Url,
    major_string_to_minor,
    minor_to_display,
)
from tests.conftest import item


def _profile(**over) -> ActivityProfile:
    base = dict(
        discipline="hiking",
        environment="alpine",
        temp_min_c=GroundedValue(value=-2),
        temp_max_c=GroundedValue(value=8),
        precipitation="light",
        humidity="moderate",
        duration_hours=8,
        overnight=False,
    )
    return ActivityProfile(**{**base, **over})


class TestKitItem:
    def test_rejects_available_false(self):
        with pytest.raises(ValidationError):
            item(available=False)

    def test_rejects_missing_available(self):
        data = item().model_dump()
        data.pop("available")
        with pytest.raises(ValidationError):
            KitItem(**data)

    def test_rejects_a_product_gid_where_a_variant_gid_belongs(self):
        with pytest.raises(ValidationError, match="ProductVariant"):
            item(variant_id="gid://shopify/Product/7839703466046")

    def test_rejects_a_bare_numeric_variant_id(self):
        with pytest.raises(ValidationError, match="ProductVariant"):
            item(variant_id="41919445434430")

    def test_rejects_a_non_url_product_url(self):
        with pytest.raises(ValidationError):
            item(product_url="quechua-mens-nh500")


class TestGroundedValue:
    def test_searched_value_without_citation_raises(self):
        with pytest.raises(ValidationError, match="citation"):
            GroundedValue(value=-5, unit="C", source="search")

    def test_searched_value_with_citation_is_accepted(self):
        v = GroundedValue(value=-5, unit="C", source="search", citation="https://weather.example/x")
        assert v.citation == "https://weather.example/x"

    def test_assumed_value_needs_no_citation(self):
        assert GroundedValue(value=-5).source == "assumed"


class TestTemperaturePlausibility:
    def test_fahrenheit_fed_as_celsius_is_rejected(self):
        # 45 C is 113 F; 113 arriving in a *_c field is a unit error, not weather.
        with pytest.raises(ValidationError, match="implausible temperature"):
            _profile(temp_max_c=GroundedValue(value=113))

    def test_absurd_cold_is_rejected(self):
        with pytest.raises(ValidationError, match="implausible temperature"):
            _profile(temp_min_c=GroundedValue(value=-70))

    def test_non_numeric_temperature_is_rejected(self):
        with pytest.raises(ValidationError, match="numeric"):
            _profile(temp_min_c=GroundedValue(value="chilly"))

    @pytest.mark.parametrize("celsius", [-60, -5, 0, 45, 60])
    def test_plausible_range_is_accepted(self, celsius):
        assert float(_profile(temp_min_c=GroundedValue(value=celsius)).temp_min_c.value) == celsius


class TestMoney:
    @pytest.mark.parametrize(
        "major,minor",
        [("50.00", 5000), ("19.99", 1999), ("0.07", 7), ("100.00", 10000), ("6.99", 699), ("65.00", 6500)],
    )
    def test_major_string_to_minor(self, major, minor):
        assert major_string_to_minor(major) == minor

    def test_no_float_drift_across_the_whole_hiking_boots_feed(self):
        from tests.conftest import feed

        for p in feed("hiking-boots"):
            for v in p["variants"]:
                assert major_string_to_minor(v["price"]) == round(float(v["price"]) * 100)

    def test_minor_to_display(self):
        assert minor_to_display(5000) == "$50.00"
        assert minor_to_display(7) == "$0.07"
        assert minor_to_display(123456) == "$1,234.56"

    def test_kit_total_is_integer_arithmetic(self):
        kit = Kit(items=[item(price_minor=6500, quantity=2), item(price_minor=1999)])
        assert kit.total_minor == 14999
        assert isinstance(kit.total_minor, int)


class TestUrlWireEncoding:
    """Regression guard. A raw pydantic HttpUrl serialises to null through Reflex's
    wire encoder — silently — which would empty every product photo and link."""

    def test_url_alias_round_trips_as_a_real_string(self):
        assert json_dumps({"u": item().image_url}) == '{"u": "%s"}' % item().image_url
        assert "null" not in json_dumps({"u": item().product_url})

    def test_a_raw_HttpUrl_would_have_serialised_to_null(self):
        class Raw(BaseModel):
            u: HttpUrl

        assert json_dumps({"u": Raw(u="https://www.decathlon.com/x").u}) == '{"u": null}'

    def test_whole_kititem_survives_the_encoder(self):
        wire = json_dumps(item().model_dump())
        assert "https://www.decathlon.com/products/quechua-mens-nh500" in wire
        assert "null" not in wire

    def test_url_annotation_still_validates(self):
        class M(BaseModel):
            u: Url

        with pytest.raises(ValidationError):
            M(u="not-a-url")
        assert isinstance(M(u="https://x.example/a").u, str)
