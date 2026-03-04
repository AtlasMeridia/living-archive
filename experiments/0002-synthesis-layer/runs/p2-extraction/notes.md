# Phase 2 — Full Entity Extraction

**Date:** 2026-03-03
**Status:** Complete

## Metrics

| Entity type | Count |
|---|---|
| Person | 826 |
| Date | 1,502 |
| Location | 18 |
| **Total** | **2,346** |
| Entity-asset links | 5,735 |

- 10 person entities have `family_role` (from cluster metadata)
- 816 person entities are unresolved (single-mention professionals, friends, etc.)

## Gate check

| Criterion | Result |
|---|---|
| Entity counts reasonable (not 0, not 10,000) | Pass — 2,346 entities |
| Date distribution spans multiple decades | Pass — 1940s through 2020s |
| Location cardinality matches family geography | Pass — 18 countries, US + Taiwan dominant |

## Person entities

Top 6 are core family members — person cluster mapping working correctly:

| Person | Documents |
|---|---|
| Feng Kuang Liu (father) | 90 |
| Meichu Grace Liu (mother) | 64 |
| Kenny Peng Liu (self) | 45 |
| Karen Peling Liu (sister) | 38 |
| Melody Tsai (stepmother) | 26 |
| Reiling Liao (aunt) | 19 |

Professionals follow: Jean M. Kohler (16), Rebeccah B. Miller (15), Robert A. Froehlich (14).

## Date distribution

Heavy concentration in 1980s–2000s, matching the family's US residency period:

- 1940s: 4 (birth-era documents)
- 1970s: 62 (early family photos)
- 1980s: 261 (immigration era)
- 1990s: 455 (peak document/photo period)
- 2000s: 547 (most documented decade)
- 2010s: 163

**Anomaly:** 1 date in 2040s — likely a data error in a manifest. Worth investigating.

## Location entities

18 countries. Top 3 match expected family geography:
1. United States (594 photos)
2. Taiwan (484 photos)
3. Italy (68 photos — travel)

## Implementation notes

- **Manifest dedup:** 2,358 photo files → 1,548 unique assets (by sha256). 233 doc files → 121 unique. Latest manifest per sha256 wins.
- **Person resolution:** 152 variant strings map to 21 clusters via frozen person_clusters.json. All other names become unresolved singleton entities.
- **Location extraction:** Country-level pattern matching on photo `location_estimate`. 18 countries found. No location entities from documents (scoped out per brief).
- **No timeline events yet** — that's Phase 4.
