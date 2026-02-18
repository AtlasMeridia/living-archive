# Phase 1 — Build Infrastructure Notes

**Date**: 2026-02-18

## Files Created

- `src/doc_extract_text.py` — PDF text extraction via pypdf + page-range chunking
- `src/doc_analyze.py` — Multi-provider LLM dispatch (Claude CLI, Codex CLI, Ollama)
- `prompts/document_analysis_v2.txt` — Prompt for pre-extracted text (v1 assumed LLM reads PDF)

## Files Modified

- `src/models.py` — Added `provider`, `model`, `input_tokens`, `output_tokens`, `chunk_count` to `DocumentInferenceMetadata`
- `src/config.py` — Added `DOC_PROVIDER`, `DOC_CLI_MODEL`, `DOC_TIMEOUT`, `CODEX_CLI`, `CODEX_MODEL`, `OLLAMA_URL`, `OLLAMA_MODEL`; updated `validate_doc_config()` with provider checks; added openai retry exceptions
- `src/doc_manifest.py` — Parameterized `inference` dict in `write_manifest()` and `method`/`provider` in `write_run_meta()`
- `src/run_doc_extract.py` — Added `--auto` flag and `auto_extract()` function
- `.env.example` — Added provider config vars
- `pyproject.toml` — Added `ollama = ["openai>=1.0"]` optional dependency

## Implementation Decisions

1. **Text extraction**: pypdf `extract_text()` per page. Page-delimited output with `--- Page N ---` markers. Image-only PDFs return `chars_extracted=0` and are skipped (OCR fallback deferred to Phase 3).

2. **Chunking**: Page-based, not token-based. Default 50 pages/chunk. Docs under 100K chars stay as single chunk. Simpler and model-agnostic.

3. **Provider abstraction**: Duck-typed Protocol class. Each provider implements `analyze(text, source_file, page_count) -> (DocumentAnalysis, DocumentInferenceMetadata)`. Factory via `get_provider()`.

4. **OpenAI strict schema**: Pydantic `model_json_schema()` doesn't produce OpenAI-compatible schemas. Added `_make_openai_strict()` to recursively add `additionalProperties: false`, set `required` to all property keys, and remove `default` values. Required for both Codex CLI and Ollama json_schema mode.

5. **Claude nested session fix**: Claude CLI fails with "cannot be launched inside another Claude Code session" when CLAUDECODE env var is set. Fixed by filtering it from subprocess env.

6. **Chunk aggregation**: Union for set fields (people, dates, tags), OR for sensitivity flags, highest-confidence date, first chunk's type/title, concatenated summaries, summed tokens.

## Smoke Test Results (4-page Will of Feng Kuang Liu)

| Provider | doc_type | Date | SSN | FIN | MED | Time |
|----------|----------|------|-----|-----|-----|------|
| Claude CLI (sonnet) | legal/will | 2007-05-10 | F | F | F | 18.5s |
| Codex CLI | legal/will | 2007-05-10 | F | T | F | 17.2s |
| Ollama (qwen3:32b) | legal/will | 2007-05-10 | F | F | F | 76.8s |

All produce valid `DocumentAnalysis` objects. Codex flagged `has_financial: true` (debatable — will references trust property).

## Decision Gate

**PASS**: Pipeline runs end-to-end on a text PDF with valid manifests for all three providers. OCR path deferred (scanned PDFs have some pypdf-extracted text, enough for initial comparison). Ready for Phase 2.
