import os
import sys
import json
import importlib
import importlib.util
from fastapi.testclient import TestClient
import pytest
from PyPDF2 import PdfWriter
import io


def create_minimal_pdf() -> bytes:
    """Create a minimal valid PDF file for testing."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def create_password_protected_pdf(password: str) -> bytes:
    """Create a password-protected PDF file for testing.

    Args:
        password: Password to protect the PDF with

    Returns:
        Encrypted PDF bytes
    """
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password=password, owner_password=password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def load_app_module():
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    path = os.path.join(base, 'src', 'main.py')
    # Ensure the package 'src' is loaded so relative imports inside main work
    pkg_init = os.path.join(base, 'src', '__init__.py')
    if os.path.exists(pkg_init):
        pkg_spec = importlib.util.spec_from_file_location('src', pkg_init)
        pkg = importlib.util.module_from_spec(pkg_spec)
        pkg_spec.loader.exec_module(pkg)
        import sys
        sys.modules['src'] = pkg

    spec = importlib.util.spec_from_file_location('src.main', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


app_mod = load_app_module()
client = TestClient(app_mod.app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j['ok'] is True
    assert 'service' in j
    assert 'version' in j


@pytest.fixture(autouse=True)
def patch_workflow(monkeypatch):
    """Monkeypatch workflow and agent dependencies to avoid network calls in tests."""
    async def fake_ainvoke(state):
        """Mock workflow invocation with valid RunResponse structure."""
        return {
            "agent_json": {"answer": {"summary": "ok", "rules": []}},
            "evidence": [],
            "citations_by_rule": {},
            "confidence": 0.5,
            "decision": "auto",
            "missing_info": [],
        }

    # Patch workflow.ainvoke to avoid actual graph execution
    m = importlib.import_module('src.main')
    monkeypatch.setattr(m.workflow, 'ainvoke', fake_ainvoke)

    # Patch PDF extraction to avoid needing real PDF files
    nodes_mod = importlib.import_module('src.graph.nodes')

    # Extract functions that accept optional password parameter
    monkeypatch.setattr(nodes_mod, 'extract_pages',
                        lambda b, password=None: ["", "dummy page text"])
    monkeypatch.setattr(nodes_mod, 'extract_pages_from_path',
                        lambda p, password=None: ["", "dummy page text"])

    yield


def test_extract_overtime(tmp_path):
    """Test POST /extract/overtime with a valid PDF file (happy path)."""
    # Create a minimal valid PDF file
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(create_minimal_pdf())

    with open(pdf_path, 'rb') as f:
        files = {'pdf': ('test.pdf', f, 'application/pdf')}
        data = {'question': 'What are the overtime compensation rules?'}
        r = client.post('/extract/overtime', files=files, data=data)

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    j = r.json()

    # Validate response structure and required fields
    assert j['document_id'] == 'test.pdf', "document_id must match filename"
    assert 'answer' in j, "Missing 'answer' field in response"
    assert isinstance(j['answer']['summary'],
                      str), "answer.summary must be a string"
    assert isinstance(j['answer']['rules'],
                      list), "answer.rules must be a list"
    assert 'trace_id' in j and j['trace_id'], "trace_id must be present and non-empty"
    assert j['confidence'] == 0.5, "confidence value mismatch"
    assert j['decision'] in [
        'auto', 'needs_human'], "decision must be 'auto' or 'needs_human'"
    assert 'evidence' in j and isinstance(
        j['evidence'], list), "evidence must be a list"


def test_extract_overtime_invalid_pdf_format(tmp_path):
    """Test POST /extract/overtime rejects non-PDF files (no PDF header)."""
    # Create a file without PDF magic bytes
    pdf_path = tmp_path / "fake.pdf"
    pdf_path.write_bytes(b"This is just plain text, not a PDF!")

    with open(pdf_path, 'rb') as f:
        files = {'pdf': ('fake.pdf', f, 'application/pdf')}
        data = {'question': 'What are the rules?'}
        r = client.post('/extract/overtime', files=files, data=data)

    # Should reject invalid PDF with error status
    assert r.status_code in [
        400, 422, 500], f"Expected error status, got {r.status_code}"
    assert 'error' in r.json() or 'detail' in r.json(
    ), "Response must include error message"


def test_extract_overtime_empty_file(tmp_path):
    """Test POST /extract/overtime rejects empty PDF files."""
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"")  # Empty file

    with open(pdf_path, 'rb') as f:
        files = {'pdf': ('empty.pdf', f, 'application/pdf')}
        data = {'question': 'What are the rules?'}
        r = client.post('/extract/overtime', files=files, data=data)

    # Should reject empty file
    assert r.status_code in [
        400, 422, 500], f"Expected error status, got {r.status_code}"


def test_extract_overtime_missing_question(tmp_path):
    """Test POST /extract/overtime handles missing question (should use default)."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(create_minimal_pdf())

    with open(pdf_path, 'rb') as f:
        files = {'pdf': ('test.pdf', f, 'application/pdf')}
        data = {}  # No question provided
        r = client.post('/extract/overtime', files=files, data=data)

    # Should succeed with default question
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    j = r.json()
    assert 'question' in j, "Response must include question field"
    assert j['question'] == 'What are the overtime compensation rules?', "Should use default question"


def test_extract_overtime_decision_needs_human(tmp_path, monkeypatch):
    """Test POST /extract/overtime returns needs_human decision."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(create_minimal_pdf())

    # Mock to return needs_human decision
    async def fake_ainvoke_human(state):
        return {
            "agent_json": {"answer": {"summary": "uncertain", "rules": []}},
            "evidence": [],
            "citations_by_rule": {},
            "confidence": 0.2,
            "decision": "needs_human",
            "missing_info": ["compensation_details"],
        }

    m = importlib.import_module('src.main')
    monkeypatch.setattr(m.workflow, 'ainvoke', fake_ainvoke_human)

    with open(pdf_path, 'rb') as f:
        files = {'pdf': ('test.pdf', f, 'application/pdf')}
        data = {'question': 'What are the overtime compensation rules?'}
        r = client.post('/extract/overtime', files=files, data=data)

    assert r.status_code == 200
    j = r.json()
    assert j['decision'] == 'needs_human', "Decision should be needs_human"
    assert j['confidence'] == 0.2, "Confidence should reflect uncertainty"
    assert len(j['missing_info']
               ) > 0, "Should include missing info for needs_human"


def test_extract_overtime_high_confidence(tmp_path, monkeypatch):
    """Test POST /extract/overtime returns high confidence auto decision."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(create_minimal_pdf())

    # Mock to return high confidence auto decision
    async def fake_ainvoke_confident(state):
        return {
            "agent_json": {
                "answer": {
                    "summary": "clear overtime rules found",
                    "rules": [{"rule_id": "1", "text": "OT after 40 hours", "confidence": 0.95}]
                }
            },
            "evidence": [{"evidence_id": "e_1", "excerpt": "overtime after 40 hours"}],
            "citations_by_rule": {"0": ["chunk_1"]},
            "confidence": 0.95,
            "decision": "auto",
            "missing_info": [],
        }

    m = importlib.import_module('src.main')
    monkeypatch.setattr(m.workflow, 'ainvoke', fake_ainvoke_confident)

    with open(pdf_path, 'rb') as f:
        files = {'pdf': ('test.pdf', f, 'application/pdf')}
        data = {'question': 'What are the overtime compensation rules?'}
        r = client.post('/extract/overtime', files=files, data=data)

    assert r.status_code == 200
    j = r.json()
    assert j['decision'] == 'auto', "Decision should be auto"
    assert j['confidence'] == 0.95, "Confidence should be high"
    assert len(j['answer']['rules']) > 0, "Should include extracted rules"
    assert len(j['evidence']) > 0, "Should include evidence"


def test_extract_overtime_cache_hit(tmp_path):
    """Test POST /extract/overtime returns cached result for same doc+question."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(create_minimal_pdf())

    # First request - should cache result
    with open(pdf_path, 'rb') as f:
        files = {'pdf': ('test.pdf', f, 'application/pdf')}
        data = {'question': 'What are the overtime compensation rules?'}
        r1 = client.post('/extract/overtime', files=files, data=data)

    assert r1.status_code == 200
    trace_id_1 = r1.json()['trace_id']

    # Second request with same file and question - should hit cache
    with open(pdf_path, 'rb') as f:
        files = {'pdf': ('test.pdf', f, 'application/pdf')}
        data = {'question': 'What are the overtime compensation rules?'}
        r2 = client.post('/extract/overtime', files=files, data=data)

    assert r2.status_code == 200
    j1 = r1.json()
    j2 = r2.json()

    # Results should match (except trace_id which is per-request)
    assert j1['document_id'] == j2['document_id']
    assert j1['answer']['summary'] == j2['answer']['summary']
    assert j1['confidence'] == j2['confidence']
    assert j1['decision'] == j2['decision']


def test_extract_overtime_different_question_no_cache(tmp_path):
    """Test POST /extract/overtime with different question bypasses cache."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(create_minimal_pdf())

    # First request
    with open(pdf_path, 'rb') as f:
        files = {'pdf': ('test.pdf', f, 'application/pdf')}
        data = {'question': 'Question 1?'}
        r1 = client.post('/extract/overtime', files=files, data=data)

    assert r1.status_code == 200
    trace_id_1 = r1.json()['trace_id']

    # Second request with different question - should NOT use cache
    with open(pdf_path, 'rb') as f:
        files = {'pdf': ('test.pdf', f, 'application/pdf')}
        data = {'question': 'Question 2?'}
        r2 = client.post('/extract/overtime', files=files, data=data)

    assert r2.status_code == 200
    j1 = r1.json()
    j2 = r2.json()

    # Trace IDs should be different (different requests)
    assert j1['trace_id'] != j2['trace_id'], "Different questions should produce different trace_ids"
    assert j1['question'] != j2['question'], "Questions should differ"


def test_extract_overtime_password_protected_no_password(tmp_path):
    """Test POST /extract/overtime rejects password-protected PDF without password."""
    pdf_path = tmp_path / "protected.pdf"
    pdf_path.write_bytes(create_password_protected_pdf("secret123"))

    with open(pdf_path, 'rb') as f:
        files = {'pdf': ('protected.pdf', f, 'application/pdf')}
        data = {'question': 'What are the rules?'}
        r = client.post('/extract/overtime', files=files, data=data)

    # Should reject with clear message asking for password
    assert r.status_code == 400
    j = r.json()
    assert 'password' in j['detail'].lower(
    ) or '🔒' in j['detail'], "Should indicate PDF is password protected"


def test_extract_overtime_password_protected_with_password(tmp_path):
    """Test POST /extract/overtime accepts password-protected PDF with correct password."""
    pdf_path = tmp_path / "protected.pdf"
    password = "mypassword123"
    pdf_path.write_bytes(create_password_protected_pdf(password))

    with open(pdf_path, 'rb') as f:
        files = {'pdf': ('protected.pdf', f, 'application/pdf')}
        data = {'question': 'What are the rules?', 'password': password}
        r = client.post('/extract/overtime', files=files, data=data)

    # Should succeed with correct password
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    j = r.json()
    assert 'answer' in j
    assert 'trace_id' in j


def test_extract_overtime_password_protected_wrong_password(tmp_path):
    """Test POST /extract/overtime rejects password-protected PDF with wrong password."""
    pdf_path = tmp_path / "protected.pdf"
    pdf_path.write_bytes(create_password_protected_pdf("correctpassword"))

    with open(pdf_path, 'rb') as f:
        files = {'pdf': ('protected.pdf', f, 'application/pdf')}
        data = {'question': 'What are the rules?', 'password': 'wrongpassword'}
        r = client.post('/extract/overtime', files=files, data=data)

    # Should reject with error message
    assert r.status_code == 400
    j = r.json()
    assert 'password' in j['detail'].lower(
    ) or 'incorrect' in j['detail'].lower(), "Should indicate password error"
