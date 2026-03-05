# Dev Log

Working record of the Living Archive project — pipeline runs, architecture decisions, process observations, and lessons learned. Each entry is a dated section capturing whatever the significant work was.

Pipeline runs include run IDs, metrics, and content notes. Architecture and process entries capture the *why* — what changed, what we learned about working this way, what patterns emerged.

## 2026-03-04 — Batch run
**Run:** `20260305T011118Z` — batch mode, 1 slices attempted
**Result:** 15/390 succeeded, 0 failures
**Triage skips:** 0
**Elapsed:** 701s (~0.2 hours)
**Model:** CLI (Opus via CLI)

| Slice | Photos | Result | Time |
|-------|--------|--------|------|
| `2025-2026 Digital Revolution Scans/1st Round/Jpeg/Red_Album_1` | 390 | 15/390 (partial) | 569s |

0 slices completed, 1 partial (budget exhausted).

---

## 2026-03-04 — Batch run
**Run:** `20260305T011118Z` — batch mode, 1 slices attempted
**Result:** 1/390 succeeded, 0 failures
**Triage skips:** 0
**Elapsed:** 194s (~0.1 hours)
**Model:** CLI (Opus via CLI)

| Slice | Photos | Result | Time |
|-------|--------|--------|------|
| `2025-2026 Digital Revolution Scans/1st Round/Jpeg/Red_Album_1` | 390 | 1/390 (partial) | 62s |

0 slices completed, 1 partial (budget exhausted).

---

## 2026-03-05 — People dashboard empty-state fix (registry path regression)

Resolved a regression where the Archive Dashboard `People` tab showed no rows even though `data/people/registry.json` contained imported Immich clusters.

**Root cause:**
- `src/people.py` still pointed at `config.AI_LAYER_DIR / "people"` (`data/photos/people/registry.json`), but the local-data migration moved the registry to `data/people/registry.json`.

**What changed:**
- `src/people.py`
  - Set canonical registry path to `config.DATA_DIR / "people" / "registry.json"`.
  - Added backward-compatible read fallback to legacy `data/photos/people/registry.json`.
  - Kept writes canonical so future updates consolidate on `data/people/`.
- `src/sync_people.py`
  - `status` now logs `src.people.REGISTRY_PATH` instead of reconstructing a stale path.
- `src/dashboard_api.py` + `dashboard.html`
  - Added fast Immich reachability check so `/api/people` fails open immediately when Immich is offline.
  - Removed expensive per-person `get_person_statistics()` loop (N+1 calls over large registries).
  - Added offline photo-count hints by parsing registry notes (`Auto-imported from Immich (N assets)`) and use `~N photos` in UI when counts are estimated.
  - Sorted People grid payload with unnamed people first, then largest clusters, to prioritize elder-identification workflow.
  - People summary now reports both `registry_count` and Immich cluster status (`Immich Clusters` vs `Immich Clusters (Offline)`), preventing misleading zero-cluster summaries during outages.
- Added `tests/test_people.py`
  - canonical path preference
  - legacy fallback behavior
  - canonical save target
- Added `tests/test_dashboard_api_people.py`
  - offline fail-open behavior
  - Immich list payload enrichment behavior
  - offline asset-hint parsing + unknown-first sorting behavior

**Validation:**
- `pytest -q tests/test_people.py tests/test_dashboard_api_people.py tests/test_synthesis_queries.py tests/test_models.py` → **24 passed**
- Function-level smoke:
  - live `/api/people` after dashboard restart: **0.01s**, `immich_available=false`, `registry_count=794`, `people_len=794`.

## 2026-03-05 — People naming queue + CSV import workflow (elder-session prep)

Added a queue + import workflow to move from "dashboard shows unknown faces" to "actionable naming list for elder review" and back into registry updates.

**What changed:**
- `src/sync_people.py`
  - Added `queue` command:
    - `python -m src.sync_people queue`
    - `python -m src.sync_people queue --limit 100`
    - `python -m src.sync_people queue --csv` (writes default `data/people/identification_queue.csv`)
    - `python -m src.sync_people queue --csv <path>` (custom export path)
  - Added `import-csv` command:
    - `python -m src.sync_people import-csv` (reads default `data/people/identification_queue.csv`)
    - `python -m src.sync_people import-csv --dry-run` (preview only)
    - `python -m src.sync_people import-csv <path>` (custom input)
  - Queue ranking:
    - unknown people first
    - largest estimated clusters first (parsed from `notes`, e.g. `(2485 assets)`)
  - Added optional `--include-named` for full-registry review.
- `README.md`
  - Updated CLI table entry for `sync_people` to include `queue` + `import-csv`.
- Added `tests/test_sync_people.py`
  - note asset-count parsing
  - unknown-first + descending-size queue ordering
  - include-named behavior
  - CSV row update application + birth-year parsing behavior

**Validation:**
- `pytest -q tests/test_sync_people.py tests/test_people.py tests/test_dashboard_api_people.py tests/test_synthesis_queries.py tests/test_models.py` → **31 passed**
- Live queue generation:
  - `python -m src.sync_people queue --csv`
  - wrote `data/people/identification_queue.csv` with top 50 unknown clusters.
- Import dry-run checks:
  - `python -m src.sync_people import-csv --dry-run` → `Updated: 0 / Unchanged: 10 / Missing IDs: 0`
  - `python -m src.sync_people import-csv /tmp/living-archive-identification-sample.csv --dry-run` (with one edited name) → `Updated: 1 / Unchanged: 2 / Missing IDs: 0`

## 2026-03-04 — Triage-aware batch processing integration

Integrated `contact_triage` outputs directly into the photo batch runner so expensive analysis can skip obvious duplicates/blanks.

**What changed:**
- `src/run_batch.py`:
  - Added `--triage` mode with `off|auto|require` (default `auto`)
  - Added triage loader that resolves matching files from `data/triage/*_triage.json` using slice path + album-name fallback scoring
  - Added keep/skip filtering before conversion/analysis work
  - Added per-slice triage stats in results (`triage_applied`, `triage_skipped`, `triage_file`, `photos_considered`)
  - Added triage fields to batch `run_meta.json` and triage skip totals in appended dev-log batch summaries
- `README.md` CLI table now includes `run_batch` and `contact_triage` entries.
- Added `tests/test_run_batch.py` for triage match resolution, filtering semantics, and `triage_mode=require` failure behavior.

**Validation:**
- `pytest -q tests/test_run_batch.py` → **5 passed**
- `pytest -q` → **66 passed**
- `python -m src.run_batch --help` confirms `--triage {off,auto,require}` is available.

## 2026-03-04 — Synthesis UX + quality sprint

Implemented the post-promotion synthesis follow-through: usable dashboard surface + chronology quality controls + unresolved-name reconciliation workflow.

**What changed:**
- Added a new `Synthesis` tab in `dashboard.html`:
  - synthesis overview cards and entity coverage bars
  - chronology quality panel (raw rows, compacted rows, outlier count + sample outliers)
  - unresolved-name queue and top-linked-people tables
  - interactive query tools for person dossier, date, and location endpoints
- Extended synthesis shared query layer (`src/synthesis_queries.py`):
  - overview now includes `resolved_people`, `unresolved_people`, and `top_unresolved`
  - added `query_unresolved_people()`
  - chronology metadata now surfaces `quality` when available
- Added chronology quality controls in `src/synthesis.py`:
  - duplicate-event suppression during `timeline_events` population (same asset/date/type)
  - chronology grouping key normalization for duplicate compaction
  - date outlier audit (`<1900` and future dates beyond `current_year + 1`)
  - emitted `quality` block in `data/chronology.json` and markdown header
- Added unresolved-name reconciliation workflow in `src/synthesis.py`:
  - `python -m src.synthesis unresolved [limit]`
  - `python -m src.synthesis reconcile "<unresolved_name>" "<canonical_name>"`
  - reconcile updates `src/person_clusters.json` safely and refreshes summary counters.
- Updated README synthesis CLI entry to include reconciliation commands.

**Validation:**
- `pytest -q` → **61 passed**.
- `python -m src.synthesis chronology` regenerated chronology artifacts with quality block.
- API smoke (function-level):
  - `api_synthesis_overview()` now returns unresolved metrics and queue.
  - `api_synthesis_chronology()` now includes `quality` (`outlier_event_count=1` in current data snapshot).

**Notes:**
- Existing dashboard server was already bound on port `8378`, so verification used function-level API calls instead of launching a second server instance.

## 2026-03-04 — Synthesis modularity refactor (shared query service)

Refactored synthesis query paths to reduce coupling and keep schema access centralized.

**What changed:**
- Added `src/synthesis_queries.py` as a shared data-access layer for:
  - synthesis DB connection/open checks
  - person/date/location/overview query helpers
  - chronology metadata/payload file readers
- Rewired `src/synthesis.py` CLI query commands (`dossier`, `date`, `location`) to use shared query helpers instead of inline SQL.
- Rewired dashboard synthesis APIs in `src/dashboard_api.py` to use the same helpers, removing duplicate SQL blocks and direct chronology parsing logic from the API layer.
- Added tests in `tests/test_synthesis_queries.py` for overview/person/date/location queries and chronology metadata/payload behavior.

**Outcome:**
- Synthesis is now integrated via a thinner boundary: producers (`src.synthesis`) and consumers (`src.dashboard_api`) share one query contract module.
- Future synthesis DB/schema or chronology changes can be isolated mostly to `src/synthesis_queries.py`.

**Validation + build output:**
- `pytest -q` → 57 passed.
- Dashboard synthesis smoke checks after refactor:
  - `overview_available=True`
  - `person_total_links=90` (`Feng Kuang Liu`)
  - `date_total_assets=26` (`1989`)
  - `location_total_photos=484` (`Taiwan`)
  - `chronology_decade_count=10`
- CLI smoke checks still succeed:
  - `python -m src.synthesis dossier "Feng Kuang Liu"`
  - `python -m src.synthesis date 1989`
  - `python -m src.synthesis location Taiwan`
- Commit: `b2a133a` — `Refactor synthesis queries into shared service module`.

---

## 2026-03-04 — Promote synthesis from experiment to infrastructure

Promoted experiment `0002-synthesis-layer` into main infrastructure with new `src/synthesis.py` and `src/person_clusters.json`.

**Promotion details:**
- Added production CLI/module path: `python -m src.synthesis` (`rebuild`, `stats`, `dossier`, `date`, `location`, `chronology`).
- Preserved deterministic Branch C behavior via frozen cluster mapping in `src/person_clusters.json`.
- Added dashboard synthesis APIs in `src/dashboard_api.py` and routes in `src/dashboard.py`:
  - `/api/synthesis/overview`
  - `/api/synthesis/person?name=...`
  - `/api/synthesis/date?year=...`
  - `/api/synthesis/location?country=...`
  - `/api/synthesis/chronology`
- Updated packaging/docs:
  - `pyproject.toml` script entry: `synthesis = "src.synthesis:main"`
  - README CLI table includes `python -m src.synthesis`
  - architecture doc now reflects `catalog.db + synthesis.db` local dashboard model
- Marked experiment manifest status as `completed`.

**Validation:**
- `python -m src.synthesis rebuild` populated 3,012 timeline events.
- `python -m src.synthesis chronology` generated `data/chronology.json` + `data/chronology.md`.
- Dashboard API smoke checks succeeded for synthesis overview/person/date/location/chronology.
- `pytest -q` → 53 passed.

---

## 2026-03-04 — Experiment 0002 Phase 5 (final report)

Completed the Phase 5 synthesis report at `experiments/0002-synthesis-layer/runs/p5-report/summary.md`.

**Included in report:**
- Final person dedup branch table (A/B/C metrics + verdicts)
- Entity extraction + timeline metrics from current rebuild
- Cross-reference precision by query type (person/date/location)
- Design retrospective (assumptions vs observed data)
- Verdict per component (`useful` / `needs-work` / `not-viable`)
- Next-step recommendations: face cluster naming, chronology quality controls, dashboard wiring, unresolved-name reconciliation, personal-branch integration

**Additional artifacts generated for query-type evaluation:**
- `runs/p3-cross-reference/location-query-taiwan.json`
- `runs/p3-cross-reference/location-query-italy.json`

---

## 2026-03-04 — Experiment 0002 Phase 4 (timeline + chronology)

Implemented Phase 4 in `experiments/0002-synthesis-layer/src/synthesis.py`.

**What changed:**
- `rebuild` now populates `timeline_events` from date entity links plus manifest labels (photo: `description_en/zh`; document: `summary_en/zh`).
- Added `chronology` command:
  - Reads `timeline_events`
  - Generates `data/chronology.json` and `data/chronology.md` (Chinese-first markdown)
  - Writes run snapshots to `experiments/0002-synthesis-layer/runs/p4-timeline/`
  - Writes `runs/p4-timeline/evaluation.md` with gate result

**Run metrics (Phase 4 generation):**
- `python -m experiments.0002-synthesis-layer.src.synthesis rebuild`
  - Timeline events populated: **3,012**
- `python -m experiments.0002-synthesis-layer.src.synthesis chronology`
  - Decades: **10** (`1940s` through `2040s`)
  - Event groups (date+type grouped): **1,532**
  - Gate: **Pass** (>=3 decades with events)

**Validation:**
- `python -m experiments.0002-synthesis-layer.src.synthesis stats` shows timeline events populated.
- `pytest -q` → 49 passed.

---

## 2026-03-04 — Experiment 0002 drift cleanup before Phase 4

Closed pre-Phase-4 drift in `experiments/0002-synthesis-layer` so timeline work starts from a consistent base.

**Changes:**
- `synthesis.py`: person resolution now does exact cluster lookup first, then Branch A-normalized fallback lookup (with ambiguity guard) to match the Phase 1 winner decision.
- `branch_c.py`: added explicit execution modes:
  - `--mode inline` (default): uses curated local cluster file
  - `--mode anthropic`: fresh API clustering
- Added `runs/p1-person-branches/branch-c-inline-clusters.json` as the reproducible curated source and `runs/p1-person-branches/README.md` with rerun commands.
- Synced `experiments/0002-synthesis-layer/manifest.json` outputs list with actual Phase 0-3 artifacts.
- Updated Phase 1 comparison note to match current Branch C artifact count (`154` variants merged).

**Validation:**
- `python -m experiments.0002-synthesis-layer.src.branch_c --mode inline ...` regenerates `branch-c-clusters.json`.
- `python -m experiments.0002-synthesis-layer.src.synthesis stats` unchanged core metrics (2,346 entities / 5,735 links / 0 timeline events).
- `pytest -q` → 49 passed.

---

## 2026-03-03 — Contact sheet triage for FastFoto scans (new tool)

Built `src/contact_triage.py` — pre-analysis triage pass for the 7,600+ FastFoto scans. The tool tiles photos into 4×4 numbered grids (contact sheets), sends each to Haiku via the Anthropic API, and saves a JSON keep/skip list to `data/triage/<album>_triage.json`.

**Rationale:** Full analysis runs ~30s/photo via Claude CLI. With 7,600 scans, that's 60+ hours of compute. Bulk scanning also produces duplicates (same photo scanned twice) and occasional blank sheets. A Haiku triage pass (~2s/grid, 16 photos) can catch these cheaply before the expensive pass.

**CLI:** `python -m src.contact_triage <album_dir> [--grid-size 16] [--dry-run]`

**Output schema:** `data/triage/<album>_triage.json` with `keep`, `skip`, `skip_reasons`, token counts, model. Future: `run_batch.py` can consult skip lists before queueing full analysis.

**Verified:** PIL tiling smoke-tested on workspace photos — contact sheets render correctly at 1200×1096px (243 KB JPEG).

---

## 2026-03-03 — Catalog caching pivot (architecture)

Rewrote the dashboard to read exclusively from `catalog.db` instead of walking the NAS filesystem. The trigger: after moving the AI layer local (2026-03-02), the dashboard was still doing 30+ second cold loads because `/api/batch-progress` imported `discover.py` and walked the NAS media tree.

**Changes:** Schema v2 migration (added `slice` column, `runs`/`photo_quality`/`doc_quality` cache tables), new `refresh` command, all dashboard API endpoints rewritten as SQL queries. Split `catalog.py` (421→281 lines) and `dashboard.py` (555→181 lines) into focused modules.

**Result:** Dashboard loads are now instant. Works fully offline — no NAS mount required. Data freshness tracked via `last_scan_at`/`last_refresh_at` metadata.

**Process note:** This was the first fully AI-implemented architecture pivot — the plan was written in one session, approved, and executed in a single pass with zero errors. The research doc → plan → implementation pipeline is working.

---

## 2026-03-03 — Synthesis layer design + experiment setup (architecture)

Wrote the synthesis layer design doc (`_dev/research/2026-03-03 synthesis-layer.md`) — a fully separate derivation layer that cross-references photo and document manifests to answer questions like "show me everything about Grandma" or "what happened in 1978."

Turned the design doc into experiment `0002-synthesis-layer` with phased execution and decision gates. This is the third time the research → experiment pattern has been used, and it's solidifying: the research doc captures *why*, the experiment brief captures *how to test*, and the phase gates prevent overbuilding.

**Observation:** The run log (now dev log) had gone stale because the project shifted from running pipelines to building infrastructure. The interesting work — architecture pivots, experiment design, process learning — had no home in an ops-only log. Broadening the log to capture all significant work, not just pipeline runs.

---

## 2026-03-02 — Move AI layer off NAS (architecture)

Moved all AI layer outputs from NAS (`_ai-layer/`) to local `data/` directory. Motivation: AFP mount latency was bottlenecking manifest reads. Migration script handles the move; config rewired to point at local paths. NAS `_ai-layer/` directories kept as inert backups.

---

## 2026-03-02 — Liu Family Trust documents (batch 2 of ~6)

- **Run:** `20260303T004945Z` — 20 documents from `Liu Family Trust Filings & Documents`
- **Result:** 20/20 succeeded, 0 failures
- **Elapsed:** 521.8s (~8.7 min, ~26.1s/doc)
- **Tokens:** 62 input / 17,773 output (est. ~8k input)
- **96 documents remain** — resume with `--resume 20260303T004945Z`
- **Content:** Mix of legal (trust administration, deeds, will, contract), financial (wire transfers, market report), personal (letters, diplomas, countries-visited list), medical (contact cards, correspondence), government (Social Security cards), employment (Agnews Center condolence letter)
- **Notes:** Automated capacity-burn batch. **Duplicate run triggered** — a second run (`20260303T005448Z`) fired in parallel before the first created manifests, processing the same 20 files twice. Both runs succeeded (20/20 each). The AI layer now has duplicate manifests for these 20 documents. Resume point going forward is `20260303T005448Z`. Dedup check recommended before next push to catalog.

---

## 2026-02-28 — Wedding (Digital Revolution Scans 1st Round)

**Run:** `20260228T100154Z` — 195 FastFoto scan JPEGs from `1st Round/Jpeg/Wedding`
**Result:** 195/195 succeeded, 0 failures
**Elapsed:** 6,321s (~105 min, ~32.4s/photo)
**Model:** Opus via CLI

### Date confidence

| High (>=0.8) | Medium (0.5–0.8) | Low (<0.5) | Date range |
|--------------|-------------------|------------|------------|
| 0 (0%) | 171 (87%) | 24 (12%) | 1960–1985 |

No high-confidence results — wedding and family celebration photos with no visible date stamps. Overwhelmingly medium confidence, consistent with Gold_Album profile. 24 low-confidence photos (12%) will need human review.

### Content

Wedding and celebration photos spanning roughly 1960–1985. Likely covers one or more family weddings plus related gatherings. Album name suggests a wedding-themed collection from the FastFoto scanning sessions.

### Notes

- Immich push skipped — no API key in session env. Manifests saved on NAS for later push.
- This is the 3rd of 6 albums processed from 1st Round. Remaining: Pink_Flower_Album (338), Red_Album_1 (390), Big_Red_Album (557).

---

## 2026-02-25 — Session summary

Single Claude Code session processing three sources back-to-back. All runs used Opus via CLI (Max plan, `photo_analysis_v1` prompt).

| Source | Photos | Result | Time | Output tokens |
|--------|--------|--------|------|---------------|
| 2009 Scanned Media (6 slices) | 133 | 133/133 | 66 min | 151,057 |
| 2022 Swei Chi (3 folders) | 87 | 87/87 | 45 min | 95,930 |
| Gold_Album (Digital Revolution 1st Round) | 145 | 145/145 | 79 min | 183,199 |
| **Total** | **365** | **365/365** | **~190 min** | **430,186** |

Zero failures. Average pace ~31s/photo across the session. Two sources fully completed (2009 Scanned Media, 2022 Swei Chi). Immich push skipped on all runs — no API key in session env; manifests saved on NAS for later push.

---

## 2026-02-25 — Gold_Album (Digital Revolution Scans 1st Round)

**Run:** `20260226T043615Z` — 145 FastFoto scan JPEGs from `1st Round/Jpeg/Gold_Album`
**Result:** 145/145 succeeded, 0 failures
**Elapsed:** 4,763s (~79 min)
**Output tokens:** 183,199 (~1,263 per photo)

### Date confidence

| High (≥0.8) | Medium (0.5–0.8) | Low (<0.5) | Date range |
|-------------|-------------------|------------|------------|
| 1 (1%) | 120 (83%) | 24 (17%) | 1973–1985 |

Overwhelmingly medium confidence. The album spans ~12 years of family life with no visible dates on most photos. The single high-confidence photo (`Photos_0083.jpg`, conf 0.97) had a legible sign — Cheng Ching Lake (澄清湖) in Kaohsiung with a visible date of 1978-02-08.

### Content

Family-focused album covering the mid-1970s through mid-1980s. Multi-generational family portraits, Chinese dinner gatherings, Taiwan landmarks (Kaohsiung, scenic overlooks), and formal group photos. Many photos show the same family across different occasions — a coherent personal album rather than a miscellaneous collection.

### Notes

- First Digital Revolution Scans album processed at scale (Albumpage was the 33-photo test). Pace was consistent with earlier runs (~33s/photo), confirming the pipeline handles the FastFoto JPEG format well.
- 24 low-confidence photos (17%) — better than the 2009 assorted folders (41%) but worse than Swei Chi (0%). The album's lack of visible dates and homogeneous 1970s–80s styling makes precise dating difficult.

## 2026-02-25 — 2022 Swei Chi (source complete)

All 87 photos from the `2022 Swei Chi/` source, across 3 subdirectories.

**Model:** Opus via Claude CLI (Max plan)
**Prompt:** `photo_analysis_v1`

| Run ID | Slice | Photos | Result | Elapsed |
|--------|-------|--------|--------|---------|
| `20260226T035029Z` | `LANGPOORT/` | 5 | 5/5 | 173s |
| `20260226T035332Z` | `Karina/` | 9 | 9/9 | 279s |
| `20260226T035819Z` | `processed/` | 73 | 73/73 | 2250s |
| | **Total** | **87** | **87/87** | **2,702s (~45 min)** |

Average pace: ~31.1s per photo. Output tokens: 95,930.

### Date confidence distribution

| Slice | High (≥0.8) | Medium (0.5–0.8) | Low (<0.5) | Date range |
|-------|-------------|-------------------|------------|------------|
| `LANGPOORT/` | 0 | 5 | 0 | 1980 |
| `Karina/` | 8 | 1 | 0 | 2022 |
| `processed/` | 30 | 43 | 0 | 1973–1994 |
| **Total** | **38 (44%)** | **49 (56%)** | **0 (0%)** | **1973–2022** |

Zero low-confidence results — much better than the 2009 assorted folders. The `processed/` files were date-named (e.g. `1976 25.jpeg`, `1978 (01-02) 47.jpeg`) which gave strong folder hints. `Karina/` photos were modern (2022, LINE app) with embedded metadata. `LANGPOORT/` photos dated 1980 with medium confidence.

## 2026-02-25 — 2009 Scanned Media remaining slices (batch complete)

Ran all 6 remaining slices from `2009 Scanned Media/`, completing the entire source. Orchestrated from a single Claude Code session — slices run sequentially via `SLICE_PATH` env var, one at a time (no multi-slice batch mode yet).

**Model:** Opus via Claude CLI (Max plan, no per-token cost)
**Prompt:** `photo_analysis_v1`

### Results

| Run ID | Slice | Photos | Source types | Result | Elapsed |
|--------|-------|--------|--------------|--------|---------|
| `20260226T022543Z` | `1993-europe/` | 8 | 8 TIFF | 8/8 | 219s |
| `20260226T023034Z` | `assorted/` | 22 | 17 TIFF + 5 JPG | 22/22 | 636s |
| `20260226T024122Z` | `assorted II/` | 40 | 40 JPG | 40/40 | 1174s |
| `20260226T030113Z` | `assorted III/` | 42 | 42 JPG | 42/42 | 1251s |
| `20260226T032219Z` | `assorted IV/` | 11 | 11 TIFF | 11/11 | 380s |
| `20260226T032854Z` | `1KUVLQ~D/` | 10 | 10 TIFF | 10/10 | 278s |
| | **Total** | **133** | 46 TIFF + 87 JPG | **133/133** | **3,938s (~66 min)** |

Average pace: ~29.6s per photo.

### Token usage

Output tokens: 151,057 (input token count in manifests only reflects CLI envelope, not actual image input). Roughly 1,135 output tokens per photo for the structured JSON analysis.

### Date confidence distribution

| Slice | High (≥0.8) | Medium (0.5–0.8) | Low (<0.5) | Date range |
|-------|-------------|-------------------|------------|------------|
| `1993-europe/` | 8 | 0 | 0 | 1993 |
| `assorted/` | 12 | 3 | 7 | 1963–2007 |
| `assorted II/` | 10 | 14 | 16 | 1970–2008 |
| `assorted III/` | 14 | 8 | 20 | 1970–1984 |
| `assorted IV/` | 0 | 1 | 10 | 1962–1968 |
| `1KUVLQ~D/` | 0 | 9 | 1 | 1972–1980 |
| **Total** | **44 (33%)** | **35 (26%)** | **54 (41%)** | **1962–2008** |

`1993-europe/` had uniformly high confidence — the folder name matched visual evidence (European landmarks, summer 1993). The `assorted` folders were much harder: mixed decades, no folder-based date hints, lots of undated casual/portrait photos. `assorted IV/` (all 1960s B&W) and `assorted III/` (1970s–80s family milestones) had the most low-confidence estimates.

### Content highlights

- **`1993-europe/`** — European vacation: Colosseum, Venice, Acropolis. Tight date cluster (Aug 20–27, 1993).
- **`assorted/`** — Widest spread: Egypt camel rides (1996), Sedona (1996), ex-Nortel party (2003), a 1963 portrait, tennis courts. Five decades of mixed content.
- **`assorted II/`** — Family milestones: multiple graduation photos (1970s–80s), a Liu family ancestral site visit (2004), restaurant gatherings, travel photos spanning 1970–2008.
- **`assorted III/`** — Life chapters: early immigration era (1970s Niagara Falls), newborn/baby photos (late 1970s–80s), wedding-adjacent family shots, some Taiwan-era portraits (1972).
- **`assorted IV/`** — Earliest material: 1960s Taiwan B&W portraits, military school photos, snow scenes. All low confidence — no visible dates, estimated from clothing/photo style.
- **`1KUVLQ~D/`** — Wedding and courtship photos (1972–1980): ceremony, Golden Gate Bridge, decorated Datsun, reception cake-cutting.

### Notes

- **Mixed source types worked seamlessly.** Three slices had JPEGs (assorted II/III from a different scanning pass), three had TIFFs, one had both. The JPEG source path (added in `e4db8e1`) copied files directly without re-encoding.
- **Immich push skipped** — no `IMMICH_API_KEY` in this session's env. All 133 manifests saved on NAS at `_ai-layer/runs/` for later push.
- **54 low-confidence photos (41%)** will need human review. These are mostly undated 1970s–80s family photos where the model could only estimate from clothing, furniture, and photo quality. The `assorted IV/` 1960s B&W material had almost no visual date anchors.
- **This completes 2009 Scanned Media.** Combined with earlier runs (1978: 26, 1980-1982: 36), all 195 photos from this source are now processed.

## 2026-02-25 — Albumpage retry (Digital Revolution Scans)

- **Run:** `20260225T092056Z` — 33 FastFoto scan JPEGs from `1st Round/Jpeg/Albumpage`
- **Result:** 31/33 succeeded, 2 timed out (Photo_028, Photo_036 — hit 120s CLI timeout)
- **Elapsed:** 2,317s (~39 min)
- **Fix applied this session:** Stripped `CLAUDECODE` env var from photo pipeline subprocess (`analyze.py`), matching existing pattern in `doc_analyze.py`. Committed as `147e5de`.
- **Previous attempt:** `20260225T074733Z` — 33/33 failed, nested Claude CLI session guard blocked every invocation
- **Immich:** Skipped (no API key in session env), manifests saved on NAS for later push
- **Next:** Retry 2 timed-out photos or move to next album

## 2026-02-19 — Liu Family Trust documents (full corpus)

- **Run:** `20260220T042253Z` — 116 documents, Opus 4.6
- **Result:** 116/116 succeeded, 0 failures
- **Elapsed:** ~43 min across 16 batches of ~20
- **Tokens:** 258k output tokens
- **Notes:** Large docs (up to 420 pages) chunked automatically without issues. Catalog reached 187 assets (121 doc + 66 photo).

## 2026-02-06 — 1980-1982 photos

- **Run:** 36 TIFFs from `2009 Scanned Media/1980-1982/`
- **Result:** 36/36 succeeded
- **Elapsed:** 369.8s

## 2026-02-05 — 1978 photos (first end-to-end run)

- **Run:** 26 TIFFs from `2009 Scanned Media/1978/`
- **Result:** 26/26 succeeded
- **Notes:** First successful end-to-end pipeline test. Established confidence-based Immich album routing.
