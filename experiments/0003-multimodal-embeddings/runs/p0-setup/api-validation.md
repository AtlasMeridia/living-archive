# Phase 0 — API Validation

**Date:** 2026-03-11

## Results

### sqlite-vec
- Loads successfully via `apsw` (macOS Python compiled with `OMIT_LOAD_EXTENSION`, so stdlib `sqlite3` cannot load extensions)
- vec0 virtual tables create, insert, and KNN search all work
- Cosine distance metric confirmed

### Gemini Embedding API
- Model: `gemini-embedding-2-preview` (was `gemini-embedding-exp-03-07` in plan — renamed)
- API key validated via `.env`
- Text embedding: 3072 dimensions, ~440ms latency
- Image embedding: 3072 dimensions, ~725ms latency
- Both return float32 vectors

### embeddings.db
- Schema created with all 6 tables (embedded_assets + 5 vec0 tables)
- Empty, ready for Phase 1

### Test Set
- 50 assets curated from catalog.db (40 photos + 10 documents)
- Distribution across 7 photo slices + 10 document types
- Locked to `runs/p0-setup/locked-inputs.json`
- Source files on NAS — require mount for Phase 1

## Notes

- `apsw` added as dependency (not in original plan) due to macOS sqlite3 extension limitation
- Model name updated from plan: `gemini-embedding-2-preview` is the current multimodal embedding model
- `gemini-embedding-001` also available but not multimodal

## Gate: PASSED
- sqlite-vec works (via apsw)
- Gemini API returns 3072-dim vectors for both text and image
