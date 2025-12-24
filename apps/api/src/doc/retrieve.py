from typing import Any, Dict, List
from .headings import detect_section

def chunk_pages(pages: List[str], max_chars: int = 1400, overlap: int = 200) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    chunk_id = 0
    for page_num in range(1, len(pages)):
        text = pages[page_num] or ""
        i = 0
        while i < len(text):
            part = text[i:i+max_chars]
            chunk_id += 1
            section = detect_section(part)
            chunks.append({
                "chunk_id": f"c{chunk_id:05d}",
                "page": page_num,
                "text": part,
                "section": section,
            })
            i += max_chars - overlap if max_chars > overlap else max_chars
    return chunks

def keyword_retrieve(chunks: List[Dict[str, Any]], question: str, k: int = 8) -> List[Dict[str, Any]]:
    # simple scoring: count keyword hits
    q = question.lower()
    keywords = ["overtime", "overwerk", "toeslag", "compensation", "vergoeding", "hours", "uren"]
    def score(ch: Dict[str, Any]) -> int:
        t = ch["text"].lower()
        return sum(t.count(kw) for kw in keywords) + (2 if any(kw in q for kw in keywords) else 0)
    ranked = sorted(chunks, key=score, reverse=True)
    return [c for c in ranked[:k] if score(c) > 0] or ranked[:min(k, len(ranked))]
