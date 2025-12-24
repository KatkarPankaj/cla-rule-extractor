import os
import importlib.util
from fastapi.testclient import TestClient
import pytest


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
    assert r.json() == {"ok": True}


# To test /extract/overtime without network calls we monkeypatch the workflow.ainvoke
@pytest.fixture(autouse=True)
def patch_workflow(monkeypatch):
    class DummyResult(dict):
        pass

    async def fake_ainvoke(state):
        # Return a structure matching the RunResponse expected fields
        return {
            "agent_json": {"answer": {"summary": "ok", "rules": []}},
            "evidence": [],
            "citations_by_rule": {},
            "confidence": 0.5,
            "decision": "auto",
            "missing_info": [],
        }

    import importlib
    m = importlib.import_module('src.main')
    monkeypatch.setattr(m.workflow, 'ainvoke', fake_ainvoke)
    # Patch nodes.ingest_node's dependency so we don't need a real PDF file for tests
    import importlib
    nodes_mod = importlib.import_module('src.graph.nodes')
    monkeypatch.setattr(nodes_mod, 'extract_pages',
                        lambda b: ["", "dummy page text"])
    # Patch the ADK agent run_text to return a valid JSON payload
    import json as _json

    async def fake_run_text(prompt):
        return _json.dumps({
            "answer": {"summary": "ok", "rules": []},
            "citations_by_rule": {},
            "confidence": 0.5,
            "decision": "auto",
            "missing_info": [],
        })

    monkeypatch.setattr(nodes_mod._agent, 'run_text', fake_run_text)
    yield


def test_extract_overtime(tmp_path):
    # create a tiny fake PDF file (not a real pdf but enough for the ingest stub)
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%fakepdf")

    with open(pdf_path, 'rb') as f:
        files = {'pdf': ('test.pdf', f, 'application/pdf')}
        data = {'question': 'What are the overtime compensation rules?'}
        r = client.post('/extract/overtime', files=files, data=data)

    assert r.status_code == 200, r.text
    j = r.json()
    assert j['document_id'] == 'test.pdf'
    assert 'answer' in j
    assert isinstance(j['answer']['summary'], str)
