"""Deterministic pricing engine.

    Upfront Payment   = Base + Taxes + Mandatory Fees - Eligible Instant Discounts
    Estimated Cashback = min(Eligible Spend x Rate, Cap)
    Estimated Net Cost = Upfront Payment - Estimated Cashback

Rules enforced here:
  * decimal arithmetic only, quantized to cents;
  * cashback never applies to taxes or fees unless the rule says so;
  * a discount is never double-counted;
  * unknown-eligibility promotions never reduce the reported net cost;
  * a payment is never negative.
"""

from __future__ import annotations

from decimal import Decimal

from ..models.hotel import HotelOffer
from ..models.money import ZERO, max_zero, to_money
from ..models.promotion import Promotion
from ..models.result import PricingBreakdown
from .eligibility import EligibilityStatus


def compute_cashback_eligible_spend(offer: HotelOffer, promotion: Promotion) -> Decimal:
    """Taxes and mandatory fees are excluded unless the promotion allows them."""
    spend = offer.base_price
    if promotion.taxes_eligible:
        spend += offer.taxes_and_fees
    return to_money(spend)


def compute_instant_discount(offer: HotelOffer, promotion: Promotion) -> Decimal:
    """Upfront, point-of-sale reduction (coupons and instant discounts)."""
    if promotion.type == "cashback":
        return ZERO
    if promotion.rate is not None:
        value = offer.base_price * promotion.rate
    else:
        value = promotion.fixed_amount or ZERO
    if promotion.cap is not None:
        value = min(value, promotion.cap)
    return to_money(value)


def compute_cashback(
    eligible_spend: Decimal, promotion: Promotion
) -> tuple[Decimal, list[str]]:
    """Return ``(cashback, warnings)`` with the cap enforced."""
    warnings: list[str] = []
    if promotion.type != "cashback":
        return ZERO, warnings

    if promotion.rate is not None:
        value = eligible_spend * promotion.rate
    else:
        value = promotion.fixed_amount or ZERO

    value = to_money(value)
    if promotion.cap is not None and value > promotion.cap:
        warnings.append(
            f"Cashback capped at {promotion.cap} "
            f"(uncapped value would be {value})"
        )
        value = promotion.cap
    return to_money(max_zero(value)), warnings


def price_offer(
    offer: HotelOffer,
    promotions: list[Promotion],
    eligibility_status: dict[str, EligibilityStatus] | None = None,
) -> PricingBreakdown:
    """Full itemised cost of ``offer`` under ``promotions``.

    ``eligibility_status`` maps promotion_id -> status; promotions whose status
    is not "verified"/"estimated" contribute no savings.
    """
    eligibility_status = eligibility_status or {}
    warnings: list[str] = []

    if offer.is_simulated:
        warnings.append("Price comes from demo data and is not a live quote")

    instant_discount = ZERO
    cashback = ZERO
    eligible_spend = to_money(offer.base_price)

    for promo in promotions:
        status = eligibility_status.get(promo.promotion_id, EligibilityStatus.ESTIMATED)
        counts = status in {EligibilityStatus.VERIFIED, EligibilityStatus.ESTIMATED}

        if promo.type == "cashback":
            if not counts:
                warnings.append(
                    f"'{promo.promotion_id}' is not confirmed; cashback not counted"
                )
                continue
            spend = compute_cashback_eligible_spend(offer, promo)
            value, promo_warnings = compute_cashback(spend, promo)
            # Guard against stacking two cashback rules on the same spend.
            cashback = to_money(cashback + value)
            eligible_spend = max(eligible_spend, spend)
            warnings.extend(promo_warnings)
            if not promo.taxes_eligible:
                warnings.append(
                    f"'{promo.promotion_id}': taxes and fees are excluded from cashback"
                )
        else:
            if counts:
                instant_discount = to_money(
                    instant_discount + compute_instant_discount(offer, promo)
                )
            else:
                warnings.append(
                    f"'{promo.promotion_id}' is not confirmed; discount not counted"
                )

    upfront = to_money(
        max_zero(offer.base_price + offer.taxes + offer.mandatory_fees - instant_discount)
    )
    net = to_money(max_zero(upfront - cashback))

    # "Certain" cost ignores every non-verified benefit.
    certain = upfront
    for promo in promotions:
        status = eligibility_status.get(promo.promotion_id, EligibilityStatus.ESTIMATED)
        if status != EligibilityStatus.VERIFIED:
            continue
        if promo.type == "cashback":
            spend = compute_cashback_eligible_spend(offer, promo)
            value, _ = compute_cashback(spend, promo)
            certain = to_money(max_zero(certain - value))

    return PricingBreakdown(
        base_price=offer.base_price,
        taxes=offer.taxes,
        mandatory_fees=offer.mandatory_fees,
        instant_discount=instant_discount,
        upfront_payment=upfront,
        cashback_eligible_spend=eligible_spend,
        estimated_cashback=to_money(cashback),
        estimated_net_cost=net,
        guaranteed_net_cost=certain,
        warnings=_dedupe(warnings),
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
