# Multi-Provider Document Pipeline — Feasibility Study

**Date**: 2026-02-16
**Thread**: pipeline
**Template**: feasibility-study (adapted from character-corpus)

## Question

Can the manual document extraction pipeline be fully automated using CLI-based LLM providers (Claude Code, Codex), and which provider produces the best classification quality for family archive documents without violating safety and privacy constraints?

## Context

The living-archive photo pipeline is already automated: `run_slice.py` calls Claude Code CLI via subprocess, gets structured JSON back, and writes manifests. The document pipeline is manual — `run_doc_extract.py` prints instructions and a human drives Claude Code through each PDF interactively.

The project has access to three inference backends:
- **Claude Code CLI** (`~/.local/bin/claude`) — Max plan subscription, proven on photos
- **Codex CLI** (`codex`) v0.101.0 — OpenAI Pro subscription, untested for this workload
- **Ollama** (`localhost:11434`) — local qwen3:32b, free but lower quality ceiling

Both CLIs support non-interactive mode with JSON schema enforcement:
- Claude: `-p "prompt" --output-format json --json-schema '{...}'`
- Codex: `exec "prompt" --json --output-schema schema.json --output-last-message out.json`

The document corpus is 72 PDFs (Liu Family Trust), 468 total pages, previously processed manually. A second batch of 44 medium/large docs (21-420 pages) is queued and hits context limits, requiring chunking and aggregation.

## Existing Assets

| Asset | Location | Notes |
|-------|----------|-------|
| Photo CLI dispatch | `src/analyze.py` | Proven subprocess pattern to replicate |
| Document orchestrator | `src/run_doc_extract.py` | Manual mode, add `--auto` |
| Document manifest I/O | `src/doc_manifest.py` | Atomic writes, catalog integration |
| PDF scanner | `src/doc_scan.py` | Discovery, hashing, page counting (pypdf) |
| Pydantic models | `src/models.py` | `DocumentAnalysis`, `DocumentManifest` schemas |
| Analysis prompt | `prompts/document_analysis_v1.txt` | Classification template with JSON schema |
| Config + retry | `src/config.py` | Env vars, paths, exponential backoff decorator |
| Existing manifests | NAS `Documents/_ai-layer/runs/` | 72 docs from manual run (baseline source) |

## Execution Preconditions

- NAS mounted at `/Volumes/MNEME/` (auto-mount via `preflight.py`)
- Claude Code CLI authenticated (Max plan)
- Codex CLI authenticated (`codex login`)
- Ollama running (`ollama serve`)
- No modifications to existing manifests from prior manual runs
- All run artifacts stay under `experiments/0000-multi-provider-doc-pipeline/runs/`
- Privacy routing policy is locked before inference:
  - Default: high-sensitivity raw text is local-only (Ollama)
  - Cloud providers receive only redacted text unless an explicit override is logged

## Success Criteria

- **Minimum**: Automated pipeline runs end-to-end on at least 5 documents, producing manifests that validate against `DocumentManifest`
- **Target**: All three providers produce valid manifests on the locked comparison set; quality and safety metrics are computed against adjudicated baseline labels
- **Stretch**: Provider comparison reveals a clear quality/speed winner; chunking + aggregation + OCR fallback handles the 44 large docs; pipeline is production-ready
- **Negative result is valid** if documented with evidence (for example: unreliable structured output, unacceptable sensitivity false negatives, or low multilingual summary quality)

## Reproducibility Lock

Phase 0 must produce lock files before any automated inference:

- `runs/p0-recon/revision.txt`: `git rev-parse HEAD`
- `runs/p0-recon/locked-inputs.json`: exact PDF paths and SHA-256 hashes for test set
- `runs/p0-recon/eval-config.json`: fixed prompt version, models, timeout, chunk size, redaction mode, aggregation strategy
- `runs/p0-recon/ground-truth.json`: adjudicated labels for evaluation fields
- `runs/p0-recon/cli-versions.json`: exact Claude/Codex/Ollama versions and invocation contract

Once written, these files are immutable. If a lock must change, document the reason in `runs/p0-recon/deviations.md`.

## Locked Evaluation Protocol

- **Unit of analysis**: per-document manifest
- **Test set**: 18 documents from the existing 72, stratified by page count and content:
  - 3 small (<5 pages)
  - 8 medium (5-50 pages)
  - 5 large (50+ pages)
  - 2 non-English dominant
- **Baseline labels**: human-adjudicated for `document_type` and `sensitivity`, with reviewer notes for disputed cases
- **Comparison method**:
  - `document_type`: exact match (primary quality metric)
  - `date` + `date_confidence`: normalized exact/within-range match
  - `sensitivity` flags: precision/recall plus explicit false-negative count
  - `summary_en` / `summary_zh`: qualitative review rubric
  - `key_people` / `key_dates`: set overlap
  - `tags`: set overlap
  - Runtime: average and P95 time per document
- **Quality gates**:
  - `document_type` exact match >= 80%
  - Sensitivity false negatives = 0 on locked test set
  - Manifest schema validation success = 100%

## Phases

### Phase 0 — Recon + Protocol Lock ($0)

Research only. No automated inference on evaluation set.

1. Verify provider structured-output contracts
   - Confirm Claude CLI schema-constrained output on smoke prompt
   - Confirm Codex CLI schema-constrained output using locked output file path
   - Confirm Ollama structured JSON path is stable
   - output: `runs/p0-recon/cli-verification.md`, `runs/p0-recon/cli-versions.json`

2. Select and adjudicate test documents
   - Build stratified 18-doc sample with page counts and language mix
   - Record SHA-256, page counts, source paths
   - Produce adjudicated labels for safety-critical fields
   - output: `runs/p0-recon/locked-inputs.json`, `runs/p0-recon/ground-truth.json`

3. Lock evaluation and privacy policy
   - Prompt version, model names, timeout, chunk size
   - Redaction and provider-routing policy
   - output: `runs/p0-recon/eval-config.json`, `runs/p0-recon/revision.txt`

**Decision gate**: Stop if any provider cannot reliably produce schema-valid structured output with the locked contract.

### Phase 1 — Build Infrastructure ($0)

Implement the pipeline code. Use local inference for initial plumbing checks when possible.

1. `src/doc_extract_text.py` — extraction + chunking
2. OCR fallback path for image-only PDFs (or explicit `ocr_required` failure state)
3. `src/doc_analyze.py` — provider abstraction (Claude, Codex, Ollama)
4. Chunk aggregation pass (do not rely on first chunk only)
5. Config/model/manifest updates (provider metadata, token counts, schema validation)
6. `src/run_doc_extract.py` — `--auto` wiring with policy-aware routing
7. Tests for extraction, provider parsing, manifest validation

output: `runs/p1-build/notes.md` (implementation decisions, code references)

**Decision gate**: Pipeline runs end-to-end on one text PDF and one scanned PDF (OCR path) with valid manifests.

### Phase 2 — Provider Comparison (~$0, covered by subscriptions)

Run locked test set through providers with policy constraints.

1. Run test set through Claude CLI
   - output: `runs/p2-compare/claude/` (manifests + timing + errors)

2. Run test set through Codex CLI
   - output: `runs/p2-compare/codex/` (manifests + timing + errors)

3. Run test set through Ollama (qwen3:32b)
   - output: `runs/p2-compare/ollama/` (manifests + timing + errors)

4. Compare all providers against locked baseline
   - output: `runs/p2-compare/comparison.md`, `runs/p2-compare/scores.json`, `runs/p2-compare/safety-metrics.json`

**Decision gate**:
- Proceed only if provider meets quality gates (`doc_type >= 80%`, zero sensitivity false negatives)
- If no provider is viable, close experiment with evidence

### Phase 3 — Production Run (conditional)

Run winning provider(s) on remaining unprocessed documents.

1. Process queued documents with chunking + OCR fallback + aggregation
2. Validate all manifests against Pydantic schema
3. Validate output manifests load into FTS5 index
4. Update `catalog.db`

output: `runs/p3-production/`

**Decision gate**: Schema validation passes for all manifests and FTS5 index build completes without errors.

### Phase 4 — Report

- `runs/p4-report/summary.md`

Required comparison table:

| Provider | doc_type Match | Sensitivity Recall | Sensitivity FN | Date Match | Avg Time/Doc | Notes |
|----------|----------------|--------------------|----------------|------------|--------------|-------|
| Claude CLI | ? | ? | ? | ? | ? | |
| Codex CLI | ? | ? | ? | ? | ? | |
| Ollama (qwen3:32b) | ? | ? | ? | ? | ? | |
| Baseline (adjudicated) | baseline | baseline | baseline | baseline | — | |

Verdict: `viable`, `conditionally-viable`, or `not-viable` per provider.

## Budget

| Phase | Estimated Cost | Notes |
|-------|---------------|-------|
| P0 | $0 | research only |
| P1 | $0 | code + local smoke checks |
| P2 | $0 | covered by Max + Pro subscriptions |
| P3 | $0 | covered by subscriptions |
| P4 | $0 | analysis only |
| **Total cap** | **$0** | all inference covered by existing subscriptions |

## Rules

1. Recon before inference — verify provider contracts before building comparisons
2. Lock protocol before comparison — same inputs, prompt, and metrics across providers
3. Privacy-first routing — high-sensitivity raw text local-only unless deviation is logged
4. Controlled comparison — same evaluation method for every provider run
5. Preserve existing manifests — outputs stay in experiment runs, never overwrite prior manual results
6. Log exact commands, versions, and deviations in each phase's `notes.md`
7. Document results inline as they happen, not retroactively
8. Negative results are valid and must be recorded with evidence
9. Atomic file writes — manifests and lock artifacts use temp-file + rename semantics
