# Phase 3 — Cross-Reference Query Evaluation

**Date:** 2026-03-03
**Status:** Complete

## Gate check

| Criterion | Result |
|---|---|
| At least 2 of 3 person dossiers return relevant, non-noisy results | **Pass — all 3** |

## Person dossiers

### Feng Kuang Liu (father) — 90 documents, 0 photos

**Relevance: Excellent.** Spans 1974–2010+. Includes MS diplomas, tax returns, employment records (BNR/Nortel), immigration docs, trust documents, health records. The chronological spread tells a life story: education → immigration → career → family trust → health decline.

Highlight: 1982 Affidavit of Support for Reiling Peng (his sister-in-law) — a cross-family connection that would be invisible without entity linking.

### Karen Peling Liu (sister) — 38 documents, 0 photos

**Relevance: Good.** Tax returns (listed as dependent), school and music certificates (1983–1988), trust documents. Fewer documents than parents, as expected — she appears mostly as a family member in shared documents rather than as the primary subject.

### Reiling Liao (aunt) — 19 documents, 0 photos

**Relevance: Good.** Immigration sponsorship (1982), trust documents, correspondence. The maiden name resolution (Reiling Peng → Reiling Liao) is working — the 1982 affidavit lists her as "Reiling Peng" and later documents use "Reiling Liao," both correctly mapped.

### Why 0 photos for all dossiers

Expected. Person entities are extracted from document `key_people` only. Photo-person linking requires face cluster naming (the 794 unnamed Immich clusters), which is scoped out per the experiment brief. Documents mention people by name; photos describe people visually ("two men in their 30s") without naming them.

## Date queries

### 1978 — 115 photos, 1 document

**Relevance: Good.** 115 photos from 1978 is a large batch — likely a heavily-photographed year (young family, travel). The single document is a multi-year investment record (1970–1979). The photo descriptions show family scenes: men outdoors, couple with toddler, father holding child.

### 1989 — 8 photos, 18 documents

**Relevance: Excellent.** Documents include home remodeling contracts (Weston Dr.), employment records, and tax returns. Photos show home interiors and travel. The mix of document types paints a picture: home renovation year, established career, family travel.

Date matching correctly handles precision tiers: `1989` (year), `1989-01` (month), `1989-05-06` (day) all included.

## False connection rate

**Zero observed.** All dossier connections are to documents where the person is genuinely named. Date queries return temporally appropriate assets. No spurious links detected.

## Observations

1. **Document-only dossiers are useful but incomplete.** The archive's value is in the photos. Until face clusters are named, person dossiers miss the visual record entirely. This is the single biggest gap.

2. **Date queries bridge documents and photos.** "Show me 1989" returns both tax returns AND family photos — the cross-content connection the synthesis layer was designed to provide.

3. **Query performance is acceptable but not fast.** Building the manifest index takes a few seconds (scanning all manifest files on each query). For dashboard integration, this index should be pre-built or cached.

4. **The person cluster mapping is paying off.** Reiling's maiden→married name resolution, the father's 28 romanization variants — all resolve correctly to single dossiers.
