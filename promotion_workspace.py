"""Reviewable extraction and impact preview, separate from the dashboard shell."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from .ai.promotion_parser import parse_promotion_terms
from .models.money import fmt_money
from .ui_format import md, promo_line
from .workflow import accept_promotion, evaluate_snapshot, promotion_key


def reprice_session():
    state = st.session_state
    if state.get('offers'):
        promotions = state.get('base_promotions', []) + [p for k, p in state.get('custom_promotions', {}).items()
            if state.get('custom_currencies', {}).get(k) == state.request.currency]
        state.results, state.plan = evaluate_snapshot(state.request, state.offers, promotions)


def render_workspace(client):
    state = st.session_state
    state.setdefault('custom_promotions', {})
    sample = ('Earn 7.5% cashback on hotel bookings. Maximum cashback is $60. '
              'Minimum spend $200. Taxes and fees are excluded. '
              'Cannot be combined with coupon codes. Valid through 2026-12-31.')
    with st.container(border=True,key='offer_input'):
        a, b = st.columns([3, 1])
        platform = a.text_input('Booking platform', value='Provider A', key='custom_platform')
        currency = b.selectbox('Offer currency', ['USD', 'EUR', 'GBP', 'CNY'], key='custom_currency')
        with st.expander('Source & analysis options'):
            source = st.text_input('Source URL (optional)', key='custom_source')
            method = st.selectbox('Analysis method', ['hybrid', 'ai', 'rules'], key='custom_method',
                                 format_func=lambda value: {'hybrid':'Gemma + source checks (recommended)',
                                 'ai':'Gemma extraction','rules':'Rule parser only'}[value])
        terms = st.text_area('Original promotion terms', value=sample, height=160, key='custom_terms')
        st.caption('One offer at a time. You’ll review the conditions before anything changes.')
        if st.button('Analyze offer', type='primary', disabled=not terms.strip() or not platform.strip()):
            key = promotion_key(terms, platform, currency)
            with st.spinner('Reading terms and checking the source…'):
                promo, trace = parse_promotion_terms(terms, key, platform=platform.strip(),
                    source_url=source.strip(), strategy=method, use_ai=method != 'rules', client=client)
            state.extraction = (promo, trace, currency, (terms, platform, source, method, client.model, client.cpu))
            state.pop('reviewed_terms', None)

    extraction = state.get('extraction')
    if extraction:
        promo, trace, extracted_currency, fingerprint = extraction
        current = (terms, platform, source, method, client.model, client.cpu)
        if current != fingerprint or extracted_currency != currency:
            st.info('Inputs changed. Extract again before applying this offer.')
        else:
            left, right = st.columns([3, 2])
            with left:
                st.subheader('What this offer means')
                st.write(md(promo_line(promo, currency)))
                st.caption('Gemma + grounded numbers' if trace.method == 'hybrid' else
                           'Gemma extraction' if trace.method == 'gemma' else 'Rule parser — no model result used')
                st.caption(f'Analyzed in {trace.elapsed_ms / 1000:.2f}s. Open the evidence to inspect the result.')
                if trace.fallback_reason:
                    st.warning('Gemma failed. This result came from the rule parser.')
                condition_rows = []
                labels = {"rate": "Benefit rate", "fixed_amount": "Fixed benefit", "cap": "Maximum benefit",
                          "minimum_spend": "Minimum booking", "stackable": "Combine with other offers",
                          "taxes_eligible": "Cashback includes taxes", "valid_until": "Valid through"}
                for key, label in labels.items():
                    value = getattr(promo, key)
                    if value is None:
                        display = "Not stated"
                    elif key == "rate":
                        display = f"{(value * 100).normalize():f}%"
                    elif key in {"fixed_amount", "cap", "minimum_spend"}:
                        display = fmt_money(value, currency)
                    elif key in {"stackable", "taxes_eligible"}:
                        display = "Yes" if value else "No / not confirmed"
                    else:
                        display = str(value)
                    excerpt = trace.evidence.get(key, "Not identified — inspect the original terms")
                    condition_rows.append({"Condition": label, "Value": md(display), "Source excerpt": md(excerpt)})
                readable = [{"Condition": row["Condition"], "Value": row["Value"]}
                            for row in condition_rows if row["Value"] != "Not stated"]
                st.table(pd.DataFrame(readable).set_index("Condition"))
                with st.expander('See the source evidence'):
                    st.table(pd.DataFrame(condition_rows).set_index("Condition"))
                    st.text(promo.raw_text)
                    for warning in trace.warnings:
                        st.warning(md(warning))
                    st.json({'method': trace.method, 'metrics': trace.metrics,
                             'fallback_reason': trace.fallback_reason, 'raw_output': trace.raw_output})
            with right:
                st.subheader('Your trip, with this offer')
                blocked = promo.requires_verification or promo.verification_status == 'unknown'
                incompatible = state.request.currency != currency
                if blocked:
                    st.warning('Unresolved conditions: this offer cannot reduce reported savings.')
                elif incompatible:
                    st.warning('Offer currency must match the trip currency. No exchange rate is assumed.')
                elif not state.get('offers'):
                    st.info('Search hotels first. You can save the reviewed offer for the next search.')
                elif state.get('plan') and not any(choice.selected for choice in state.plan.choices):
                    st.info('No stays match your preferences yet. Adjust your trip before previewing savings.')
                else:
                    base = state.get('base_promotions', [])
                    existing = [p for k, p in state.custom_promotions.items() if k != promo.promotion_id
                                and state.get('custom_currencies', {}).get(k) == currency]
                    _, before = evaluate_snapshot(state.request, state.offers, base + existing)
                    _, after = evaluate_snapshot(state.request, state.offers, base + existing + [promo])
                    st.metric('Estimated trip net cost', fmt_money(after.total_net_cost, currency))
                    st.write(md(f'Before: {fmt_money(before.total_net_cost, currency)} → '
                                f'after: {fmt_money(after.total_net_cost, currency)}'))
                    st.caption('Same hotel snapshot and objective; no price refresh.')
                    used = any(promo.promotion_id in {p.promotion_id for p in c.selected.applied_promotions}
                               for c in after.choices if c.selected)
                    if not used:
                        st.info('This offer is ineligible or does not improve the selected objective.')
                reviewed = st.checkbox('I reviewed the source terms.', key='reviewed_terms')
                if st.button('Apply to my trip', disabled=blocked or incompatible or not reviewed, type='primary'):
                    state.custom_promotions[promo.promotion_id] = accept_promotion(promo, reviewed=reviewed)
                    state.setdefault('custom_traces', {})[promo.promotion_id] = trace
                    state.setdefault('custom_currencies', {})[promo.promotion_id] = currency
                    reprice_session()
                    state.flash = 'Offer applied. Your trip has been updated.' if state.get('offers') else 'Offer saved. Find a stay to see its impact.'
                    state.navigate_to = 'Your trip'
                    st.rerun()

    if state.custom_promotions:
        st.subheader('Your reviewed offers')
        for key, promo in list(state.custom_promotions.items()):
            a, b = st.columns([5, 1])
            a.write(md(f'{promo.platform} · {promo_line(promo, state.get("custom_currencies", {}).get(key, currency))}'))
            if b.button('Remove', key=f'remove_{key}'):
                del state.custom_promotions[key]
                state.get('custom_traces', {}).pop(key, None)
                state.get('custom_currencies', {}).pop(key, None)
                reprice_session()
                st.rerun()
