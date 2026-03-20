# Phase 4 — Embedding Clusters vs. Synthesis Entities

**Date:** 2026-03-11

## K-means (5 clusters)

| Cluster | Size | Top Tags | Interpretation |
|---------|------|----------|---------------|
| 0 | 2 | portrait, outdoor, travel, solo | Solo formal portraits at landmarks |
| 1 | 9 | family, indoor, casual, home | Indoor family scenes on sofas/living rooms |
| 2 | 8 | 1970s, wedding, family, formal | Wedding + formal celebrations |
| 3 | 3 | outdoor, travel, nature, landscape | Landscapes and outdoor scenes |
| 4 | 18 | casual, family, outdoor, travel | Mixed family photos (largest, catch-all) |

K-means discovers **visual/thematic** groupings: weddings cluster together, indoor family scenes cluster together, landscapes cluster together. These cut across eras and people — a 1970s wedding and a 2000s wedding end up in the same cluster.

## HDBSCAN (3 clusters, 29 noise)

More conservative — only finds tight clusters:
- **Cluster 0 (5):** Indoor family photos on sofas/couches — very tight visual similarity
- **Cluster 1 (6):** Wedding photos — ceremonies and portraits
- **29 noise points:** Everything else doesn't form a dense enough cluster

HDBSCAN is more useful for identifying strong visual themes but leaves most photos unclustered at this scale.

## Synthesis Comparison

**Zero overlaps** between embedding clusters and synthesis entity groups.

This is expected and informative:
- **Synthesis entities group by person/date/location** — structured metadata from document analysis
- **Embedding clusters group by visual similarity** — scene type, setting, formality, era

These are complementary axes of organization:
- Synthesis answers: "What documents mention Feng Kang Liu?"
- Embeddings answer: "What photos look like this wedding photo?"

The lack of overlap confirms embeddings discover structure **invisible to metadata**.

## Key Finding

Embedding-based clustering provides a visual taxonomy that structured metadata cannot. The two approaches serve different use cases and should coexist:

| Axis | Source | Example Query |
|------|--------|---------------|
| Person | Synthesis entities | "Show all photos of Grandma Liu" |
| Date | Synthesis timeline | "What happened in 1978?" |
| Visual theme | Embedding clusters | "Photos similar to this wedding" |
| Semantic | Embedding search | "Family gathering outdoors" |
