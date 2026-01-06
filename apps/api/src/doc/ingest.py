from pypdf import PdfReader
from typing import List
import io


def extract_pages(pdf_bytes: bytes, password: str = None) -> List[str]:
    """Extract pages from PDF bytes.

    Args:
        pdf_bytes: PDF file content as bytes
        password: Optional password for encrypted PDFs

    Returns:
        List of page text, padded so page 1 is at index 1
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if reader.is_encrypted:
        if not password:
            raise ValueError(
                "PDF is password protected but no password provided")
        decrypt_result = reader.decrypt(password)
        if decrypt_result == 0:
            raise ValueError("Incorrect password")

    pages = [""]  # pad so page 1 is index 1
    for p in reader.pages:
        pages.append(p.extract_text() or "")
    return pages


def extract_pages_from_path(path: str, password: str = None) -> List[str]:
    """Extract pages from a PDF file on disk without loading whole file into memory.

    Args:
        path: Path to PDF file
        password: Optional password for encrypted PDFs

    Returns:
        List of page text, padded so page 1 is at index 1
    """
    reader = PdfReader(path)
    if reader.is_encrypted:
        if not password:
            raise ValueError(
                "PDF is password protected but no password provided")
        decrypt_result = reader.decrypt(password)
        if decrypt_result == 0:
            raise ValueError("Incorrect password")

    pages = [""]
    for p in reader.pages:
        pages.append(p.extract_text() or "")
    return pages
