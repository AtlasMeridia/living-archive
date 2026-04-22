"""PDF text extraction for the automated document pipeline.

Uses pypdf (already a dependency) to extract text page-by-page. Modern
Claude models handle 400+ page documents in a single call, so chunking
was removed on 2026-04-21.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

log = logging.getLogger("living_archive")


@dataclass
class ExtractionResult:
    """Result of extracting text from a PDF."""

    total_pages: int = 0
    page_texts: list[str] = field(default_factory=list)
    chars_extracted: int = 0

    @property
    def full_text(self) -> str:
        parts = []
        for i, text in enumerate(self.page_texts, 1):
            parts.append(f"--- Page {i} ---\n{text}")
        return "\n\n".join(parts)

    @property
    def is_empty(self) -> bool:
        return self.chars_extracted == 0


def extract_text(pdf_path: Path) -> ExtractionResult:
    """Extract text from every page of a PDF using pypdf.

    Returns an ExtractionResult with page-level text and total character count.
    Image-only PDFs will return chars_extracted=0 (OCR fallback needed).
    """
    reader = PdfReader(pdf_path)
    page_texts = []
    total_chars = 0

    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        page_texts.append(text)
        total_chars += len(text)

    result = ExtractionResult(
        total_pages=len(reader.pages),
        page_texts=page_texts,
        chars_extracted=total_chars,
    )

    log.debug(
        "Extracted %d chars from %d pages: %s",
        total_chars,
        result.total_pages,
        pdf_path.name,
    )
    return result
