"""The debugging bundle. The point of this artifact is that payloads arrive WHOLE —
`summarise()` clamps them for the panel, and a bundle that inherited that clamp would
be a screenshot with extra steps.
"""

from __future__ import annotations

import json

from concierge.obs.bundle import INLINE_MAX, RunSnapshot, render


def _event(seq: int, ts: float, name: str, payload: dict, level: str = "info") -> dict:
    return {"seq": seq, "ts": ts, "event": name, "payload": payload, "level": level}


def _snap(**over) -> RunSnapshot:
    base = {
        "stamp": "2026-07-28T19:04:11+00:00",
        "mode": "live",
        "gated": True,
        "lane": "reserved",
        "messages": [
            {"role": "user", "content": "Hiking Páramo de Santurbán, 2 nights", "citations": []},
            {
                "role": "assistant",
                "content": "Here is the kit.",
                "citations": ["https://a.example/x", "https://b.example/y"],
            },
        ],
        "events": [
            _event(1, 1000.0, "turn.start", {"turn": 1, "text": "Hiking Páramo"}),
            _event(2, 1000.412, "intent.verdict", {"intent": "expedition"}, "guardrail"),
            _event(3, 1002.5, "turn.error", {"error": "RuntimeError('boom')"}, "error"),
        ],
        "items": [
            {
                "slot": "boots",
                "product_title": "Quechua NH500",
                "product_url": "https://www.decathlon.com/products/nh500",
                "variant_id": "gid://shopify/ProductVariant/41919445434430",
                "size_label": "Dark Cinnamon / 9.5",
                "quantity": 1,
                "price_minor": 10000,
                "size_substituted": False,
                "rationale": "Waterproof, above the ankle.",
            }
        ],
        "unservable": ["bike_helmet"],
        "budget_minor": 5000,
        "cart": {
            "cart_id": "gid://shopify/Cart/abc",
            "url": "https://www.decathlon.com/cart/c/tok?key=k",
            "total_minor": 10000,
            "line_count": 1,
            "expires_at": "2026-07-29T19:04:11Z",
        },
    }
    return RunSnapshot(**{**base, **over})


class TestSections:
    def test_every_section_is_present(self):
        out = render(_snap())
        for heading in ("# DecaBot run bundle", "## Conversation", "## Kit", "## Cart", "## Trace"):
            assert heading in out

    def test_header_counts_turns_and_levels(self):
        out = render(_snap()).splitlines()[1]
        assert "turns=1" in out
        assert "events=3 (1 guardrail, 1 error)" in out
        assert "mode=live" in out and "gate=on" in out and "lane=reserved" in out

    def test_a_live_cart_link_is_announced(self):
        assert "NOTE: contains a live Decathlon cart link." in render(_snap())

    def test_no_cart_means_no_note(self):
        assert "NOTE:" not in render(_snap(cart=None))

    def test_conversation_numbers_turns_and_lists_citations(self):
        out = render(_snap())
        assert "[1 user] Hiking Páramo de Santurbán, 2 nights" in out
        assert "[1 assistant] Here is the kit." in out
        assert "cite https://a.example/x  https://b.example/y" in out

    def test_second_user_message_opens_turn_two(self):
        msgs = _snap().messages + [{"role": "user", "content": "swap the tent"}]
        assert "[2 user] swap the tent" in render(_snap(messages=msgs))


class TestPayloadsSurviveWhole:
    def test_a_long_payload_is_not_truncated(self):
        # summarise() would clamp this at 120 chars per value and 300 for the line.
        blob = "x" * 4000
        out = render(_snap(events=[_event(1, 0.0, "tool.result", {"body": blob})]))
        assert blob in out
        assert "…" not in out

    def test_a_long_payload_renders_indented_not_inline(self):
        out = render(_snap(events=[_event(1, 0.0, "e", {"body": "y" * (INLINE_MAX + 50)})]))
        assert '\n              {\n                "body"' in out

    def test_a_short_payload_stays_on_one_line(self):
        out = render(_snap(events=[_event(1, 0.0, "e", {"a": 1})]))
        assert '              {"a": 1}' in out

    def test_an_empty_payload_renders_as_empty_object(self):
        assert "              {}" in render(_snap(events=[_event(1, 0.0, "gate.unlocked", {})]))

    def test_nested_payloads_keep_their_structure(self):
        nested = {"slots": [{"name": "boots", "handles": ["a", "b"]}]}
        out = render(_snap(events=[_event(1, 0.0, "slots.derived", nested)]))
        assert json.dumps(nested, ensure_ascii=False) in out

    def test_a_non_serializable_value_does_not_raise(self):
        out = render(_snap(events=[_event(1, 0.0, "e", {"exc": RuntimeError("boom")})]))
        assert "boom" in out


class TestTrace:
    def test_offsets_are_relative_to_the_first_event(self):
        out = render(_snap())
        assert "   1  +0.000s  info       turn.start" in out
        assert "   2  +0.412s  guardrail  intent.verdict" in out
        assert "   3  +2.500s  error      turn.error" in out

    def test_events_keep_their_emitted_order(self):
        out = render(_snap())
        assert out.index("turn.start") < out.index("intent.verdict") < out.index("turn.error")


class TestKitAndCart:
    def test_kit_totals_and_flags_over_budget(self):
        assert "## Kit — 1 items · $100.00 · budget $50.00 · OVER by $50.00" in render(_snap())

    def test_under_budget_says_under(self):
        assert "under by $150.00" in render(_snap(budget_minor=25000))

    def test_no_budget_omits_the_verdict(self):
        head = [ln for ln in render(_snap(budget_minor=None)).splitlines() if ln.startswith("## Kit")]
        assert head == ["## Kit — 1 items · $100.00"]

    def test_quantity_multiplies_into_the_total(self):
        items = [{**_snap().items[0], "quantity": 3}]
        assert "## Kit — 3 items · $300.00" in render(_snap(items=items, budget_minor=None))

    def test_a_substitution_is_flagged(self):
        items = [{**_snap().items[0], "size_substituted": True}]
        assert "[SIZE SUBSTITUTED]" in render(_snap(items=items))

    def test_variant_gid_and_product_url_are_both_present(self):
        out = render(_snap())
        assert "gid://shopify/ProductVariant/41919445434430" in out
        assert "https://www.decathlon.com/products/nh500" in out

    def test_unservable_slots_are_listed(self):
        assert "unservable: bike_helmet" in render(_snap())

    def test_cart_line_carries_id_count_total_and_expiry(self):
        assert (
            "gid://shopify/Cart/abc  ·  1 lines  ·  $100.00  ·  expires 2026-07-29T19:04:11Z"
            in render(_snap())
        )

    def test_the_cart_url_is_not_redacted(self):
        assert "https://www.decathlon.com/cart/c/tok?key=k" in render(_snap())


class TestDegenerateRuns:
    def test_an_empty_run_renders_without_raising(self):
        out = render(RunSnapshot(stamp="2026-07-28T00:00:00+00:00"))
        assert "(nothing said yet)" in out
        assert "(no kit built)" in out
        assert "(no cart created)" in out
        assert "(no events)" in out

    def test_unservable_survives_an_empty_kit(self):
        assert "unservable: tent" in render(_snap(items=[], unservable=["tent"]))

    def test_output_ends_with_a_newline(self):
        assert render(_snap()).endswith("\n")

    def test_unicode_is_preserved_not_escaped(self):
        out = render(_snap())
        assert "Páramo de Santurbán" in out
        assert "\\u00e1" not in out
