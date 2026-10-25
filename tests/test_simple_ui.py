"""Product-flow regressions: keep progressive disclosure and navigation usable."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from tripstack.ai.gemma_client import GemmaClient


def app(monkeypatch):
    monkeypatch.setattr(GemmaClient,'diagnostics',lambda self:{'reachable':False,'installed':False})
    return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=20).run()


def test_start_page_is_single_city_with_no_sidebar_or_parallel_tabs(monkeypatch):
    page=app(monkeypatch)
    assert not page.exception
    assert page.number_input(key='city_count').value == 1
    assert page.text_input(key='city_0').value == 'Boston'
    assert len(page.tabs)==0
    assert not page.sidebar.title
    assert not any(b.label=='Analyze offer' for b in page.button)
    page.toggle[0].set_value(False).run()
    next(b for b in page.button if b.label=='Find my stay').click().run()
    assert not page.exception
    assert any('Your stays' in heading.value for heading in page.markdown)
    assert page.session_state['plan'] is not None
    assert next(b for b in page.button if b.label=='Update my plan')


def test_navigation_preserves_city_location_and_budget(monkeypatch):
    page=app(monkeypatch)
    page.text_input(key='city_0').set_value('Chicago').run()
    page.number_input(key='trip_budget').set_value(1800.).run()
    page.selectbox(key='location_0').set_value('downtown').run()
    page.number_input(key='radius_0').set_value(1.5).run()
    page.radio(key='page').set_value('Add an offer').run()
    assert not page.exception
    page.radio(key='page').set_value('Inside TripStack').run()
    assert not page.exception
    page.radio(key='page').set_value('Your trip').run()
    assert not page.exception
    assert page.text_input(key='city_0').value == 'Chicago'
    assert page.number_input(key='trip_budget').value == 1800.
    assert page.selectbox(key='location_0').value == 'downtown'
    assert page.number_input(key='radius_0').value == 1.5


def test_offer_preview_does_not_display_zero_when_location_matches_nothing(monkeypatch):
    from tripstack.models.hotel import TripRequest,TripSegment
    from tripstack.workflow import evaluate_snapshot
    from .helpers import offer
    from datetime import date
    request=TripRequest(segments=[TripSegment(city='Boston',check_in=date(2026,11,10),
        check_out=date(2026,11,15),location_preference='downtown',max_distance_km=1)])
    offers=[offer(city='Boston')]
    _,plan=evaluate_snapshot(request,offers,[])
    page=app(monkeypatch)
    page.session_state['request']=request
    page.session_state['offers']=offers
    page.session_state['plan']=plan
    page.session_state['base_promotions']=[]
    page.radio(key='page').set_value('Add an offer').run()
    page.selectbox(key='custom_method').set_value('rules').run()
    next(b for b in page.button if b.label=='Analyze offer').click().run()
    assert not page.exception
    assert not page.metric
    assert any('No stays match' in message.value for message in page.info)
