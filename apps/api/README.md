# CLA Evidence Extractor — Quick Start

This folder contains a small proof-of-concept web API that extracts clause-level evidence and rules from PDF policy documents using an LLM-based agent.

Purpose
- Provide a simple API to upload a PDF, ask a question (for example: "What are the overtime compensation rules?"), and receive a structured JSON response containing a short summary, identified rules, and evidence citations.

Highlights
- Web server: FastAPI (Python)
- LLM integration: Google Generative AI (via google-adk / google-genai) as an agent runner
- Simple file-backed caching for repeated queries
- Demo UI: static page served at `/static/demo.html` and accessible at `/demo`

Before you run
- Python 3.11+ recommended
- Create a virtual environment and install dependencies from the repo's `pyproject.toml` or `requirements.txt` (project root).
- You must set a Google API key for the Generative AI API. The app requires an environment variable:

  - `GOOGLE_API_KEY` — your Google Generative AI API key (the app prints only the first/last 4 chars at startup for safe debug).

Optional environment variables
- `ENABLE_SUMMARIZER_AGENT` — when set (any non-empty value), the service uses a small summarizer agent to produce per-chunk summaries.

Run locally (from `apps/api`)

PowerShell example:

```powershell
$env:GOOGLE_API_KEY = '<YOUR_KEY>'
python -m uvicorn src.main:app --reload --port 8000 --app-dir .
```

Open the demo UI in a browser: http://127.0.0.1:8000/demo

API endpoints
- `GET /health` — simple liveness check
- `GET /demo` — redirects to the static demo page (`/static/demo.html`)
- `POST /extract/overtime` — upload a PDF (form field `pdf`) and supply a `question` form field. Returns a typed JSON response with `answer`, `evidence`, `citations_by_rule`, `confidence`, `decision`, and `trace_id`.

Troubleshooting
- If you see a 502 with a message about authentication/usage, check `GOOGLE_API_KEY` — the app maps provider ClientErrors to HTTP 502 and logs provider messages.
- The app prints a short debug line with the first and last 4 characters of the `GOOGLE_API_KEY` at startup; this helps verify which key is loaded without exposing the full key.
- Caching is stored under the `apps/api/.cache/` folder. Remove it to clear cached summaries and query results.

Tests
- Unit tests live in `apps/api/tests/`. They mock the agent runner so they don't require a real API key. Run tests with:

```powershell
python -m pytest -q
```

Where the code lives (quick pointers)
- `apps/api/src/main.py` — FastAPI app, request handling, middleware, static file mount, query cache lookup
- `apps/api/src/graph/` — workflow graph nodes and state definitions (ingest, index, retrieve, analyze, evidence, verify)
- `apps/api/src/adk/` — agent builders and the ADK runner that calls the LLM
- `apps/api/src/cache.py` — simple file-backed cache for per-chunk summaries and query-level caching
- `apps/api/static/demo.html` — simple demo UI

Security and keys
- Do not commit your real `GOOGLE_API_KEY` to source control. Use an environment manager (local .env or CI secrets) to provide it.

Next steps and suggestions
- Add a small CI workflow to run tests and linters.
- Replace file-based cache with Redis if running multiple app instances.
- Add tests for the summarizer path when `ENABLE_SUMMARIZER_AGENT` is enabled.

If you'd like, I can also create a one-page non-technical architecture summary (plain-language) explaining the components and the user-visible request flow.
# CLA Evidence Extractor (API)

This is a small FastAPI service that extracts overtime compensation rules from PDFs using a workflow of ingest/index/retrieve/analyze/evidence/verify stages.

## Quick start (local)

Prerequisites:
- Python 3.11
- A virtual environment (recommended)

1. Create and activate a venv (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Set your Google Generative AI API key (dev):

```powershell
# temporary for current session
$env:GOOGLE_API_KEY='<YOUR_KEY>'
# or persistently (new terminal required)
setx GOOGLE_API_KEY "<YOUR_KEY>"
```

Alternatively create a `.env` file in this folder containing `GOOGLE_API_KEY=...`.

3. Run the server:

```powershell
python -m uvicorn src.main:app --reload --port 8000 --app-dir .
```

4. Open the interactive docs: http://127.0.0.1:8000/docs
5. Or open the demo UI: http://127.0.0.1:8000/demo

## Tests

The test suite uses `pytest` and FastAPI's `TestClient`. Tests mock the ADK runner so they do not require network access or API keys.

Run tests from the repo root (PowerShell):

```powershell
python -m pytest apps/api/tests -q
```

## Notes
- Do not commit API keys to source control. Use environment variables or a secrets manager.
- If you see `google.genai.errors.ClientError: API key not valid`, ensure `GOOGLE_API_KEY` is set and the Generative AI API is enabled for your project.
