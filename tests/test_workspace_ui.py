"""Exercise the actual Streamlit extraction -> review -> repricing interactions."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from tripstack.ai.gemma_client import GemmaClient
from .helpers import offer, trip_request


def test_review_apply_remove_and_stale_input_guard(monkeypatch):
    monkeypatch.setattr(GemmaClient, 'diagnostics', lambda self: {
        'reachable': True, 'installed': True, 'models': [self.model]})
    monkeypatch.setattr(GemmaClient, 'generate_json', lambda self, prompt: {
        'promotion_type': 'cashback', 'rate': .075, 'cap': 60,
        'minimum_spend': 200, 'taxes_eligible': False, 'stackable': False,
        'valid_until':'2026-12-31'})
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20)
    app.session_state['request'] = trip_request()
    app.session_state['offers'] = [offer(base='1000', taxes='0', fees='0')]
    app.session_state['base_promotions'] = []
    app.run()
    assert not app.exception
    app.radio(key='page').set_value('Add an offer').run()
    next(b for b in app.button if b.label == 'Analyze offer').click().run()
    assert not app.exception
    assert next(b for b in app.button if b.label == 'Apply to my trip').disabled
    app.checkbox(key='reviewed_terms').check().run()
    next(b for b in app.button if b.label == 'Apply to my trip').click().run()
    assert not app.exception
    assert len(app.session_state['custom_promotions']) == 1
    assert app.session_state['plan'].total_net_cost == 940
    assert app.session_state['plan'].choices[0].selected.applied_promotions
    app.radio(key='page').set_value('Add an offer').run()
    next(b for b in app.button if b.label == 'Remove').click().run()
    assert not app.exception
    assert app.session_state['plan'].total_net_cost == 1000
    app.text_area(key='custom_terms').set_value('Save $5 instantly.').run()
    assert not any(b.label == 'Apply to my trip' for b in app.button)
