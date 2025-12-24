import hashlib
import json
import time
from pathlib import Path
from typing import Optional, Callable

CACHE_DIR = Path('.cache')
CHUNK_SUMMARY_DIR = CACHE_DIR / 'chunk_summaries'
QUERY_CACHE_DIR = CACHE_DIR / 'queries'
_TTL_DEFAULT = 60 * 60 * 24  # 1 day

for p in (CACHE_DIR, CHUNK_SUMMARY_DIR, QUERY_CACHE_DIR):
    p.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    tmp.replace(path)


def _read_json(path: Path) -> Optional[dict]:
    try:
        with path.open('r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _hash_text(text: bytes) -> str:
    return hashlib.sha256(text).hexdigest()


def get_query_cache(document_hash: str, question_hash: str) -> Optional[dict]:
    key = f"{document_hash}_{question_hash}.json"
    p = QUERY_CACHE_DIR / key
    meta = _read_json(p)
    if not meta:
        return None
    if meta.get('ts') and time.time() - meta['ts'] > meta.get('ttl', _TTL_DEFAULT):
        try:
            p.unlink()
        except Exception:
            pass
        return None
    return meta.get('value')


def set_query_cache(document_hash: str, question_hash: str, value: dict, ttl: int = _TTL_DEFAULT) -> None:
    key = f"{document_hash}_{question_hash}.json"
    p = QUERY_CACHE_DIR / key
    _write_json(p, {'ts': time.time(), 'ttl': ttl, 'value': value})


def get_chunk_summary(document_id: str, chunk_id: str) -> Optional[str]:
    safe_doc = hashlib.sha1(document_id.encode('utf-8')).hexdigest()
    key = f"{safe_doc}_{chunk_id}.json"
    p = CHUNK_SUMMARY_DIR / key
    meta = _read_json(p)
    if not meta:
        return None
    return meta.get('summary')


def set_chunk_summary(document_id: str, chunk_id: str, summary: str) -> None:
    safe_doc = hashlib.sha1(document_id.encode('utf-8')).hexdigest()
    key = f"{safe_doc}_{chunk_id}.json"
    p = CHUNK_SUMMARY_DIR / key
    _write_json(p, {'ts': time.time(), 'summary': summary})


def compute_summary_if_missing(document_id: str, chunk_id: str, text: str, summarizer: Optional[Callable[[str], str]] = None) -> str:
    """Return cached summary or compute one using summarizer (or fallback simple truncation)."""
    s = get_chunk_summary(document_id, chunk_id)
    if s:
        return s
    if summarizer:
        s = summarizer(text)
    else:
        # naive summarizer: first 300 chars, prefer sentence boundary
        s = (text or '').strip()
        if len(s) > 300:
            # cut at last period before cutoff
            cut = s.rfind('.', 0, 300)
            if cut > 50:
                s = s[:cut+1]
            else:
                s = s[:300]
    set_chunk_summary(document_id, chunk_id, s)
    return s


def doc_hash_from_bytes(b: bytes) -> str:
    return _hash_text(b)


def question_hash(q: str) -> str:
    return hashlib.sha1(q.strip().lower().encode('utf-8')).hexdigest()
