# SUTRANETRA

**Sutra** = thread / connection · **Netra** = eye / vision

*"The eye that follows the hidden threads."*

SUTRANETRA attributes pseudonymous dark-web marketplace actors to real-world infrastructure for SIH26151 (NTRO). The system has three layers:

1. **Correlation** — which aliases are probably the same actor (stylometry, hard evidence, graph).
2. **Attribution** — which actors leak infrastructure that can lead investigators outward (OpSec scanning, Certificate Transparency pivoting).
3. **Evidence / Investigation** — why an investigator should believe a result, what was observed, and what to check next (explanations, Evidence Trail, exports, read-only query).

## Legal and ethical scope

- We do not interact with live criminal infrastructure: no Tor scraping, no third-party hidden services.
- The corpus is historical and public (Darknet Market Archives on archive.org, defunct markets circa 2013–2015).
- The only hidden service scanned in this project is one we run locally, deliberately misconfigured for demonstration.
- Certificate Transparency data is public by design.
- Intended use is law-enforcement attribution research for NTRO.
- Wallets, PGP fingerprints, and handles are reported as **pseudonymous identifiers with confidence scores**, not identity verdicts.

## Quick start

Requires **Python 3.11+** (3.12 acceptable).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.ingest.schema
```

This creates `data/db/attrib.sqlite` with the full corpus + cases schema (`posts`, `aliases`, `evidence`, `cases`, `pair_scores`, `clusters`, `opsec_findings`). Re-running the command is safe (idempotent).

Configuration lives in `config.yaml` (`dev` profile by default: Neo4j off, Groq phrasing on when `GROQ_API_KEY` is present). For the local judge demo (investigator + explanation polish): copy `.env.example` to `.env`, set `GROQ_API_KEY`, and launch with the repository root on `PYTHONPATH`. Use `SUTRANETRA_PROFILE=cloud` only for the public judge path later.

## Local website + LLM (no deploy)

```bash
cp .env.example .env   # paste GROQ_API_KEY from https://console.groq.com
source .venv/bin/activate
pip install -r requirements-agent.txt -r requirements-api.txt -r requirements-ui.txt

# terminal 1 — API + built-in site
uvicorn src.api.app:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000   GET /health should show llm.reachable true

# terminal 2 — optional Streamlit console (same .env)
streamlit run src/ui/app.py
```

If the key is unavailable, the investigator reports that live phrasing is unavailable and the evidence-led case views remain usable. No Gemini: Groq is the SPEC provider and already in `src/llm/client.py`.

## Cloud (free, remote judges)

Pipeline stays local/CLI. Cloud serves a **read-only precomputed case**.

1. Pack a snapshot: `python -m scripts.pack_demo_db` (writes `data/demo/attrib.sqlite`).
2. Backend (Render): `uvicorn src.api.app:app --host 0.0.0.0 --port $PORT` with `SUTRANETRA_PROFILE=cloud` and `GROQ_API_KEY`.
3. Frontend (Streamlit Community Cloud): `streamlit run src/ui/app.py` with secret `SUTRANETRA_API_URL` = the Render URL.

See `.env.example` and `render.yaml`. Never commit API keys.

Local website (FastAPI, no Streamlit): `uvicorn src.api.app:app --host 127.0.0.1 --port 8000` then open http://127.0.0.1:8000.

Streamlit remains the optional cloud frontend: `streamlit run src/ui/app.py`.

Full technical specification: `SPEC.md`.
