# CLA Evidence Extractor — Architecture & User-Friendly Overview

This document explains, in plain English and without assuming coding knowledge, how the CLA Evidence Extractor is organized and how a request flows through the system.

High-level purpose
- The app accepts a PDF and a question, then uses a combination of text extraction and a language model (LLM) to find rules and supporting evidence inside the document. It returns structured results so a human or another service can act on them.

Main components (simple terms)
- Web server (FastAPI): receives requests from your browser or a client, and sends back responses.
- Document reader: extracts pages and text from the uploaded PDF.
- Chunker / Indexer: breaks the document into smaller pieces (chunks) so the LLM can reason about parts instead of the whole document at once.
- Retriever: picks the most relevant chunks that are likely to answer the question.
- Analyzer (LLM agent): the language model examines the retrieved chunks and returns a structured answer (summary, a list of rules, citations to chunks that support each rule, and confidence/decision metadata).
- Evidence builder: converts chunk references into human-friendly excerpts (short text snippets with page numbers).
- Cache: saves small summaries and entire query responses so repeated requests are faster and cheaper.
- Static demo page: a small web form that lets you try the API by uploading a PDF and entering a question.

Step-by-step request flow (what happens after you click submit)
1. You upload a PDF and type a question in the demo page (or call the API directly).
2. The server generates a unique trace id for this request. This id is included in logs and the response so you can trace what happened for that request.
3. The PDF is converted to plain text pages (the Document reader). The document is split into smaller chunks.
4. For each chunk, a short text summary may be computed and cached. This summary speeds up later steps.
5. The Retriever finds the top-N chunks that match the question.
6. The Analyzer (an agent that calls an LLM) receives the question plus the retrieved chunks. It returns JSON describing: a short answer/summary, a list of specific rules it found, which chunk ids support each rule, a confidence score, and whether the system can decide automatically or a human review is needed.
7. The Evidence builder turns chunk ids into short excerpts and page numbers so users can check the original text.
8. The result is returned to the client as JSON. The response includes the `trace_id` to help debug or audit that specific run.

Where data (and logs) are stored
- Temporary: uploaded PDF bytes are read in memory during processing.
- Cache: a small on-disk cache lives at `apps/api/.cache/` for chunk summaries and recent query responses.
- Audit log: simple JSONL audit events are appended to `apps/api/audit_log.jsonl` when certain steps run.

Typical failure modes and how to interpret them
- Missing or invalid Google API key: the LLM call fails with an authentication error. The server maps provider errors to a 502 response and logs the provider's message. The startup logs also print first/last 4 chars of the API key (so you can confirm which key the app used).
- Non-JSON replies from the LLM: sometimes the LLM responds with prose or includes markdown code fences. The app extracts the JSON block if possible; if the reply is not parseable, the app logs a short snippet to help debugging.

How to inspect logs and trace a request
- Each request has a `trace_id` returned in the response. Search logs for that `trace_id` to see step-level events and any errors.

Where to look in the code (developer pointers)
- `src/main.py` — web routes, middleware, static demo mount, query-level cache check
- `src/graph/nodes.py` — the workflow nodes that implement ingest → index → retrieve → analyze → evidence → verify
- `src/adk/agents.py` — where agent prompts and behavior are defined
- `src/cache.py` — file-backed cache logic
- `static/demo.html` — demo UI

Extending the system (non-technical summary)
- Want higher throughput or multiple app instances? Replace the on-disk cache with a shared cache service (Redis).
- Want to support other LLMs? Add or change the agent runner configuration and prompts.
- Want stricter reliability? Add more unit tests, and a CI workflow that runs them automatically on every push.

If you'd like, I can create a simple diagram (PNG or ASCII) to add to this file, or produce a one-page handout you can give to non-technical reviewers.
