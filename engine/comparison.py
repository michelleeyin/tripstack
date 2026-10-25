"""Offer comparison: price every offer, then rank them by a chosen objective."""

from __future__ import annotations

from datetime import date

from ..models.hotel import HotelOffer
from ..models.money import ZERO, fmt_money
from ..models.promotion import Promotion
from ..models.result import ComparisonResult
from .eligibility import EligibilityStatus, select_promotions
from .pricing import price_offer, sort_key_for_objective

Objective = str  # "lowest_net" | "lowest_upfront" | "lowest_certain"


def build_comparison_result(
    offer: HotelOffer,
    promotions: list[Promotion],
    today: date | None = None,
    objective: str = "lowest_net",
) -> ComparisonResult:
    """Match promotions to one offer and price it end-to-end.

    ``objective`` drives which promotion combination is chosen, so the set of
    promotions is optimal for the metric the user is actually sorting by.
    """
    chosen, all_results, warnings = select_promotions(
        offer, promotions, today, objective=objective
    )
    status_map = {r.promotion_id: r.status for r in all_results}

    breakdown = price_offer(offer, chosen, status_map)
    all_warnings = list(warnings) + list(breakdown.warnings)

    uncertain = any(
        r.status == EligibilityStatus.UNKNOWN
        for r in all_results
        if r.promotion_id in {p.promotion_id for p in chosen}
    )

    return ComparisonResult(
        offer=offer,
        breakdown=breakdown,
        applied_promotions=chosen,
        eligibility=all_results,
        warnings=_dedupe(all_warnings),
        confidence="unknown" if uncertain else _confidence(chosen),
        explanation=_explain(offer, chosen, breakdown, all_warnings),
    )


def _confidence(chosen: list[Promotion]) -> str:
    if not chosen:
        return "none"
    if all(p.verification_status == "verified" for p in chosen):
        return "verified"
    return "estimated"


def _explain(offer, chosen, breakdown, warnings) -> str:
    cur = offer.currency
    discount_term = (
        f" - instant discount {fmt_money(breakdown.instant_discount, cur)}"
        if breakdown.instant_discount > ZERO else ""
    )
    parts = [
        f"{offer.hotel_name} ({offer.room_type}) on {offer.platform}: "
        f"base {fmt_money(offer.base_price, cur)} + tax/fees "
        f"{fmt_money(offer.taxes_and_fees, cur)}{discount_term} = "
        f"{fmt_money(breakdown.upfront_payment, cur)} upfront for "
        f"{offer.nights} night(s)."
    ]
    if breakdown.instant_discount > ZERO:
        parts.append(
            f"Instant discount applied: {fmt_money(breakdown.instant_discount, cur)}."
        )
    if chosen:
        detail = "; ".join(_promo_sentence(p, cur) for p in chosen)
        parts.append(f"Promotions: {detail}.")
        parts.append(
            f"Estimated cashback {fmt_money(breakdown.estimated_cashback, cur)} "
            f"-> net cost {fmt_money(breakdown.estimated_net_cost, cur)}."
        )
    else:
        parts.append("No promotion matched this platform.")
    if not offer.refundable:
        parts.append("Non-refundable rate.")
    return " ".join(parts)


def _promo_sentence(p: Promotion, currency: str) -> str:
    if p.rate is not None:
        label = "cashback" if p.type == "cashback" else "off"
        benefit = f"{p.rate * 100:.2f}% {label}"
    else:
        label = "cashback" if p.type == "cashback" else "off"
        benefit = f"{fmt_money(p.fixed_amount, currency)} {label}"
    if p.cap is not None:
        benefit += f" (capped at {fmt_money(p.cap, currency)})"
    return f"{p.promotion_id} [{p.verification_status}] {benefit}"


def compare_offers(
    offers: list[HotelOffer],
    promotions: list[Promotion],
    today: date | None = None,
    currency: str = "USD",
    refundable_only: bool = False,
    exclude_uncertain: bool = False,
    objective: str = "lowest_net",
) -> tuple[list[ComparisonResult], list[str]]:
    """Price and rank a set of comparable offers.

    Offers in a different currency are dropped rather than converted: the MVP
    has no documented FX source, and silent conversion would be misleading.
    """
    warnings: list[str] = []
    results: list[ComparisonResult] = []

    for offer in offers:
        if offer.currency != currency:
            warnings.append(
                f"Skipped '{offer.offer_id}': currency {offer.currency} does not "
                f"match the trip currency {currency}"
            )
            continue
        if refundable_only and not offer.refundable:
            continue
        result = build_comparison_result(offer, promotions, today, objective=objective)
        if exclude_uncertain and result.promotion_status == "unknown":
            continue
        results.append(result)

    return rank_results(results, objective), warnings


def _sort_key(objective: Objective):
    """Offer ordering: objective metric, shared tie-break, then a stable id.

    The first two elements come from ``sort_key_for_objective``, the exact
    function promotion selection uses — so ranking offers and choosing
    promotions apply one rule, not two.
    """
    return lambda r: (*sort_key_for_objective(r.breakdown, objective), r.offer_id)


def rank_results(
    results: list[ComparisonResult], objective: Objective = "lowest_net"
) -> list[ComparisonResult]:
    return sorted(results, key=_sort_key(objective))


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
