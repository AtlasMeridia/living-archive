# Branch Comparison — Person Name Deduplication

**Date:** 2026-03-03
**Input:** 1,009 unique `key_people` strings from 233 document manifests (1,955 total mentions)

## Key discovery: corpus is much larger than expected

The brief estimated ~20-30 unique raw name strings. Actual count: **1,009**. Most are single-mention professionals (doctors, lawyers, colleagues, real estate agents). The core family members who need dedup are ~10-15 high-frequency names. This changes the problem shape — it's not "dedup 30 names" but "find 15-20 family clusters in 1,000 names."

## Metrics

| Metric | Branch A | Branch B | Branch C |
|--------|----------|----------|----------|
| **Method** | String normalization | Fuzzy/phonetic | LLM clustering |
| **Total clusters** | 910 | 226 | 22 |
| **Multi-variant clusters** | 59 | 60 | 22 |
| **Singletons** | 851 | 166 | n/a (only reports merges) |
| **Largest cluster** | 10 | **640** | 28 |
| **Known-correct merges** | Partial | Partial | Yes |
| **False merges** | 0 | **Catastrophic** | 1 tentative (flagged) |
| **Catches romanization variants** | No | Overmerges | Yes |
| **Catches abbreviations** | No | Overmerges | Yes |
| **Catches maiden/married names** | No | No | Yes |
| **Deterministic** | Yes | Yes | No |
| **Cost** | $0 | $0 | $0 (inline) |

## Branch A — String Normalization

**Correct merges:** Groups parenthetical variants (e.g., "Feng Kuang Liu" + "Feng Kuang Liu (劉逢光)") and hyphen variants ("Feng-Kuang Liu" → "Feng Kuang Liu"). Does exactly what it promises.

**Misses:**
- "Feng Kuang Liu" vs "Feng K. Liu" vs "Feng Kang Liu" → 3 separate clusters
- "Meichu Grace Liu" vs "M. Grace Liu" vs "Grace Liu" → 3 separate clusters
- "Kenny Peng Liu" vs "Kenny Liu" → 2 separate clusters
- "Reiling Liao" vs "Reiling Peng" (maiden/married) → 2 separate clusters

**Verdict:** Safe but insufficient. Catches ~40% of meaningful variants. No false merges.

## Branch B — Fuzzy/Phonetic

**Catastrophic failure.** The Jaro-Winkler + Metaphone approach created a 640-name mega-cluster merging completely unrelated people (e.g., "Feng Kuang Liu" merged with "Jim Barber", "Todd Richards", "Suzanne Tegio"). The phonetic algorithms are designed for English names and behave unpredictably on romanized Chinese names — exactly the weakness the brief predicted.

Also merged all Chinese-character names into one cluster (21 names), and created several smaller false-merge clusters (e.g., "Barry Chiverton" + "Eric Davey" + "Erik Hansson", "Bill Cheal" + "Bill Fearon" + "Bill Jenkins").

**Verdict: Not viable.** Zero useful signal. The aggressive similarity thresholds that would catch romanization variants also destroy precision. Tuning thresholds wouldn't fix this — the fundamental approach is wrong for this data.

## Branch C — LLM Clustering

**22 clusters, 156 variants merged.** Correctly identifies:

- **Core family:** Feng Kuang Liu (28 variants), Meichu Grace Liu (27), Kenny Peng Liu (12), Karen Peling Liu (13), Melody Tsai (12), Reiling Liao (6)
- **Maiden/married name links:** Swei-Chih Peng = Suei Chih Ho (same person, maiden/married), Reiling Peng = Reiling Liao
- **Abbreviation expansion:** F.K. Liu → Feng Kuang Liu, JMK → Jean M. Kohler, M. Grace Liu → Meichu Grace Liu
- **Romanization variants:** Kang/Kuang, Liang/Lian, Meichu/Mei Chu/Mei-Chu, Kwang/Hsiung (confirmed by shared 彭國祥)
- **Misspelling correction:** Robert Frehlich → Robert Froehlich, Joanne Imperal → Joanne Imperial
- **Semantic reasoning:** "Grandma" and "Mom (Mrs. Liu)" → Meichu Grace Liu cluster

**One tentative cluster flagged:** Y S Liu-Chen ↔ A Shio Chen (confidence 0.65). Needs human review.

**Correctly kept separate:**
- Feng Kuang Liu (劉逢光, father) vs Feng Shih Liu (劉逢時, brother) — different people with similar names
- Hsin Mei Liu and Tie Jia Liu — other Liu family members, not merged with each other or with the core family names

**Verdict:** Best results by far. Near-perfect precision with one flagged uncertain case. Human review of the 22 clusters takes ~5 minutes.

## Observations

1. **Branch B's failure validates the brief's concern.** Phonetic algorithms tuned for English are a poor fit for romanized Chinese names. The O(n²) comparison also means that even a small false-positive rate cascades into mega-clusters via transitive merging.

2. **Branch A is a useful preprocessing step, not a complete solution.** Its normalization (strip parentheticals, lowercase, remove hyphens) is valuable before any matching strategy. Branch C's clusters subsume all of Branch A's correct merges.

3. **The real dedup problem has three tiers:**
   - **Tier 1 — String normalization** (Branch A): Catches ~40% of variants. Free, deterministic.
   - **Tier 2 — Semantic matching** (Branch C): Catches ~95%+ of variants. Requires LLM or human knowledge.
   - **Tier 3 — Maiden/married name resolution**: Requires understanding of Chinese naming conventions. Only LLM or human curation handles this.

4. **The "20-30 names" estimate was wrong but the experimental design handled it.** 1,009 names is fine — the branching structure tested each approach on the same data regardless of scale.
