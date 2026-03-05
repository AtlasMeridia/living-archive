# Backlog

## Burn

Tasks explicitly approved for unattended automated dispatch by the capacity-burn scheduler.
Prereq: NAS must be mounted (`python -m src.preflight` handles auto-mount).
## Equipment

- **Epson FastFoto FF-680W** — High-speed photo scanner (1 photo/sec, 1200 dpi, wireless)
  - Acquired: 2026-02-09
  - Purpose: Bulk family photo digitization
  - Expense: ATLAS Meridia LLC

## Now — Cross-Pollination with Naked Robot

Both projects share the same arc (source media → AI vision → JSON manifests → SQLite → browser review) but developed different strengths in isolation. NR's haptic pipeline has a tag audit tool, faceted browser workbench, and contact-sheet batch triage that would directly improve LA's review workflow and tagging quality. LA's SHA-256 keying and FTS5 catalog are more robust than NR's equivalents. See `~/Projects/naked-robot/experiments/0008-cross-pollination-living-archive/README.md` for full analysis and priority table.

- [x] **Port tag audit pattern from NR** — `src/audit_tags.py`: 7 concept categories (relationship, condition/damage, activity, group, outdoor, indoor, era). Audited 2358 photos — `condition/damage` 100% gap rate, `group/crowd` 46%, `setting/indoor` 18%. — 2026-03-03
- [x] **Adapt haptic browser for photo/doc review** — `haptic.html` + `src/haptic_api.py` + routes in `src/dashboard.py`: faceted sidebar (confidence tiers, era/decade, people count, tags), photo grid, modal with full analysis + keyboard navigation. Accessible at `/haptic` on the dashboard server (port 8378). — 2026-03-03
- [x] **Contact sheet triage for FastFoto scans** — `src/contact_triage.py`: tiles up to 20 photos into 4×4 numbered grids, sends to Haiku via API, saves keep/skip lists to `data/triage/<album>_triage.json`; CLI `python -m src.contact_triage <album_dir>` — 2026-03-03
- [x] **Wire triage skip lists into batch photo processing** — `src/run_batch.py` now supports `--triage off|auto|require`, auto-loads matching `data/triage/*_triage.json`, filters album queues by keep/skip decisions, and records triage counts/files in `run_meta.json`; covered by new `tests/test_run_batch.py` — 2026-03-04
- [x] **Anti-euphemization prompting** — add explicit vocabulary examples to photo prompts ("include relationship tags: parent-child, couple, siblings" / "include condition tags: faded, torn, water-damaged") — 2026-03-03

## Now — Synthesis Layer (Experiment 0002)

- [x] **Clean pre-Phase-4 drift in experiment 0002** — aligned person cluster lookup with Branch A normalization fallback, added explicit Branch C inline/API reproducibility path, synced experiment manifest outputs with produced artifacts — 2026-03-04
- [x] **Implement Phase 4 timeline + chronology artifacts (experiment 0002)** — timeline events now populated during rebuild (`3012`), added `chronology` command, generated `data/chronology.{json,md}` and `runs/p4-timeline/*` with gate pass across 10 decades — 2026-03-04
- [x] **Complete Phase 5 final report (experiment 0002)** — added `runs/p5-report/summary.md` with branch outcomes, extraction/timeline metrics, query precision by type, design retrospective, and next-step recommendations — 2026-03-04
- [x] **Promote synthesis module to `src/` + wire dashboard synthesis APIs** — promoted `src/synthesis.py` + `src/person_clusters.json`, added dashboard endpoints (`/api/synthesis/overview|person|date|location|chronology`), and marked experiment 0002 complete — 2026-03-04
- [x] **Extract shared synthesis query service for modularity** — added `src/synthesis_queries.py` and rewired both `src/synthesis.py` (CLI queries) and `src/dashboard_api.py` (synthesis endpoints) to use shared DB + chronology access helpers, reducing duplicated SQL and tightening the synthesis boundary — 2026-03-04
- [x] **Synthesis UX + quality sprint** — added dashboard `Synthesis` tab (overview + person/date/location query tools + chronology snapshot), chronology quality controls (`quality` block with outlier audit and compaction metrics), and unresolved-name reconciliation workflow (`python -m src.synthesis unresolved|reconcile`) — 2026-03-04

## Now — Project Self-Awareness

The codebase, architecture, and documentation need to catch up to what the project has become.

- [x] Update project brief — reconciled dual identity (working system + methodology), added architecture and case study sections, updated open questions — 2026-02-11
- [x] Update README — rewrote to lead with system description, real directory tree, CLI reference, quick start — 2026-02-11
- [x] Retire `docs/open-questions.md` — answered questions archived to `_dev/resolved-decisions.md`, remaining items absorbed into backlog; doc deleted — 2026-02-11
- [x] Create `_dev/research/` — narrative and research layer; moved council and personal-data docs in, added README with conventions — 2026-02-11
- [x] Sketch personal branch in `docs/architecture.md` — document intent, integration points, and how pipeline improvements benefit both Family and Personal branches — 2026-02-12
- [ ] Review medium-confidence photos in Immich "Needs Review" albums — 5 from 1978 run, 34 from 1980-1982 run (human task)
- [x] Document local LLM inference mode — added Inference Modes section to README (env vars, provider table, all three backends), updated architecture.md with Inference Routing section (CLI mechanics, chunking, rate limits, CLAUDECODE env var) — 2026-02-20
- [x] Fix People dashboard data path + fail-open latency — `src/people.py` now reads canonical `data/people/registry.json` (with legacy fallback from `data/photos/people/registry.json`), `sync_people status` reports canonical path, `api_people()` now fails open fast when Immich is offline and avoids per-person N+1 stats calls, and the UI now surfaces offline `~N photos` hints from registry notes with unknown-first sorting; regressions covered in `tests/test_people.py` + `tests/test_dashboard_api_people.py` — 2026-03-05

## Next — Focused Conversations

Each of these needs a dedicated session producing artifacts in `_dev/research/`.

- [x] AI layer architecture deep dive — council session produced unified catalog design (SQLite asset catalog + entity index); see `_dev/research/2026-02-12 unified-catalog.md` — 2026-02-12
- [x] Personal filesystem organization — raw export stays untouched, catalog is the interface; 6-phase ingestion plan (photos, notes, journals, dedup, Drive, small sources); see `_dev/research/2026-02-12 personal-data-organization.md` — 2026-02-12
- [x] Presentation layer discussion — public layer is methodology-first (blog series at `kennyliu.io/living-archive`), family access deferred, admin tools built as needed; see `_dev/research/2026-02-18 presentation-layer.md` — 2026-02-18

## Next — Pipeline Operations

- [x] Build unified asset catalog — `_ai-layer/catalog.db` with asset table, backfill + scan commands, inline updates from manifest writers; see `_dev/research/2026-02-12 unified-catalog.md` — 2026-02-16
- [x] Build `scan` command — `python -m src.catalog scan` inventories filesystem, diffs against catalog, reports new/changed/stale items — 2026-02-16
- [x] Subscription-aware batch controls — `--batch N`, `--delay`, `--dry-run`, cumulative usage tracking, CLI rate-limit detection + 60s retry; run_meta.json now includes usage and batch_size — 2026-02-18
- [x] Run remaining Liu Family Trust documents in batches — 116 docs processed with Opus 4.6, 0 failures, 258k output tokens, catalog at 187 assets (121 doc + 66 photo) — 2026-02-19
- [x] Batch mode for `SLICE_PATH` — `--slices` arg with glob patterns for targeted slice filtering in `run-batch` — 2026-03-03
- [x] Run remaining 2009 Scanned Media slices — 133/133 photos across 6 slices, 0 failures, ~65 min total — 2026-02-25
- [x] Enumerate new media sources — inventoried 4 sources, see below — 2026-02-20
- [x] Page-range chunking for document pipeline — chunking worked automatically on large docs (up to 420pp), no failures — 2026-02-19

## Media Source Inventory

Enumerated 2026-02-20. All paths relative to `Living Archive/Family/Media/` on NAS.

### 2025-2026 Digital Revolution Scans — 7,629 unique photos, ~388 GB

Scanned with Epson FastFoto FF-680W. Each album has both TIFF and JPEG (15,258 total files). JPEGs already exist — pipeline can skip TIFF-to-JPEG conversion.

**1st Round (1,658 photos, 6 albums):** Big_Red_Album (557), Red_Album_1 (390), Pink_Flower_Album (338), Wedding (195), Gold_Album (145), Albumpage (33)

**2nd Round (3,599 photos, 10 albums):** Big_Black_Album (984), White_Album (804), Red_Album_2 (401), Black_Album (355), Grey_Album (329), Red_Album_1 (261), Green_Album (216), Lifes_Garden (153), Yellow_Album (51), Misc (45)

**3rd Round (2,372 photos, 6 albums):** Red_Album (655), Blue_Album2 (532), Blue_Memories_1978_3A_!981_1A (466), Brown_Album_A18 (352), Brown_Wooden_Album (250), Orange_Textured_Album (117)

Note: 1st Round TIFF folder misspelled "TiIF". 3rd Round album name `Blue_Memories_1978_3A_!981_1A` has `!981` typo (likely `1981`).

### Unsorted Archival / Liu Family Scans — ~2,997 photos, 698 MB

Date-organized folders (1973–2019), mix of JPEG and TIFF. **Overlaps with 2009 Scanned Media** in folders: `1978`, `1980-1982`, `1993-europe`, `assorted` I–IV. Needs dedup before processing.

New content not in 2009 Scanned Media: `1973` (8), `1974?` (10), `1975` (170), `1978-1981` (358), `1978 (01-02)` (144), `1980-1983` (473), `1983-1985` (385), `1985-1987` (531), `1989` (571), `1991` (4), `1994` (83), `Dad's Family Album` (69). Several empty folders.

### 2022 Swei Chi — 87 photos, 280 MB

All JPEG. Three subdirs: `processed/` (73, date-named 1973–1998), `Karina/` (9, LINE app photos), `LANGPOORT/` (5, dated 1980-05-23).

### 2025 Scanned Media — 1 PDF (3.5 MB)

Just `letter.pdf` and an empty `Letters/` folder. Candidate for document pipeline.

### Grandma 2012 b-day pics — 4 JPGs

## Next — Digital Revolution Scans

Processing the 7,629 FastFoto scans. Pipeline needs adaptation since JPEGs already exist (no TIFF conversion needed).

- [x] Adapt photo pipeline for JPEG source input — skip TIFF-to-JPEG conversion when source is already JPEG, hash the JPEG source instead — 2026-02-25
- [x] Run test batch on a small album — `Albumpage/` (33 photos), 31/33 succeeded, 2 timed out — 2026-02-25
- [ ] Process 1st Round albums — Albumpage (31/33), Gold_Album (145/145), Wedding (195/195), Pink_Flower_Album (338/338), Big_Red_Album (557/557) done; remaining: Red_Album_1 (60/390 processed, 330 remaining; run `20260305T011118Z` in progress).
- [ ] Process 2nd Round albums (3,599 photos across 10 albums)
- [ ] Process 3rd Round albums (2,372 photos across 6 albums)

## Next — Unsorted Archival Dedup & Processing

- [x] Hash-compare overlapping folders between `Unsorted Archival/Liu Family Scans/` and `2009 Scanned Media/` — `dedup-report` tool: SHA-256 intra-source dupes + folder-name/stem cross-source comparison — 2026-03-03
- [ ] Process non-overlapping Liu Family Scans folders (~2,806 photos across 12 date-range folders)
- [x] Process `2022 Swei Chi/` — 87/87 photos across 3 folders, 0 failures, ~45 min — 2026-02-25

## Later — Face Recognition & People Tagging

Steps 1-4 done. Steps 5-6 blocked on human activity. See `_dev/research/2026-02-06 council-face-recognition.md`.

- [x] 1. Enable Immich face recognition — buffalo_l running, 1241 clusters — 2026-02-06
- [x] 2. Investigate Immich face/person API — full CRUD available — 2026-02-06
- [x] 3. Create people registry in AI layer — `_ai-layer/people/registry.json` — 2026-02-06
- [x] 4. Build Immich sync script — `python -m src.sync_people`, 794 clusters imported — 2026-02-06
- [x] 4.1 Build naming queue + import workflow — `python -m src.sync_people queue [--limit N] [--csv [PATH]]` prioritizes unknown clusters by estimated asset count and exports elder-session worksheets; `python -m src.sync_people import-csv [PATH|--csv PATH] [--dry-run]` applies filled naming sheets back into registry (generated `data/people/identification_queue.csv`) — 2026-03-05
- [ ] 5. Elder knowledge capture session — get faces in front of family elders
- [ ] 6. Evaluate elder UX — Immich native face tagging vs. custom tool

## Later — Personal Data Integration

Plan defined in `_dev/research/2026-02-12 personal-data-organization.md`. Depends on unified catalog being built first.

- [ ] Copy Day One archive from Dropbox to NAS `Personal/Day One/`
- [ ] Parse iCloud Photo Details CSVs → catalog (~26,000 assets across 20 parts)
- [ ] Ingest iCloud Notes → catalog + FTS5 (~949 notes, 2,700 text files)
- [ ] Ingest Day One journals → catalog + FTS5 (~918 entries, YAML frontmatter parsing)
- [ ] Dedup pass — cross-reference Day One attachment hashes against iCloud Photos checksums
- [ ] Investigate `👀` folder in iCloud Drive (7.8 GB unknown content)
- [ ] Small sources (Mail, Contacts, Calendars) — deferred until catalog is proven

## Next — Public Presence (Living Archive Blog)

Methodology blog at `kennyliu.io/living-archive` using headless-atlas (Next.js + Ghost + Vercel).
See `_dev/research/2026-02-18 presentation-layer.md` for full design session.

- [ ] Add `/living-archive` routes to headless-atlas — index + detail pages, Ghost tag filter, nav link
- [ ] Co-write first 2-3 posts with openclaw agent — establish voice, format, and what a good post looks like; posts should document current AI tooling practices (see `_dev/research/ai-tooling-snapshot.md`)
- [ ] Transition to agent-drafted posts — agent drafts from `_dev/research/` docs and dev sessions, Kenny reviews

## Later — Public Presence (Other)

- [ ] Remote access for review dashboard — expose via Cloudflare Tunnel or Tailscale so collaborators outside LAN can view and use the review UI
- [ ] Family access — Cloudflare Tunnel + Access for secure remote Immich viewing
- [ ] Family photo uploads — find an easy upload system (existing app) for family members to contribute photos
- [ ] Privacy defaults for published content — opt-in vs. opt-out for people in photos, deceased vs. living distinction
- [ ] Decide what's public repo vs. private — methodology public, family-specific data private
- [x] Cost estimation tool — `src/cost.py` with token + dollar estimates in both `run-batch --dry-run` and `doc-extract --dry-run` — 2026-03-03

## Later — Future Work

- [x] Process `2025 Scanned Media/letter.pdf` — config fix: absolute `DOC_SLICE_PATH` support in config.py, doc_scan.py, run_doc_extract.py — 2026-03-03
- [ ] Red book (族譜) OCR — traditional Chinese genealogy book processing (April 2026)
- [ ] Elder interview capture — oral history before Taiwan trip
- [ ] Quarterly reindex — re-run manifests as models improve

## Done

- [x] Move AI layer off NAS to local `data/` — config rewired, migration script added, architecture docs updated — 2026-03-02
- [x] NAS-independent dashboard via catalog caching — schema v2 (slice column + cache tables), `refresh` command, dashboard rewritten as SQL queries, no NAS needed for dashboard — 2026-03-03
- [x] Build unified asset catalog (Phase 1) — `catalog.db` with 136 indexed assets (62 photo + 74 document), backfill/scan/stats CLI, 
- [x] `python -m src.run_doc_extract --auto --batch 20 --delay 2` — Process up to 20 unprocessed documents with 2s pacing — 2026-03-02inline manif

- [x] `python -m src.run_batch --hours 2 --push` — Process unprocessed photo slices with 2-hour time budget, push metadata to Immich — 2026-03-02est updates — 2026-02-16
- [x] Harden NAS auto-mount with retry logic, fix stale smb:// references, add mount to doc pipeline — 2026-02-11
- [x] Run document pipeline on Liu Family Trust — 72 docs, 468 pages, 26 doc types, FTS5 index built — 2026-02-07
- [x] Run photo pipeline on `1980-1982/` — 36 TIFFs, 36 succeeded, 369.8s — 2026-02-06
- [x] Add people registry and Immich face sync pipeline — 2026-02-06
- [x] Add CLI dispatch, review dashboard, preflight checks — 2026-02-06
- [x] Verify Immich metadata push — descriptions and dates confirmed on all 26 assets — 2026-02-06
- [x] Create project map (interactive HTML) — 2026-02-06
- [x] Add preflight checks: NAS auto-mount, Immich health, config validation — 2026-02-06
- [x] Harden codebase: Pydantic models, structured logging, retry, validation, 32 tests — 2026-02-05
- [x] Run photo pipeline end-to-end on `1978/` (26 TIFFs) — 2026-02-05
