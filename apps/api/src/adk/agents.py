from google.adk.agents.llm_agent import Agent
from ..tools.audit import write_audit

ANALYZER_INSTRUCTION = """
You extract overtime compensation rules from a collective labor agreement (CLA).

You will receive:
- QUESTION
- EVIDENCE_CHUNKS: a list of chunks with chunk_id, page, section, text.

Rules:
1) You MUST only use the provided chunks.
2) Every rule MUST cite at least one chunk_id in citations_by_rule.
3) If you cannot find evidence, set decision="needs_human" and explain missing_info.
4) Return ONLY valid JSON matching this shape:

{
  "answer": {
    "summary": "...",
    "rules": [
      {
        "rule_name": "...",
        "conditions": ["..."],
        "compensation": "...",
        "exceptions": ["..."]
      }
    ]
  },
  "citations_by_rule": { "0": ["c00001","c00002"] },
  "confidence": 0.0,
  "decision": "auto" | "needs_human",
  "missing_info": ["..."]
}

Be conservative with confidence.
"""


def build_overtime_agent() -> Agent:
    return Agent(
        name="cla_overtime_agent",
        model="gemini-2.0-flash",
        instruction=ANALYZER_INSTRUCTION,
        tools=[write_audit],
    )


SUMMARIZER_INSTRUCTION = """
You are a strict summarizer. Given a chunk of a document, produce a short, factual summary.

Requirements:
- ONLY summarize the provided text; do not add new facts or infer beyond the text.
- Produce one paragraph, <= 300 characters.
- Keep key phrases and numbers when present.
- Output only the summary text (no JSON wrapper).
"""


def build_summarizer_agent() -> Agent:
    return Agent(
        name="cla_chunk_summarizer",
        model="gemini-2.0-flash",
        instruction=SUMMARIZER_INSTRUCTION,
        tools=[],
    )
