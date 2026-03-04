# Winner: Branch C — LLM-Assisted Clustering

**Date:** 2026-03-03

## Decision

Branch C wins. Branch A is adopted as a preprocessing step within the Branch C workflow.

## Why

- **Branch B is eliminated.** Catastrophic false merges (640-name mega-cluster). The phonetic matching approach is fundamentally unsuited for romanized Chinese names.
- **Branch A is safe but insufficient.** Catches only string-level variants (parentheticals, hyphens, case). Misses the hard cases: abbreviations (F.K. → Feng Kuang), romanization variants (Kang ↔ Kuang), maiden/married name links (Peng ↔ Liao).
- **Branch C catches everything Branch A catches, plus abbreviations, romanization variants, maiden/married names, misspellings, and semantic references** (Grandma → Meichu Grace Liu). One low-confidence cluster flagged for human review.

## Implementation for Phase 2

The winning strategy for the synthesis layer rebuild:

1. **Static cluster mapping.** Branch C's output becomes a JSON lookup table (`person_clusters.json`) checked into the experiment directory. The rebuild process loads this table and uses it to normalize `key_people` entries to canonical person entities.

2. **No live LLM calls during rebuild.** The clustering is a one-time curation step. When new documents are added and new names appear, the clusters are re-evaluated (manually or with another LLM call) and the mapping is updated. This preserves the "pure post-processing" ideal — rebuilds are deterministic and free.

3. **Branch A normalization as preprocessing.** Before looking up the cluster mapping, normalize the input string using Branch A's rules (strip parentheticals, lowercase, remove hyphens). This handles future variants that match existing clusters without needing to enumerate every possible annotation.

4. **Human review required.** The Y S Liu-Chen ↔ A Shio Chen cluster (confidence 0.65) needs verification. Additionally, the "Kenny Liu's father (deceased)" and "Kenny Liu's stepmother" entries in the Kenny cluster are relational references, not identity matches — they should be handled differently in extraction.

5. **Reproducibility path is explicit.** `branch_c.py` supports `--mode inline` (default, from curated `branch-c-inline-clusters.json`) and `--mode anthropic` (fresh API clustering). Inline mode matches the original experiment run and keeps rebuild deterministic.

## Risks accepted

- **Non-deterministic origin.** The clusters were produced by LLM reasoning. Different runs might produce slightly different groupings. Mitigated by freezing the output as a static mapping.
- **New names require re-curation.** Future document batches may introduce new name variants not in the mapping. These will be flagged as unresolved until the mapping is updated.
