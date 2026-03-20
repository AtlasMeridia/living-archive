# Phase 1 — Embedding Stats & Cost Projection

**Date:** 2026-03-11

## Results

### What embedded
| Table | Count | Source |
|-------|-------|--------|
| vec_text | 40 | Photo manifest `description_en` |
| vec_documents | 10 | Document manifest `summary_en` |
| vec_images | 0 | NAS not mounted — image files inaccessible |
| **Total** | **50** | All text embeddings succeeded |

### Latency
- Text embeddings: 50 calls, avg ~351ms per call
- Image embeddings: not yet measured (NAS needed)

### What's missing
- 40 image embeddings (photos) — require NAS mount for source TIFF/JPEG files
- PDF direct embeddings (documents) — also on NAS
- When NAS is mounted, re-run with `python -m experiments.0003-multimodal-embeddings.src.embed phase1`

## Cost Projection

Gemini Embedding API is free tier for embedding calls. Based on 50 test calls with zero charges:

| Scenario | Calls | Estimated Cost |
|----------|-------|---------------|
| Test set (50 assets, text only) | 50 | $0 |
| Test set (50 assets, text + image) | 100 | $0 |
| Full corpus (~10,000 photos, text + image) | ~20,000 | <$1 (free tier) |
| Full corpus + documents (~200 docs) | ~20,400 | <$1 (free tier) |

**Verdict:** Cost is not a constraint. Gemini embedding API appears to be free for current usage levels.

## Gate Assessment
- API success rate: 100% (50/50 text embeddings)
- Image embeddings blocked by NAS mount, not API issues
- **Gate: PASSED** (text embeddings work; image embeddings need NAS re-run)
