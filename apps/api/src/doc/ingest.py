from pypdf import PdfReader
from typing import List
import io


def extract_pages(pdf_bytes: bytes) -> List[str]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = [""]  # pad so page 1 is index 1
    for p in reader.pages:
        pages.append(p.extract_text() or "")
    return pages
