# Backlog

## Equipment

- **Epson FastFoto FF-680W** — High-speed photo scanner (1 photo/sec, 1200 dpi, wireless)
  - Acquired: 2026-02-09
  - Purpose: Bulk family photo digitization
  - Expense: ATLAS Meridia LLC

## Now — Project Self-Awareness

The codebase, architecture, and documentation need to catch up to what the project has become.

- [x] Update project brief — reconciled dual identity (working system + methodology), added architecture and case study sections, updated open questions — 2026-02-11
- [x] Update README — rewrote to lead with system description, real directory tree, CLI reference, quick start — 2026-02-11
- [x] Retire `docs/open-questions.md` — answered questions archived to `_dev/resolved-decisions.md`, remaining items absorbed into backlog; doc deleted — 2026-02-11
- [x] Create `_dev/research/` — narrative and research layer; moved council and personal-data docs in, added README with conventions — 2026-02-11
- [x] Sketch personal branch in `docs/architecture.md` — document intent, integration points, and how pipeline improvements benefit both Family and Personal branches — 2026-02-12
- [ ] Review medium-confidence photos in Immich "Needs Review" albums — 5 from 1978 run, 34 from 1980-1982 run (human task)
- [ ] Document local LLM inference mode — `config.py` has `USE_CLI`/`CLAUDE_CLI`/`CLI_MODEL` and `analyze.py` has `analyze_via_cli()`, but README and architecture docs only mention the Anthropic API path; need to document the CLI routing option and when/why to use it

## Next — Focused Conversations

Each of these needs a dedicated session producing artifacts in `_dev/research/`.

- [x] AI layer architecture deep dive — council session produced unified catalog design (SQLite asset catalog + entity index); see `_dev/research/unified-catalog-2026-02-12.md` — 2026-02-12
- [x] Personal filesystem organization — raw export stays untouched, catalog is the interface; 6-phase ingestion plan (photos, notes, journals, dedup, Drive, small sources); see `_dev/research/personal-data-organization-2026-02-12.md` — 2026-02-12
- [ ] UI development discussion — Immich covers photos but no interface for document search (FTS5 index is SQLite-only), no cross-collection browsing, no unified dashboard; define what "showing this publicly" looks like

## Next — Pipeline Operations

- [x] Build unified asset catalog — `_ai-layer/catalog.db` with asset table, backfill + scan commands, inline updates from manifest writers; see `_dev/research/unified-catalog-2026-02-12.md` — 2026-02-16
- [x] Build `scan` command — `python -m src.catalog scan` inventories filesystem, diffs against catalog, reports new/changed/stale items — 2026-02-16
- [ ] Batch mode for `SLICE_PATH` — accept multiple paths or glob so remaining slices can run unattended
- [ ] Run remaining 2009 Scanned Media slices: `1993-europe/` (8), `assorted/` (22), `assorted II/` (40), `assorted III/` (42), `assorted IV/` (11), `1KUVLQ~D/` (10)
- [ ] Enumerate `2022 Swei Chi/` and `2025-2026 Digital Revolution Scans/` — count files, check formats
- [ ] Page-range chunking for document pipeline — 44 medium/large Liu Family Trust docs (21-420pp) hit 20MB context limit; need subagent chunking strategy

## Later — Face Recognition & People Tagging

Steps 1-4 done. Steps 5-6 blocked on human activity. See `_dev/council-face-recognition-2026-02-06.md`.

- [x] 1. Enable Immich face recognition — buffalo_l running, 1241 clusters — 2026-02-06
- [x] 2. Investigate Immich face/person API — full CRUD available — 2026-02-06
- [x] 3. Create people registry in AI layer — `_ai-layer/people/registry.json` — 2026-02-06
- [x] 4. Build Immich sync script — `python -m src.sync_people`, 794 clusters imported — 2026-02-06
- [ ] 5. Elder knowledge capture session — get faces in front of family elders
- [ ] 6. Evaluate elder UX — Immich native face tagging vs. custom tool

## Later — Personal Data Integration

Plan defined in `_dev/research/personal-data-organization-2026-02-12.md`. Depends on unified catalog being built first.

- [ ] Copy Day One archive from Dropbox to NAS `Personal/Day One/`
- [ ] Parse iCloud Photo Details CSVs → catalog (~26,000 assets across 20 parts)
- [ ] Ingest iCloud Notes → catalog + FTS5 (~949 notes, 2,700 text files)
- [ ] Ingest Day One journals → catalog + FTS5 (~918 entries, YAML frontmatter parsing)
- [ ] Dedup pass — cross-reference Day One attachment hashes against iCloud Photos checksums
- [ ] Investigate `👀` folder in iCloud Drive (7.8 GB unknown content)
- [ ] Small sources (Mail, Contacts, Calendars) — deferred until catalog is proven

## Later — Public Presence & Content

- [ ] First blog post — document the methodology with real results to show
- [ ] Family access — Cloudflare Tunnel + Access for secure remote Immich viewing
- [ ] Family photo uploads — find an easy upload system (existing app) for family members to contribute photos
- [ ] Privacy defaults for published content — opt-in vs. opt-out for people in photos, deceased vs. living distinction
- [ ] Decide what's public repo vs. private — methodology public, family-specific data private
- [ ] Cost estimation tool — preview API costs before running a large batch

## Later — Future Work

- [ ] Process `2025 Scanned Media/` (letters/PDFs — document pipeline)
- [ ] Red book (族譜) OCR — traditional Chinese genealogy book processing (April 2026)
- [ ] Elder interview capture — oral history before Taiwan trip
- [ ] Quarterly reindex — re-run manifests as models improve

## Done

- [x] Build unified asset catalog (Phase 1) — `catalog.db` with 136 indexed assets (62 photo + 74 document), backfill/scan/stats CLI, inline manifest updates — 2026-02-16
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
