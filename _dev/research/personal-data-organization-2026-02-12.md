# Personal Data Organization Plan

**Date:** 2026-02-12
**Status:** Decision made — ready to implement
**Depends on:** Unified catalog (`_ai-layer/catalog.db`) from unified-catalog-2026-02-12.md

---

## Goal

Organize 726 GB of personal data (Apple iCloud export + Day One journals) so that current and future AI models can analyze it to reconstruct the past. The value is in cross-referencing: photos, notes, journal entries, and documents from the same time periods, telling a richer story together than any single content type alone.

This is not about getting photos into Immich or building a viewing interface. It's about making 25 years of digital life queryable through the unified catalog and text-searchable through FTS5.

---

## Inventory

### iCloud Photos — 710 GB, ~26,000 files
Split across 20 arbitrary Apple download parts (no semantic meaning to the split).

| Type | Count | Notes |
|------|-------|-------|
| Photos (HEIC, JPG, JPEG, PNG) | ~13,600 | iPhone photos, screenshots, saved images |
| Videos (MOV, MP4) | ~7,400 | iPhone videos, GoPro |
| Raw/creative (DNG, RAF, PSD, AI) | ~100 | Fuji RAFs, Adobe files |
| Other (GIF, WebP, 3GP, M4V) | ~85 | Miscellaneous |
| Photo Details CSVs | 640 | Apple metadata: date, checksum, favorite, hidden, deleted |

Date range: ~2013–2025 (iCloud account era).

### iCloud Notes — 684 MB, ~949 notes
Three-level hierarchy: `Notes/<folder>/<note-title>/<note-title>.txt` with optional image/gif attachments.

| Component | Count |
|-----------|-------|
| Text files (.txt) | 2,700 |
| Attachments (images, gifs) | 1,978 |
| Notes Details CSV | 1 (title, created, modified, pinned, deleted, drawing, content hash) |

Date range: 2019–2023. Plain text format. Folder names are emoji-heavy and personal (Chinese characters, Russian, creative names).

### Day One Archive — ~918 entries (in Dropbox, not yet on NAS)
Already converted to Obsidian-compatible markdown with YAML frontmatter.

| Component | Details |
|-----------|---------|
| Format | YYYY-MM folders, YYYY-MM-DD.md files |
| Frontmatter | Dates, tags, journal sources |
| Attachments | Hash-based filenames (SHA-256 overlap with iCloud Photos possible) |
| Location | `~/Dropbox/ATLASM Obsidian/00 Inbox/Daily/_dayone archive/` |

Date range: 1999–2024.

### iCloud Drive — 9.8 GB
Mostly app sync data. One large folder (`👀`, 7.8 GB) dominates.

| Category | Size | Notes |
|----------|------|-------|
| `👀` folder | 7.8 GB | Unknown content — needs investigation |
| App data (Clips, Sketches, Playgrounds, WhatsApp, iBooks, iMovie) | ~1.2 GB | App-specific formats |
| Day One iCloud Drive backup | 20 MB | May overlap with Dropbox archive |
| PDFs, Downloads | ~38 MB | Potentially meaningful documents |

### Small/metadata-only
| Source | Size | Value |
|--------|------|-------|
| iCloud Mail | 27 MB | Timeline enrichment (who/when) |
| iCloud Contacts | 20 MB | People registry cross-reference |
| iCloud Calendars & Reminders | 844 KB | Event dates for timeline |
| iCloud Bookmarks | 612 KB | Interests over time |
| Other Data Part 6 (iCloud usage) | 482 MB | Account history |
| Apple Media Services | 142 MB | Purchase/subscription history |

---

## Architecture Decision: Raw Export Stays Untouched

The raw Apple export remains as-is on the NAS. No files are moved, renamed, or reorganized. The 20-part photo split, the emoji folder names, the app data directories — all stay exactly as Apple delivered them.

**Rationale:**
- Consistent with the "data layer is read-only" principle from the family branch
- The unified catalog is the interface — you query the catalog, not the filesystem
- Reorganizing 26,000 files and 710 GB produces no analytical value
- Raw export preserves provenance ("this is exactly what Apple gave me on Feb 2026")
- No risk of losing files or breaking internal references during reorganization

**Consequence:** The catalog must be comprehensive enough that no one ever needs to browse the raw filesystem. Every asset gets a row with a date, type, and path.

---

## Content Type Processing Plans

### 1. iCloud Photos → Catalog (no AI processing yet)

**Input:** 640 Photo Details CSVs + filesystem scan of 26,000 files.

**Process:**
1. Parse all `Photo Details*.csv` files from all 20 parts
2. Extract: filename, checksum (`fileChecksum`), creation date (`originalCreationDate`), import date, favorite/hidden/deleted flags
3. Match CSV rows to actual files on disk (by filename within each part)
4. Insert into `catalog.db` assets table: `sha256` (from Apple's checksum or computed), `path`, `content_type=photo` or `video`, `file_size`, `file_mtime`, `status=indexed`
5. Optionally extract EXIF metadata (GPS, camera model) for photos where Apple CSV lacks detail

**What we DON'T do yet:**
- No Claude Vision processing. Most iPhone photos have dates and GPS from EXIF. Vision adds value for contextless images (screenshots, saved photos, old scans) — that's a selective future operation.
- No Immich import. Personal photos stay in the data layer until a presentation decision is made.

**Cost:** Near zero — it's CSV parsing and filesystem stats.

### 2. iCloud Notes → Catalog + FTS5

**Input:** 2,700 text files + Notes Details CSV.

**Process:**
1. Parse `Notes Details.csv` for creation/modification dates, titles, deleted flag
2. Read each `.txt` file content
3. Insert into `catalog.db`: one asset row per note, `content_type=note`
4. Index text content into FTS5 for full-text search
5. Catalog note attachments (images/gifs) as separate assets linked to their parent note

**Value:** Notes span 2019–2023 and contain personal writing, business notes, coding notes, creative work — rich context for understanding what you were thinking about during those years.

### 3. Day One Journals → Catalog + FTS5

**Input:** 918 markdown files with YAML frontmatter.

**Process:**
1. Copy archive from Dropbox to NAS: `Personal/Day One/` (one-time operation)
2. Parse YAML frontmatter: dates, tags, journal sources
3. Insert into `catalog.db`: one asset row per entry, `content_type=journal`
4. Index markdown body text into FTS5
5. Catalog photo attachments; record their SHA-256 hashes for dedup against iCloud Photos

**Value:** 1999–2024 is the longest continuous personal record. Journal entries provide narrative context that photos and notes lack.

### 4. iCloud Drive → Selective Cataloging

**Input:** 9.8 GB of mixed content.

**Process:**
1. Investigate the `👀` folder (7.8 GB — unknown content, needs manual review)
2. Catalog meaningful documents (PDFs, text files) from `Downloads/`, `Desktop/`, loose files
3. Check Day One iCloud Drive data (20 MB) against Dropbox archive for overlap
4. Skip app-specific data (Clips, Sketches, Playgrounds, etc.) unless it contains documents
5. Insert meaningful items into `catalog.db`, run doc pipeline on PDFs if warranted

**Value:** Variable — depends on what's in the unknown folders. The PDFs and documents have clear value; app data is mostly low-signal.

### 5. Small Sources → Deferred

iCloud Mail, Contacts, Calendars, Bookmarks, and Apple service data are valuable for timeline enrichment but low priority. They're small, structured, and can be ingested later when the catalog is proven.

**Future value:**
- Contacts → cross-reference with people registry
- Calendars → event dates for timeline reconstruction
- Mail → communication patterns and dates
- Bookmarks → interests over time

---

## Dedup Strategy

The primary dedup concern: Day One photo attachments vs. iCloud Photos.

**Approach:**
1. Day One attachments use hash-based filenames (e.g., `a1b2c3d4e5f6.jpg`)
2. Apple's Photo Details CSVs include `fileChecksum` for every iCloud photo
3. Compute SHA-256 of Day One attachments
4. Cross-reference against Apple checksums (may need to determine if Apple uses SHA-256 or a different hash)
5. Mark duplicates in the catalog's asset table — both copies get rows, with a `duplicate_of` field linking them
6. Never delete duplicates — just mark them. Both sources are canonical in their own context.

**Secondary dedup:** Within the 20 iCloud Photos parts, Apple should not have duplicated files, but the catalog will detect it if they did (same checksum, different paths).

---

## Integration with Unified Catalog

This plan feeds directly into the `catalog.db` design from the unified catalog discussion:

```
catalog.db
├── assets table     ← every photo, video, note, journal entry, document
├── entities table   ← people, dates extracted from text content (Phase 2)
└── entity_assets    ← cross-references (Phase 2)
```

The personal branch adds these content types to the catalog:
- `photo` — iCloud Photos (HEIC, JPG, PNG, etc.)
- `video` — iCloud Photos (MOV, MP4)
- `note` — iCloud Notes (.txt files)
- `journal` — Day One entries (.md files)
- `document` — meaningful docs from iCloud Drive

The same catalog serves both Family and Personal branches. A query like "everything from 1999" could return family scanned photos AND personal journal entries.

---

## What This Enables

With the catalog and FTS5 index populated:

- **"What was happening in March 2015?"** → Returns photos taken that month, journal entries from those dates, notes created then
- **"Find everything mentioning Taiwan"** → FTS5 search across notes, journals, documents
- **"Timeline of 2018"** → Every cataloged asset with a 2018 date, sorted chronologically
- **Cross-referencing:** A journal entry about a trip + photos from the same dates + notes about planning the trip — connected by date in the catalog
- **Future AI analysis:** Point a model at a date range and give it photos + text from that period. The catalog makes the selection; the model does the analysis.

---

## Open Questions

1. **`👀` folder (7.8 GB):** What's in it? Needs manual investigation before deciding whether to catalog.
2. **Apple checksum format:** Are the `fileChecksum` values in Photo Details CSVs SHA-256, or something else? Determines whether dedup against Day One is a direct hash comparison or needs conversion.
3. **Notes dedup:** Some notes appear to have duplicate text files (`-1.txt` suffix). Are these Apple export artifacts or actual versioned content?
4. **Shared Album "SWEI":** Is this a shared album with family photos? Could bridge personal and family branches.
5. **Day One on NAS:** Should Day One live at `Personal/Day One/` or somewhere else? It predates the Apple export and has a different provenance.
6. **iCloud Drive app data:** Any of the app-specific folders (WhatsApp, iBooks, etc.) contain content worth preserving?

---

## Execution Phases

### Phase 0: Day One copy
Copy Day One archive from Dropbox to NAS `Personal/Day One/`. One manual operation.

### Phase 1: Photo catalog (highest asset count)
Parse all 640 Photo Details CSVs, match to files, populate catalog. ~26,000 assets.

### Phase 2: Notes ingestion
Parse Notes Details CSV, read all .txt files, populate catalog + FTS5. ~949 notes, 2,700 text files.

### Phase 3: Journal ingestion
Parse Day One YAML frontmatter + markdown body, populate catalog + FTS5. ~918 entries.

### Phase 4: Dedup pass
Cross-reference Day One attachment hashes against iCloud Photos checksums. Mark duplicates.

### Phase 5: iCloud Drive triage
Investigate `👀` folder. Catalog meaningful documents. Skip app data.

### Phase 6: Small sources (deferred)
Contacts, Calendars, Mail, Bookmarks — when the catalog is proven and there's a use case.

---

*This document captures the personal data organization plan. Implementation tracked in BACKLOG.md.*
