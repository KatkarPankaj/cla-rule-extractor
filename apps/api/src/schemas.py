from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class Evidence(BaseModel):
    evidence_id: str
    excerpt: str
    page: int
    section: Optional[str] = None
    chunk_id: str


class Rule(BaseModel):
    rule_name: str
    conditions: List[str] = []
    compensation: str
    exceptions: List[str] = []


class Answer(BaseModel):
    summary: str
    rules: List[Rule]


class RunResponse(BaseModel):
    document_id: str
    question: str
    answer: Answer
    evidence: List[Evidence]
    citations_by_rule: Dict[str, List[str]]
    confidence: float = Field(ge=0.0, le=1.0)
    decision: str
    missing_info: List[str] = []
    trace_id: str
