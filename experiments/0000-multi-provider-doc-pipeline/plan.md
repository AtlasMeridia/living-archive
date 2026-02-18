# Plan: Automated Document Pipeline with Multi-Provider LLM Support

## Context

The document pipeline is currently manual — `run_doc_extract.py` prints instructions and a human drives Claude Code through each PDF interactively. The photo pipeline is already automated via Claude CLI subprocess calls. The implementation target is an automated, policy-aware document pipeline that supports Claude CLI, Codex CLI, and Ollama with reproducible comparison outputs.

## Implementation Goals

1. Fully automate document extraction + analysis (`--auto` path).
2. Make provider calls interchangeable under a shared schema contract.
3. Enforce privacy routing and redaction policy before any cloud call.
4. Handle large/image-heavy PDFs through chunking + OCR fallback + aggregation.
5. Produce deterministic experiment artifacts for scoring and replay.

## Files to Create

### 1. `src/doc_extract_text.py`
PDF text extraction with chunking and extraction metadata.

- `extract_text(pdf_path) -> ExtractionResult`
- `chunk_for_analysis(result, chunk_pages=50) -> list[TextChunk]`
- page-range metadata per chunk for evidence tracking

### 2. `src/doc_ocr.py`
OCR fallback for image-only/scanned PDFs.

- `ocr_pdf(pdf_path) -> ExtractionResult`
- return explicit failure state when OCR is unavailable or unsuccessful

### 3. `src/doc_policy.py`
Policy guardrail for provider routing and text redaction.

- classify sensitivity risk from extracted text + manifest hints
- route high-risk raw text to local provider by default
- redact high-risk patterns for non-local providers unless override is logged

### 4. `src/doc_analyze.py`
Provider abstraction and dispatch.

Provider protocol:
```python
class AnalysisProvider(Protocol):
    name: str
    def analyze(self, *, text: str, source_file: str, page_count: int, chunk_range: str | None = None) -> tuple[DocumentAnalysis, DocumentInferenceMetadata]
```

Providers:
- `ClaudeCliProvider`
- `CodexCliProvider` (locked contract: `--output-schema` + `--output-last-message`)
- `OllamaProvider` (OpenAI-compatible endpoint)

Shared behavior:
- prompt build from pre-extracted text
- JSON schema derived from `DocumentAnalysis`
- retry wrapper via `@config.retry()`
- chunk aggregation pass that synthesizes a final document-level analysis from chunk-level outputs

### 5. `prompts/document_analysis_v2.txt`
Prompt adapted for pre-extracted text and chunk context.

### 6. `tests/test_doc_extract_text.py`
Extraction + chunking behavior tests.

### 7. `tests/test_doc_analyze.py`
Provider output parsing and schema validation tests (mocked subprocess/API).

### 8. `tests/test_doc_manifest.py`
Manifest write/load validation and inference metadata assertions.

## Files to Modify

### 9. `src/config.py`
Add provider/policy settings and provider-specific validation:

- `DOC_PROVIDER` (`claude-cli | codex | ollama`)
- provider binary/model/timeout config
- redaction/policy toggle config
- retryable exception coverage for OpenAI-compatible client errors

### 10. `src/models.py`
Extend `DocumentInferenceMetadata`:

- `model`
- `input_tokens`
- `output_tokens`
- `chunk_count`
- `provider`

### 11. `src/doc_manifest.py`
Make document manifest writes provider-agnostic and schema-validated:

- accept full `inference` payload instead of hardcoded method
- validate manifest against `DocumentManifest` before write
- include run-level method/provider in `write_run_meta()`

### 12. `src/doc_scan.py`
Add incremental scan optimization:

- optional hash cache keyed by `(path, size, mtime)`
- avoid full SHA recomputation for unchanged files

### 13. `src/run_doc_extract.py`
Add `--auto` mode and end-to-end automated flow:

1. preflight + config/policy validation
2. discover work and skip already-processed docs
3. extract text
4. if empty text: OCR fallback
5. write extracted text artifact immediately
6. chunk for analysis as needed
7. apply routing/redaction policy per chunk/provider
8. analyze chunks
9. aggregate final document analysis
10. write manifest + run metadata
11. non-zero exit if failures

### 14. `.env.example`
Add provider and policy env vars.

### 15. `pyproject.toml`
Add optional dependency for OpenAI-compatible Ollama client path.

## Output Contract (Locked)

- Claude: parse `structured_output` from JSON envelope.
- Codex: parse final message from `--output-last-message` JSON file (single canonical path).
- Ollama: parse structured JSON from OpenAI-compatible response.
- Every provider output must pass `DocumentAnalysis` validation before manifest write.

## Aggregation Strategy (Large Docs)

1. Run chunk-level analysis with page ranges.
2. Produce lightweight chunk evidence records.
3. Run a final aggregation pass over chunk outputs to produce:
   - final `document_type`
   - final `title`
   - merged `key_people`, `key_dates`, `tags`
   - conservative `sensitivity` (OR flags)
   - best-supported `date` + `date_confidence`

## Safety/Privacy Strategy

- High-risk raw text defaults to local-only analysis.
- Non-local providers receive redacted text unless an override is explicitly configured and logged.
- Evaluation reporting includes sensitivity false-negative counts by provider.

## Implementation Order

1. `src/doc_extract_text.py`
2. `src/doc_ocr.py`
3. `src/models.py`
4. `src/config.py`
5. `src/doc_policy.py`
6. `src/doc_manifest.py`
7. `prompts/document_analysis_v2.txt`
8. `src/doc_analyze.py`
9. `src/run_doc_extract.py`
10. `src/doc_scan.py` hash cache
11. tests (`test_doc_extract_text.py`, `test_doc_analyze.py`, `test_doc_manifest.py`)
12. `.env.example` + `pyproject.toml`

## Verification

```bash
# Unit tests for new document pipeline modules
pytest tests/test_doc_extract_text.py tests/test_doc_analyze.py tests/test_doc_manifest.py -q

# Smoke: local provider with one text PDF
DOC_PROVIDER=ollama python -m src.run_doc_extract --auto --new-run

# Smoke: CLI provider with locked output contract
DOC_PROVIDER=claude-cli python -m src.run_doc_extract --auto --new-run
DOC_PROVIDER=codex CODEX_MODEL=codex-5.3 python -m src.run_doc_extract --auto --new-run

# Validate schema on produced manifests
python -c "import json,glob; from src.models import DocumentManifest; [DocumentManifest(**json.load(open(p))) for p in glob.glob('*/manifests/*.json')]"
```

## Experiment Artifacts to Produce

- `runs/p1-build/notes.md`
- `runs/p2-compare/scores.json`
- `runs/p2-compare/safety-metrics.json`
- `runs/p2-compare/comparison.md`

## Done Criteria

1. Automated `--auto` flow runs end-to-end without manual intervention.
2. Structured output contract is stable for all providers.
3. All manifests validate against Pydantic schema.
4. Sensitivity false negatives are explicitly measured and reported.
5. Provider comparison outputs are reproducible from locked artifacts.
