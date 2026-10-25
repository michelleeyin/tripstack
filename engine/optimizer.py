"""Trip-level optimizer.

For each lodging segment: price every comparable offer, rank by the chosen
objective, pick the winner. Then aggregate and compare against a clearly
defined baseline.

Baseline definition (naive booking): the cheapest *upfront* price in each
segment, ignoring promotions entirely — i.e. what a traveller who only sorts
by advertised price would pay. Savings = baseline - optimized net cost.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..models.hotel import HotelOffer, TripRequest
from ..models.money import ZERO, to_money
from ..models.promotion import Promotion
from ..models.result import ComparisonResult, SegmentChoice, TripPlan
from .comparison import build_comparison_result, rank_results


def optimize_trip(
    request: TripRequest,
    offers: list[HotelOffer],
    promotions: list[Promotion],
    today: date | None = None,
) -> TripPlan:
    warnings: list[str] = []
    choices: list[SegmentChoice] = []
    analyzed = 0

    total_upfront = ZERO
    total_cashback = ZERO
    total_net = ZERO
    baseline = ZERO
    average_baseline = ZERO

    for segment in request.segments:
        seg_offers = [
            o
            for o in offers
            if o.segment_key == segment.key and o.currency == request.currency
        ]
        if request.refundable_only:
            seg_offers = [o for o in seg_offers if o.refundable]
        if not seg_offers:
            warnings.append(
                f"No offers found for {segment.city} "
                f"({segment.check_in} to {segment.check_out})"
            )
            choices.append(
                SegmentChoice(
                    city=segment.city,
                    check_in=segment.check_in,
                    check_out=segment.check_out,
                    warnings=["No comparable offers available"],
                )
            )
            continue

        analyzed += len(seg_offers)
        results = [
            build_comparison_result(o, promotions, today) for o in seg_offers
        ]
        ranked = rank_results(results, request.objective)

        if request.objective == "lowest_certain":
            ranked = rank_results(results, "lowest_certain")

        selected = ranked[0]
        # Naive baseline: cheapest advertised upfront price in the segment.
        naive = min(r.upfront_payment for r in ranked)
        average = sum((r.upfront_payment for r in ranked), ZERO) / Decimal(len(ranked))

        baseline = to_money(baseline + naive)
        average_baseline = to_money(average_baseline + average)
        total_upfront = to_money(total_upfront + selected.upfront_payment)
        total_cashback = to_money(total_cashback + selected.estimated_cashback)
        total_net = to_money(total_net + selected.estimated_net_cost)

        seg_warnings = list(selected.warnings)
        if not selected.offer.refundable:
            seg_warnings.append(
                "Selected rate is non-refundable; cancellation terms differ from "
                "refundable alternatives"
            )
        choices.append(
            SegmentChoice(
                city=segment.city,
                check_in=segment.check_in,
                check_out=segment.check_out,
                selected=selected,
                alternatives=ranked[1:],
                warnings=_dedupe(seg_warnings),
            )
        )

    savings = to_money(max(baseline - total_net, ZERO))

    if request.budget > 0 and total_upfront > request.budget:
        warnings.append(
            f"Selected itinerary costs {total_upfront} upfront, which exceeds the "
            f"{request.budget} budget by {to_money(total_upfront - request.budget)}"
        )
    if any(c.selected is None for c in choices):
        warnings.append(
            "Some segments have no offers; totals cover available segments only"
        )
    if total_cashback > ZERO:
        warnings.append(
            "Cashback figures are estimates based on published terms and are not "
            "guaranteed payouts"
        )

    return TripPlan(
        choices=choices,
        total_upfront=total_upfront,
        total_cashback=total_cashback,
        total_net_cost=total_net,
        naive_baseline_total=baseline,
        average_baseline_total=average_baseline,
        estimated_savings=savings,
        budget=request.budget,
        offers_analyzed=analyzed,
        currency=request.currency,
        warnings=_dedupe(warnings),
    )


def best_alternative_without_promotions(
    results: list[ComparisonResult],
) -> ComparisonResult | None:
    """Cheapest offer judged purely on upfront payment (no promotion logic)."""
    if not results:
        return None
    return min(results, key=lambda r: (r.upfront_payment, r.offer_id))


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
