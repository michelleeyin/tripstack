from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

from tripstack.ai.gemma_client import GemmaClient
from tripstack.engine.location import distance_km, filter_location, provider_coordinates
from tripstack.engine.optimizer import optimize_trip
from tripstack.models.hotel import HotelOffer, TripSegment
from tripstack.providers import DemoProvider, search_sync
from tripstack.providers.amadeus import _normalize_offer
from tripstack.workflow import evaluate_snapshot
from .helpers import TODAY, offer, trip_request


def segment(**options):
    return TripSegment(city='Boston', check_in=date(2026,11,10), check_out=date(2026,11,15), **options)


def located(id, lat, lon, base='100'):
    data = offer(offer_id=id, city='Boston', base=base, taxes='0', fees='0').model_dump()
    return HotelOffer(**dict(data, latitude=lat, longitude=lon))


def test_haversine_known_geometry_and_dateline():
    assert distance_km(0,0,0,0) == 0
    assert distance_km(0,0,0,1) == pytest.approx(111.195, abs=.001)
    assert distance_km(0,179.9,0,-179.9) == pytest.approx(22.239, abs=.001)


def test_active_filter_rejects_cheaper_far_and_unknown_hotels_and_limits_baseline():
    near = located('near',42.3603,-71.0581,base='200')
    far = located('far',42.4,-71.2,base='10')
    unknown = offer(offer_id='unknown',city='Boston',base='1')
    req = trip_request().model_copy(update={'segments':[segment(location_preference='downtown',max_distance_km=1)]})
    table, plan = evaluate_snapshot(req,[near,far,unknown],[])
    assert [r.offer_id for r in table] == ['near']
    assert plan.choices[0].selected.offer_id == 'near'
    assert plan.naive_baseline_total == Decimal('200')
    assert plan.total_net_cost == Decimal('200')
    assert plan.choices[0].selected.distance_km == 0
    assert any('missing coordinates' in w for w in plan.choices[0].warnings)


def test_any_location_keeps_offers_without_coordinates():
    offers = [offer(city='Boston')]
    assert filter_location(offers,segment())[0] == offers


def test_radius_boundary_is_inclusive_without_rounding():
    center = located('a',0,0)
    boundary = located('b',0,1)
    radius=distance_km(0,0,0,1)
    seg=segment(location_preference='custom', reference_latitude=0, reference_longitude=0,max_distance_km=radius)
    assert len(filter_location([center,boundary],seg)[0]) == 2
    seg=seg.model_copy(update={'max_distance_km':radius-.000001})
    assert [o.offer_id for o in filter_location([center,boundary],seg)[0]] == ['a']


def test_unknown_downtown_and_no_matching_offers_do_not_silently_relax_constraints():
    seg=segment(location_preference='downtown').model_copy(update={'city':'Unknown city'})
    assert filter_location([offer()],seg)[0] == []
    req=trip_request().model_copy(update={'segments':[segment(location_preference='downtown',max_distance_km=.1)]})
    plan=optimize_trip(req,[located('far',42.4,-71.2)],[])
    assert plan.choices[0].selected is None
    assert plan.total_net_cost == 0
    assert any('totals cover' in w for w in plan.warnings)


@pytest.mark.parametrize('options', [dict(location_preference='custom'),dict(reference_latitude=0),
    dict(location_preference='custom',reference_latitude=91,reference_longitude=0),
    dict(max_distance_km=0),dict(max_distance_km=float('nan'))])
def test_invalid_location_preferences_fail_validation(options):
    with pytest.raises(ValidationError):
        segment(**options)


def test_invalid_provider_coordinates_are_unknown():
    assert provider_coordinates('42.36','-71.05') == (42.36,-71.05)
    for coords in [(None,0),(91,0),(float('nan'),0),('bad',0)]:
        assert provider_coordinates(*coords) == (None,None)


def test_live_normalization_preserves_coordinates_without_inventing_an_area():
    result=_normalize_offer('h','hotel','Boston',{'price':{'total':'100'}},
        date(2026,11,10),date(2026,11,15),datetime.now(),latitude=42.36,longitude=-71.05)
    assert result.latitude == 42.36
    assert result.area == 'Unknown'
    assert result.location_source == 'provider'


def test_boston_downtown_and_custom_kendall_choose_different_hotels():
    offers=search_sync(DemoProvider(),'Boston',date(2026,11,10),date(2026,11,15))
    request=trip_request().model_copy(update={'segments':[segment(location_preference='downtown',max_distance_km=1)]})
    plan=optimize_trip(request,offers,[],TODAY)
    assert plan.choices[0].selected.offer.hotel_id == 'hotel-bos-004'
    request=request.model_copy(update={'segments':[segment(location_preference='custom',reference_name='Kendall Square',
        reference_latitude=42.3628,reference_longitude=-71.09,max_distance_km=.5)]})
    table,plan=evaluate_snapshot(request,offers,[])
    assert plan.choices[0].selected.offer.hotel_id == 'hotel-bos-002'
    assert all(r.offer.hotel_id == 'hotel-bos-002' for r in table)


def test_dashboard_passes_location_preference_to_table_and_plan(monkeypatch):
    monkeypatch.setattr(GemmaClient,'diagnostics',lambda self:{'reachable':False,'installed':False})
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=20).run()
    app.toggle[0].set_value(False).run()
    app.number_input(key='city_count').set_value(3).run()
    app.text_input(key='city_0').set_value('Chicago').run()
    app.text_input(key='city_2').set_value('Boston').run()
    app.selectbox(key='location_2').set_value('downtown').run()
    app.number_input(key='radius_2').set_value(1.0).run()
    next(b for b in app.button if b.label=='Find my stay').click().run()
    assert not app.exception
    choice=app.session_state['plan'].choices[2]
    assert choice.selected.offer.hotel_id == 'hotel-bos-004'
    assert choice.max_distance_km == 1
    boston=[r for r in app.session_state['results'] if r.offer.city=='Boston']
    assert all(r.distance_km <= 1 for r in boston)


def test_no_matching_hotels_are_not_shown_as_a_free_itinerary(monkeypatch):
    monkeypatch.setattr(GemmaClient,'diagnostics',lambda self:{'reachable':False,'installed':False})
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=20).run()
    app.toggle[0].set_value(False).run()
    next(n for n in app.number_input if n.label=='Number of cities').set_value(1).run()
    app.text_input(key='city_0').set_value('Boston').run()
    app.selectbox(key='location_0').set_value('downtown').run()
    app.number_input(key='radius_0').set_value(.1).run()
    next(b for b in app.button if b.label=='Find my stay').click().run()
    assert not app.exception
    assert app.session_state['plan'].choices[0].selected is None
    assert not app.metric
    assert any('zero total is not' in warning.value for warning in app.warning)


def test_live_directory_coordinates_flow_into_offer_normalization():
    import asyncio
    from tripstack.providers.amadeus import AmadeusProvider
    provider=AmadeusProvider()
    async def get(url,params):
        if 'by-city' in url:
            return {'data':[{'hotelId':'h','geoCode':{'latitude':42.36,'longitude':-71.05}}]}
        return {'data':[{'hotel':{'hotelId':'h','name':'Test'},'offers':[{'id':'o','price':{'total':'100'}}]}]}
    provider._get=get
    async def query():
        ids=await provider._hotel_ids_for_city('BOS',20)
        return await provider._fetch_offers(ids,'Boston',date(2026,11,10),date(2026,11,15),2,20)
    offers=asyncio.run(query())
    assert offers[0].latitude == 42.36
    assert offers[0].longitude == -71.05
    assert offers[0].location_source == 'provider'
