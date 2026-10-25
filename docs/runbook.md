# Local operation

## Environment

From the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.port 8599
```

Open <http://localhost:8599>. Keep the terminal running. Stop the server with
Control-C. The launcher's `TRIPSTACK_CPU` setting affects only an Ollama process
started by that launcher; it cannot reconfigure an existing server.

## Local model

```bash
ollama pull gemma:2b
ollama serve
```

Use **Settings & model diagnostics** to select a model and check inference.
A successful connection or model listing does not confirm inference works.
The interface retains the model's error message when generation fails.
See [gemma-workflow.md](gemma-workflow.md) for CPU configuration and extraction
behavior.

## Application flow

1. In **Your trip**, enter the destination, dates, nights and budget.
2. Use **More trip options** for additional cities, currency and ranking.
3. Select **Find my stay**. Results appear in the same view.
4. Open a stay's details for its calculation, conditions and alternatives.
5. Use **Add an offer** to parse and review another promotion.
6. **Inside TripStack** contains extraction records and diagnostics.

Demo data is simulated. Live data requires the Amadeus settings described in
[README.md](../README.md). The default provider host is a sandbox.

## Diagnostics

```bash
curl --fail http://127.0.0.1:8599/_stcore/health
curl --fail http://127.0.0.1:11434/api/tags
python -m pytest -q
```

If the web address refuses connections, check that the application process is
running on the same port. If Ollama is unavailable, extraction can fall back to
the rule parser; the result records which method was used. Invalid or ambiguous
benefits remain excluded from savings.

Custom offers and quote snapshots are session state. Download a report before
reloading or restarting if those records are needed.
