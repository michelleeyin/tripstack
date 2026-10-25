"""Optimizer, comparison and integration tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tripstack.data_loader import load_demo_trip, load_promotions
from tripstack.engine.comparison import build_comparison_result, compare_offers
from tripstack.engine.optimizer import optimize_trip
from tripstack.providers import DemoProvider, search_sync

from .helpers import TODAY, cashback, instant, offer, trip_request


def test_ranks_cheapest_net_cost_first():
    cheap = offer(offer_id="a", platform="Provider A", base="500.00", taxes="50.00", fees="0")
    pricey = offer(offer_id="b", platform="Provider B", base="800.00", taxes="50.00", fees="0")
    promos = [cashback(platform="Provider A", rate="0.08", cap="30.00")]
    results, _ = compare_offers([pricey, cheap], promos, today=TODAY, currency="USD")
    assert results[0].offer_id == "a"
    assert results[0].estimated_net_cost < results[1].estimated_net_cost


def test_ranking_by_upfront_objective():
    net_cheap = offer(offer_id="a", platform="Provider A", base="500.00")
    upfront_cheap = offer(offer_id="b", platform="Provider B", base="420.00")
    promos = [cashback(platform="Provider A", rate="0.08", cap="30.00")]
    request = trip_request(objective="lowest_upfront")
    plan = optimize_trip(request, [net_cheap, upfront_cheap], promos, today=TODAY)
    assert plan.choices[0].selected.offer_id == "b"


def test_refundable_only_constraint_is_respected():
    refundable = offer(offer_id="a", platform="Provider A", base="300.00", refundable=True)
    non_refundable = offer(offer_id="b", platform="Provider B", base="150.00", refundable=False)
    request = trip_request(objective="lowest_upfront", refundable_only=True)
    plan = optimize_trip(request, [refundable, non_refundable], [], today=TODAY)
    assert plan.choices[0].selected.offer_id == "a"


def test_multi_city_totals_aggregate_correctly():
    demo = load_demo_trip()
    provider = DemoProvider()
    offers = []
    for seg in demo.segments:
        offers.extend(
            search_sync(provider, seg.city, seg.check_in, seg.check_out, adults=2)
        )
    promos = load_promotions()
    plan = optimize_trip(demo, offers, promos, today=TODAY)

    assert len(plan.choices) == 3
    assert all(c.selected is not None for c in plan.choices)
    expected_upfront = sum((c.selected.upfront_payment for c in plan.choices), Decimal("0.00"))
    expected_net = sum((c.selected.estimated_net_cost for c in plan.choices), Decimal("0.00"))
    assert plan.total_upfront == expected_upfront
    assert plan.total_net_cost == expected_net
    assert plan.total_cashback == plan.total_upfront - plan.total_net_cost


def test_offers_in_other_currencies_are_excluded_not_converted():
    usd = offer(offer_id="a", currency="USD")
    eur = offer(offer_id="b", currency="EUR")
    results, warnings = compare_offers([usd, eur], [], today=TODAY, currency="USD")
    assert [r.offer_id for r in results] == ["a"]
    assert any("does not match" in w for w in warnings)


def test_budget_remaining_is_reported_on_both_bases():
    # Upfront 975 with 30 cashback -> 945 net; budget 1200.
    a = offer(base="850.00", taxes="100.00", fees="25.00")
    promos = [cashback(platform="Provider A", rate="0.08", cap="30.00")]
    plan = optimize_trip(trip_request(budget="1200.00"), [a], promos, today=TODAY)
    assert plan.total_upfront == Decimal("975.00")
    assert plan.total_net_cost == Decimal("945.00")
    assert plan.remaining_budget == Decimal("225.00")
    assert plan.remaining_budget_net == Decimal("255.00")
    assert plan.remaining_budget_net - plan.remaining_budget == plan.total_cashback


def test_baseline_is_measured_before_promotions():
    """A $25 instant discount must show as $25 saved, not $0.

    If the baseline were taken after the discount, baseline and net cost would
    both be $75 and the report would claim no saving at all.
    """
    a = offer(base="100.00", taxes="0", fees="0")
    promos = [instant(fixed="25.00", minimum_spend=None)]
    plan = optimize_trip(trip_request(), [a], promos, today=TODAY)
    assert plan.naive_baseline_total == Decimal("100.00")
    assert plan.total_upfront == Decimal("75.00")
    assert plan.total_net_cost == Decimal("75.00")
    assert plan.estimated_savings == Decimal("25.00")


def test_budget_breach_produces_a_warning():
    request = trip_request(budget="100.00")
    plan = optimize_trip(request, [offer(base="500.00")], [], today=TODAY)
    assert plan.over_budget
    assert any("exceeds" in w for w in plan.warnings)


def test_savings_are_measured_against_cheapest_advertised_baseline():
    # Provider B is cheaper upfront; Provider A wins after an 8% cashback.
    a = offer(offer_id="a", platform="Provider A", base="1000.00", taxes="0", fees="0")
    b = offer(offer_id="b", platform="Provider B", base="970.00", taxes="0", fees="0")
    promos = [cashback(platform="Provider A", rate="0.08", cap=None)]
    plan = optimize_trip(trip_request(), [a, b], promos, today=TODAY)
    assert plan.naive_baseline_total == Decimal("970.00")
    assert plan.choices[0].selected.offer_id == "a"
    assert plan.total_net_cost == Decimal("920.00")
    assert plan.estimated_savings == Decimal("50.00")


def test_missing_segment_reports_a_warning_instead_of_crashing():
    request = trip_request(cities=("Chicago", "Atlanta"))
    plan = optimize_trip(request, [offer(city="Chicago")], [], today=TODAY)
    assert plan.choices[1].selected is None
    assert any("No offers" in w for w in plan.warnings)


def test_comparison_result_carries_an_explanation_and_source():
    result = build_comparison_result(
        offer(), [cashback(rate="0.08", cap="30.00")], today=TODAY
    )
    assert "Example Hotel" in result.explanation
    assert "net cost" in result.explanation
    assert result.offer.source_url
    assert result.offer.retrieved_at is not None


def test_demo_provider_is_deterministic():
    p1 = DemoProvider()
    p2 = DemoProvider()
    a = search_sync(p1, "Chicago", date(2026, 11, 10), date(2026, 11, 15))
    b = search_sync(p2, "Chicago", date(2026, 11, 10), date(2026, 11, 15))
    assert [o.base_price for o in a] == [o.base_price for o in b]
    assert all(o.data_mode == "demo" for o in a)


def test_end_to_end_pipeline_with_demo_data():
    demo = load_demo_trip()
    provider = DemoProvider()
    offers = []
    for seg in demo.segments:
        offers.extend(search_sync(provider, seg.city, seg.check_in, seg.check_out))
    promos = load_promotions()
    results, _ = compare_offers(offers, promos, today=TODAY, currency="USD")
    plan = optimize_trip(demo, offers, promos, today=TODAY)

    assert len(results) == len(offers)
    assert plan.offers_analyzed == len(offers)
    assert plan.estimated_savings >= Decimal("0.00")
    assert plan.currency == "USD"
