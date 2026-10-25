# Demo script — TripStack v0.1

Two uses: (a) a live walkthrough someone follows on screen, (b) the shot list
for the 90-second Hacktoberfest video. Every number below was produced by the
demo fixtures on 2026-10-24.

---

## 0. Pre-flight (2 minutes, do this before anyone watches)

```bash
# Terminal 1 — model server (required for the AI page)
/opt/homebrew/opt/ollama/bin/ollama serve

# Terminal 2 — dashboard
cd tripstack
PYTHONPATH=<workspace> OLLAMA_MODEL=gemma:7b \
  /Users/yinjiayi/.workbuddy/binaries/python/envs/default/bin/streamlit run app.py
```

Checks before you start:

- [ ] Dashboard opens at `http://localhost:8599`
- [ ] Sidebar shows **"Ollama reachable — model `gemma:7b`"** (green)
- [ ] If Ollama is down: the sidebar warns instead, and the app still works —
      but page 4 will say `method: heuristic`, which is the honest fallback,
      not the demo you want.

Recommended sidebar settings for the demo:

- Data mode: **demo**
- Use Gemma AI parser: **on**
- Parser strategy: **hybrid**

---

## 1. The problem (say this first, ~15 s)

> "A 15-day, three-city trip means comparing hotels across platforms, then
> reading cashback terms, caps, minimum spends and stacking rules — by hand,
> for every city. The cheapest advertised price is usually not the cheapest
> final price."

## 2. Enter the trip — Page 1 (~20 s)

1. Click **Load demo trip**.
   Banner should read: *3 cities · 15 nights · budget $2,500 · 2 travelers*.
2. Click **Search hotels**.
3. Point at the success line: *Analyzed 24 offers via DemoProvider (demo mode)*.

Talking point: no hotel data was typed in by hand — 24 offers came from the
provider layer.

## 3. Gemma reads the terms — Page 4 (~20 s)

1. Open **4 · Promotion Lab**.
2. Keep the default text ("Earn 8% cashback… Taxes and fees are excluded.").
3. Click **Extract with Gemma**.

Expect:

```
Method: `gemma`  ·  model `gemma:7b`
{"promotion_type":"cashback","rate":0.08,"cap":30,"taxes_eligible":false,
 "stackable":false,...}
```

Two things worth saying out loud:

- `method: gemma` proves the model was really called, not the fallback.
- Below it, the **curated rule set** table includes
  `promo-c-cashback-unknown` — Gemma returned numbers for it, the grounding
  check threw them out, and it stays `unknown`. That is the safety property.

## 4. Upfront vs. net cost — Page 2 (~20 s)

1. Open **2 · Offer Comparison**.
2. Sort by **Estimated net cost**.
3. Expand the top offer and read the breakdown:

```
base + taxes + fees  ->  upfront payment
cashback (capped)    ->  estimated net cost
guaranteed_net_cost  ->  what is actually confirmed
```

Talking point: sort by *Upfront payment* and the order changes — the offer
that is cheapest today is not always the cheapest after cashback.

## 5. The report — Page 3 (~15 s)

1. Open **3 · Savings Report**.

Numbers you should see:

| Metric | Value |
|---|---|
| Upfront total | $2,331.03 |
| Estimated cashback | $75.10 |
| Estimated net cost | $2,255.93 |
| Savings vs. cheapest advertised | $86.28 (3.7%) |
| Savings vs. average offer | $730.21 (24.5%) |
| Budget remaining (upfront) | $168.97 |
| Budget remaining after cashback | $244.07 |

Then point at the disclosures under it:

- baseline defined as the **pre-promotion** price
- "Cashback is an estimate, not a guaranteed payout"
- every offer carries a source URL and a retrieval timestamp
- demo prices are labelled simulated

## 6. Close (~10 s)

> "It replaces an afternoon of manual comparison with one report — and every
> number in it is traceable to a source, or flagged as unverified."

---

## Fallbacks

| Symptom | Fix |
|---|---|
| Sidebar says Ollama unreachable | `ollama serve` in a terminal; page 4 will otherwise show `heuristic` |
| Page 2/3 empty | Go back to page 1, Load demo trip → Search hotels |
| `ModuleNotFoundError: tripstack` | Run from the workspace root, or set `PYTHONPATH` as above |
| Slow on page 4 | Switch sidebar strategy to `rules`, or use `OLLAMA_MODEL=gemma:2b` |

## Recording tips for the 90 s video

- Window at 1440×900 or larger; the comparison table is wide.
- Cursor slow and deliberate; pause ~1 s on each number you quote.
- Capture the sidebar at least once (shows mode + model status — it is the
  honesty signal).
- End the video on page 3 with the full report visible.
