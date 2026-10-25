"""Eligibility validator tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tripstack.engine.eligibility import (
    EligibilityStatus,
    evaluate_promotion,
    select_promotions,
)
from tripstack.engine.pricing import price_offer

from .helpers import TODAY, cashback, instant, offer


def test_expired_promotion_is_ineligible():
    promo = cashback(valid_until=date(2025, 12, 31))
    result = evaluate_promotion(promo, offer(), today=TODAY)
    assert result.status == EligibilityStatus.INELIGIBLE
    assert not result.applies_discount


def test_platform_mismatch_is_ineligible():
    promo = cashback(platform="Provider Z")
    result = evaluate_promotion(promo, offer(platform="Provider A"), today=TODAY)
    assert result.status == EligibilityStatus.INELIGIBLE


def test_minimum_spend_not_met_is_ineligible():
    promo = cashback(minimum_spend="900.00")
    result = evaluate_promotion(promo, offer(base="850.00"), today=TODAY)
    assert result.status == EligibilityStatus.INELIGIBLE


def test_eligible_promotion_is_estimated_and_warned():
    promo = cashback()
    result = evaluate_promotion(promo, offer(), today=TODAY)
    assert result.status == EligibilityStatus.ESTIMATED
    assert result.counts_as_saving
    assert any("not guaranteed" in w for w in result.warnings)


def test_unknown_promotion_is_never_a_guaranteed_saving():
    promo = cashback(status="unknown")
    result = evaluate_promotion(promo, offer(), today=TODAY)
    assert result.status == EligibilityStatus.UNKNOWN
    assert result.applies_discount
    assert not result.counts_as_saving


def test_incompatible_coupon_stacking_is_rejected():
    promos = [
        cashback(promo_id="a", rate="0.08", cap="30.00", stackable=False),
        instant(promo_id="b", fixed="25.00", stackable=False),
    ]
    chosen, _, warnings = select_promotions(offer(), promos, today=TODAY)
    assert len(chosen) == 1
    assert any("cannot be combined" in w for w in warnings)


def test_stackable_promotions_combine():
    promos = [
        cashback(promo_id="a", rate="0.08", cap="30.00", stackable=True),
        instant(promo_id="b", fixed="25.00", stackable=True),
    ]
    chosen, _, warnings = select_promotions(offer(), promos, today=TODAY)
    assert {p.promotion_id for p in chosen} == {"a", "b"}
    assert not any("cannot be combined" in w for w in warnings)


def test_stackable_pair_beats_a_larger_single_discount():
    """Two stackable $30 discounts ($60) must beat a lone $50 discount."""
    promos = [
        instant(promo_id="solo-50", fixed="50.00", minimum_spend=None, stackable=False),
        instant(promo_id="stack-a", fixed="30.00", minimum_spend=None, stackable=True),
        instant(promo_id="stack-b", fixed="30.00", minimum_spend=None, stackable=True),
    ]
    chosen, _, _ = select_promotions(offer(), promos, today=TODAY)
    assert {p.promotion_id for p in chosen} == {"stack-a", "stack-b"}


def test_best_single_discount_wins_when_stacking_is_worth_less():
    promos = [
        instant(promo_id="solo-50", fixed="50.00", minimum_spend=None, stackable=False),
        instant(promo_id="stack-a", fixed="10.00", minimum_spend=None, stackable=True),
        instant(promo_id="stack-b", fixed="10.00", minimum_spend=None, stackable=True),
    ]
    chosen, _, warnings = select_promotions(offer(), promos, today=TODAY)
    assert [p.promotion_id for p in chosen] == ["solo-50"]
    assert any("cannot be combined" in w for w in warnings)


def test_certain_objective_prefers_a_verified_discount_over_a_bigger_estimate():
    """$100 room: estimated $50 off vs verified $30 off.

    Under "lowest certain cost" the verified $30 wins (certain cost $70 vs
    $100); under "lowest net cost" the bigger estimated discount does.
    """
    promos = [
        instant(promo_id="est-50", fixed="50.00", minimum_spend=None, status="estimated"),
        instant(promo_id="ver-30", fixed="30.00", minimum_spend=None, status="verified"),
    ]
    o = offer(base="100.00", taxes="0", fees="0")

    chosen, _, _ = select_promotions(o, promos, today=TODAY, objective="lowest_certain")
    assert [p.promotion_id for p in chosen] == ["ver-30"]

    chosen_net, _, _ = select_promotions(o, promos, today=TODAY, objective="lowest_net")
    assert [p.promotion_id for p in chosen_net] == ["est-50"]


def test_upfront_objective_prefers_a_discount_over_cashback():
    """$100 room: $50 cashback leaves $100 upfront; $30 off leaves $70."""
    promos = [
        cashback(promo_id="cb-50", rate="0.50", cap=None, minimum_spend=None),
        instant(promo_id="off-30", fixed="30.00", minimum_spend=None),
    ]
    chosen, _, _ = select_promotions(
        offer(base="100.00", taxes="0", fees="0"),
        promos,
        today=TODAY,
        objective="lowest_upfront",
    )
    assert [p.promotion_id for p in chosen] == ["off-30"]


def test_selection_uses_the_same_tax_basis_as_the_pricing_engine():
    """$100 room + $100 tax: 20% off is $20 (room rate only), so $30 off wins."""
    from tripstack.models.promotion import Promotion

    o = offer(base="100.00", taxes="100.00", fees="0")
    pct = Promotion(
        promotion_id="pct-20",
        type="instant_discount",
        rate=Decimal("0.20"),
        taxes_eligible=True,
        verification_status="estimated",
    )
    promos = [pct, instant(promo_id="fix-30", fixed="30.00", minimum_spend=None)]

    chosen, _, _ = select_promotions(o, promos, today=TODAY, objective="lowest_net")
    assert [p.promotion_id for p in chosen] == ["fix-30"]

    # What selection predicted must be what the engine actually charges.
    breakdown = price_offer(
        o, chosen, {p.promotion_id: EligibilityStatus.ESTIMATED for p in chosen}
    )
    assert breakdown.upfront_payment == Decimal("170.00")


def test_wildcard_platform_matches_any_offer():
    promo = cashback(platform="*")
    result = evaluate_promotion(promo, offer(platform="Anything"), today=TODAY)
    assert result.status == EligibilityStatus.ESTIMATED


def test_ineligible_promotions_are_excluded_from_selection():
    promos = [
        cashback(promo_id="expired", valid_until=date(2020, 1, 1)),
        cashback(promo_id="good", rate="0.05", cap="50.00"),
    ]
    chosen, results, _ = select_promotions(offer(), promos, today=TODAY)
    assert [p.promotion_id for p in chosen] == ["good"]
    assert results[0].status == EligibilityStatus.INELIGIBLE
