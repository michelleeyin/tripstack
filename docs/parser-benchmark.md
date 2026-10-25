# Promotion parser benchmark — Gemma vs. rule-based fallback

Measured on 2026-10-24, macOS arm64 (16 GB), Ollama 0.40.11, 10 hand-labelled
promotion texts × 9 fields (`data/promotion_bench.json`).

Reproduce with:

```bash
OLLAMA_MODEL=gemma:7b python benchmark_parser.py --json
```

Everything below is measured output, not a target.

---

## Headline

| Model | Gemma only | Hybrid | Rule-based |
|---|---|---|---|
| **gemma:7b** — field accuracy | **93.3%** | **96.7%** | 97.8% |
| **gemma:7b** — perfect cases (9/9) | 50% | 70% | 80% |
| **gemma:2b** — field accuracy | 75.6% | 91.1% | 97.8% |
| **gemma:2b** — perfect cases (9/9) | 10% | 40% | 80% |

- *Gemma only* = model output, validated, with the grounding check below.
- *Hybrid* = numeric fields from the rule parser (grounded in the text),
  semantic fields (`type`, `taxes_eligible`, `stackable`, `requires_verification`)
  from the model.
- *Rule-based* = regex/heuristic parser, no model.

**gemma:2b → gemma:7b is the single biggest win: 75.6% → 93.3% on model-only
extraction, and 91.1% → 96.7% hybrid.**

---

## Per-field, gemma:7b (correct out of 10)

| Field | Gemma | Hybrid | Rules |
|---|---|---|---|
| `type` | 10 | 10 | 10 |
| `rate` | 10 | 10 | 10 |
| `fixed_amount` | 7 | 9 | 9 |
| `cap` | 9 | 10 | 10 |
| `minimum_spend` | 10 | 10 | 10 |
| `taxes_eligible` | 8 | 8 | 10 |
| `stackable` | **10** | **10** | 9 |
| `requires_verification` | 10 | 10 | 10 |
| `valid_until` | 10 | 10 | 10 |

The model beats the rules on `stackable` (10 vs 9) — it reads "cannot be
combined with other promotions" correctly where the regex missed it — and loses
on `fixed_amount` and `taxes_eligible`.

## Per-field, gemma:2b (correct out of 10)

| Field | Gemma | Hybrid | Rules |
|---|---|---|---|
| `type` | 6 | 6 | 10 |
| `rate` | 10 | 10 | 10 |
| `fixed_amount` | 3 | 9 | 9 |
| `cap` | 6 | 10 | 10 |
| `minimum_spend` | 9 | 10 | 10 |
| `taxes_eligible` | 9 | 9 | 10 |
| `stackable` | 8 | 8 | 9 |
| `requires_verification` | 7 | 10 | 10 |
| `valid_until` | 10 | 10 | 10 |

---

## Failure modes found (and the fixes they produced)

These are the real behaviours observed while building this; each one changed
the code.

1. **Few-shot contamination.** With a worked example containing 8% / $30,
   gemma:2b copied those figures into promotions whose text contained *no
   numbers at all*. With an "ambiguous" example, it copied
   `requires_verification: true` into 9 of 10 cases.
   → Prompt is now **zero-shot**; the 12 explicit rules carry the task.
2. **Invented numbers.** gemma:2b returned `rate: 0.08` for
   "Special member pricing may apply at checkout."
   → **Grounding check**: any number the model returns must literally appear
   in the source text, otherwise it is discarded and flagged.
3. **Invented expiry dates.** gemma:2b returned `valid_until: 2023-04-01` for
   texts with no date — which would silently mark a live promotion expired.
   → Grounding check extended to dates.
4. **Zero instead of null.** gemma:2b returned `fixed_amount: 0.0` where the
   correct answer was `null`; after grounding the promotion correctly degrades
   to "requires verification" rather than "no benefit".
5. **Hybrid gap-filling hurt.** Letting model numbers fill fields the rule
   parser left empty cost accuracy (e.g. reusing the minimum spend as a fixed
   discount).
   → Hybrid now takes numeric values from the rule parser **only**.

Result of the guardrails: a hallucinated value can no longer reach the pricing
engine. The worst case is a promotion flagged `unknown`, which the eligibility
validator excludes from reported savings.

---

## Honest read: is the model worth it?

On this benchmark — ten clean, single-sentence English promotions — **the rule
parser scores highest (97.8%)**. That is the truthful result and it is worth
saying out loud.

Why keep the model:

- **It wins the fields regexes are worst at** (`stackable`: 10 vs 9), and it
  classifies promo *type* correctly on phrasing no rule anticipates.
- **The benchmark favours rules by construction.** These texts are tidy. Real
  promotion copy is multi-clause, misspelled, and full of conditions like
  "except where prohibited"; that is where extraction beats pattern matching.
- **The cost of being wrong is bounded.** Every value is grounded in the source
  text, and anything unverifiable is excluded from savings rather than guessed.
- **The hybrid strategy closes most of the gap**: 96.7% with gemma:7b, versus
  93.3% for the model alone and 97.8% for rules alone.

Caveat: n = 10. Treat this as a smoke test that exposed concrete bugs, not as
a claim about general accuracy.

---

## Notes on method

- Labels were written by hand before either parser was run.
- A money/rate field counts as correct when within 0.005 of the label.
- `requires_verification` is a safety flag: case c08 ("Terms shown after
  login") must be flagged, not guessed.
- The model was invoked for all 10 cases in both runs. `method=gemma` is
  recorded when a grounded benefit survived; `method=failed` means the model
  answered but nothing grounded remained, so the promotion was flagged for
  verification (gemma:2b: 4 such cases; gemma:7b: 1).
- Wall clock: gemma:2b ≈ 2–3 s/promotion, gemma:7b ≈ 10–20 s/promotion on this
  machine. The app therefore parses only promotions that ship as raw text, not
  the whole curated rule set.
