"""TripStack Streamlit dashboard.

Pages: Trip Search -> Offer Comparison -> Trip Savings Report -> Promotion Lab.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tripstack.ai.gemma_client import GemmaClient  # noqa: E402
from tripstack.ai.promotion_parser import (  # noqa: E402
    heuristic_extract,
    parse_promotion_terms,
)
from tripstack.config import get_settings  # noqa: E402
from tripstack.data_loader import load_demo_trip, load_raw_promotions  # noqa: E402
from tripstack.engine.comparison import build_comparison_result  # noqa: E402
from tripstack.engine.optimizer import optimize_trip  # noqa: E402
from tripstack.models.hotel import TripRequest, TripSegment  # noqa: E402
from tripstack.models.money import fmt_money  # noqa: E402
from tripstack.models.result import ComparisonResult, TripPlan  # noqa: E402
from tripstack.providers import get_provider, search_sync  # noqa: E402
from tripstack.providers.base import ProviderError  # noqa: E402

st.set_page_config(page_title="TripStack — Travel Savings Agent", layout="wide")

DEFAULT_CITIES = ["Chicago", "New York", "Boston"]


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------
def init_state() -> None:
    if "plan" not in st.session_state:
        st.session_state.plan = None
    if "results" not in st.session_state:
        st.session_state.results = []
    if "request" not in st.session_state:
        st.session_state.request = load_demo_trip()
    if "provider_label" not in st.session_state:
        st.session_state.provider_label = ""
    if "search_warnings" not in st.session_state:
        st.session_state.search_warnings = []


init_state()
settings = get_settings()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def run_search(
    request: TripRequest, mode: str, use_ai: bool, strategy: str = "hybrid"
) -> None:
    promos, disclaimer = load_raw_promotions()
    provider = get_provider(mode)
    st.session_state.provider_label = provider.describe()
    st.session_state.disclaimer = disclaimer

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
        st.session_state.search_warnings = warnings or ["No offers were returned"]
        return

    if use_ai:
        from tripstack.ai.promotion_parser import enrich_promotions

        promos, traces = enrich_promotions(promos, use_ai=True, strategy=strategy)
        st.session_state.parse_traces = traces

    results = [
        build_comparison_result(o, promos) for o in offers
    ]
    plan = optimize_trip(request, offers, promos)

    st.session_state.request = request
    st.session_state.results = results
    st.session_state.plan = plan
    st.session_state.search_warnings = warnings


def results_frame(results: list[ComparisonResult]) -> pd.DataFrame:
    return pd.DataFrame([r.to_row() for r in results])


def apply_filters(results: list[ComparisonResult]) -> list[ComparisonResult]:
    filtered = results
    if st.session_state.get("f_refundable"):
        filtered = [r for r in filtered if r.offer.refundable]
    if st.session_state.get("f_exclude_uncertain"):
        filtered = [r for r in filtered if r.promotion_status != "unknown"]
    sort_by = st.session_state.get("f_sort", "Estimated net cost")
    if sort_by == "Upfront payment":
        filtered = sorted(filtered, key=lambda r: r.upfront_payment)
    elif sort_by == "Guaranteed net cost":
        filtered = sorted(filtered, key=lambda r: r.guaranteed_net_cost)
    else:
        filtered = sorted(filtered, key=lambda r: r.estimated_net_cost)
    return filtered


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------
with st.sidebar:
    st.title("TripStack")
    st.caption("Open-source AI travel savings agent — MVP v0.1")

    mode = st.radio(
        "Data mode",
        options=["demo", "live"],
        index=0,
        help="Live mode requires Amadeus credentials and returns real quotes.",
    )
    if mode == "live" and not settings.live_ready:
        st.warning(
            "Live credentials not found (AMADEUS_CLIENT_ID / "
            "AMADEUS_CLIENT_SECRET). Falling back to Demo Mode."
        )
        mode = "demo"

    use_ai = st.toggle("Use Gemma AI parser", value=settings.use_ai_parser)
    strategy = "rules"
    if use_ai:
        strategy = st.radio(
            "Parser strategy",
            options=["hybrid", "ai", "rules"],
            index=0,
            help=(
                "hybrid = numbers from the grounded rule parser, semantics from "
                "Gemma (recommended, best measured accuracy); "
                "ai = model output only; rules = no model."
            ),
        )
        gemma = GemmaClient()
        if gemma.is_available():
            st.success(f"Ollama reachable — model `{gemma.model}`")
        else:
            st.warning(
                f"Ollama not reachable at {gemma.host}. "
                "Rule-based fallback will be used."
            )

    st.divider()
    st.markdown(
        "**Transparency**\n"
        "- Demo prices are simulated and labelled.\n"
        "- Cashback is an estimate, never a guarantee.\n"
        "- Every offer keeps its source and timestamp."
    )


# --------------------------------------------------------------------------
# Tabs
# --------------------------------------------------------------------------
tab_search, tab_compare, tab_report, tab_lab = st.tabs(
    ["1 · Trip Search", "2 · Offer Comparison", "3 · Savings Report", "4 · Promotion Lab"]
)

# ---- Page 1: Trip search -------------------------------------------------
with tab_search:
    st.header("Plan a trip")
    st.caption(
        "Enter destinations, dates and budget. TripStack retrieves offers, "
        "matches promotions, and ranks them by effective cost."
    )

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        currency = st.selectbox("Currency", ["USD", "EUR", "GBP", "CNY"], index=0)
    with col_b:
        travelers = st.number_input("Travelers", min_value=1, max_value=8, value=2)
    with col_c:
        budget = st.number_input("Hotel budget", min_value=0.0, value=2500.0, step=50.0)

    n_segments = st.number_input("Number of cities", min_value=1, max_value=5, value=3)
    start = st.date_input("Trip start date", value=date(2026, 11, 10))

    segments: list[TripSegment] = []
    seg_cols = st.columns(min(int(n_segments), 5))
    cursor = start
    for i in range(int(n_segments)):
        with seg_cols[i % len(seg_cols)]:
            city = st.text_input(
                f"City {i + 1}",
                value=DEFAULT_CITIES[i] if i < len(DEFAULT_CITIES) else "",
                key=f"city_{i}",
            )
            nights = st.number_input(
                f"Nights in city {i + 1}", min_value=1, max_value=30, value=5, key=f"n_{i}"
            )
            check_in = cursor
            check_out = cursor + timedelta(days=int(nights))
            st.caption(f"{check_in.isoformat()} → {check_out.isoformat()}")
            cursor = check_out
            if city.strip():
                segments.append(
                    TripSegment(city=city.strip(), check_in=check_in, check_out=check_out)
                )

    with st.expander("Preferences"):
        objective = st.selectbox(
            "Optimize for",
            options=["lowest_net", "lowest_upfront", "lowest_certain"],
            format_func=lambda v: {
                "lowest_net": "Lowest estimated net cost",
                "lowest_upfront": "Lowest upfront payment",
                "lowest_certain": "Lowest cost excluding uncertain cashback",
            }[v],
        )
        refundable_only = st.checkbox("Refundable rates only", value=False)

    c1, c2 = st.columns([1, 1])
    with c1:
        search_clicked = st.button("Search hotels", type="primary", use_container_width=True)
    with c2:
        demo_clicked = st.button("Load demo trip", use_container_width=True)

    if demo_clicked:
        st.session_state.request = load_demo_trip()
        st.session_state.plan = None
        st.session_state.results = []
        st.success("Demo trip loaded (Chicago → New York → Boston, 15 nights).")

    if search_clicked:
        if not segments:
            st.error("Add at least one city.")
        else:
            request = TripRequest(
                currency=currency,
                budget=budget,
                travelers=int(travelers),
                segments=segments,
                refundable_only=refundable_only,
                objective=objective,
            )
            with st.spinner("Searching offers and evaluating promotions..."):
                run_search(request, mode, use_ai, strategy)
            if st.session_state.plan:
                st.success(
                    f"Analyzed {st.session_state.plan.offers_analyzed} offers via "
                    f"{st.session_state.provider_label}."
                )
            for w in st.session_state.search_warnings:
                st.warning(w)

    if st.session_state.request:
        req: TripRequest = st.session_state.request
        st.info(
            f"Current trip: {len(req.segments)} cities · {req.total_nights} nights · "
            f"budget {fmt_money(req.budget, req.currency)} · {req.travelers} traveler(s)"
        )

# ---- Page 2: Comparison --------------------------------------------------
with tab_compare:
    st.header("Offer comparison")
    if not st.session_state.results:
        st.info("Run a search first (Page 1), or load the demo trip.")
    else:
        f1, f2, f3 = st.columns(3)
        with f1:
            st.session_state.f_sort = st.selectbox(
                "Sort by",
                ["Estimated net cost", "Upfront payment", "Guaranteed net cost"],
            )
        with f2:
            st.session_state.f_refundable = st.checkbox("Refundable only")
        with f3:
            st.session_state.f_exclude_uncertain = st.checkbox(
                "Exclude uncertain promotions"
            )

        req = st.session_state.request
        cur = req.currency
        filtered = apply_filters(st.session_state.results)
        df = results_frame(filtered)
        st.dataframe(
            df.style.format({"Upfront": "{:,.2f}", "Cashback": "{:,.2f}", "Net Cost": "{:,.2f}"}),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Offer detail")
        for r in filtered[:8]:
            label = (
                f"{r.offer.hotel_name} · {r.offer.platform} · "
                f"{fmt_money(r.upfront_payment, cur)} upfront · "
                f"{fmt_money(r.estimated_net_cost, cur)} net"
            )
            with st.expander(label):
                st.write(r.explanation)
                left, right = st.columns(2)
                with left:
                    st.markdown("**Cost breakdown**")
                    st.json(
                        {
                            "base_price": float(r.breakdown.base_price),
                            "taxes": float(r.breakdown.taxes),
                            "mandatory_fees": float(r.breakdown.mandatory_fees),
                            "list_price": float(r.breakdown.list_price),
                            "instant_discount": float(r.breakdown.instant_discount),
                            "upfront_payment": float(r.upfront_payment),
                            "cashback_eligible_spend": float(
                                r.breakdown.cashback_eligible_spend
                            ),
                            "estimated_cashback": float(r.estimated_cashback),
                            "estimated_net_cost": float(r.estimated_net_cost),
                            "guaranteed_net_cost": float(r.guaranteed_net_cost),
                        }
                    )
                with right:
                    st.markdown("**Applied promotions**")
                    if r.applied_promotions:
                        for p in r.applied_promotions:
                            st.markdown(f"- `{p.promotion_id}` ({p.type})")
                            st.caption(
                                f"status={p.verification_status} · cap="
                                f"{p.cap if p.cap is not None else '—'} · "
                                f"stackable={p.stackable}"
                            )
                    else:
                        st.caption("No promotion matched.")
                    st.markdown("**Source**")
                    st.caption(
                        f"{r.offer.source_url} · retrieved "
                        f"{r.offer.retrieved_at} · mode={r.offer.data_mode}"
                    )
                if r.warnings:
                    st.markdown("**Warnings**")
                    for w in r.warnings:
                        st.warning(w)

# ---- Page 3: Report ------------------------------------------------------
with tab_report:
    st.header("Trip savings report")
    plan: TripPlan | None = st.session_state.plan
    if not plan:
        st.info("Run a search to generate a savings report.")
    else:
        cur = plan.currency
        m1, m2, m3 = st.columns(3)
        m1.metric("Upfront total", fmt_money(plan.total_upfront, cur))
        m2.metric("Estimated cashback", fmt_money(plan.total_cashback, cur))
        m3.metric("Estimated net cost", fmt_money(plan.total_net_cost, cur))
        m4, m5, m6 = st.columns(3)
        m4.metric(
            "Savings vs. cheapest advertised",
            fmt_money(plan.estimated_savings, cur),
            f"{plan.savings_pct:.1f}%",
        )
        m5.metric(
            "Savings vs. average offer",
            fmt_money(plan.savings_vs_average, cur),
            f"{plan.savings_vs_average_pct:.1f}%",
        )
        m6.metric(
            "Budget remaining (upfront)",
            fmt_money(plan.remaining_budget, cur),
            f"net basis {fmt_money(plan.remaining_budget_net, cur)}",
        )
        st.caption(
            f"Budget {fmt_money(plan.budget, cur)} · paid upfront "
            f"{fmt_money(plan.total_upfront, cur)} → "
            f"**{fmt_money(plan.remaining_budget, cur)} left to spend today** · "
            f"after estimated cashback "
            f"{fmt_money(plan.remaining_budget_net, cur)} "
            "(cashback is an estimate and arrives later, if at all)"
        )

        if plan.over_budget:
            st.error("Selected itinerary exceeds the stated budget.")

        st.subheader("Recommended booking per segment")
        for choice in plan.choices:
            st.markdown(
                f"### {choice.city} · {choice.check_in} → {choice.check_out} "
                f"({choice.nights} nights)"
            )
            if choice.selected is None:
                st.warning("No comparable offers for this segment.")
                continue
            sel = choice.selected
            st.write(sel.explanation)
            cols = st.columns(4)
            cols[0].markdown(f"**Hotel:** {sel.offer.hotel_name}")
            cols[1].markdown(f"**Channel:** {sel.offer.platform}")
            cols[2].markdown(
                f"**Upfront:** {fmt_money(sel.upfront_payment, cur)} → "
                f"**Net:** {fmt_money(sel.estimated_net_cost, cur)}"
            )
            cols[3].markdown(f"**Confidence:** {sel.confidence}")
            if sel.applied_promotions:
                st.caption(
                    "Promotion: "
                    + ", ".join(
                        f"`{p.promotion_id}` ({p.source_url or 'no source'})"
                        for p in sel.applied_promotions
                    )
                )
            for w in choice.warnings:
                st.warning(w)
            if choice.alternatives:
                with st.expander(f"Alternatives ({len(choice.alternatives)})"):
                    st.dataframe(
                        results_frame(choice.alternatives),
                        use_container_width=True,
                        hide_index=True,
                    )

        st.subheader("Disclosures")
        st.caption(
            f"Conservative baseline: cheapest advertised price per segment before "
            f"any promotion ({fmt_money(plan.naive_baseline_total, cur)}). "
            f"Reference baseline: average of all comparable offers "
            f"({fmt_money(plan.average_baseline_total, cur)}). "
            "Savings compare each baseline against the optimized net cost."
        )
        st.caption(f"Provider: {st.session_state.provider_label}")
        if st.session_state.get("parse_traces"):
            methods = [t.method for t in st.session_state.parse_traces]
            models = {t.model for t in st.session_state.parse_traces if t.model}
            st.caption(
                "Promotion parsing: "
                + ", ".join(f"`{m}`" for m in dict.fromkeys(methods))
                + (f" via {', '.join(sorted(models))}" if models else "")
            )
        st.caption(
            "Data freshness: every offer carries its own retrieval timestamp; "
            "prices change frequently and must be re-checked before booking."
        )
        for w in plan.warnings:
            st.warning(w)
        if st.session_state.get("disclaimer"):
            st.caption(st.session_state.disclaimer)

        report = {
            "currency": plan.currency,
            "total_upfront": float(plan.total_upfront),
            "estimated_cashback": float(plan.total_cashback),
            "estimated_net_cost": float(plan.total_net_cost),
            "baseline_cheapest_advertised": float(plan.naive_baseline_total),
            "baseline_average_offer": float(plan.average_baseline_total),
            "estimated_savings": float(plan.estimated_savings),
            "estimated_savings_vs_average": float(plan.savings_vs_average),
            "remaining_budget_upfront": float(plan.remaining_budget),
            "remaining_budget_after_cashback": float(plan.remaining_budget_net),
            "segments": [
                {
                    "city": c.city,
                    "check_in": c.check_in.isoformat(),
                    "check_out": c.check_out.isoformat(),
                    "hotel": c.selected.offer.hotel_name if c.selected else None,
                    "platform": c.selected.offer.platform if c.selected else None,
                    "upfront": float(c.selected.upfront_payment) if c.selected else None,
                    "net_cost": float(c.selected.estimated_net_cost) if c.selected else None,
                }
                for c in plan.choices
            ],
        }
        st.download_button(
            "Download savings report (JSON)",
            data=json.dumps(report, indent=2),
            file_name="tripstack_report.json",
            mime="application/json",
        )

# ---- Page 4: Promotion lab ----------------------------------------------
with tab_lab:
    st.header("Promotion Lab — Gemma term extraction")
    st.caption(
        "Paste promotional terms. Gemma (via Ollama) extracts structured "
        "conditions; output is validated and never invented."
    )
    sample = (
        "Earn 8% cashback on eligible hotel bookings. Maximum cashback is $30. "
        "Not valid with third-party coupon codes. Taxes and fees are excluded."
    )
    terms = st.text_area("Promotion terms", value=sample, height=120)
    col1, col2, col3 = st.columns(3)
    with col1:
        run_ai = st.button("Extract with Gemma", type="primary", use_container_width=True)
    with col2:
        run_hybrid = st.button("Extract (hybrid)", use_container_width=True)
    with col3:
        run_rules = st.button("Rule-based only", use_container_width=True)

    def _show(promo, trace, title: str) -> None:
        st.markdown(f"**{title}** — method `{trace.method}`"
                    + (f", model `{trace.model}`" if trace.model else ""))
        if trace.raw_output:
            st.markdown("Raw output")
            st.json(trace.raw_output)
        st.markdown("Validated promotion")
        st.json(json.loads(promo.model_dump_json()))
        for w in trace.warnings:
            st.warning(w)

    if run_ai:
        promo, trace = parse_promotion_terms(
            terms, promotion_id="lab-001", platform="Provider A",
            source_url="https://example.com", use_ai=True, strategy="ai",
        )
        _show(promo, trace, "Gemma")

    if run_hybrid:
        promo, trace = parse_promotion_terms(
            terms, promotion_id="lab-hybrid", platform="Provider A",
            source_url="https://example.com", use_ai=True, strategy="hybrid",
        )
        _show(promo, trace, "Hybrid (rules for numbers, Gemma for meaning)")

    if run_rules:
        st.markdown("**Rule-based extraction (no model)**")
        st.json(heuristic_extract(terms))

    st.divider()
    st.subheader("Curated rule set")
    promos, disclaimer = load_raw_promotions()
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": p.promotion_id,
                    "Platform": p.platform,
                    "Type": p.type,
                    "Rate": float(p.rate) if p.rate is not None else None,
                    "Fixed": float(p.fixed_amount) if p.fixed_amount is not None else None,
                    "Cap": float(p.cap) if p.cap is not None else None,
                    "Min spend": float(p.minimum_spend) if p.minimum_spend is not None else None,
                    "Stackable": p.stackable,
                    "Status": p.verification_status,
                }
                for p in promos
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(disclaimer)
