"""Pricing engine tests (section 9 of the technical plan)."""

from __future__ import annotations

from decimal import Decimal

from tripstack.engine.eligibility import EligibilityStatus
from tripstack.engine.pricing import (
    compute_cashback,
    compute_cashback_eligible_spend,
    compute_instant_discount,
    price_offer,
)
from tripstack.models.money import to_money

from .helpers import cashback, instant, offer


def test_upfront_payment_includes_taxes_and_mandatory_fees():
    result = price_offer(offer(), [])
    assert result.base_price == Decimal("850.00")
    assert result.upfront_payment == Decimal("975.00")
    assert result.estimated_cashback == Decimal("0.00")
    assert result.estimated_net_cost == Decimal("975.00")


def test_cashback_is_capped():
    promo = cashback(rate="0.08", cap="30.00")
    result = price_offer(offer(), [promo], {promo.promotion_id: EligibilityStatus.ESTIMATED})
    # 850 * 0.08 = 68 -> capped at 30
    assert result.estimated_cashback == Decimal("30.00")
    assert result.estimated_net_cost == Decimal("945.00")
    assert any("capped" in w for w in result.warnings)


def test_cashback_excludes_taxes_and_fees_by_default():
    promo = cashback(rate="0.10", cap=None)
    assert compute_cashback_eligible_spend(offer(), promo) == Decimal("850.00")
    promo_taxed = cashback(rate="0.10", cap=None, taxes_eligible=True)
    assert compute_cashback_eligible_spend(offer(), promo_taxed) == Decimal("975.00")


def test_instant_discount_reduces_upfront_payment():
    promo = instant(fixed="25.00")
    result = price_offer(offer(), [promo], {promo.promotion_id: EligibilityStatus.ESTIMATED})
    assert result.instant_discount == Decimal("25.00")
    assert result.upfront_payment == Decimal("950.00")


def test_unknown_promotion_is_not_counted_as_a_saving():
    promo = cashback(rate="0.08", cap="30.00")
    result = price_offer(offer(), [promo], {promo.promotion_id: EligibilityStatus.UNKNOWN})
    assert result.estimated_cashback == Decimal("0.00")
    assert result.estimated_net_cost == result.upfront_payment
    assert any("not confirmed" in w for w in result.warnings)


def test_verified_promotion_counts_toward_guaranteed_net_cost():
    promo = cashback(rate="0.08", cap="30.00")
    result = price_offer(offer(), [promo], {promo.promotion_id: EligibilityStatus.VERIFIED})
    assert result.guaranteed_net_cost == Decimal("945.00")


def test_estimated_promotion_does_not_count_as_guaranteed():
    promo = cashback(rate="0.08", cap="30.00")
    result = price_offer(offer(), [promo], {promo.promotion_id: EligibilityStatus.ESTIMATED})
    assert result.guaranteed_net_cost == Decimal("975.00")
    assert result.estimated_net_cost == Decimal("945.00")


def test_money_uses_exact_decimal_arithmetic():
    value, _ = compute_cashback(Decimal("850.00"), cashback(rate="0.08", cap=None))
    assert value == Decimal("68.00")
    assert value == to_money(68.0)
    assert isinstance(value, Decimal)


def test_payment_never_goes_negative():
    promo = instant(fixed="2000.00")
    result = price_offer(offer(base="100.00", taxes="0", fees="0"), [promo],
                         {promo.promotion_id: EligibilityStatus.ESTIMATED})
    assert result.upfront_payment == Decimal("0.00")


def test_fixed_amount_cashback_and_discount_types():
    promo = cashback(rate=None, cap=None, fixed="40.00")
    value, _ = compute_cashback(Decimal("500.00"), promo)
    assert value == Decimal("40.00")

    discount_promo = instant(fixed="25.00")
    assert compute_instant_discount(offer(), discount_promo) == Decimal("25.00")


def test_demo_offers_are_flagged_in_warnings():
    result = price_offer(offer(), [])
    assert any("demo data" in w for w in result.warnings)
