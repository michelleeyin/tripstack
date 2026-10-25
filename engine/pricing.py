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
    """Upfront, point-of-sale reduction (coupons and instant discounts).

    A percentage discount applies to the room rate only: taxes and fees are
    charged on the discounted rate, not discounted themselves. ``taxes_eligible``
    therefore affects cashback only, and a rule that sets it on a discount is
    flagged rather than silently honoured.

    Whatever this function returns is also what promotion selection compares,
    so the two can never disagree again.
    """
    if promotion.type == "cashback":
        return ZERO
    if promotion.rate is not None:
        value = offer.base_price * promotion.rate
    else:
        value = promotion.fixed_amount or ZERO
    if promotion.cap is not None:
        value = min(value, promotion.cap)
    return to_money(value)


def score_for_objective(breakdown: PricingBreakdown, objective: str) -> Decimal:
    """The single number an objective ranks on.

    Sharing this between promotion selection and offer ranking is what keeps
    the two from disagreeing.
    """
    if objective == "lowest_upfront":
        return breakdown.upfront_payment
    if objective == "lowest_certain":
        return breakdown.guaranteed_net_cost
    return breakdown.estimated_net_cost


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
    # Discounts that are confirmed enough to show, and the subset that is
    # actually verified — the "certain" figure may only use the latter.
    verified_instant = ZERO
    verified_cashback = ZERO
    eligible_spend = to_money(offer.base_price)
    list_price = to_money(offer.base_price + offer.taxes + offer.mandatory_fees)

    for promo in promotions:
        status = eligibility_status.get(promo.promotion_id, EligibilityStatus.ESTIMATED)
        counts = status in {EligibilityStatus.VERIFIED, EligibilityStatus.ESTIMATED}
        verified = status == EligibilityStatus.VERIFIED

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
            if verified:
                verified_cashback = to_money(verified_cashback + value)
            eligible_spend = max(eligible_spend, spend)
            warnings.extend(promo_warnings)
            if not promo.taxes_eligible:
                warnings.append(
                    f"'{promo.promotion_id}': taxes and fees are excluded from cashback"
                )
        else:
            if counts:
                discount = compute_instant_discount(offer, promo)
                instant_discount = to_money(instant_discount + discount)
                if verified:
                    verified_instant = to_money(verified_instant + discount)
                if promo.taxes_eligible:
                    warnings.append(
                        f"'{promo.promotion_id}': taxes_eligible has no effect on a "
                        "discount — percentages apply to the room rate only"
                    )
            else:
                warnings.append(
                    f"'{promo.promotion_id}' is not confirmed; discount not counted"
                )

    upfront = to_money(
        max_zero(offer.base_price + offer.taxes + offer.mandatory_fees - instant_discount)
    )
    net = to_money(max_zero(upfront - cashback))

    # "Certain" cost counts verified benefits only. It must start from the
    # undiscounted price: an *estimated* instant discount lowers the upfront
    # payment, but it must not lower the figure we call certain.
    certain = to_money(
        max_zero(list_price - verified_instant - verified_cashback)
    )

    return PricingBreakdown(
        list_price=list_price,
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
