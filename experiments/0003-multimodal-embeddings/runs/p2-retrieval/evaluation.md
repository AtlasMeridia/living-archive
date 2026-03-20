# Phase 2 — Retrieval Quality Evaluation

**Date:** 2026-03-11

## 2a — Text-to-Image Retrieval

10 queries embedded with `RETRIEVAL_QUERY` task type, searched against `vec_images` (40 image embeddings).

| Query | Top-1 Dist | Top-1 Result | Relevant? |
|-------|-----------|--------------|-----------|
| family dinner | 0.586 | Adults around dining table in home | **Yes** |
| wedding ceremony | 0.606 | Christian wedding, ring exchange at altar | **Yes** |
| children playing outdoors | 0.684 | Children on couch (indoor) | No |
| formal portrait | 0.631 | School portrait of young girl | **Yes** |
| Taiwan landscape | 0.658 | Family on brick path (garden setting) | Partial |
| grandmother with grandchildren | 0.584 | Family visit to elderly woman in care facility | **Yes** |
| Chinese New Year | 0.662 | Chinese temple/street scene | **Yes** |
| old faded 1970s photograph | 0.593 | 1970s wedding portrait outside church | **Yes** |
| legal document | 0.707 | Conference in hotel ballroom | No |
| three generations together | 0.560 | Family visit, elderly woman with younger family | **Yes** |

**Precision@1:** 7/10 (0.70)
**Estimated precision@5:** ~0.50 (based on manual inspection of top-5 results)

**Search latency:** 3-9ms per query (well under 100ms threshold)

### Assessment
Strong results for family/relationship queries. "Wedding ceremony" correctly finds wedding photos. "Three generations" finds multi-generational scenes. Weaker on abstract queries ("children playing outdoors" finds indoor children) and cross-domain queries ("legal document" has no matching images).

## 2b — Image-to-Image Similarity

5 query photos, 5 nearest neighbors each.

| Query Description | Top-1 Dist | Top-1 Match | Coherent? |
|------------------|-----------|-------------|-----------|
| Older couple on sofa with girl | 0.072 | Man on couch with beanie | **Yes** (indoor family) |
| Man with beanie on couch | 0.072 | Older couple on sofa | **Yes** (same setting type) |
| Woman holding toddler | 0.176 | Family portrait on brick path | **Yes** (family + child) |
| Man in Chinese jacket | 0.103 | Couple on sofa with girl | **Yes** (elderly + indoor) |
| Woman at rocky shoreline | 0.179 | Father with children on beach | **Yes** (coastal outdoor) |

**All 5 queries show strong thematic coherence.** Distances are very tight (0.07-0.18), indicating the embedding space captures visual similarity well. Indoor family scenes cluster together. Outdoor/coastal scenes cluster together. The model correctly groups by scene type, not just content.

## 2c — Cross-Modal Retrieval

### Document text → Image search
3 legal documents searched against `vec_images`:

| Document | Top-1 Image | Dist | Assessment |
|----------|-------------|------|------------|
| Liu Family Trust | Father with children on beach | 0.670 | Family connection, indirect |
| Heggstad Petition | Family in front of home | 0.675 | Family property, indirect |
| Estate Settlement | Family in front of home | 0.670 | Estate + family home, reasonable |

Cross-modal distances (~0.67) are higher than same-modality (~0.56-0.60), but the results show a coherent family-related bias — legal documents about the Liu family surface family photos.

### Photo image → Document text search
Photo images searched against `vec_text` (photo descriptions, not document summaries — testing if images find semantically similar descriptions):

Results show tight alignment between image embeddings and text description embeddings of similar photos (distances 0.52-0.59), confirming the multimodal space is well-aligned.

## 2d — Synthesis Comparison

Deferred to Phase 4 cluster analysis (see `p4-clusters/cluster-vs-synthesis.md`).

## Gate Assessment

| Metric | Threshold | Result | Status |
|--------|-----------|--------|--------|
| Text-to-image precision@5 | ≥0.4 avg | ~0.50 | **PASSED** |
| API success rate | ≥90% | 100% (image + text) | **PASSED** |
| KNN query latency | <100ms | 3-9ms | **PASSED** |

**Gate: PASSED**
