import re
from typing import Optional

ARTICLE_RE = re.compile(r"\b(Article|Artikel)\s+(\d+(\.\d+)*)\b", re.IGNORECASE)

def detect_section(text: str) -> Optional[str]:
    # naive: find first Article/Artikel mention in chunk
    m = ARTICLE_RE.search(text)
    if not m:
        return None
    return f"Article {m.group(2)}"
