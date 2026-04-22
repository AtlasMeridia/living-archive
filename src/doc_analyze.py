"""Document analysis via Anthropic SDK (Max Plan OAuth)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from . import config
from .models import DocumentAnalysis, DocumentInferenceMetadata, Sensitivity

log = logging.getLogger("living_archive")


def _build_prompt(source_file: str, page_count: int, text: str) -> str:
    """Format the document analysis prompt with extracted text."""
    template = config.DOC_PROMPT_FILE.read_text()
    return template.format(
        source_file=source_file,
        page_count=page_count,
        text=text,
    )


def _strip_json_fences(text: str) -> str:
    """Strip markdown code fences from a JSON response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text


@config.retry()
def analyze_document(
    text: str,
    source_file: str,
    page_count: int,
) -> tuple[DocumentAnalysis, DocumentInferenceMetadata]:
    """Analyze a document via the Anthropic SDK using Max Plan OAuth credentials."""
    from .auth import get_client, is_oauth, OAUTH_SYSTEM_PREFIX

    client = get_client()
    prompt = _build_prompt(source_file, page_count, text)

    kwargs = {}
    if is_oauth():
        kwargs["system"] = OAUTH_SYSTEM_PREFIX

    log.debug("OAuth SDK: analyzing %s (%d pages)", source_file, page_count)
    response = client.messages.create(
        model=config.OAUTH_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )

    raw_text = response.content[0].text
    analysis = DocumentAnalysis.model_validate_json(_strip_json_fences(raw_text))

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


def merge_chunk_analyses(
    analyses: list[tuple[DocumentAnalysis, DocumentInferenceMetadata]],
) -> tuple[DocumentAnalysis, DocumentInferenceMetadata]:
    """Merge analyses from multiple chunks of the same document.

    Strategy:
    - document_type, title, language, quality: from first chunk
    - date: highest confidence across chunks
    - summaries: concatenated
    - key_people, key_dates, tags: union (order-preserving)
    - sensitivity: OR across all chunks (conservative — any True wins)
    - tokens: summed
    """
    if len(analyses) == 1:
        return analyses[0]

    first_analysis = analyses[0][0]
    first_inference = analyses[0][1]

    best_date = first_analysis.date
    best_date_conf = first_analysis.date_confidence
    for a, _ in analyses[1:]:
        if a.date_confidence > best_date_conf:
            best_date = a.date
            best_date_conf = a.date_confidence

    def _union_lists(*lists: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for lst in lists:
            for item in lst:
                if item not in seen:
                    seen.add(item)
                    result.append(item)
        return result

    all_people = _union_lists(*(a.key_people for a, _ in analyses))
    all_dates = _union_lists(*(a.key_dates for a, _ in analyses))
    all_tags = _union_lists(*(a.tags for a, _ in analyses))

    merged_sensitivity = Sensitivity(
        has_ssn=any(a.sensitivity.has_ssn for a, _ in analyses),
        has_financial=any(a.sensitivity.has_financial for a, _ in analyses),
        has_medical=any(a.sensitivity.has_medical for a, _ in analyses),
    )

    en_parts = [a.summary_en for a, _ in analyses if a.summary_en]
    zh_parts = [a.summary_zh for a, _ in analyses if a.summary_zh]

    merged_analysis = DocumentAnalysis(
        document_type=first_analysis.document_type,
        title=first_analysis.title,
        date=best_date,
        date_confidence=best_date_conf,
        summary_en=" ".join(en_parts),
        summary_zh="".join(zh_parts),
        key_people=all_people,
        key_dates=all_dates,
        sensitivity=merged_sensitivity,
        tags=all_tags,
        language=first_analysis.language,
        quality=first_analysis.quality,
    )

    total_input = sum(inf.input_tokens for _, inf in analyses)
    total_output = sum(inf.output_tokens for _, inf in analyses)

    merged_inference = DocumentInferenceMetadata(
        method=first_inference.method,
        provider=first_inference.provider,
        model=first_inference.model,
        prompt_version=first_inference.prompt_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_tokens=total_input,
        output_tokens=total_output,
        chunk_count=len(analyses),
    )

    return merged_analysis, merged_inference
