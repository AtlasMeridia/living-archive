# Backlog

## Now

- [ ] Review medium-confidence photos in Immich "Needs Review" albums — confirm or correct dates (5 from 1978 run, 34 from 1980-1982 run)

## Next

- [ ] Run remaining 2009 Scanned Media slices: `1993-europe/` (8), `assorted/` (22), `assorted II/` (40), `assorted III/` (42), `assorted IV/` (11), `1KUVLQ~D/` (10)
- [ ] Make `SLICE_PATH` accept multiple paths or a batch mode so you don't have to run one-at-a-time
- [ ] Run document pipeline on a small PDF batch to validate extraction quality
- [ ] Enumerate `2022 Swei Chi/` and `2025-2026 Digital Revolution Scans/` — count files, check formats
- [ ] Add preflight checks to document pipeline (`run_doc_extract.py`)

## Later — Face Recognition & People Tagging (council: 2026-02-06)

Steps 1-2 are research/validation. Steps 3-6 are implementation. See `_dev/council-face-recognition-2026-02-06.md`.

- [ ] 1. Enable Immich face recognition on existing photos — evaluate clustering quality on 1970s scans
- [ ] 2. Investigate Immich face/person API — can we pull face crops, bounding boxes, person assignments? Document findings
- [ ] 3. Create people registry in AI layer — `_ai-layer/people/registry.json` with `{person_id, name_en, name_zh, relationship, birth_year, notes}`
- [ ] 4. Build Immich ↔ AI layer sync script — pull face assignments from Immich into registry, push confirmed names back
- [ ] 5. Elder knowledge capture session — get faces in front of family elders (Immich mobile or printed face crops as fallback)
- [ ] 6. Evaluate elder UX — decide between Immich's native face tagging on mobile vs. building a custom "name this face" tool

## Later — Other

- [ ] Family access — Cloudflare Tunnel + Access for secure remote Immich viewing
- [ ] Cost estimation tool — preview API costs before running a large batch
- [ ] Process `2025 Scanned Media/` (letters/PDFs — document pipeline)
- [ ] Red book (族譜) OCR — traditional Chinese genealogy book processing
- [ ] Elder interview capture — oral history before Taiwan trip

## Done

- [x] Run photo pipeline end-to-end on `1978/` (26 TIFFs) — 2026-02-05
- [x] Harden codebase: Pydantic models, structured logging, retry, validation, 32 tests — 2026-02-05
- [x] Add preflight checks: NAS auto-mount, Immich health, config validation — 2026-02-06
- [x] Create project map (interactive HTML) — 2026-02-06
- [x] Verify Immich metadata push — descriptions and dates confirmed on all 26 assets — 2026-02-06
- [x] Run photo pipeline on `1980-1982/` (36 TIFFs, 36 succeeded, 0 failed, 369.8s) — 2026-02-06
