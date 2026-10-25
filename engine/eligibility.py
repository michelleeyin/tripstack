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


def _benefit_estimate(promotion: Promotion, offer: HotelOffer) -> Decimal:
    """Rough benefit size used only for ranking promotions, never for reporting."""
    spend = offer.base_price
    if promotion.taxes_eligible:
        spend += offer.taxes_and_fees
    if promotion.rate is not None:
        value = spend * promotion.rate
    else:
        value = promotion.fixed_amount or ZERO
    if promotion.cap is not None:
        value = min(value, promotion.cap)
    return value


def select_promotions(
    offer: HotelOffer,
    promotions: list[Promotion],
    today: date | None = None,
) -> tuple[list[Promotion], list[EligibilityResult], list[str]]:
    """Pick the promotions that may be applied to ``offer`` together.

    Stacking rule: a non-stackable promotion is used alone. Only mutually
    stackable promotions combine. Incompatible promotions are never summed.
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

    usable.sort(key=lambda pr: _benefit_estimate(pr[0], offer), reverse=True)
    chosen: list[Promotion] = [usable[0][0]]

    if usable[0][0].stackable:
        for p, _ in usable[1:]:
            if p.stackable:
                chosen.append(p)
    elif len(usable) > 1:
        names = ", ".join(p.promotion_id for p, _ in usable[1:])
        warnings.append(
            f"'{usable[0][0].promotion_id}' cannot be combined with other offers; "
            f"skipped {names}"
        )

    return chosen, results, warnings
