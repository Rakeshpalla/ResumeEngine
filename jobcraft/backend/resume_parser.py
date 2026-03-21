"""
Resume parser — reads uploaded PDF or DOCX files and extracts plain text.
Supports .pdf (via PyPDF2) and .docx (via python-docx).
"""

from pathlib import Path
from PyPDF2 import PdfReader
from docx import Document


def extract_text_from_pdf(file_path: Path) -> str:
    """Read all pages of a PDF and return combined text."""
    reader = PdfReader(str(file_path))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def extract_text_from_docx(file_path: Path) -> str:
    """Read all paragraphs from a DOCX file and return combined text."""
    doc = Document(str(file_path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def parse_resume(file_path: Path) -> str:
    """
    Auto-detect file type and extract text.
    Raises ValueError if the file type is unsupported.
    """
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(file_path)
    elif suffix == ".docx":
        return extract_text_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}. Only .pdf and .docx are allowed.")
