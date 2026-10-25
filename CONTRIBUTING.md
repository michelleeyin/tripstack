# Contributing to TripStack

Thanks for helping build an honest travel-savings agent. This project values
**verifiable numbers over impressive-sounding ones** — that principle should
survive every pull request.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m pytest -q          # 44 tests, must pass
streamlit run app.py         # Demo Mode works with no credentials
```

Optional (for the AI parser):

```bash
brew install ollama
ollama pull gemma:7b
ollama serve
```

## Pull request rules

1. **Tests must pass.** New pricing or eligibility logic needs a test that
   fails before your change and passes after it.
2. **Money is `Decimal`, never `float`.** Use `models/money.to_money`.
3. **Never invent a number.** Any value that reaches the pricing engine must be
   traceable to a source: a provider response, a curated rule, or text that
   literally contains the figure.
4. **Label simulated data.** New demo fixtures must set `data_mode`.
5. **No credentials in commits.** Keys come from environment variables only.
6. **Keep the disclosures.** If a change makes a claim stronger, it must also
   make the underlying evidence visible in the UI.

## Good first issues

- **Add a hotel provider.** Implement `providers/base.HotelProvider` for another
  authorized API and normalize to `HotelOffer`.
- **Add promotion fixtures.** Realistic terms in `data/promotion_rules.json`
  (with `source_url` and `raw_text`).
- **Grow the benchmark.** Add labelled cases to `data/promotion_bench.json` —
  especially messy, multi-clause, real-world copy where regexes struggle.
- **Improve the rule parser.** New patterns in `ai/promotion_parser.py`, with a
  test proving the improvement on the existing benchmark.
- **Price freshness.** Show "retrieved N minutes ago" in the UI and warn when
  an offer is stale.
- **Export.** CSV / Markdown export for the savings report.
- **UI polish.** Filters, sorting, accessibility, empty states.

## Reporting a wrong number

If TripStack reports a saving you think is wrong, please open an issue with the
offer, the promotion text and the expected calculation. Pricing bugs are treated
as correctness bugs, not cosmetic ones.
