import uuid
import logging
import os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from dotenv import load_dotenv
from .logging_config import configure_logging, trace_id_var

try:
    # google.genai.errors is optional in some environments; import when available
    import google.genai.errors as genai_errors
except Exception:
    genai_errors = None

from .graph.workflow import build_workflow
from .schemas import RunResponse, Evidence, Answer, Rule
from . import cache

load_dotenv()

configure_logging()
app = FastAPI(title="CLA Evidence Extractor POC")
logger = logging.getLogger(__name__)
# Fail-fast check for GOOGLE_API_KEY (print only first/last chars for safe debug)
key = os.getenv("GOOGLE_API_KEY")
if not key:
    raise RuntimeError("GOOGLE_API_KEY not set")
logger.info("GOOGLE_API_KEY: %s ... %s", key[:4], key[-4:])

workflow = build_workflow()

# Mount static files directory (serves /static/demo.html)
static_dir = str(Path(__file__).resolve().parents[1] / "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.middleware("http")
async def add_trace_id_middleware(request: Request, call_next):
    # generate a trace id for each incoming request and store it in contextvar
    tid = str(uuid.uuid4())
    trace_id_var.set(tid)
    # also attach to request.state for handlers that want it
    request.state.trace_id = tid
    response = await call_next(request)
    return response


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def root():
    """Redirect root to the demo page for convenience."""
    return RedirectResponse(url="/demo")


@app.get("/demo")
def demo_page():
    # Redirect to the static demo HTML for a safer, static-served UI
    return RedirectResponse(url="/static/demo.html")


@app.post("/extract/overtime", response_model=RunResponse)
async def extract_overtime(
    request: Request,
    pdf: UploadFile = File(...),
    question: str = Form("What are the overtime compensation rules?")
):
    # prefer middleware-provided trace id; fall back to a new uuid
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    pdf_bytes = await pdf.read()
    document_id = pdf.filename or "uploaded.pdf"

    # Query-level caching: use document hash + normalized question hash as key.
    doc_hash = cache.doc_hash_from_bytes(pdf_bytes)
    q_hash = cache.question_hash(question)
    cached = cache.get_query_cache(doc_hash, q_hash)
    if cached:
        # attach trace id and return cached response
        cached['trace_id'] = trace_id
        logger.info("cache hit for doc=%s q=%s", document_id, q_hash)
        return cached

    state = {
        "pdf_bytes": pdf_bytes,
        "document_id": document_id,
        "question": question,
        "trace_id": trace_id,
    }

    # workflow contains async nodes (e.g. analyze_node). Use the async invoke API so
    # async nodes are executed correctly instead of raising the "No synchronous
    # function provided" TypeError from langgraph. Wrap invocation to return a
    # clear HTTP error for provider/auth issues (e.g. missing/invalid API key).
    try:
        result = await workflow.ainvoke(state)
    except Exception as e:
        # If google.genai raised a ClientError, translate to a 502 with a helpful message
        if genai_errors is not None and isinstance(e, genai_errors.ClientError):
            logger.error("Google GenAI client error: %s", e)
            raise HTTPException(
                status_code=502, detail="Google GenAI authentication/usage error: check GOOGLE_API_KEY and API access")
        # Otherwise re-raise so FastAPI will return 500 and log the traceback
        raise
    agent_json = result.get("agent_json", {})
    answer = agent_json.get("answer") or {"summary": "", "rules": []}

    # build serializable response dict
    out = {
        "document_id": document_id,
        "question": question,
        "answer": {
            "summary": answer.get("summary", ""),
            "rules": answer.get("rules", []),
        },
        "evidence": result.get("evidence") or [],
        "citations_by_rule": result.get("citations_by_rule") or {},
        "confidence": float(result.get("confidence", 0.0)),
        "decision": result.get("decision", "needs_human"),
        "missing_info": result.get("missing_info") or [],
        "trace_id": trace_id,
    }

    # Cache the successful auto decision results (short TTL) keyed by document+question
    try:
        if out.get('decision') == 'auto':
            cache.set_query_cache(doc_hash, q_hash, out, ttl=60 * 60)
    except Exception:
        logger.exception('failed to set query cache')

    # Return Pydantic model (will be validated/serialized)
    return RunResponse(
        document_id=out['document_id'],
        question=out['question'],
        answer=Answer(
            summary=out['answer']['summary'],
            rules=[Rule(**r) for r in out['answer'].get('rules') or []],
        ),
        evidence=[Evidence(**e) for e in out.get('evidence') or []],
        citations_by_rule=out.get('citations_by_rule') or {},
        confidence=float(out.get('confidence', 0.0)),
        decision=out.get('decision', 'needs_human'),
        missing_info=out.get('missing_info') or [],
        trace_id=out.get('trace_id'),
    )
