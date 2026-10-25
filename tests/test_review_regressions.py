from decimal import Decimal

import pytest
from pydantic import ValidationError

from tripstack.ai.promotion_parser import parse_promotion_terms
from tripstack.engine.comparison import build_comparison_result
from tripstack.models.promotion import Promotion
from tripstack.providers.amadeus import _is_refundable
from .helpers import TODAY, instant, offer


def test_grouped_money_survives_extraction_and_grounding():
    p, _ = parse_promotion_terms('Save $1,000 instantly on stays of $2,000 or more.', 'p', use_ai=False)
    assert p.fixed_amount == Decimal('1000')
    assert p.minimum_spend == Decimal('2000')
    p, _ = parse_promotion_terms('Earn 8% cashback, capped at $1,000.50.', 'p', use_ai=False)
    assert p.cap == Decimal('1000.50')


@pytest.mark.parametrize('policy', [{}, {'cancellations': [{'type': 'FULL_STAY'}]}, {'cancellations': [{'amount': '100'}]}])
def test_unknown_or_penalty_policy_is_not_confirmed_refundable(policy):
    assert not _is_refundable({'policies': policy})


def test_explicit_refundable_policy_is_supported():
    assert _is_refundable({'policies': {'refundable': {'cancellationRefund': 'REFUNDABLE'}}})
    assert not _is_refundable({'policies': {'refundable': {'cancellationRefund': 'NON_REFUNDABLE'}}})


@pytest.mark.parametrize('field', ['fixed_amount', 'cap', 'minimum_spend'])
def test_negative_promotion_money_is_rejected(field):
    with pytest.raises(ValidationError):
        Promotion(promotion_id='p', rate='.10', **{field: '-25'})


def test_explanation_accounts_for_discount_in_equation():
    r = build_comparison_result(offer(base='100', taxes='10', fees='0'), [instant(fixed='25', minimum_spend=None)], TODAY)
    assert '$100.00 + tax/fees $10.00 - instant discount $25.00 = $85.00' in r.explanation


@pytest.mark.parametrize('kind,expected', [('cashback', '10.00% cashback'), ('instant_discount', '10.00% off'), ('coupon', '10.00% off')])
def test_percentage_promotion_wording_matches_type(kind, expected):
    p = Promotion(promotion_id='p', type=kind, rate='.10')
    r = build_comparison_result(offer(), [p], TODAY)
    assert expected in r.explanation


def test_explicit_zero_penalties_are_refundable_but_mixed_penalties_are_not():
    assert _is_refundable({'policies': {'cancellations': [{'amount': '0.00'}]}})
    assert not _is_refundable({'policies': {'cancellations': [{'amount': '0'}, {'amount': '100'}]}})
