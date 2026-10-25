# TripStack technical notes

## Data flow

```text
Trip request -> hotel provider -> quote snapshot
Promotion text -> extraction -> source validation -> reviewed promotion
Quote snapshot + promotions -> eligibility -> location filter -> pricing -> ranking
Ranked segments -> trip totals -> recommendation and report
```

The hotel provider supplies prices. Promotion extraction supplies conditions;
model output does not supply hotel prices or perform monetary arithmetic.

## Components

| Component | Implementation |
|---|---|
| Interface | Streamlit; shared styles in `design.py` |
| Model inference | Gemma through Ollama, using structured JSON output |
| Input validation | Pydantic |
| Pricing | Python `Decimal` |
| Hotel data | Local demo records or the Amadeus adapter |
| Requests | httpx |
| Tests | pytest and Streamlit AppTest |

`app.py` provides three views: Your trip, Add an offer and Inside TripStack.
`workflow.evaluate_snapshot` derives the comparison table and trip plan from the
same eligible quotes. Applying or removing a promotion recalculates that
snapshot rather than refreshing provider prices.

## Promotion extraction

The prompt treats promotion text as data, limits its length and requests
structured fields. The client records request duration, model loading time and
token counts when the server supplies them. Connection, model-loading and output
errors are surfaced as extraction failures with an explicit fallback reason.

- `hybrid` takes numeric fields from rule matches and other conditions from the
  model. Explicit source exclusions override conflicting model booleans.
- `ai` uses model output subject to validation and source checks.
- `rules` does not invoke the model.

Numbers and dates absent from the source are discarded. Conflicting amount
roles, multiple rates and truncated input require review and do not enter
reported savings. A user review confirms the extraction was inspected; it does
not change an estimated benefit into a verified payout.

Eligibility states are `verified`, `estimated`, `unknown` and `ineligible`.
Unknown and ineligible benefits do not reduce reported costs.

Historical experiments are recorded in [parser-benchmark.md](docs/parser-benchmark.md).
They use a small fixed dataset and do not establish general model accuracy.

## Pricing and ranking

```text
Upfront payment    = base + taxes + mandatory fees - instant discounts
Estimated cashback = eligible spend × rate, limited by the promotion cap
Estimated net cost = upfront payment - estimated cashback
```

Amounts are quantized to cents; fractional rates retain six decimal places.
Percentage instant discounts apply to the base room rate. Tax amounts are not
recomputed. Cashback excludes taxes and fees unless explicitly allowed.

Promotion selection prices candidate combinations with the same engine used
for reporting. Selection and offer ranking share objective and tie-breaking
rules. Objectives are lowest estimated net cost, lowest upfront payment and
lowest cost using verified benefits only.

Savings baselines use pre-promotion prices among quotes satisfying the same
currency, location and refund constraints. Totals for incomplete itineraries
cover matched segments only; an itinerary with no matching stays is not shown
as a free trip.

## Location constraints

Each segment supports an unrestricted location, a built-in downtown reference
or a custom reference with coordinates. Haversine distance determines radius
eligibility before prices are ranked. Missing coordinates fail an active radius
constraint; they do not become zero distance. No matching hotel produces no
recommendation rather than an unconstrained replacement.

Reference points are approximate anchors, not neighborhood boundaries.
Distances do not estimate travel time or transportation cost. See
[location-preferences.md](docs/location-preferences.md).

## State and reporting

Form values survive navigation between views. Custom promotions, extraction
records and the hotel snapshot are stored in the current browser session.
A page reload or server restart can clear this state.

The downloadable report includes totals, eligible selections, geographic
preferences, source information and custom-promotion extraction records.
Money values are exported as decimal strings.

## Operational limits

Demo prices and coordinates are simulated. The Amadeus test host is a sandbox;
production access, coverage and refund behavior need verification with the
configured account. No live multi-platform promotion search, automatic booking,
payment processing or account scraping is implemented.

Configuration comes from environment variables. `.env.example` documents the
settings and is not loaded automatically. Credentials must not be committed.

## Verification

```bash
python -m pytest -q
```

The suite covers money and rates, eligibility and stacking, source validation,
model error handling, location filtering, snapshot recalculation and page
interactions. Model responses in automated tests are mocked. Live inference
checks are separate from the deterministic test suite.
