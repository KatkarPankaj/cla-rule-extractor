import json
import time
from pathlib import Path
from typing import Any, Dict

AUDIT_PATH = Path("audit_log.jsonl")


def write_audit(event: Dict[str, Any]) -> Dict[str, Any]:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    event = {**event, "ts": time.time()}
    with AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return {"ok": True}
