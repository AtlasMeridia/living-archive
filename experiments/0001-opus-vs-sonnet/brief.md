# Opus 4.6 vs Sonnet 4.6 — Document Analysis Quality & Cost

**Date**: 2026-02-19
**Thread**: pipeline
**Depends on**: Experiment 0000 (pipeline infrastructure, provider abstraction)

## Question

Does Opus 4.6 produce meaningfully better document analysis than Sonnet 4.6 for family archive documents, and is any quality difference worth the additional cost and latency?

Experiment 0000 established Claude CLI (Sonnet) as the recommended provider. But that comparison tested *providers* (Claude vs Codex vs Ollama), not *model tiers* within Claude. Opus 4.6 is the most capable model in the Claude family — it may extract richer metadata, better classify edge-case document types, or produce higher-quality summaries. The question is whether the difference justifies the token cost and slower inference.

## Context

- Experiment 0000 used `DOC_CLI_MODEL=sonnet` for all Claude CLI runs
- The `ClaudeCliProvider` in `src/doc_analyze.py` passes `config.DOC_CLI_MODEL` to `claude --model`
- Switching to Opus requires only `DOC_CLI_MODEL=opus` — no code changes
- Both models are available through the Claude Max plan subscription
- 116 unprocessed documents remain in the Liu Family Trust corpus (1–420 pages, 0.1–250 MB)

## Test Set Design

5 documents selected for diversity across:
- **Page count**: 1–4 pages (small, fast to process)
- **Document type**: legal, financial, medical, personal artifact, sensitive
- **Content complexity**: simple single-purpose docs and mixed-content collections
- **Language**: primarily English with potential Chinese elements

All documents are small enough to avoid chunking, isolating model quality from aggregation behavior.

### Selected Documents

| # | Document | Size | Pages | Type |
|---|----------|------|-------|------|
| 1 | `2010-04-14 Quitclaim Deed.pdf` | 0.3 MB | 2 | Legal (property transfer) |
| 2 | `Artifacts/Countries Visited.pdf` | 0.5 MB | 1 | Personal artifact |
| 3 | `2007-05-10 Will of Feng Kuang Liu.pdf` | 1.5 MB | 4 | Legal (will, sensitive) |
| 4 | `1970-08-29 Investment Record.pdf` | 1.9 MB | 2 | Financial |
| 5 | `Medical/2004-06-16 MEICHU LIU HR Letter.pdf` | 0.6 MB | 1 | Medical/HR |

## Evaluation Criteria

For each document, compare Opus vs Sonnet on:

1. **document_type** — Does one model pick a more accurate category?
2. **date + date_confidence** — Does one extract dates more reliably?
3. **summary_en / summary_zh** — Quality, specificity, factual accuracy
4. **key_people** — Completeness of person extraction
5. **key_dates** — Completeness of date extraction
6. **sensitivity flags** — Any false negatives? Over-flagging?
7. **tags** — Relevance and coverage
8. **Token usage** — input_tokens, output_tokens per document
9. **Latency** — wall-clock time per document

## Success Criteria

- **Minimum**: Both models produce valid manifests for all 5 documents. Usage and latency are recorded.
- **Target**: Side-by-side comparison identifies concrete quality differences (or confirms parity). Token costs are computed per document.
- **Negative result is valid**: If Sonnet matches Opus quality, that's a useful finding — it means we can process the remaining 116 documents at lower cost with confidence.

## Phases

### Phase 0 — Setup ($0)

1. Lock the 5-document test set (paths, SHA-256 hashes, page counts)
2. Extract text from all 5 documents (cached, one-time)
3. Record git revision and model versions

Output: `runs/p0-setup/`

### Phase 1 — Inference (~$0, covered by Max plan)

1. Run all 5 documents through `DOC_CLI_MODEL=sonnet`
2. Run all 5 documents through `DOC_CLI_MODEL=opus`
3. Record per-document: analysis output, token usage, latency

Output: `runs/p1-inference/sonnet/`, `runs/p1-inference/opus/`

### Phase 2 — Comparison

Side-by-side analysis of outputs. Human review of summary quality.

Output: `runs/p2-compare/comparison.md`

## Budget

| Phase | Estimated Cost | Notes |
|-------|---------------|-------|
| P0 | $0 | text extraction only |
| P1 | $0 | covered by Max plan subscription |
| P2 | $0 | analysis only |
| **Total** | **$0** | all inference covered by subscription |

## Rules

1. Same prompt, same schema, same extracted text for both models
2. Text extracted once and cached — models see identical input
3. Record exact model identifiers from CLI response envelopes
4. Document all results inline as they happen
5. No modifications to existing pipeline code — use env var overrides only
