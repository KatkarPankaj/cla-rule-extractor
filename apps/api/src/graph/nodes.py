import json
import logging
from typing import Dict, Any, List
from .state import WorkflowState
from ..doc.ingest import extract_pages
from ..doc.retrieve import chunk_pages, keyword_retrieve
from .. import cache
from src.adk.agents import build_overtime_agent
from src.adk.runtime import AdkRunner
from ..tools.audit import write_audit
import src.adk.agents as agents_mod

logger = logging.getLogger(__name__)
logger.debug("AGENTS MODULE PATH: %s", getattr(
    agents_mod, "__file__", "<unknown>"))
logger.debug("HAS build_overtime_agent: %s",
             hasattr(agents_mod, "build_overtime_agent"))

_agent = AdkRunner(build_overtime_agent())


def ingest_node(state: WorkflowState) -> WorkflowState:
    # pdf_bytes is injected by the API layer (see main.py)
    pdf_bytes = state["pdf_bytes"]  # internal field
    pages = extract_pages(pdf_bytes)
    return {"pages": pages}


def index_node(state: WorkflowState) -> WorkflowState:
    chunks = chunk_pages(state["pages"])
    # compute or attach cached summaries per chunk (keyed by document_id + chunk_id)
    document_id = state.get("document_id", "unknown")
    for c in chunks:
        try:
            summ = cache.get_chunk_summary(document_id, c["chunk_id"])
            if not summ:
                # compute and persist a light-weight summary
                summ = cache.compute_summary_if_missing(
                    document_id, c["chunk_id"], c.get("text", ""))
            c["summary"] = summ
        except Exception:
            # non-fatal: continue without summary
            c["summary"] = None
    return {"chunks": chunks}


def retrieve_node(state: WorkflowState) -> WorkflowState:
    # use document-scoped summaries when available to enrich retrieved chunks
    retrieved = keyword_retrieve(state["chunks"], state["question"], k=8)
    document_id = state.get("document_id", "unknown")
    for c in retrieved:
        if "summary" not in c or not c.get("summary"):
            try:
                c["summary"] = cache.get_chunk_summary(
                    document_id, c["chunk_id"]) or None
            except Exception:
                c["summary"] = None

    write_audit({"trace_id": state["trace_id"],
                "step": "retrieve", "k": len(retrieved)})
    return {"retrieved": retrieved}


async def analyze_node(state: WorkflowState) -> WorkflowState:
    # send compact payload (don’t dump entire doc)
    chunks_payload: List[Dict[str, Any]] = [
        {
            "chunk_id": c["chunk_id"],
            "page": c["page"],
            "section": c.get("section"),
            "text": c["text"],
            "summary": c.get("summary"),
        }
        for c in state["retrieved"]
    ]

    prompt = json.dumps({
        "QUESTION": state["question"],
        "EVIDENCE_CHUNKS": chunks_payload
    }, ensure_ascii=False)

    raw = await _agent.run_text(prompt)
    agent_json = json.loads(raw)

    write_audit({"trace_id": state["trace_id"], "step": "analyze",
                "decision": agent_json.get("decision")})
    return {
        "agent_json": agent_json,
        "confidence": float(agent_json.get("confidence", 0.0)),
        "decision": agent_json.get("decision", "needs_human"),
        "missing_info": agent_json.get("missing_info", []),
        "citations_by_rule": agent_json.get("citations_by_rule", {}),
    }


def evidence_node(state: WorkflowState) -> WorkflowState:
    # build evidence objects from cited chunk_ids
    by_id = {c["chunk_id"]: c for c in state["retrieved"]}
    used_ids = sorted({cid for cids in state.get(
        "citations_by_rule", {}).values() for cid in cids})

    evidence = []
    for eid in used_ids:
        c = by_id.get(eid)
        if not c:
            continue
        excerpt = (c["text"] or "").strip()
        # keep response small; in prod use anchored spans
        excerpt = excerpt[:800]
        evidence.append({
            "evidence_id": f"e_{eid}",
            "chunk_id": eid,
            "page": int(c["page"]),
            "section": c.get("section"),
            "excerpt": excerpt,
        })

    return {"evidence": evidence}


def verify_node(state: WorkflowState) -> WorkflowState:
    # Hard gate: every rule must have ≥1 evidence item
    agent_json = state.get("agent_json", {})
    rules = ((agent_json.get("answer") or {}).get("rules")) or []
    citations = state.get("citations_by_rule", {}) or {}

    ok = True
    for i in range(len(rules)):
        if str(i) not in citations or not citations[str(i)]:
            ok = False

    if not state.get("evidence"):
        ok = False

    if not ok:
        return {"decision": "needs_human", "confidence": min(state.get("confidence", 0.0), 0.6)}

    return {}
