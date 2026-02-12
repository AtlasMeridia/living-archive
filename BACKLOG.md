# Backlog

## Equipment

- **Epson FastFoto FF-680W** — High-speed photo scanner (1 photo/sec, 1200 dpi, wireless)
  - Acquired: 2026-02-09
  - Purpose: Bulk family photo digitization
  - Expense: ATLAS Meridia LLC

## Now — Project Self-Awareness

The codebase, architecture, and documentation need to catch up to what the project has become.

- [ ] Update project brief — currently dated Jan 11, describes "not software" but we built a working system; reconcile methodology + engineering reality
- [ ] Update README — repo structure references `templates/` and `guides/` that don't exist; real `src/`, `prompts/`, `tests/` are unmentioned
- [ ] Update `docs/open-questions.md` — questions 1, 2, 4, 5 have been answered; add new open questions (personal branch, UI, AI layer for personal data)
- [ ] Create `_dev/research/` — narrative and research layer where decisions, session insights, and blog-ready seeds accumulate over time
- [ ] Sketch personal branch in `docs/architecture.md` — document intent, integration points, and how pipeline improvements benefit both Family and Personal branches
- [ ] Review medium-confidence photos in Immich "Needs Review" albums — 5 from 1978 run, 34 from 1980-1982 run (human task)

## Next — Focused Conversations

Each of these needs a dedicated session producing artifacts in `_dev/research/`.

- [ ] AI layer architecture deep dive — how does the three-layer model extend to personal data? What's the AI layer for iCloud Photos (HEIC not TIFF), iCloud Drive, Notes? How do family and personal cross-reference?
- [ ] Personal filesystem organization — 726 GB Apple export (20 iCloud Photos parts, Drive, Notes, Mail, etc.) needs a plan before pipeline can touch it; dedup strategy against Day One archive
- [ ] UI development discussion — Immich covers photos but no interface for document search (FTS5 index is SQLite-only), no cross-collection browsing, no unified dashboard; define what "showing this publicly" looks like

## Next — Pipeline Operations

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

Depends on the focused conversations above producing a plan.

- [ ] Define `PERSONAL_ROOT` and personal pipeline paths in `config.py`
- [ ] Create AI layer structure for personal photos and documents
- [ ] Day One journal cross-referencing — 918 entries (1999-2024) as metadata enrichment for photos from same dates
- [ ] iCloud Photos deduplication and organization (20 parts, ~726 GB)

## Later — Public Presence & Content

- [ ] First blog post — document the methodology with real results to show
- [ ] Family access — Cloudflare Tunnel + Access for secure remote Immich viewing
- [ ] Decide what's public repo vs. private — methodology public, family-specific data private
- [ ] Cost estimation tool — preview API costs before running a large batch

## Later — Future Work

- [ ] Process `2025 Scanned Media/` (letters/PDFs — document pipeline)
- [ ] Red book (族譜) OCR — traditional Chinese genealogy book processing (April 2026)
- [ ] Elder interview capture — oral history before Taiwan trip
- [ ] Quarterly reindex — re-run manifests as models improve

## Done

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
