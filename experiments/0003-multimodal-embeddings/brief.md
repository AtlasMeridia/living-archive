# Multimodal Embeddings — Gemini Embedding 2

**Date**: 2026-03-11
**Thread**: search
**Depends on**: Catalog v2 (live), manifest schemas (stable), NAS mount (read-only source files)

## Question

Can Gemini Embedding 2's natively multimodal embedding model enable useful semantic search and cross-modal discovery across archival family photos and documents?

## What makes this an experiment

Living Archive currently has no semantic or visual search. Every asset requires expensive Claude Vision analysis before it becomes searchable. Cross-modal connections only exist through the synthesis layer's entity extraction — which requires both items to be fully analyzed first. With 10,000+ photos still unprocessed, this is a bottleneck.

Gemini Embedding 2 maps text, images, and PDFs into a single 3,072-dim vector space. If it works well on archival family photos (old scans, faded, mixed quality), it could enable:

1. **Instant semantic search** across the entire archive, including unanalyzed photos
2. **Cross-modal discovery** — search text to find photos, or use a photo to find related documents
3. **Embedding-based clustering** that discovers structure invisible to structured metadata

The unknowns:
- How well do old, faded scanned photos embed compared to modern digital photos?
- Is the cross-modal alignment strong enough to find relevant photos from text queries?
- Do Matryoshka dimensions (768, 1536) retain enough quality for production use?
- How does embedding-based discovery compare to the synthesis layer's entity linking?

## Architecture Constraint

Fully self-contained under `experiments/0003-multimodal-embeddings/`. No imports from `src/`. Manifests, catalog.db, and NAS files are the contract boundary. Own database: `embeddings.db`.

Image preparation (TIFF→JPEG, resize) is reimplemented locally (~20 lines) rather than importing from `src/convert.py`.

### Experiment-local code

```
experiments/0003-multimodal-embeddings/
├── brief.md
├── manifest.json
├── src/
│   ├── config.py       # env vars, paths, model name, defaults
│   ├── embed.py        # Gemini API client, embed image/text/pdf
│   ├── vecdb.py        # sqlite-vec DB init, insert, KNN search
│   ├── test_set.py     # curate test set from catalog.db
│   ├── evaluate.py     # precision@k, nDCG, relevance scoring
│   └── cluster.py      # HDBSCAN/k-means clustering
└── runs/               # phase outputs
```

**Invocation** from project root:
```
python -m experiments.0003-multimodal-embeddings.src.embed phase1
python -m experiments.0003-multimodal-embeddings.src.evaluate phase2
```

## Input Data

### Test Set (50 assets)

**Photos (40):** Selected across era, subject, and quality diversity:
- 5 from 1978 scans (1970s era, TIFFs)
- 5 from 1980-1982 scans
- 10 from Wedding album (single-event consistency)
- 5 from Big_Red_Album (diverse subjects)
- 5 from Pink_Flower_Album
- 5 from 2022 Swei Chi (recent scans, different family branch)
- 5 from assorted albums (mixed eras)

**Documents (10):** Selected for cross-modal overlap with photo test set:
- 2 legal/trust, 2 financial, 1 letter, 1 certificate, 1 medical, 1 deed, 1 employment, 1 memorial
- Prioritize documents whose `key_people` overlap with people visible in photo test set

Selection via read-only queries against `catalog.db`.

## Dependencies

```
pip install google-genai sqlite-vec numpy scikit-learn
```

- `google-genai` — Gemini API client for embeddings
- `sqlite-vec` — Vector search extension for SQLite
- `numpy` — Vector serialization for sqlite-vec
- `scikit-learn` — Phase 4 clustering only

`GOOGLE_API_KEY` env var required.

## Phases

### Phase 0 — Setup & API Validation ($0)

1. Install dependencies, validate `GOOGLE_API_KEY`
2. One test text embedding, one test image embedding (not from archive)
3. Confirm: API returns 3072-dim vectors
4. Create `embeddings.db` with schema, verify sqlite-vec loads
5. Curate test set from `catalog.db`, write `locked-inputs.json`
6. Validate NAS mount and source file accessibility

**Output:** `runs/p0-setup/` — `api-validation.md`, `locked-inputs.json`, `dependencies.txt`
**Gate:** sqlite-vec works, Gemini API returns vectors for both text and image

### Phase 1 — Embed Test Set (~$0.01)

1. Image embeddings: JPEG (convert TIFF if needed, resize ≤2048px) → `vec_images`
2. Text embeddings: manifest descriptions → `vec_text`
3. Document embeddings: PDF direct or extracted text → `vec_documents`
4. Record per-asset: latency, tokens, success/failure
5. Cost projection for full corpus

**Output:** `runs/p1-embed/` — `embed-stats.json`, `cost-projection.md`
**Gate:** ≥90% success rate. Full corpus cost <$5.

### Phase 2 — Retrieval Quality ($0)

10 text queries embedded and searched against `vec_images`. Image-to-image similarity. Cross-modal retrieval. Synthesis comparison.

**Output:** `runs/p2-retrieval/` — result JSONs + `evaluation.md`
**Gate:** Text-to-image precision@5 ≥ 0.4 average

### Phase 3 — Dimensionality & Performance (~$0.01)

Re-embed at 768 and 1536 dimensions. Compare precision, storage, latency.

**Output:** `runs/p3-dimensions/` — `dimension-comparison.json`, `storage-benchmarks.md`
**Gate:** None (informational)

### Phase 4 — Embedding Clusters vs. Synthesis Entities ($0)

HDBSCAN/k-means on image embeddings. Compare against synthesis entity groupings.

**Output:** `runs/p4-clusters/` — `cluster-analysis.json`, `cluster-vs-synthesis.md`
**Gate:** None (exploratory)

### Phase 5 — Report ($0)

**Output:** `runs/p5-report/summary.md`

## Success Criteria

| Metric | Threshold |
|--------|-----------|
| API success rate | ≥90% |
| Cost per photo embedding | <$0.001 |
| Full corpus cost projection | <$5 |
| Text-to-image precision@5 | ≥0.4 avg |
| 768-dim quality retention | ≥80% of 3072 precision |
| 1536-dim quality retention | ≥90% of 3072 precision |
| KNN query latency (3072) | <100ms on test set |

Negative results are valid.

## Budget

| Phase | Estimated Cost |
|-------|---------------|
| P0 | $0 |
| P1 | ~$0.01 |
| P2 | ~$0 (10 query embeddings) |
| P3 | ~$0.01 |
| P4-P5 | $0 |
| **Total** | **<$0.05** |

## Rules

1. All code in `experiments/0003-multimodal-embeddings/src/`, not in `src/`
2. No imports from pipeline code — manifests and catalog.db are the contract
3. `embeddings.db` is disposable — drop and rebuild freely
4. Record metrics after every embedding batch
5. Phase outputs in `runs/pN-name/`
6. Negative results are valid — document and close
7. Do not modify manifests, catalog.db, or source files
8. Human relevance judgment required for Phase 2 evaluation
9. Test set is locked after Phase 0 — no cherry-picking
