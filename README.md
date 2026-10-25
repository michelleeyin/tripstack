# TripStack — AI Travel Savings Agent

> One trip. Multiple destinations. Dozens of offers. One explainable savings report.

TripStack is an open-source agent that automates the repetitive work of
comparing hotel offers: it retrieves offers, interprets cashback and coupon
terms with an open-weight model, computes the **effective** cost with a
deterministic pricing engine, and recommends the cheapest option — with every
number traceable to a source.

**MVP status:** v0.1 — Demo Mode is fully reproducible without any paid API
credentials. Live hotel search requires Amadeus credentials.

---

## Why this exists

The lowest advertised price is not the lowest final cost. A traveller comparing
a 15-day, multi-city trip has to weigh:

- prices across booking platforms
- taxes and mandatory fees
- cashback rates and caps
- minimum-spend and coupon-stacking rules
- refundability
- total cost across all destinations

TripStack automates that comparison and shows its work.

---

## Quick start (Demo Mode, ~2 minutes)

```bash
git clone <your-fork-url> tripstack && cd tripstack
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # optional; defaults already run Demo Mode
streamlit run app.py
```

Then click **Load demo trip** → **Search hotels**.

Demo Mode uses `data/demo_hotels.json` and `data/promotion_rules.json`. It is
deterministic (same seed → same prices), so it is safe for demos and tests.
All demo offers carry `data_mode = "demo"` and are labelled as simulated.

### Run the tests

```bash
python -m pytest -q
```

43 tests cover money arithmetic, cashback caps, tax exclusion, expiry,
platform matching, minimum spend, coupon stacking, unknown-eligibility
handling, currency safety, ranking, budget checks, multi-city aggregation and
AI parser behaviour — including malformed model output, hallucinated numbers,
invented expiry dates and the hybrid merge rules.

---

## Live Mode (optional)

Live Mode queries the Amadeus Self-Service hotel APIs. **Verify access,
coverage and permitted usage before enabling it.**

```bash
export TRIPSTACK_DATA_MODE=live
export AMADEUS_CLIENT_ID=...
export AMADEUS_CLIENT_SECRET=...
streamlit run app.py
```

If credentials are missing, TripStack silently falls back to Demo Mode rather
than pretending to have live prices.

---

## Gemma / Ollama setup (optional but recommended)

The promotion parser uses Google Gemma served locally by Ollama — no API key,
no data leaves the machine.

```bash
brew install ollama          # or see https://ollama.com
ollama pull gemma:7b         # recommended; gemma:2b is ~4x faster, far less accurate
ollama serve                 # or: brew services start ollama
```

The sidebar reports whether Ollama is reachable, and the **Promotion Lab** page
proves it: it shows the raw model output plus the validated promotion, so you
can see the model was really called (`method: gemma`) instead of the fallback.

### Three parser strategies

| Strategy | Numbers | Semantics | Use when |
|---|---|---|---|
| `hybrid` (default) | rule parser | Gemma | recommended |
| `ai` | Gemma | Gemma | you want pure model extraction |
| `rules` | rule parser | rule parser | no model installed |

### Measured accuracy — [docs/parser-benchmark.md](docs/parser-benchmark.md)

10 hand-labelled promotions × 9 fields, measured 2026-10-24:

| Parser | gemma:2b | gemma:7b |
|---|---|---|
| Gemma only | 75.6% | 93.3% |
| Hybrid | 91.1% | 96.7% |
| Rule-based (no model) | 97.8% | 97.8% |

The honest read is in the benchmark doc: on tidy promotion text the rule parser
is still slightly ahead; the model wins the fields regexes handle worst (coupon
-stacking language); and every model number is grounded in the source text, so a
hallucination can never reach the pricing engine — the worst case is a promotion
flagged `unknown` and excluded from savings.

```bash
OLLAMA_MODEL=gemma:7b python benchmark_parser.py     # re-run it yourself
```

---

## How it works

```text
User Input
   |
   v
Trip Search Controller
   |
   +--------------------+--------------------+
   |                                         |
   v                                         v
Hotel Provider (Demo / Amadeus)      Promotion rules (JSON)
   |                                         |
   v                                         v
Normalized HotelOffer                Gemma promotion parser
   |                                         |
   +--------------------+--------------------+
                        |
                        v
              Eligibility Validator
                        |
                        v
                 Pricing Engine (Decimal)
                        |
                        v
                 Trip Optimizer
                        |
                        v
              Savings Report (Streamlit)
```

### Pricing rules

```text
Upfront Payment     = Base + Taxes + Mandatory Fees - Eligible Instant Discounts
Estimated Cashback  = min(Eligible Spend x Rate, Cap)
Estimated Net Cost  = Upfront Payment - Estimated Cashback
```

- All money is `Decimal`, quantized to cents — no floats.
- Cashback never applies to taxes or fees unless the rule allows it.
- Caps are enforced; a payment is never negative.
- A promotion with **unknown** eligibility is never counted as a saving.
- Non-stackable promotions are never summed.
- Offers in a different currency are excluded, never silently converted.

### Baselines

Savings are reported against two clearly defined baselines:

| Baseline | Definition |
|---|---|
| Cheapest advertised | Cheapest upfront price per segment — what a "sort by price" shopper pays |
| Average comparable | Mean upfront price of all comparable offers — reference only |

---

## Repository layout

```text
tripstack/
├── app.py                  # Streamlit dashboard (4 pages)
├── config.py               # env-driven settings
├── data_loader.py          # demo trip + promotion rule loaders
├── providers/              # base, demo (fixtures), amadeus (live)
├── ai/                     # prompts, Ollama/Gemma client, promotion parser
├── engine/                 # eligibility, pricing, comparison, optimizer
├── models/                 # money, hotel, promotion, result schemas
├── data/                   # demo_trip.json, demo_hotels.json, promotion_rules.json
├── tests/                  # pytest suite
├── .env.example
├── requirements.txt
├── TECHNICAL_PLAN.md
└── LICENSE
```

---

## Transparency & limits

TripStack is intentionally conservative:

- **Demo prices are simulated** and always labelled. They are not live quotes.
- **Cashback is an estimate** based on published terms, never a guaranteed payout.
- Promotion rules come from a **curated local JSON file**, not a real-time
  all-platform cashback search.
- No scraping of login-protected accounts. No payment processing. No automatic
  booking.
- Retrieved promotion text is treated as **untrusted data**; model output is
  validated by Pydantic before it can affect any calculation.
- Every offer keeps its source URL and retrieval timestamp.

---

## Roadmap

- **v0.2** — more providers, better cashback sources, price-freshness tracking
- **v0.3** — flights, ground transport, attraction tickets
- **v0.4** — loyalty programmes and personalized eligibility
- **v1.0** — cross-category budget optimization and price alerts

## Contributing

Hacktoberfest-friendly: good first issues are extra providers, more promotion
fixtures, additional pricing tests, and UI polish. Please open an issue before
large changes.

## License

MIT — see [LICENSE](LICENSE).
