"""TripStack: one simple planning flow, with inspectable AI underneath."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tripstack.ai.gemma_client import GemmaClient
from tripstack.config import get_settings
from tripstack.data_loader import load_demo_trip, load_raw_promotions
from tripstack.design import feature, hero, install_design
from tripstack.engine.comparison import rank_results
from tripstack.engine.location import downtown_reference
from tripstack.models.hotel import TripRequest, TripSegment
from tripstack.models.money import fmt_money
from tripstack.providers import get_provider, search_sync
from tripstack.providers.base import ProviderError
from tripstack.promotion_workspace import render_workspace
from tripstack.ui_format import bill_rows, md, promo_line
from tripstack.workflow import evaluate_snapshot

st.set_page_config(page_title="TripStack — A better stay, less effort", page_icon="↗", layout="wide",initial_sidebar_state="collapsed")
settings=get_settings()
state=st.session_state
for key,value in {"plan":None,"results":[],"request":load_demo_trip(),"provider_label":"", "search_warnings":[],
                  "page":"Your trip","data_mode":"demo","use_ai":settings.use_ai_parser,
                  "parser_strategy":"hybrid","selected_model":settings.ollama_model,"cpu_inference":False}.items():
    state.setdefault(key,value)

# Keep form values when moving between the three product views. Streamlit
# otherwise removes state owned by widgets not rendered on the current view.
for widget_key in list(state):
    if widget_key.startswith(('city_', 'location_', 'radius_', 'reference_', 'n_', 'custom_')) or widget_key in {
        'trip_currency','travelers','objective','refundable_only','trip_start','trip_budget','reviewed_terms'}:
        state[widget_key]=state[widget_key]


def active_client():
    return GemmaClient(model=state.selected_model or settings.ollama_model,cpu=state.cpu_inference)


@st.cache_data(ttl=10,show_spinner=False)
def cached_diagnostics(host,model):
    return GemmaClient(host=host,model=model).diagnostics()


def run_search(
    request: TripRequest, mode: str, use_ai: bool, strategy: str = "hybrid"
) -> None:
    st.session_state.request = request
    promos, disclaimer = load_raw_promotions()
    provider = get_provider(mode)
    st.session_state.provider_label = provider.describe()
    st.session_state.disclaimer = disclaimer

    st.session_state.parse_traces = []
    offers = []
    warnings: list[str] = []
    for seg in request.segments:
        try:
            offers.extend(
                search_sync(
                    provider,
                    seg.city,
                    seg.check_in,
                    seg.check_out,
                    adults=request.travelers,
                )
            )
        except ProviderError as exc:
            warnings.append(f"{seg.city}: provider failed ({exc})")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{seg.city}: unexpected error ({exc})")

    if not offers:
        st.session_state.plan = None
        st.session_state.results = []
        st.session_state.offers = []
        st.session_state.search_warnings = warnings or ["No offers were returned"]
        return

    if use_ai:
        from tripstack.ai.promotion_parser import enrich_promotions

        promos, traces = enrich_promotions(promos, use_ai=True, strategy=strategy, client=active_client())
        st.session_state.parse_traces = traces

    st.session_state.offers = offers
    st.session_state.base_promotions = promos
    custom = [p for k, p in st.session_state.get("custom_promotions", {}).items()
              if st.session_state.get("custom_currencies", {}).get(k) == request.currency]
    results, plan = evaluate_snapshot(request, offers, promos + custom)

    st.session_state.request = request
    st.session_state.results = results
    st.session_state.plan = plan
    st.session_state.search_warnings = warnings


def request_editor():
    """Three visible decisions; optional complexity stays in contextual disclosures."""
    errors=[]
    n=state.get('city_count',1)
    defaults=['Boston','New York','Chicago']
    start=None
    cursor=None
    segments=[]
    for i in range(int(n)):
        a,b,c=st.columns([2.2,1.5,1])
        city=a.text_input('Destination' if n==1 else f'Destination {i+1}',value=defaults[i] if i<3 else '',key=f'city_{i}')
        if i==0:
            start=b.date_input('Check-in',value=date(2026,11,10),key='trip_start')
            cursor=start
        else:
            b.caption('Check-in')
            b.write(cursor.strftime('%b %d, %Y'))
        nights=c.number_input('Nights' if n==1 else f'Nights · city {i+1}',min_value=1,max_value=30,value=5,key=f'n_{i}')
        end=cursor+timedelta(days=int(nights))
        a,b=st.columns([2.2,2.5])
        location=a.selectbox('Stay near' if n==1 else f'Stay near · city {i+1}',['any','downtown','custom'],
            format_func=lambda x:{'any':'Anywhere in the city','downtown':'Downtown','custom':'A specific place'}[x],key=f'location_{i}')
        options={'location_preference':location}
        if i==0:
            budget=b.number_input(f"Hotel budget ({state.get('trip_currency','USD')})",min_value=0.,value=1000.,step=100.,key='trip_budget',help='Zero means no budget limit.')
        else:
            b.caption(f'{cursor:%b %d} — {end:%b %d} · {int(nights)} nights')
        if location!='any':
            with st.expander(f'Location details{f" · {city}" if n>1 else ""}',expanded=True):
                options['max_distance_km']=st.number_input('Maximum distance (km)',min_value=.1,max_value=200.,value=3.,step=.5,key=f'radius_{i}')
                center=downtown_reference(city)
                if location=='downtown':
                    if center:
                        st.caption(f'From {center[0]}. Straight-line distance, not travel time.')
                    else:
                        errors.append(f'{city}: choose a specific place; no downtown reference is available.')
                else:
                    st.caption('Use coordinates from your chosen destination. Place names are labels, not an address search.')
                    options['reference_name']=st.text_input('Place name',value='My destination',key=f'reference_name_{i}')
                    a,b=st.columns(2)
                    options['reference_latitude']=a.number_input('Latitude',min_value=-90.,max_value=90.,value=None,format='%.6f',key=f'reference_lat_{i}')
                    options['reference_longitude']=b.number_input('Longitude',min_value=-180.,max_value=180.,value=None,format='%.6f',key=f'reference_lon_{i}')
                    if options['reference_latitude'] is None or options['reference_longitude'] is None:
                        errors.append(f'{city}: enter both coordinates.')
                        cursor=end
                        continue
        if not city.strip():
            errors.append('Enter a destination for each city.')
        else:
            segments.append(TripSegment(city=city.strip(),check_in=cursor,check_out=end,**options))
        cursor=end
    with st.expander('More trip options', expanded=False):
        a,b,c=st.columns(3)
        n=a.number_input('Number of cities',min_value=1,max_value=5,value=1,key='city_count')
        currency=b.selectbox('Currency',['USD','EUR','GBP','CNY'],key='trip_currency')
        travelers=c.number_input('Travelers',min_value=1,max_value=8,value=2,key='travelers')
        a,b=st.columns(2)
        objective=a.selectbox('Prioritize',['lowest_net','lowest_upfront','lowest_certain'],
            format_func=lambda x:{'lowest_net':'Lowest estimated total','lowest_upfront':'Pay less upfront',
                                  'lowest_certain':'Verified benefits only'}[x],key='objective')
        refundable=b.checkbox('Refundable rates only',key='refundable_only')
    request=TripRequest(currency=currency,budget=budget,travelers=int(travelers),segments=segments,
                        refundable_only=refundable,objective=objective) if segments else None
    if state.plan and request and request != state.request:
        st.caption('Preferences changed. Update your plan to apply them.')
    if st.button('Find my stay' if not state.plan else 'Update my plan',type='primary',width='stretch'):
        if errors or request is None:
            for error in errors or ['Add a destination.']:
                st.error(error)
        else:
            mode=state.data_mode if state.data_mode!='live' or settings.live_ready else 'demo'
            with st.spinner('Finding stays and checking the fine print…'):
                run_search(request,mode,state.use_ai,state.parser_strategy)
            st.rerun()
    for warning in state.search_warnings:
        st.warning(md(warning))


def details(result,cur):
    st.table(pd.DataFrame(bill_rows(result,cur),columns=['Item','Amount']).set_index('Item'))
    if result.applied_promotions:
        for promo in result.applied_promotions:
            st.write(md(promo_line(promo,cur)))
    st.caption('Benefits marked estimated must be confirmed before booking.')
    if result.offer.is_simulated:
        st.caption('Demo hotel, price and coordinates. No live booking is offered.')
    else:
        st.caption(f'Source: {result.offer.source_url}')
    if result.warnings:
        for warning in result.warnings:
            st.caption(md(warning))


def report_data(plan):
    return {
        'currency':plan.currency,'total_upfront':str(plan.total_upfront),'estimated_cashback':str(plan.total_cashback),
        'estimated_net_cost':str(plan.total_net_cost),'estimated_savings':str(plan.estimated_savings),
        'baseline_cheapest_advertised':str(plan.naive_baseline_total),'baseline_average_offer':str(plan.average_baseline_total),
        'complete':all(c.selected for c in plan.choices),'distance_method':'haversine_straight_line_km',
        'location_preferences':[json.loads(s.model_dump_json()) for s in state.request.segments],
        'segments':[{'city':c.city,'location_reference':c.location_reference,'max_distance_km':c.max_distance_km,
                     'offer':json.loads(c.selected.offer.model_dump_json()) if c.selected else None,
                     'distance_km':c.selected.distance_km if c.selected else None,
                     'upfront':str(c.selected.upfront_payment) if c.selected else None,
                     'estimated_net_cost':str(c.selected.estimated_net_cost) if c.selected else None,
                     'warnings':c.warnings} for c in plan.choices],
        'custom_offers':[json.loads(p.model_dump_json()) for k,p in state.get('custom_promotions',{}).items()
                         if state.get('custom_currencies',{}).get(k)==plan.currency],
        'extraction_traces':[{'promotion_id':k,'method':t.method,'model':t.model,'elapsed_ms':t.elapsed_ms,
                             'metrics':t.metrics,'evidence':t.evidence,'fallback_reason':t.fallback_reason,'warnings':t.warnings}
                            for k,t in state.get('custom_traces',{}).items()
                            if state.get('custom_currencies',{}).get(k)==plan.currency]}


def recommendations():
    plan=state.plan
    if not plan:
        return
    if not any(c.selected for c in plan.choices):
        st.warning('No matching hotels. A zero total is not a priced itinerary. Try a wider area or different dates.')
        for choice in plan.choices:
            for message in choice.warnings:
                st.caption(message)
        return
    cur=plan.currency
    complete=all(c.selected for c in plan.choices)
    if not complete:
        st.warning('This trip is incomplete. Totals cover matched cities only.')
    with st.container(border=True,key='trip_summary'):
        st.markdown(f'<div class="summary"><div class="label">{"Estimated trip total" if complete else "Estimated subtotal · incomplete trip"}</div>'
            f'<div class="amount">{escape(fmt_money(plan.total_net_cost,cur))}</div>'
            f'<div class="support">Pay upfront <b>{escape(fmt_money(plan.total_upfront,cur))}</b>'
            f' &nbsp;·&nbsp; Estimated cashback <b>{escape(fmt_money(plan.total_cashback,cur))}</b></div>'
            f'<div class="saving">{escape(fmt_money(plan.estimated_savings,cur))} estimated savings with offers</div></div>',unsafe_allow_html=True)
        st.caption('Cashback arrives later, if eligible. The total above includes estimated benefits.')
        if plan.over_budget:
            st.warning(md(f'Upfront payment is {fmt_money(plan.total_upfront-plan.budget,cur)} over your budget.'))
    st.markdown('### Your stays')
    for index,choice in enumerate(plan.choices):
        if not choice.selected:
            st.warning(f'{choice.city}: no stay meets your preferences.')
            continue
        result=choice.selected
        with st.container(border=True,key=f'stay_card_{index}'):
            a,b=st.columns([3,1.2])
            a.markdown(f'<div class="stay"><div class="city">{escape(choice.city)} · {choice.nights} nights · '
                f'{choice.check_in:%b %d}–{choice.check_out:%b %d}</div><h3>{escape(result.offer.hotel_name)}</h3>'
                f'<div class="meta">{escape(result.offer.area)} · {escape(result.offer.room_type)} · via {escape(result.offer.platform)}</div></div>',unsafe_allow_html=True)
            b.markdown(f'<div class="stay-price"><strong>{escape(fmt_money(result.estimated_net_cost,cur))}</strong><p>estimated total · {choice.nights} nights</p></div>',unsafe_allow_html=True)
            tags=[]
            if result.distance_km is not None:
                tags.append(f'{result.distance_km:.2f} km straight-line to {result.location_reference}')
            tags.append('Refundable rate' if result.offer.refundable else 'Refundability restricted or unconfirmed')
            if result.offer.is_simulated:
                tags.append('Demo stay')
            st.markdown(''.join(f'<span class="pill neutral">{escape(t)}</span>' for t in tags),unsafe_allow_html=True)
            if choice.max_distance_km is not None:
                st.caption(f'Within your {choice.max_distance_km:g} km limit. Distances are straight-line; demo coordinates are illustrative.'
                           if result.offer.is_simulated else f'Within your {choice.max_distance_km:g} km straight-line limit.')
            with st.expander('Why this stay & price details'):
                pool=[result]+choice.alternatives
                cheapest=min(pool,key=lambda x:(x.upfront_payment,x.estimated_net_cost))
                if result.upfront_payment>cheapest.upfront_payment:
                    extra=result.upfront_payment-cheapest.upfront_payment
                    difference=cheapest.estimated_net_cost-result.estimated_net_cost
                    st.write(md(f'Compared with the lowest-upfront option: {fmt_money(extra,cur)} more upfront; '
                                f'estimated total {fmt_money(abs(difference),cur)} {"lower" if difference>=0 else "higher"}.'))
                else:
                    st.write('This stay also has the lowest upfront price among the options that meet your preferences.')
                details(result,cur)
                if choice.alternatives:
                    st.caption('Other stays that meet the same location and refund preferences')
                    st.dataframe(pd.DataFrame([r.to_row() for r in choice.alternatives])[
                        ['Hotel','Area','Upfront','Net Cost','Distance (km)']],hide_index=True,width='stretch')
                for warning in choice.warnings:
                    if warning not in result.warnings:
                        st.caption(md(warning))
    with st.expander('All options & calculation notes'):
        st.caption('Savings compare against the lowest pre-promotion prices satisfying the same location and refund constraints. '
                   'Missing segments are not priced. Estimated benefits are not guaranteed payouts.')
        st.dataframe(pd.DataFrame([r.to_row() for r in state.results]),hide_index=True,width='stretch')
        for warning in plan.warnings:
            st.caption(md(warning))
        st.download_button('Download full report',json.dumps(report_data(plan),indent=2),
                           file_name='tripstack_report.json',mime='application/json')


def settings_panel():
    with st.expander('Settings & model diagnostics'):
        a,b=st.columns(2)
        a.radio('Data source',['demo','live'],key='data_mode',horizontal=True)
        b.toggle('Use Gemma AI parser',key='use_ai')
        if state.data_mode=='live' and not settings.live_ready:
            st.warning('Live credentials are missing. Searches will use demo data.')
        a,b=st.columns(2)
        a.text_input('Local model',key='selected_model')
        b.selectbox('Parser strategy',['hybrid','ai','rules'],key='parser_strategy')
        st.checkbox('CPU inference',key='cpu_inference')
        client=active_client()
        if st.button('Check model inference'):
            with st.spinner('Running a real model check…'):
                try:
                    client.generate_json('Return JSON with promotion_type cashback and no numeric benefit.')
                    state.model_check=(client.model,client.cpu,True,client.last_metrics)
                except Exception as exc:
                    state.model_check=(client.model,client.cpu,False,str(exc))
        diag=cached_diagnostics(client.host,client.model)
        st.caption(f'Model endpoint: {client.host}')
        if not diag['reachable']:
            st.caption('Ollama is offline. Rule parsing is available.')
        elif not diag['installed']:
            st.caption(f'Model not installed: {client.model}')
        else:
            st.caption(f'{client.model} is installed. This does not certify inference success.')
        check=state.get('model_check')
        if check and check[:2]==(client.model,client.cpu):
            if check[2]:
                st.success('Model inference passed')
            else:
                st.error('Inference failed. Rule parsing remains available.')
                st.text(check[3])


install_design()
if state.get("navigate_to"):
    state.page=state.pop("navigate_to")
left,right=st.columns([1.4,2])
left.markdown('<div class="brand"><span class="brand-mark">↗</span>TripStack</div>',unsafe_allow_html=True)
with right:
    st.radio('Navigation',['Your trip','Add an offer','Inside TripStack'],horizontal=True,label_visibility='collapsed',key='page')
mode=state.data_mode if state.data_mode!='live' or settings.live_ready else 'demo'
st.markdown(f'<div class="quiet-note">{"Demo preview · simulated hotel prices. No booking or payment." if mode=="demo" else "Live provider quotes · confirm rates and terms before booking."}</div>',unsafe_allow_html=True)

if state.get('flash'):
    st.success(state.pop('flash'))
if state.page=='Your trip':
    if state.plan:
        destinations = state.request.segments
        hero('YOUR TRIP, SIMPLIFIED.', 'Your stay. Sorted.' if len(destinations)==1 else 'Your stays. Sorted.',
             f'{destinations[0].city if len(destinations)==1 else str(len(destinations))+" destinations"} · {state.request.total_nights} nights. A clear price. A considered choice.', compact=True)
    else:
        hero('A LITTLE PLANNING. A LOT LESS WORK.', 'A better stay.\nLess to think about.',
             'Tell us where you’re going. We’ll compare the stays, read the offers, and make the trade-offs clear.')
    if state.plan:
        with st.expander('Edit your trip',expanded=False):
            request_editor()
        recommendations()
    else:
        with st.container(border=True,key='trip_form'):
            request_editor()
    if not state.plan:
        a,b,c=st.columns(3)
        with a: feature('Fine print, simplified.','Gemma reads offer terms so you don’t have to.')
        with b: feature('Numbers you can inspect.','Exact arithmetic calculates the bill. Unclear benefits stay out.')
        with c: feature('The right part of town.','Compare stays near downtown or your chosen place.')
elif state.page=='Add an offer':
    hero('YOUR OFFERS. UNDERSTOOD.', 'Let the fine print\ndo less hiding.',
         'Paste a promotion. See what it means, what it could save, and whether it fits your trip.')
    render_workspace(active_client())
else:
    hero('OPEN INTELLIGENCE. CLEAR REASONING.', 'Smart where it helps.\nExact where it matters.',
         'Gemma reads the language. Code checks the numbers. You can inspect the evidence behind each decision.')
    a,b,c=st.columns(3)
    with a: feature('Read locally with Gemma.','An open-weight model extracts conditions from promotional text. Model failures are labelled, not hidden.','01 / UNDERSTAND')
    with b: feature('Check against the source.','Numbers are grounded in the original terms. Conflicts and ambiguous rates are held for review.','02 / VERIFY')
    with c: feature('Compare with exact math.','Decimal arithmetic applies discounts, caps and eligibility, within your location constraints.','03 / DECIDE')
    traces=list(state.get('custom_traces',{}).values())+state.get('parse_traces',[])
    st.subheader('From your latest analyses')
    if not traces:
        st.caption('Analyze an offer to see its actual model, runtime and source evidence here.')
    for trace in traces:
        analysis_label={'gemma':'Gemma extraction','hybrid':'Gemma + source checks',
                        'heuristic':'Rules only','failed':'Unclear benefit excluded'}.get(trace.method,trace.method)
        if trace.fallback_reason:
            analysis_label='Model unavailable · rules used'
        with st.expander(f'{trace.model or "Rule parser"} · {analysis_label} · {trace.elapsed_ms/1000:.2f}s'):
            if trace.fallback_reason:
                st.warning('The model failed; this result used the rule parser.')
                st.text(trace.fallback_reason)
            st.json({'method':trace.method,'model':trace.model,'metrics':trace.metrics,
                     'source_evidence':trace.evidence,'warnings':trace.warnings,'raw_output':trace.raw_output})
    st.caption('Model requests go to the configured endpoint. Demo prices and hotel coordinates are simulated. '
               'Cashback is estimated; no booking or payment is made by this app.')

settings_panel()
st.markdown('<div class="footer">TripStack · Estimated benefits are subject to eligibility.</div>',unsafe_allow_html=True)
