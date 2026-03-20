# Phase 3 — Dimensionality & Performance

**Date:** 2026-03-11

## Top-1 Agreement

9/10 queries return the same top-1 result across all three dimensions. The only disagreement is "Chinese New Year" where 768d picks a slightly different image.

| Query | 3072 dist | 1536 dist | 768 dist | Same top-1? |
|-------|-----------|-----------|----------|-------------|
| family dinner | 0.5862 | 0.5859 | 0.5691 | Y |
| wedding ceremony | 0.6061 | 0.6038 | 0.5898 | Y |
| children playing outdoors | 0.6844 | 0.6809 | 0.6675 | Y |
| formal portrait | 0.6313 | 0.6296 | 0.6166 | Y |
| Taiwan landscape | 0.6579 | 0.6567 | 0.6393 | Y |
| grandmother with grandchildren | 0.5836 | 0.5878 | 0.5746 | Y |
| Chinese New Year | 0.6619 | 0.6649 | 0.6523 | N |
| old faded 1970s photograph | 0.5932 | 0.5898 | 0.5788 | Y |
| legal document | 0.7068 | 0.7056 | 0.6903 | Y |
| three generations together | 0.5598 | 0.5588 | 0.5495 | Y |

## Search Latency

| Dimension | Avg latency | Relative |
|-----------|-------------|----------|
| 3072 | 4.5ms | 1.0x |
| 1536 | 2.2ms | 2.0x faster |
| 768 | 1.0ms | 4.5x faster |

All well under the 100ms threshold, even at 3072.

## Storage Projection (10,000 photos)

| Dimension | Per-vector | 10k vectors | With text + doc |
|-----------|------------|-------------|-----------------|
| 3072 | 12,288 B | 117.2 MB | ~235 MB |
| 1536 | 6,144 B | 58.6 MB | ~117 MB |
| 768 | 3,072 B | 29.3 MB | ~59 MB |

## Assessment

**768d is viable for production.** 90% top-1 agreement with 3072d, 4.5x faster search, 4x smaller storage. The quality retention far exceeds the 80% threshold.

**1536d is nearly identical to 3072d.** 90% agreement (same as 768d on this test set), 2x faster. The small improvement over 768d may not justify the doubled storage.

**Recommendation:** Use 768d for production search, store 3072d only for re-ranking or future experiments.
