# TripStack — Technical Design & MVP Implementation Plan

**Version:** 0.1 MVP · **Target:** Hacktoberfest 2026 · **License:** MIT

---

## 1. Overview

**Problem.** Comparing hotel prices for a 15-day, multi-city trip means manual
evaluation of platform prices, taxes, fees, cashback rates and caps, coupon
eligibility, stacking rules and cancellation policies. The lowest advertised
price is not the lowest final cost.

**Solution.** TripStack is an open-source AI agent that automates hotel offer
discovery, interprets discount conditions with an open-weight model, compares
effective costs with a deterministic engine, and emits an explainable report.

**Value proposition.** One trip. Multiple destinations. Dozens of offers. One
optimized savings report. The product answers *how to book more cheaply*, not
*what to see*.

---

## 2. MVP Scope

### P0 (required)

1. User enters destinations, dates, budget.
2. Offers retrieved automatically from one supported provider.
3. Cashback / promotion rules loaded and matched.
4. Open-weight model extracts structured discount conditions.
5. Deterministic pricing engine computes effective cost.
6. Offers ranked; best options recommended.
7. Dashboard shows savings, sources and eligibility warnings.
8. Demo Mode reproduces the workflow with no paid credentials.

### P1 (optional)

Multiple providers · multiple cities · cashback cap and stacking analysis ·
exportable report · price-freshness indicators.

### Out of scope

Flights · checkout/payment · credit-card linking · scraping login-protected
cashback accounts · "we search every travel site" claims · un-sourced real-time
cashback rates · automatic reservations.

### Success criteria

A search can be submitted without manually entering offers; at least one
provider returns offers in Live Mode; the model parses multiple promotion
descriptions; pricing is correct and tested; recommendations separate upfront
from net cost; Demo Mode reproduces the flow; repo has setup docs, tests,
license and a working demo.

---

## 3. Architecture

```text
User Input -> Trip Search Controller
                 -> Hotel Provider (normalized offers)
                 -> Promotion rules -> Gemma parser
                 -> Eligibility Validator -> Pricing Engine
                 -> Trip Optimizer -> Savings Report -> Streamlit
```

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Backend | Python 3.11+ |
| AI model | Google Gemma via Ollama |
| Validation | Pydantic v2 |
| Hotel search | Amadeus (live) / local fixtures (demo) |
| Promotion DB | JSON |
| Data | Pandas (display), Decimal (money) |
| HTTP | httpx |
| Tests | pytest |

---

## 4. Modules

| Module | Responsibility |
|---|---|
| `models/` | `HotelOffer`, `TripRequest`, `Promotion`, `PricingBreakdown`, `ComparisonResult`, `TripPlan`, money helpers |
| `providers/` | `HotelProvider` ABC, `DemoProvider` (fixtures), `AmadeusProvider` (OAuth + hotel-offers) |
| `ai/` | Ollama/Gemma client, prompt templates, promotion parser with rule-based fallback |
| `engine/eligibility` | Expiry, platform, category, minimum spend, cap, stacking, ambiguity |
| `engine/pricing` | Upfront payment, cashback with caps, net cost, guaranteed cost |
| `engine/comparison` | Match promotions, price, rank by objective |
| `engine/optimizer` | Per-segment selection, aggregation, baseline comparison |
| `app.py` | 4 pages: Search · Comparison · Report · Promotion Lab |

### Eligibility states

`verified` · `estimated` · `unknown` · `ineligible`. Only `verified`/`estimated`
benefits reduce the reported net cost; `unknown` is always excluded and flagged.

### Parser safety

Promotion text is untrusted data. The prompt forbids following instructions
found inside it, caps input length, requires JSON only, and tells the model to
return `null` rather than guess. Output is validated by Pydantic; on any
failure the parser falls back to deterministic heuristics and marks the rule
`requires_verification`.

Two additional guardrails were added after measuring real model behaviour
(`docs/parser-benchmark.md`):

1. **Grounding check** — every number and date the model returns must literally
   appear in the source text. gemma:2b produced `rate: 0.08` for a text with no
   numbers, and `valid_until: 2023-04-01` for texts with no date. Both are now
   discarded and flagged.
2. **Hybrid merge** — numeric fields come from the rule parser only (grounded by
   construction); semantic fields (`type`, `stackable`, `taxes_eligible`,
   `requires_verification`) come from the model, which reads phrasing the
   regexes cannot.

Prompt is zero-shot: with worked examples, small models copied the example's
figures into unrelated promotions.

---

## 5. Data models

See `models/`. Canonical shapes:

```jsonc
// HotelOffer
{"offer_id":"demo-001","hotel_id":"hotel-001","hotel_name":"Example Hotel",
 "city":"Chicago","check_in":"2026-11-10","check_out":"2026-11-15",
 "room_type":"Standard King","platform":"Provider A","currency":"USD",
 "base_price":850,"taxes":100,"mandatory_fees":25,"refundable":true,
 "source_url":"https://example.com","data_mode":"demo",
 "retrieved_at":"2026-10-24T18:00:00-05:00"}

// Promotion
{"promotion_id":"promo-001","platform":"Provider A","type":"cashback",
 "rate":0.08,"cap":30,"minimum_spend":100,"taxes_eligible":false,
 "stackable":false,"valid_until":"2026-12-31",
 "source_url":"https://example.com/promo","verification_status":"estimated"}

// ComparisonResult
{"offer_id":"demo-001","upfront_payment":975,"estimated_cashback":30,
 "estimated_net_cost":945,"currency":"USD","promotion_status":"estimated",
 "warnings":["Cashback is not guaranteed"]}
```

---

## 6. Roadmap

| Phase | Work | Status |
|---|---|---|
| 1 | Repo scaffold, Streamlit shell, schemas, demo data | Done |
| 2 | Pricing engine, eligibility, unit tests | Done |
| 3 | Gemma/Ollama parser, validation, fallback, UI display | Done — Ollama 0.40.11 + gemma:7b running locally, real model calls verified, benchmark recorded |
| 4 | Amadeus adapter, live/demo separation, failure handling | Adapter done; needs credentials to verify |
| 5 | Ranking, trip report, disclosures, demo video, article | Report done; video + article pending |

---

## 7. Testing

39 pytest cases across money arithmetic, cashback caps, tax exclusion,
expired/mismatched/below-minimum promotions, coupon stacking, unknown
eligibility, currency safety, ranking, refundability, multi-city aggregation,
budget warnings, parser extraction and malformed model output.

---

## 8. Security & transparency

Keys live in env vars only · no credential commits · no login-walled scraping ·
provider terms and rate limits respected · untrusted text never controls app
behaviour · every model output validated · source URLs and timestamps shown ·
simulated data labelled · cashback never presented as guaranteed · no payment
data · graceful fallback when a provider is unavailable.

---

## 9. Definition of Done

- [x] Trip search input
- [x] Automatic offer retrieval (Demo Mode; Live Mode adapter ready)
- [x] Gemma promotion extraction wired with validated output
- [x] Pricing calculations covered by tests
- [x] Upfront vs. estimated net cost distinction
- [x] Traceable savings (source URL + timestamp per offer)
- [x] Trip-level savings report
- [x] Tests, requirements, license, setup docs
- [ ] Public GitHub repository
- [ ] Demo video (~90 s)
- [ ] DEV submission article

**Principle:** automate repetitive deal comparison while keeping every
recommendation transparent, verifiable and realistic.
