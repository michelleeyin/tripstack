# Local Gemma workflow

Run `bash start.sh` from the project directory, then visit http://127.0.0.1:8599.
The launcher defaults to the installed `gemma:2b` and CPU-compatible Ollama startup
(`GGML_METAL_DEVICES=0`). Set `TRIPSTACK_CPU=0` before starting to use automatic
GPU discovery. This flag affects a newly started Ollama process; it cannot
reconfigure an Ollama server that was already running. A failed model check
shows the server error rather than claiming AI is ready.

## Review and apply

1. Select **Find my stay** in **Your trip**.
2. Open **Add an offer**, specify its platform and currency, and paste one offer.
3. Choose a method under **Source & analysis options**, then select **Analyze offer**.
4. Review numeric source excerpts, extracted conditions, actual method, model,
   timing and token counts. Input changes invalidate the pending review.
5. Compare the before/after trip price on the same hotel snapshot.
6. Check the review box and apply. Offers remain estimated, never verified.
7. Remove an offer to recompute the original plan. No fresh hotel request occurs.

Custom offers and extraction traces live only in the current browser session.
A page reload or server restart can clear them. The downloadable report includes
custom offer records and extraction diagnostics. This does not publish or book
anything.

## Grounding and limitations

Hybrid uses deterministic source numbers and model semantics. Explicit source
exclusions override conflicting model booleans. Model numbers absent from the
text are removed; conflicting amount roles, multiple rates, and text beyond the
2,000-character model input limit are held for review and excluded from savings.
The evidence snippets demonstrate where numbers occur; they are not a guarantee
that the whole offer is eligible. Human review does not verify a payout.

Multiple rates require splitting into separate unambiguous offers. Currency
must match the trip; the workflow does not convert currencies. All demo hotel
prices and curated promotions remain fixtures. Live hotel data requires the
existing provider setup.

## Checks

With the project environment activated:

```sh
python -m pytest -q
```

Tests use mocked model responses for repeatability. A live smoke check was also
performed locally with Gemma: a 7.5% offer capped at $60 on a $1,000 room produced
$60 estimated cashback and $940 net cost, with no rule fallback. Timing is
machine-dependent; the observed cold request was approximately seven seconds.
