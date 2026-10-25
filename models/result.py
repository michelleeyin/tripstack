"""Result schemas produced by the pricing engine and optimizer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from .hotel import HotelOffer
from .money import ZERO, to_money
from .promotion import Promotion

if TYPE_CHECKING:  # avoids a models <-> engine import cycle
    from ..engine.eligibility import EligibilityResult


@dataclass
class PricingBreakdown:
    """Itemised cost of one offer under one set of promotions."""

    base_price: Decimal
    taxes: Decimal
    mandatory_fees: Decimal
    # Price before any promotion: base + taxes + mandatory fees.
    list_price: Decimal
    instant_discount: Decimal
    upfront_payment: Decimal
    cashback_eligible_spend: Decimal
    estimated_cashback: Decimal
    estimated_net_cost: Decimal
    guaranteed_net_cost: Decimal
    warnings: list[str] = field(default_factory=list)


@dataclass
class ComparisonResult:
    """One ranked, fully explained offer."""

    offer: HotelOffer
    breakdown: PricingBreakdown
    applied_promotions: list[Promotion] = field(default_factory=list)
    eligibility: list["EligibilityResult"] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: str = "estimated"
    explanation: str = ""
    distance_km: float | None = None
    location_reference: str = ""

    # --- convenience passthroughs -------------------------------------
    @property
    def offer_id(self) -> str:
        return self.offer.offer_id

    @property
    def upfront_payment(self) -> Decimal:
        return self.breakdown.upfront_payment

    @property
    def estimated_cashback(self) -> Decimal:
        return self.breakdown.estimated_cashback

    @property
    def estimated_net_cost(self) -> Decimal:
        return self.breakdown.estimated_net_cost

    @property
    def guaranteed_net_cost(self) -> Decimal:
        return self.breakdown.guaranteed_net_cost

    @property
    def currency(self) -> str:
        return self.offer.currency

    @property
    def promotion_status(self) -> str:
        if not self.applied_promotions:
            return "none"
        statuses = {p.verification_status for p in self.applied_promotions}
        for candidate in ("unknown", "estimated", "verified"):
            if candidate in statuses:
                return candidate
        return "estimated"

    def to_row(self) -> dict[str, object]:
        return {
            "Hotel": self.offer.hotel_name,
            "City": self.offer.city,
            "Area": self.offer.area,
            "Distance (km)": round(self.distance_km, 2) if self.distance_km is not None else None,
            "Distance to": self.location_reference or "Not available",
            "Platform": self.offer.platform,
            "Room": self.offer.room_type,
            "Refundable": "Yes" if self.offer.refundable else "No",
            "Upfront": float(self.upfront_payment),
            "Cashback": float(self.estimated_cashback),
            "Net Cost": float(self.estimated_net_cost),
            "Confidence": self.promotion_status,
            "Mode": self.offer.data_mode,
        }


@dataclass
class SegmentChoice:
    """The winning offer for one trip segment, plus the runners-up."""

    city: str
    check_in: date
    check_out: date
    selected: ComparisonResult | None = None
    alternatives: list[ComparisonResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    location_preference: str = "any"
    location_reference: str = ""
    max_distance_km: float | None = None

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days


@dataclass
class TripPlan:
    """Trip-level savings report."""

    choices: list[SegmentChoice]
    total_upfront: Decimal
    total_cashback: Decimal
    total_net_cost: Decimal
    naive_baseline_total: Decimal
    average_baseline_total: Decimal
    estimated_savings: Decimal
    budget: Decimal
    offers_analyzed: int
    currency: str = "USD"
    warnings: list[str] = field(default_factory=list)

    @property
    def remaining_budget(self) -> Decimal:
        """Cash you actually have left on the day you pay (upfront basis)."""
        if self.budget <= 0:
            return Decimal("0.00")
        return to_money(self.budget - self.total_upfront)

    @property
    def remaining_budget_net(self) -> Decimal:
        """Budget left *after* estimated cashback — not spendable today.

        Kept separate from :attr:`remaining_budget` because cashback is an
        estimate that arrives later, if at all.
        """
        if self.budget <= 0:
            return Decimal("0.00")
        return to_money(self.budget - self.total_net_cost)

    @property
    def over_budget(self) -> bool:
        return self.budget > 0 and self.total_upfront > self.budget

    @property
    def savings_pct(self) -> float:
        if self.naive_baseline_total <= 0:
            return 0.0
        return float(self.estimated_savings / self.naive_baseline_total * 100)

    @property
    def savings_vs_average(self) -> Decimal:
        return to_money(max(self.average_baseline_total - self.total_net_cost, ZERO))

    @property
    def savings_vs_average_pct(self) -> float:
        if self.average_baseline_total <= 0:
            return 0.0
        return float(self.savings_vs_average / self.average_baseline_total * 100)
