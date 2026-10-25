"""Promotion eligibility validation.

A promotion only reaches the pricing engine after it passes these checks.
Anything ambiguous is downgraded to ``unknown`` and is never counted as a
guaranteed saving.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

from ..models.hotel import HotelOffer
from ..models.money import ZERO
from ..models.promotion import Promotion


class EligibilityStatus(str, Enum):
    VERIFIED = "verified"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"
    INELIGIBLE = "ineligible"


@dataclass
class EligibilityResult:
    promotion_id: str
    status: EligibilityStatus
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def applies_discount(self) -> bool:
        """Whether the promotion may enter the pricing calculation at all."""
        return self.status in {
            EligibilityStatus.VERIFIED,
            EligibilityStatus.ESTIMATED,
            EligibilityStatus.UNKNOWN,
        }

    @property
    def counts_as_saving(self) -> bool:
        """Whether the benefit may be subtracted from the reported net cost."""
        return self.status in {
            EligibilityStatus.VERIFIED,
            EligibilityStatus.ESTIMATED,
        }


def evaluate_promotion(
    promotion: Promotion,
    offer: HotelOffer,
    today: date | None = None,
) -> EligibilityResult:
    """Check one promotion against one offer.

    Order matters: hard failures (expired, wrong platform, below minimum
    spend) return ``ineligible`` immediately and stop evaluation.
    """
    today = today or date.today()
    res = EligibilityResult(promotion_id=promotion.promotion_id, status=EligibilityStatus.VERIFIED)

    if promotion.valid_until is not None and promotion.valid_until < today:
        res.status = EligibilityStatus.INELIGIBLE
        res.reasons.append(
            f"Expired on {promotion.valid_until.isoformat()}"
        )
        return res

    if not promotion.matches_platform(offer.platform):
        res.status = EligibilityStatus.INELIGIBLE
        res.reasons.append(
            f"Promotion is limited to '{promotion.platform}', offer is on '{offer.platform}'"
        )
        return res

    if promotion.minimum_spend is not None and offer.base_price < promotion.minimum_spend:
        res.status = EligibilityStatus.INELIGIBLE
        res.reasons.append(
            f"Base price {offer.base_price} is below the "
            f"{promotion.minimum_spend} minimum spend"
        )
        return res

    if promotion.requires_verification or promotion.verification_status == "unknown":
        res.status = EligibilityStatus.UNKNOWN
        res.warnings.append(
            "Terms could not be confirmed from the source; promotion excluded "
            "from reported savings"
        )
        return res

    res.status = EligibilityStatus(
        "verified" if promotion.verification_status == "verified" else "estimated"
    )
    if res.status == EligibilityStatus.ESTIMATED:
        res.warnings.append(
            "Cashback is estimated from published terms and is not guaranteed"
        )

    if not offer.refundable:
        res.warnings.append(
            "Offer is non-refundable; a cancelled stay forfeits the cashback"
        )
    return res


def select_promotions(
    offer: HotelOffer,
    promotions: list[Promotion],
    today: date | None = None,
    objective: str = "lowest_net",
) -> tuple[list[Promotion], list[EligibilityResult], list[str]]:
    """Pick the promotions that may be applied to ``offer`` together.

    Stacking rule: a non-stackable promotion is used alone. Only mutually
    stackable promotions combine. Incompatible promotions are never summed.

    Candidates are priced with the real engine (``price_offer``) and compared
    on the same metric the user's objective ranks offers by. Maintaining a
    separate "estimated benefit" here caused two bugs: picking a larger
    estimated discount over a smaller *verified* one under the "lowest certain
    cost" objective, and valuing a percentage discount against a tax base the
    pricing engine never used.
    """
    results = [evaluate_promotion(p, offer, today) for p in promotions]
    usable = [
        (p, r)
        for p, r in zip(promotions, results)
        if r.applies_discount and r.counts_as_saving
    ]
    warnings: list[str] = []

    skipped = [
        r for r in results
        if r.status == EligibilityStatus.UNKNOWN
    ]
    for r in skipped:
        warnings.extend(r.warnings)

    if not usable:
        return [], results, warnings

    # Local import: pricing imports this module, so this must not be top-level.
    from .pricing import price_offer, score_for_objective, sort_key_for_objective

    status_map = {r.promotion_id: r.status for p, r in usable}

    # Every admissible combination: each promotion alone, plus the stackable
    # group together. Two stackable $30 discounts ($60) must beat a lone $50.
    stackable = [p for p, _ in usable if p.stackable]
    candidate_sets: list[list[Promotion]] = [[p] for p, _ in usable]
    if len(stackable) > 1:
        candidate_sets.append(stackable)

    scored = [
        (combo, price_offer(offer, combo, status_map)) for combo in candidate_sets
    ]
    # Identical ordering to offer ranking: objective metric, then the shared
    # tie-break, then the smaller combination, then a stable id order. Without
    # the tie-break two equal-scoring combinations were chosen by input order.
    chosen, best = min(
        scored,
        key=lambda c: (
            sort_key_for_objective(c[1], objective),
            len(c[0]),
            sorted(p.promotion_id for p in c[0]),
        ),
    )
    best_value = score_for_objective(best, objective)

    chosen_ids = {p.promotion_id for p in chosen}
    skipped = [p.promotion_id for p, _ in usable if p.promotion_id not in chosen_ids]
    if skipped:
        if len(chosen) == 1 and not chosen[0].stackable:
            warnings.append(
                f"'{chosen[0].promotion_id}' cannot be combined with other offers; "
                f"skipped {', '.join(skipped)}"
            )
        else:
            warnings.append(
                f"Skipped {', '.join(skipped)}: the selected combination scores "
                f"better on '{objective}' ({best_value})"
            )

    return chosen, results, warnings
