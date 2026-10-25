import json
from decimal import Decimal

import httpx
import pytest

from tripstack.ai.gemma_client import GemmaClient, GemmaUnavailable
from tripstack.ai.promotion_parser import parse_promotion_terms
from tripstack.workflow import accept_promotion, evaluate_snapshot, promotion_key
from .helpers import offer, trip_request


class Model:
    model = 'gemma-test'
    last_metrics = {'output_tokens': 42}

    def __init__(self, payload):
        self.payload = payload

    def generate_json(self, prompt):
        return self.payload


def test_structured_inference_records_metrics_and_cpu_setting():
    def handler(request):
        body = json.loads(request.content)
        assert body['format']['type'] == 'object'
        assert body['options']['num_gpu'] == 0
        assert body['options']['num_predict'] == 512
        return httpx.Response(200, json={'response': '{"rate":0.075}', 'eval_count': 12,
                                        'prompt_eval_count': 50, 'load_duration': 2000000})
    client = GemmaClient(cpu=True, transport=httpx.MockTransport(handler))
    assert client.generate_json('read terms')['rate'] == .075
    assert client.last_metrics['output_tokens'] == 12
    assert client.last_metrics['inference_verified']


def test_installed_model_check_does_not_claim_inference_success():
    client = GemmaClient(model='missing', transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'models': [{'name': 'other'}]})))
    result = client.diagnostics()
    assert result['reachable'] and not result['installed']
    assert not result['inference_verified']
    assert not client.is_available()


@pytest.mark.parametrize('body,status', [({'error':'Metal allocation failed'},500),
    ({'response':'not json'},200), ({'response':'{}', 'done_reason':'length'},200)])
def test_inference_failures_are_explicit(body, status):
    client = GemmaClient(transport=httpx.MockTransport(lambda req: httpx.Response(status, json=body)))
    with pytest.raises(GemmaUnavailable):
        client.generate_json('read terms')
    assert not client.last_metrics.get('inference_verified')


def test_real_client_failure_is_labelled_fallback_with_reason():
    client = GemmaClient(transport=httpx.MockTransport(
        lambda req: httpx.Response(500, json={'error':'Metal allocation failed'})))
    promo, trace = parse_promotion_terms('Earn 7.5% cashback, capped at $60.', 'p', client=client)
    assert trace.method == 'heuristic'
    assert 'Metal allocation failed' in trace.fallback_reason
    assert promo.rate == Decimal('.075')
    assert '$60' in trace.evidence['cap']


def test_model_cannot_override_explicit_exclusions():
    terms = 'Earn 7.5% cashback. Taxes and fees are excluded. Cannot be combined with coupons.'
    model = Model({'rate': .075, 'taxes_eligible': True, 'stackable': True})
    for strategy in ['hybrid', 'ai']:
        promo, trace = parse_promotion_terms(terms, 'p', client=model, strategy=strategy)
        assert not promo.taxes_eligible and not promo.stackable
        assert trace.warnings


@pytest.mark.parametrize('terms', ['Earn 5% cashback, or 10% for new users.', 'Earn 5% cashback. ' + 'x' * 2100])
def test_ambiguous_or_truncated_terms_cannot_be_accepted(terms):
    promo, trace = parse_promotion_terms(terms, 'p', use_ai=False)
    assert promo.requires_verification
    with pytest.raises(ValueError):
        accept_promotion(promo, reviewed=True)


def test_amount_role_conflict_is_held_for_review():
    model = Model({'fixed_amount':200, 'minimum_spend':25, 'promotion_type':'instant_discount'})
    promo, trace = parse_promotion_terms('Save $25 instantly on stays of $200 or more.', 'p', client=model)
    assert promo.requires_verification
    assert any('source role' in w for w in trace.warnings)


def test_reviewed_extraction_changes_plan_and_removal_restores_it():
    text = 'Save $25 instantly on stays of $100 or more.'
    key = promotion_key(text, 'Provider A', 'USD')
    promo, trace = parse_promotion_terms(text, key, platform='Provider A', use_ai=False)
    with pytest.raises(ValueError):
        accept_promotion(promo, reviewed=False)
    accepted = accept_promotion(promo, reviewed=True)
    assert accepted.verification_status == 'estimated'
    request = trip_request()
    offers = [offer(base='100',taxes='0',fees='0')]
    _, before = evaluate_snapshot(request, offers, [])
    results, after = evaluate_snapshot(request, offers, [accepted])
    assert after.total_net_cost == Decimal('75')
    assert before.total_net_cost - after.total_net_cost == Decimal('25')
    assert results[0].applied_promotions[0].promotion_id == key
    assert after.choices[0].selected.guaranteed_net_cost == Decimal('100')
    assert evaluate_snapshot(request, offers, [])[1].total_net_cost == before.total_net_cost
    assert promotion_key(text, 'Provider A', 'EUR') != key


def test_negative_model_amount_uses_validated_fallback():
    promo, trace = parse_promotion_terms('Save $25 instantly.', 'p', client=Model({'fixed_amount': -25}))
    assert trace.method == 'heuristic'
    assert promo.fixed_amount == Decimal('25')


def test_model_cannot_omit_explicit_cashback_cap_and_still_be_applied():
    promo, trace = parse_promotion_terms('Earn 8% cashback. Maximum cashback is $30.', 'p',
        client=Model({'rate': .08}), strategy='ai')
    assert promo.requires_verification
    with pytest.raises(ValueError):
        accept_promotion(promo, reviewed=True)
