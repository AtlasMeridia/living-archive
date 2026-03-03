# Synthesis Layer — Entity Extraction, Cross-Reference, and Timeline

**Date**: 2026-03-03
**Thread**: synthesis
**Depends on**: Catalog v2 (live), manifest schemas (stable), people registry (structure exists but unpopulated)

## Question

Can a useful entity graph be derived from existing photo and document manifests, and what extraction rules produce meaningful cross-content connections?

## What makes this an experiment

The design doc (`_dev/research/2026-03-03 synthesis-layer.md`) captured architectural decisions assuming certain data conditions. Data reconnaissance revealed the assumptions don't hold:

1. **The people registry is empty.** All 794 entries are unnamed face clusters from Immich. The design's "match key_people against registry" strategy has nothing to match against. The experiment must BUILD person identity from document mentions, not look it up.

2. **Person names are inconsistent across documents.** The same person appears as "Feng Kang Liu", "Feng Kuang Liu", and "Feng-Kuang Liu" — romanization variants, not typos. Deduplication is the core challenge.

3. **Photo `people_notes` is prose, not names.** It's "elderly woman in blue dress, approximately 50s" — not "Grandma Liu." Person-to-photo linking from manifests alone is nearly impossible. The real link will come from face cluster naming (a separate effort).

These discoveries turn the experiment from "build a known thing, see if it works" into "test three competing approaches to the hardest sub-problem (person dedup) and pick the winner empirically."

## Architecture Constraint

The synthesis layer is **fully decoupled** from the analysis pipeline:

- Own database: `data/synthesis.db` (dropped and rebuilt on every run)
- Own module: `src/synthesis.py` (no imports from pipeline code)
- Reads manifest JSON files directly — manifests are the only contract
- No inline hooks in the analysis pipeline
- Dashboard joins via SQLite `ATTACH DATABASE`

This means every phase can freely change schemas, extraction rules, and normalization logic. Branching is cheap — swap the matching function, run rebuild, compare stats.

## Input Data

| Content type | Count | Source |
|---|---|---|
| Photo manifests | ~195 | `data/photos/runs/*/manifests/*.json` |
| Document manifests | 121 | `data/documents/runs/*/manifests/*.json` |
| People registry | 794 entries (all unnamed) | `data/people/registry.json` |

Key manifest fields consumed:

**Photos:** `date_estimate`, `date_precision`, `date_confidence`, `location_estimate`, `location_confidence`, `people_count`, `people_notes`, `ocr_text`, `tags`, `description_en`, `description_zh`

**Documents:** `key_people`, `key_dates`, `date`, `date_confidence`, `document_type`, `summary_en`, `summary_zh`, `title`, `sensitivity`

### Data shape observations (from recon)

**Document `key_people`:** Romanized Chinese names in Western order (given-name surname). Same person appears with 3-4 spelling variants. Partial names present ("Dr. Li", "R. Cummings"). No Chinese characters in this field. ~20-30 unique raw name strings across the corpus.

**Document `key_dates`:** Consistently ISO format (`YYYY-MM-DD` or `YYYY-MM`). Clean, no normalization needed.

**Photo `people_notes`:** Free prose visual descriptions. Names appear in ~20-30% of photos, only when physically visible in the image (cake writing, banners, tombstone inscriptions). Not a reliable person-identification source.

**Photo `location_estimate`:** Free text, highly variable specificity. Ranges from "Glacier Bay National Park, Alaska, USA" to "Cruise ship interior." Country-level extraction is feasible; finer granularity is unreliable.

**Photo `date_estimate`:** Two tiers — high-confidence ISO dates from visible stamps (`YYYY-MM-DD`, 0.95+) and year-only estimates from style inference (`YYYY`, 0.4-0.6).

## Branched Decision: Person Name Deduplication

This is the experiment's central empirical question. Three approaches, tested on the same data:

### Branch A — String Normalization

Deterministic rules: lowercase, strip hyphens, collapse whitespace, normalize common patterns (e.g., "Liu-Chen" → "liu chen"). Group by exact normalized string.

**Strengths:** Fast, predictable, reproducible, zero cost.
**Weakness:** Won't catch romanization variants ("Kang" vs "Kuang"). These are different strings and will produce separate entities.

### Branch B — Fuzzy/Phonetic Matching

String normalization (Branch A) plus phonetic similarity (Soundex, Metaphone, or similar). Group names that normalize differently but sound similar.

**Strengths:** Catches "Feng Kang Liu" / "Feng Kuang Liu" as the same person. Handles common romanization inconsistencies.
**Weakness:** Risk of false positives (merging genuinely different people whose names sound similar). Phonetic algorithms are tuned for English — may behave unpredictably on romanized Chinese names.

### Branch C — LLM-Assisted Clustering

Extract all unique `key_people` strings from document manifests. Feed them to Claude in one call: "These names appear across a family archive. Group names that likely refer to the same person. Return clusters." Apply clusters as the dedup mapping.

**Strengths:** Understands romanization context ("Kang" and "Kuang" are both valid romanizations of 光). Can use semantic cues ("Meichu Grace Liu" and "MeiChu Liu" are clearly the same person). Handles partial names with reasoning.
**Weakness:** Non-deterministic (different calls may produce different clusters). Costs one LLM call (~$0, covered by Max plan but breaks the "pure post-processing" ideal). Requires human review of clusters before adoption.

### Branch Comparison Metrics

Run all three on the same `key_people` corpus. For each branch, record:

| Metric | What it measures |
|---|---|
| Cluster count | How many distinct "people" did this approach identify? |
| Largest cluster | How many name variants map to the most-referenced person? |
| Singleton count | How many names couldn't be grouped with anything? |
| Known-correct merges | Did it correctly merge known variants (e.g., "Feng Kang Liu" + "Feng Kuang Liu")? |
| False merges | Did it incorrectly merge two different people? |
| Human review time | How long does it take a human to verify/correct the clusters? |

**Winner criteria:** Highest correct merges, zero false merges (or easily caught false merges). If LLM clustering produces perfect results with minimal review, it wins despite being non-deterministic. If string normalization catches 80%+ of variants, it wins on simplicity.

## Scoped-Out Decisions

### Photo-person linking

**Status:** Deferred. Documented as a known limitation.

Person-to-photo linking requires face cluster naming (the 794 unnamed Immich clusters). This is a human-intensive process (elders identifying faces) that's independent of the synthesis layer. Once face clusters are named, person entities in the synthesis layer can link to photos via `immich_person_ids` → face cluster → photo asset. This experiment focuses on document-to-person linking only.

### Location normalization (advanced)

**Status:** Simple country-level extraction only, no branching.

Extract country names from `location_estimate` using pattern matching for known countries. Store as location entities. Don't attempt hierarchical decomposition (country > region > city > setting) — the free-text format is too inconsistent, and the useful query at current scale is "show me all Taiwan photos" not "show me all Taipei photos."

### Narrative generation

**Status:** Out of scope. The experiment builds data infrastructure (entities, timeline), not stories.

## Evaluation Criteria

**Entity extraction quality:**
- Person dedup accuracy: measured per-branch (see branch comparison metrics above)
- Date entity distribution: how many per decade? Does coverage match known archive range?
- Location entity cardinality: how many distinct countries? (Target: 3-10, matching the family's actual geography)

**Cross-reference utility (tested with winning person branch):**
- Pick 3 people who appear in multiple documents. Does their dossier return all expected documents?
- Pick 2 known dates. Does the date query return relevant documents AND photos from that era?
- False connection rate: connections that would mislead a user

**Timeline coherence:**
- Does the generated chronology span the expected decades (1970s–2020s)?
- Is the markdown artifact readable by someone with no context?

## Phases

### Phase 0 — Module Skeleton ($0)

Build the synthesis module with no extraction logic yet.

1. Create `src/synthesis.py` with schema definition, database init, CLI entry point
2. `python -m src.synthesis rebuild` creates an empty `data/synthesis.db`
3. `python -m src.synthesis stats` reports zero entities
4. Verify: no imports from pipeline code (`analyze.py`, `catalog.py`, etc.)

Output: `runs/p0-setup/`

**Gate:** Empty synthesis.db creates and stats report cleanly.

### Phase 1 — Person Dedup Branch Comparison ($0)

The core branching phase. Build all three person matching strategies, run each against the full document manifest corpus.

1. Extract all unique `key_people` strings from all document manifests
2. Implement Branch A (string normalization), Branch B (fuzzy/phonetic), Branch C (LLM clustering)
3. Run each branch independently — produce person clusters
4. Record metrics per branch (see branch comparison table above)
5. Human review: verify clusters against known family knowledge

Output: `runs/p1-person-branches/`
- `raw-names.txt` — all unique `key_people` strings extracted
- `branch-a-clusters.json` — string normalization result
- `branch-b-clusters.json` — fuzzy/phonetic result
- `branch-c-clusters.json` — LLM clustering result
- `comparison.md` — side-by-side metrics and human assessment
- `winner.md` — which branch was selected and why

**Gate:** One branch produces usable person clusters with zero false merges (or false merges easily caught in review). If no branch is acceptable, the experiment pauses for redesign.

### Phase 2 — Full Entity Extraction ($0)

Using the winning person dedup strategy from Phase 1, build the complete extraction pipeline.

1. Integrate winning person matcher into rebuild
2. Add date entity extraction (documents: `date` + `key_dates`; photos: `date_estimate`)
3. Add location entity extraction (photos: country-level from `location_estimate`)
4. Run full `rebuild` against all manifests
5. Record: entity counts by type, date distribution by decade, location inventory

Output: `runs/p2-extraction/`
- `entity-stats.json` — counts by type
- `date-distribution.json` — entity count per decade
- `location-inventory.txt` — all location entities
- `notes.md` — observations, adjustments needed

**Gate:** Entity counts are reasonable (not 0, not 10,000). Date distribution spans multiple decades.

### Phase 3 — Cross-Reference Queries ($0)

Build and test cross-reference query functions against the populated synthesis.db.

1. Implement person dossier query (by name or person cluster ID)
2. Implement date range query
3. Implement location query
4. Test with 3 known people, 2 known dates
5. Evaluate: meaningful connections or noise?

Output: `runs/p3-cross-reference/`
- `person-dossier-{name}.json` — sample outputs
- `date-query-{year}.json` — sample outputs
- `evaluation.md` — human assessment of connection quality

**Gate:** At least 2 of 3 person dossiers return relevant, non-noisy results.

### Phase 4 — Timeline + Chronology ($0)

Build the timeline layer and generate the chronology artifact.

1. Populate `timeline_events` from entity dates + manifest labels (description_en/summary_en)
2. Generate `data/chronology.json` + `data/chronology.md` (bilingual, Chinese-first)
3. Evaluate: readable? Spans expected decades? Useful for elders?

Output: `runs/p4-timeline/`
- Copy of generated `chronology.json` and `chronology.md`
- `evaluation.md`

**Gate:** Chronology covers at least 3 decades with events in each.

### Phase 5 — Report

What worked, what didn't, which design decisions held up.

Output: `runs/p5-report/summary.md`

Required:
- Person dedup branch comparison (final table with all metrics)
- Entity extraction metrics (counts, distribution)
- Cross-reference evaluation (precision per query type)
- Design decision retrospective: what the design doc assumed vs. what the data showed
- Recommendations for next steps (face cluster naming, personal branch integration, dashboard wiring)

Verdict per component: `useful`, `needs-work`, or `not-viable`.

## Budget

| Phase | Estimated Cost | Notes |
|-------|---------------|-------|
| P0 | $0 | code only |
| P1 | ~$0 | Branches A+B are free; Branch C uses one LLM call (Max plan) |
| P2-P4 | $0 | local processing, SQL queries |
| P5 | $0 | analysis only |
| **Total** | **~$0** | one LLM call for Branch C, everything else is post-processing |

## Rules

1. Synthesis module must not import from pipeline code — manifests are the only contract
2. `synthesis.db` is disposable — drop and rebuild on every run
3. Record metrics after every rebuild
4. Each branch and phase iteration gets its own output directory
5. Negative results are valid — document why and propose alternatives
6. Do not modify existing manifests or pipeline code
7. Cross-reference evaluation includes human review
8. Bilingual: person entities store both name_en and name_zh when available; chronology is bilingual with Chinese-first
9. Branch comparison must be on identical input data — extract raw names once, feed to all three strategies
10. LLM clustering output (Branch C) must be human-reviewed before adoption — don't auto-trust the clusters
