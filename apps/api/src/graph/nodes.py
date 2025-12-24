"""Minimal, clean workflow nodes to restore API stability.

These implementations are intentionally simple and safe. We'll incrementally
add retries, richer parsing, and audit hygiene once the codebase is stable.
"""
import json
import logging
import os
from typing import Any, Dict, List

from .state import WorkflowState
from ..doc.ingest import extract_pages, extract_pages_from_path
from ..doc.retrieve import chunk_pages, keyword_retrieve
from .. import cache
from ..tools.audit import write_audit

logger = logging.getLogger(__name__)


def ingest_node(state: WorkflowState) -> WorkflowState:
    pdf_path = state.get("pdf_path")
    if pdf_path:
        pages = extract_pages_from_path(pdf_path)
        try:
            os.remove(pdf_path)
        except Exception:
            logger.debug("failed to remove temp pdf: %s", pdf_path)
        return {"pages": pages}

    pdf_bytes = state.get("pdf_bytes")
    if pdf_bytes:
        pages = extract_pages(pdf_bytes)
        return {"pages": pages}

    raise RuntimeError("no pdf provided to ingest_node")


async def index_node(state: WorkflowState) -> WorkflowState:
    chunks = chunk_pages(state["pages"])
    document_id = state.get("document_id", "unknown")
    for c in chunks:
        try:
            summ = cache.get_chunk_summary(document_id, c["chunk_id"]) or None
            if not summ:
                summ = cache.compute_summary_if_missing(document_id, c["chunk_id"], c.get("text", ""))
            c["summary"] = summ
        except Exception:
            c["summary"] = None
    return {"chunks": chunks}


def retrieve_node(state: WorkflowState) -> WorkflowState:
    retrieved = keyword_retrieve(state["chunks"], state["question"], k=8)
    write_audit({"trace_id": state.get("trace_id"), "step": "retrieve", "k": len(retrieved)})
    return {"retrieved": retrieved}


async def analyze_node(state: WorkflowState) -> WorkflowState:
    # Minimal analyzer stub: echo question and indicate human review required.
    write_audit({"trace_id": state.get("trace_id"), "step": "analyze"})
    return {"agent_json": {"answer": {"summary": "", "rules": []}, "confidence": 0.0, "decision": "needs_human"}, "confidence": 0.0, "decision": "needs_human", "missing_info": [], "citations_by_rule": {}}


def evidence_node(state: WorkflowState) -> WorkflowState:
    # Build lightweight evidence from retrieved chunks if present
    by_id = {c["chunk_id"]: c for c in state.get("retrieved", [])}
    evidence = []
    for cid, c in by_id.items():
        excerpt = (c.get("text") or "")[:800]
        evidence.append({"evidence_id": f"e_{cid}", "chunk_id": cid, "page": int(c.get("page", 0)), "excerpt": excerpt})
    return {"evidence": evidence}


def verify_node(state: WorkflowState) -> WorkflowState:
    # Conservative: if no evidence or agent decision is needs_human, require human
    agent_json = state.get("agent_json", {})
    decision = agent_json.get("decision", "needs_human")
    if decision == "needs_human" or not state.get("evidence"):
        return {"decision": "needs_human", "confidence": 0.0}
    return {"decision": decision, "confidence": float(agent_json.get("confidence", 0.0))}
