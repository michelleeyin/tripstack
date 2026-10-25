"""Pure session workflow: reviewed terms -> same-offer repricing -> trip plan."""
from __future__ import annotations

import hashlib

from .engine.comparison import build_comparison_result
from .engine.optimizer import optimize_trip
from .models.promotion import Promotion


def promotion_key(terms: str, platform: str, currency: str) -> str:
    payload = '\0'.join((terms.strip(), platform.strip().lower(), currency.upper()))
    return 'custom-' + hashlib.sha256(payload.encode()).hexdigest()[:16]


def accept_promotion(promotion: Promotion, *, reviewed: bool) -> Promotion:
    if not reviewed:
        raise ValueError('Review the extracted conditions before applying this promotion.')
    if promotion.requires_verification or promotion.verification_status == 'unknown':
        raise ValueError('Unresolved terms cannot be included in reported savings.')
    # A user review acknowledges the extraction; it does not verify a payout.
    return promotion.model_copy(update={'verification_status': 'estimated'})


def evaluate_snapshot(request, offers, promotions):
    plan = optimize_trip(request, offers, promotions)
    # The table, preview and report use the exact same feasible hotel set.
    results = [result for choice in plan.choices if choice.selected
               for result in [choice.selected, *choice.alternatives]]
    return results, plan
