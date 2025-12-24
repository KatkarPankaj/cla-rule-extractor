from typing import TypedDict, Dict, Any, List, Optional

class WorkflowState(TypedDict, total=False):
    document_id: str
    question: str
    trace_id: str

    pdf_bytes: bytes            # ✅ add this

    pages: List[str]
    chunks: List[Dict[str, Any]]
    retrieved: List[Dict[str, Any]]

    agent_json: Dict[str, Any]
    evidence: List[Dict[str, Any]]
    citations_by_rule: Dict[str, List[str]]

    confidence: float
    decision: str
    missing_info: List[str]
    error: Optional[str]
