"""TripStack engine — eligibility, pricing, comparison and optimization."""

from .comparison import compare_offers, rank_results
from .eligibility import EligibilityStatus, evaluate_promotion, select_promotions
from .optimizer import optimize_trip
from .pricing import compute_cashback, price_offer

__all__ = [
    "EligibilityStatus",
    "evaluate_promotion",
    "select_promotions",
    "compute_cashback",
    "price_offer",
    "compare_offers",
    "rank_results",
    "optimize_trip",
]
