from fastapi.testclient import TestClient
import src.main as main_mod
import os
import os
import sys
import importlib.util


def load_app_module():
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    pkg_init = os.path.join(base, 'src', '__init__.py')
    if os.path.exists(pkg_init):
        pkg_spec = importlib.util.spec_from_file_location('src', pkg_init)
        pkg = importlib.util.module_from_spec(pkg_spec)
        pkg_spec.loader.exec_module(pkg)
        sys.modules['src'] = pkg

    path = os.path.join(base, 'src', 'main.py')
    spec = importlib.util.spec_from_file_location('src.main', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


main_mod = load_app_module()

client = TestClient(main_mod.app)


def test_genai_client_error_returns_502(monkeypatch):
    # Ensure genai errors module is available
    genai_errors = getattr(main_mod, 'genai_errors', None)
    assert genai_errors is not None, "genai_errors import missing in main module"

    # Create a dummy ClientError instance similar to google.genai.errors.ClientError
    err = genai_errors.ClientError(
        400, {"error": {"message": "API key not valid."}}, None)

    async def raise_client_error(state):
        raise err

    monkeypatch.setattr(main_mod.workflow, 'ainvoke', raise_client_error)

    # post a tiny fake pdf
    files = {'pdf': ('f.pdf', b'%PDF-1.4\n%fakepdf', 'application/pdf')}
    data = {'question': 'What are the overtime compensation rules?'}

    r = client.post('/extract/overtime', files=files, data=data)
    assert r.status_code == 502
    assert 'Google GenAI' in r.json().get('detail', '')
