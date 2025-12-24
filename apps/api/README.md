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
