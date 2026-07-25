"""Cross-lane invariants. Offline, no network.

Everything here imports lazily and skips if the other lane has not landed yet, so
the suite stays green during the build and grows teeth as the lanes arrive.
"""

from __future__ import annotations

import pytest

from concierge.domain.guardrails import check_budget, check_substitution, find_unbacked_claims
from concierge.domain.models import Kit
from tests.conftest import VARIANT_GID, feed, item


def _mod(name: str):
    return pytest.importorskip(name)


class TestHumanInTheLoop:
    def test_create_cart_is_not_a_model_tool(self):
        """SPEC.md §6.1: only a user click calls create_cart. If the model can call
        it, the agent can transact without a human and the guarantee is gone."""
        tools = _mod("concierge.agent.tools")
        names = {d.name for t in tools.CATALOG_TOOLS for d in t.function_declarations}
        assert "create_cart" not in names, f"create_cart is exposed to the model: {sorted(names)}"
        assert not any("cart" in n or "checkout" in n for n in names), sorted(names)

    def test_catalog_tools_are_wrapped_in_Tool(self):
        types = _mod("google.genai.types")
        tools = _mod("concierge.agent.tools")
        assert tools.CATALOG_TOOLS
        for t in tools.CATALOG_TOOLS:
            assert isinstance(t, types.Tool), (
                "tools= must be a list of types.Tool. A bare FunctionDeclaration raises "
                "AttributeError before any HTTP call (SPEC.md §3.4)."
            )
            assert t.function_declarations


class TestCartLineShape:
    def test_cart_line_uses_item_id(self):
        cart = _mod("concierge.commerce.cart")
        assert cart.cart_line(VARIANT_GID, 2) == {"item": {"id": VARIANT_GID}, "quantity": 2}

    def test_cart_line_never_emits_merchandise_id(self):
        cart = _mod("concierge.commerce.cart")
        assert "merchandise_id" not in str(cart.cart_line(VARIANT_GID))


class TestCatalogMapping:
    def test_map_product_stores_minor_units_from_a_major_unit_string(self):
        catalog = _mod("concierge.commerce.catalog")
        raw = feed("hiking-boots")[0]
        assert raw["variants"][0]["price"] == "100.00"
        p = catalog.map_product(raw)
        assert p.variants[0].price_minor == 10000
        assert isinstance(p.variants[0].price_minor, int)

    def test_map_product_urls_are_plain_strings(self):
        """A pydantic HttpUrl here serialises to null through Reflex's encoder."""
        catalog = _mod("concierge.commerce.catalog")
        p = catalog.map_product(feed("hiking-boots")[0])
        assert isinstance(p.product_url, str)
        assert p.image_url is None or isinstance(p.image_url, str)

    def test_map_product_agrees_with_the_spec_field_mapping(self):
        from tests.conftest import catalog as reference

        catalog = _mod("concierge.commerce.catalog")
        mine = {p.product_gid: p for p in reference("hiking-boots")}
        for raw in feed("hiking-boots"):
            theirs = catalog.map_product(raw)
            ref = mine[theirs.product_gid]
            assert theirs.product_url == ref.product_url
            assert [v.variant_gid for v in theirs.variants] == [v.variant_gid for v in ref.variants]
            assert [v.price_minor for v in theirs.variants] == [v.price_minor for v in ref.variants]
            assert [v.available for v in theirs.variants] == [v.available for v in ref.variants]

    def test_map_product_preserves_real_out_of_stock_flags(self):
        catalog = _mod("concierge.commerce.catalog")
        bag = next(p for p in feed("sleeping-bags") if "MT500" in p["title"])
        p = catalog.map_product(bag)
        assert [v.available for v in p.variants] == [True, False, False]
        assert p.min_price_minor == 6500


class TestQueryShapeAgreement:
    @pytest.mark.parametrize(
        "query", ["sleeping bag 0 degrees celsius", "60L backpacking pack with rain cover", "tent"]
    )
    def test_catalog_sanitizer_also_collapses_descriptive_queries(self, query):
        catalog = _mod("concierge.commerce.catalog")
        out = catalog.sanitize_query(query)
        assert 1 <= len(out.split()) <= 3
        assert not any(ch.isdigit() for ch in out)


class TestDisclosureReachesTheUser:
    def test_loop_discloses_a_substituted_size(self):
        """check_substitution() is only a guarantee if something renders it."""
        loop = _mod("concierge.agent.loop")
        kit = Kit(items=[item(size_label="L", size_substituted=True)])
        text = loop._disclosures(kit)
        assert "size" in text.lower()
        assert "L" in text
        assert check_substitution(kit.items), "guardrail and loop disagree about disclosure"

    def test_loop_names_unservable_slots(self):
        loop = _mod("concierge.agent.loop")
        kit = Kit(items=[item()], unservable_slots=["helmet"])
        assert "helmet" in loop._disclosures(kit)

    def test_loop_budget_line_agrees_with_the_budget_guardrail(self):
        loop = _mod("concierge.agent.loop")
        kit = Kit(items=[item(price_minor=10000), item(price_minor=6500)], budget_minor=12000)
        text = loop._disclosures(kit)
        v = check_budget(kit)
        assert "$45.00" in text and v.over_by_minor == 4500

    def test_disclosure_text_invents_no_specifications(self):
        loop = _mod("concierge.agent.loop")
        kit = Kit(items=[item(size_label="L", size_substituted=True)], unservable_slots=["helmet"], budget_minor=9000)
        assert find_unbacked_claims(loop._disclosures(kit), kit.items) == []
