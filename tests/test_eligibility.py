"""Eligibility validator tests."""

from __future__ import annotations

from datetime import date

from tripstack.engine.eligibility import (
    EligibilityStatus,
    evaluate_promotion,
    select_promotions,
)

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
