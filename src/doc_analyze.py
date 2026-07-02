"""Document analysis via Anthropic SDK (Max Plan OAuth)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from . import config
from .inference import create_message, strip_json_fences
from .models import DocumentAnalysis, DocumentInferenceMetadata

log = logging.getLogger("living_archive")


def _build_prompt(source_file: str, page_count: int, text: str) -> str:
    """Format the document analysis prompt with extracted text."""
    template = config.DOC_PROMPT_FILE.read_text()
    return template.format(
        source_file=source_file,
        page_count=page_count,
        text=text,
    )


@config.retry()
def analyze_document(
    text: str,
    source_file: str,
    page_count: int,
) -> tuple[DocumentAnalysis, DocumentInferenceMetadata]:
    """Analyze a document via the Anthropic SDK using Max Plan OAuth credentials."""
    prompt = _build_prompt(source_file, page_count, text)

    log.debug("OAuth SDK: analyzing %s (%d pages)", source_file, page_count)
    response = create_message([{"role": "user", "content": prompt}])

    raw_text = response.content[0].text
    analysis = DocumentAnalysis.model_validate_json(strip_json_fences(raw_text))

    inference = DocumentInferenceMetadata(
        method="auto",
        provider="oauth",
        model=response.model,
        prompt_version=config.DOC_PROMPT_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        estimated_input_tokens=len(text) // 4,
    )
    return analysis, inference
