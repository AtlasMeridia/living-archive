# Experiment 0002 — Final Summary Report

**Date:** 2026-03-04  
**Experiment:** `0002-synthesis-layer`  
**Status:** Phase 0-5 complete (promotion to main `src/` still pending explicit decision)

## 1) Person Dedup Branch Comparison (Final)

Input corpus: 1,009 unique `key_people` strings from 233 document manifests.

| Metric | Branch A | Branch B | Branch C |
|---|---:|---:|---:|
| Method | String normalization | Fuzzy/phonetic | LLM clustering (frozen inline output) |
| Total clusters | 910 | 226 | 22 |
| Multi-variant clusters | 59 | 60 | 22 |
| Singletons | 851 | 166 | n/a |
| Largest cluster size | 10 | 640 | 28 |
| Known-correct merges | Partial | Partial | Yes |
| False merges | 0 | Catastrophic | 1 tentative (flagged) |
| Deterministic at rebuild time | Yes | Yes | Yes (after freeze) |
| Cost | $0 | $0 | $0 (inline artifact) |
| Verdict | `needs-work` | `not-viable` | `useful` |

Decision: Branch C won. Branch A normalization is now used as fallback in resolver logic before unresolved fallback.

## 2) Entity Extraction Metrics (Phase 2 + rebuild with Phase 4)

From `data/synthesis.db` after current rebuild:

| Metric | Value |
|---|---:|
| Total entities | 2,346 |
| Person entities | 826 |
| Date entities | 1,502 |
| Location entities | 18 |
| Entity-asset links | 5,735 |
| Timeline events | 3,012 |
| Unique photos processed | 1,548 |
| Unique documents processed | 121 |

Date-entity decade distribution:
- 1940s: 4
- 1950s: 1
- 1960s: 7
- 1970s: 62
- 1980s: 261
- 1990s: 455
- 2000s: 547
- 2010s: 163
- 2020s: 1
- 2040s: 1 (outlier to investigate)

Entity extraction verdict: `useful`.

## 3) Cross-Reference Evaluation (Precision by Query Type)

### Person dossier query
- Sample size: 3 (`Feng Kuang Liu`, `Karen Peling Liu`, `Reiling Liao`)
- Relevant/non-noisy dossiers: 3/3
- Observed false links: 0
- Observed precision on sample: **1.00**
- Limitation: photo links are currently 0 for dossier samples (face clusters still unnamed)
- Verdict: `useful`

### Date query
- Sample size: 2 years (`1978`, `1989`)
- Relevant/non-noisy query results: 2/2
- Observed false links: 0
- Observed precision on sample: **1.00**
- Verdict: `useful`

### Location query
- Supplemental sample: `Taiwan`, `Italy`
- Output files: `location-query-taiwan.json`, `location-query-italy.json`
- Sample sizes: 484 photos (Taiwan), 68 photos (Italy)
- Heuristic precision check (`location_detail` contains expected location tokens): 484/484 and 68/68
- Manual spot-check: first rows in both outputs are consistent with country assignment
- Verdict: `useful`

Overall cross-reference verdict: `useful` (with person-photo linking still `needs-work`).

## 4) Timeline + Chronology (Phase 4)

Generated artifacts:
- `data/chronology.json`
- `data/chronology.md`
- `runs/p4-timeline/chronology.json`
- `runs/p4-timeline/chronology.md`
- `runs/p4-timeline/evaluation.md`

Output metrics:
- Decades represented: 10 (`1940s` through `2040s`)
- Event groups (date+type grouped): 1,532
- Gate result (>=3 decades with events): **Pass**

Timeline/chronology verdict: `useful`.

## 5) Design Retrospective — Assumptions vs Observed Data

| Design assumption | What data showed | Outcome |
|---|---|---|
| People registry could anchor person matching | Registry entries were unnamed face clusters | Needed document-first person identity build |
| Name dedup problem was small (~20-30) | 1,009 unique strings in corpus | Branch testing still scaled; Branch C required |
| Photo person fields could support person linking | `people_notes` is mostly prose descriptors | Person-photo linking deferred to face naming |
| Phonetic/fuzzy branch might catch romanization variants | Massive over-merging (640-name mega-cluster) | Branch B rejected as `not-viable` |
| Decoupled synthesis layer would enable fast iteration | Schema and extraction logic changed safely across phases | Design held; no pipeline regression risk |
| Batch rebuild model would be acceptable | Rebuild + chronology iteration remained fast and deterministic | Design held |

## 6) Verdict by Component

| Component | Verdict | Note |
|---|---|---|
| Branch A dedup | `needs-work` | Good preprocessing, not sufficient alone |
| Branch B dedup | `not-viable` | Catastrophic false merges |
| Branch C dedup (frozen mapping) | `useful` | Best merge quality; deterministic after freeze |
| Entity extraction | `useful` | Strong counts and broad temporal coverage |
| Cross-reference queries | `useful` | Good person/date/location retrieval on evaluated samples |
| Person-photo linking | `needs-work` | Blocked on face-cluster naming |
| Timeline + chronology | `useful` | Gate passed; some quality cleanup still needed |
| Dashboard integration | `needs-work` | Not yet wired to synthesis outputs |

## 7) Recommendations (Next Steps)

1. Face cluster naming pass (human-led) and mapping into synthesis person entities to unlock photo links in dossiers.
2. Add chronology quality controls:
   - date outlier audit (e.g., 2040s)
   - duplicate-event compaction for repetitive financial/legal documents.
3. Wire synthesis into dashboard with `ATTACH DATABASE`:
   - person dossier endpoint
   - date/location exploration
   - chronology view.
4. Add unresolved-name reconciliation workflow:
   - list unresolved person entities
   - curated merge/update back into `person_clusters.json`.
5. Start personal-branch integration after dashboard wiring:
   - ingest notes/journals
   - reuse same entity/date/timeline derivation path.

## 8) Budget Outcome

Phase costs remained consistent with plan: effectively **~$0**, with Branch C clustering handled through curated inline output and no recurring inference cost in rebuild/chronology paths.
