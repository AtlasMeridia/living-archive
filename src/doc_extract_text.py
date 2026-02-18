"""PDF text extraction and chunking for the automated document pipeline.

Uses pypdf (already a dependency) to extract text page-by-page.
Large documents are split into page-range chunks for LLM analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

log = logging.getLogger("living_archive")

# Docs under this character count stay as a single chunk
SMALL_DOC_THRESHOLD = 100_000

# Default chunk size in pages (not tokens — simpler, model-agnostic)
DEFAULT_CHUNK_PAGES = 50


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


@dataclass
class TextChunk:
    """A page-range chunk of extracted text for LLM analysis."""

    text: str
    page_start: int  # 1-indexed
    page_end: int  # inclusive
    chunk_index: int
    total_chunks: int


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


def chunk_for_analysis(
    result: ExtractionResult,
    chunk_pages: int = DEFAULT_CHUNK_PAGES,
) -> list[TextChunk]:
    """Split an extraction result into page-range chunks for LLM analysis.

    Small documents (< SMALL_DOC_THRESHOLD chars) stay as a single chunk.
    Large documents are split into chunks of `chunk_pages` pages each.
    """
    full = result.full_text

    if len(full) < SMALL_DOC_THRESHOLD:
        return [
            TextChunk(
                text=full,
                page_start=1,
                page_end=result.total_pages,
                chunk_index=0,
                total_chunks=1,
            )
        ]

    chunks = []
    total_chunks = (result.total_pages + chunk_pages - 1) // chunk_pages

    for i in range(total_chunks):
        start = i * chunk_pages
        end = min(start + chunk_pages, result.total_pages)
        page_slice = result.page_texts[start:end]

        parts = []
        for j, text in enumerate(page_slice, start + 1):
            parts.append(f"--- Page {j} ---\n{text}")
        chunk_text = "\n\n".join(parts)

        chunks.append(
            TextChunk(
                text=chunk_text,
                page_start=start + 1,
                page_end=end,
                chunk_index=i,
                total_chunks=total_chunks,
            )
        )

    log.debug(
        "Split %d pages into %d chunks of ~%d pages",
        result.total_pages,
        total_chunks,
        chunk_pages,
    )
    return chunks
