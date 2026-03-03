# Synthesis Layer — Entity Extraction, Cross-Reference, and Timeline

**Date**: 2026-03-03
**Thread**: synthesis
**Depends on**: Catalog v2 (live), manifest schemas (stable), people registry (seeded)

## Question

Can a useful entity graph be derived from existing photo and document manifests, and what extraction rules produce meaningful cross-content connections?

The pipeline already collects rich per-asset metadata — photo dates, people notes, locations, tags; document key_people, key_dates, sensitivity flags, summaries. But nothing connects across assets. This experiment builds the synthesis layer as a **separate, disposable derivation** from manifest data and measures what it actually produces.

## What makes this an experiment

The design doc (`_dev/research/2026-03-03 synthesis-layer.md`) captures architectural decisions. This experiment tests whether those decisions produce useful results against real data:

- Do person names in `key_people` match registry entries, or are they all unresolved?
- Do date entities cluster into meaningful eras, or is it noise?
- Do location strings normalize usefully, or collapse into variants?
- Does cross-referencing actually surface meaningful connections (immigration papers + arrival photos) or just coincidental date overlaps?
- Is the drop-and-rebuild architecture fast enough to iterate comfortably?

These are empirical questions that can only be answered by running the code against the ~316 existing manifests (121 documents + ~195 photos).

## Architecture Constraint

The synthesis layer is **fully decoupled** from the analysis pipeline:

- Own database: `data/synthesis.db` (dropped and rebuilt on every run)
- Own module: `src/synthesis.py` (no imports from pipeline code)
- Reads manifest JSON files directly — manifests are the only contract
- No inline hooks in the analysis pipeline
- Dashboard joins via SQLite `ATTACH DATABASE`

This means every phase can freely change schemas, extraction rules, and normalization logic. The worst case is "delete synthesis.db, try again."

## Input Data

| Content type | Count | Source |
|---|---|---|
| Photo manifests | ~195 | `data/photos/runs/*/manifests/*.json` |
| Document manifests | 121 | `data/documents/runs/*/manifests/*.json` |
| People registry | ~794 entries | `data/people/registry.json` |

Key manifest fields consumed:

**Photos:** `date_estimate`, `date_precision`, `date_confidence`, `location_estimate`, `location_confidence`, `people_count`, `people_notes`, `ocr_text`, `tags`, `description_en`, `description_zh`

**Documents:** `key_people`, `key_dates`, `date`, `date_confidence`, `document_type`, `summary_en`, `summary_zh`, `title`, `sensitivity`

## Evaluation Criteria

Each phase has specific metrics. The experiment succeeds if the entity index produces enough resolved, high-confidence connections to make cross-reference queries useful.

**Entity extraction quality:**
- Person entity resolution rate: what % of `key_people` mentions match a registry entry?
- Date entity distribution: how many per decade? Is coverage sparse or dense?
- Location entity cardinality: how many distinct normalized locations? (Too few = over-collapsed, too many = under-normalized)

**Cross-reference utility:**
- Pick 3 known people from the registry. Does their dossier include the expected photos and documents?
- Pick 2 known dates (e.g., a trust amendment year). Does the date query return both the document AND photos from that era?
- Are there any false connections that would mislead a user?

**Timeline coherence:**
- Does the generated chronology have events across multiple decades?
- Are there gaps that don't match the known archive coverage?
- Is the markdown artifact readable by someone with no context?

## Phases

### Phase 0 — Module Skeleton + Schema ($0)

Build the synthesis module with no extraction logic yet. Verify the infrastructure works.

1. Create `src/synthesis.py` with schema definition, database init, CLI entry point
2. `python -m src.synthesis rebuild` should create an empty `data/synthesis.db`
3. `python -m src.synthesis stats` should report zero entities
4. Verify the module has no imports from pipeline code (`analyze.py`, `catalog.py`, etc.)

Output: `runs/p0-setup/`

**Decision gate:** Empty synthesis.db creates and stats report cleanly.

### Phase 1 — First Entity Extraction ($0)

Build extraction rules and run against all existing manifests. Measure what comes out.

1. Implement person entity extraction from document `key_people` + photo `people_notes`
2. Implement date entity extraction from document `date`/`key_dates` + photo `date_estimate`
3. Implement location entity extraction from photo `location_estimate`
4. Run `rebuild` against all manifests
5. Record: total entities by type, resolution rate for persons, distribution by decade for dates, cardinality for locations

Output: `runs/p1-first-extraction/`
- `entity-stats.json` — counts by type, resolution rates
- `unresolved-persons.txt` — all `_unresolved:` person entities (for debugging name matching)
- `date-distribution.json` — entity count per decade
- `location-inventory.txt` — all normalized location values
- `notes.md` — observations, surprises, issues found

**Decision gate:** Person resolution rate > 50% on document `key_people`. If lower, extraction rules need revision before proceeding.

### Phase 2 — Extraction Refinement ($0)

Iterative. Tune extraction rules based on Phase 1 findings, rebuild, re-measure.

This phase may loop multiple times. Each iteration:
1. Identify the biggest quality issue from current stats
2. Adjust extraction/normalization rules
3. Run `rebuild`
4. Re-measure and record delta

Exit when: person resolution rate is acceptable, date distribution covers known archive range, location cardinality is reasonable (target: 10-30 distinct locations, not 200 variants).

Output: `runs/p2-refinement/`
- `iteration-N.md` per iteration — what changed, before/after metrics

**Decision gate:** Entity quality is good enough to attempt cross-reference queries.

### Phase 3 — Cross-Reference Queries ($0)

Build and test the cross-reference query functions.

1. Implement person dossier query (by name_en, name_zh, or person_id)
2. Implement date range query
3. Implement location query
4. Test with 3 known people, 2 known dates — record results
5. Evaluate: are the connections meaningful or noisy?

Output: `runs/p3-cross-reference/`
- `person-dossier-{name}.json` — sample dossier outputs
- `date-query-{year}.json` — sample date query outputs
- `evaluation.md` — human assessment of connection quality

**Decision gate:** At least 2 of 3 person dossiers return relevant results spanning both photos and documents.

### Phase 4 — Timeline + Chronology ($0)

Build the timeline layer and generate the chronology artifact.

1. Populate `timeline_events` from entity dates + manifest labels
2. Generate `data/chronology.json` + `data/chronology.md`
3. Evaluate: is the chronology readable? Does it span the expected decades?

Output: `runs/p4-timeline/`
- Copy of generated `chronology.json` and `chronology.md`
- `evaluation.md` — is this useful for elders and future generations?

**Decision gate:** Chronology covers at least 3 decades with events in each.

### Phase 5 — Report

Record what worked, what didn't, design decisions that held up vs. needed revision.

Output: `runs/p5-report/summary.md`

Required tables:
- Entity extraction metrics (final): counts, resolution rates, distribution
- Cross-reference evaluation: per-query precision (relevant results / total results)
- Design decision retrospective: which decisions from the design doc held, which changed, why

Verdict per component: `useful`, `needs-work`, or `not-viable`.

## Budget

| Phase | Estimated Cost | Notes |
|-------|---------------|-------|
| P0 | $0 | code only |
| P1-P2 | $0 | local processing, no inference |
| P3-P4 | $0 | SQL queries only |
| P5 | $0 | analysis only |
| **Total** | **$0** | synthesis is pure post-processing, no LLM calls |

## Rules

1. Synthesis module must not import from pipeline code — manifests are the only contract
2. `synthesis.db` is disposable — drop and rebuild is the only schema change mechanism
3. Record extraction metrics after every rebuild, not retroactively
4. Each phase iteration gets its own output directory with dated notes
5. Negative results are valid — if entity extraction produces unusable connections, document why and propose alternatives
6. Do not modify existing manifests or pipeline code during this experiment
7. All cross-reference evaluation includes human review — automated metrics alone can't judge "is this connection meaningful?"
8. Bilingual: person entities must store both name_en and name_zh; chronology must be bilingual with Chinese-first ordering
