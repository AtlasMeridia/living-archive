# Personal Cloud Data Retrieval — Intent Document

**Created:** January 19, 2026
**Status:** In Progress (Phase 2 complete)
**Scope:** Personal leg of Living Archive case study

---

## Purpose

This document outlines the plan to retrieve, organize, and integrate personal data from cloud services—specifically Apple iCloud—into the Living Archive methodology. This effort complements the Liu family archive work by preserving personal digital history alongside family records.

---

## Context

### Existing Assets

**Day One Journal Archive** (already converted)
- Location: `~/Dropbox/ATLASM Obsidian/00 Inbox/Daily/_dayone archive/`
- **918 markdown entries** spanning 1999–2024 (25+ years)
- Organized by YYYY-MM folders with YYYY-MM-DD.md files
- YAML frontmatter with dates, tags, and journal sources
- Photo attachments preserved with hash-based filenames
- Already Obsidian-compatible with wiki-link syntax

This archive represents a significant personal record that predates and overlaps with the iCloud photo library.

### Data to Retrieve

**Apple iCloud** (account active since ~2013)
- Photos and videos from iOS devices
- iCloud Drive documents
- Notes
- Contacts and calendars
- Health data (if exportable)
- Messages (if exportable)

---

## Relationship to Living Archive

This work serves multiple purposes within the Living Archive project:

1. **Personal case study** — Demonstrates the methodology for retrieving data from major cloud platforms, documenting pain points and solutions

2. **Content for blog** — The process of requesting and organizing iCloud data becomes publishable content at atlas.kennypliu.com/living-archive

3. **Cross-reference opportunity** — iCloud photos from 2013+ can be matched with Day One journal entries from the same period, enriching both datasets

4. **Template development** — Workflows developed here become reusable templates in the public repository

---

## Approach

### Phase 1: Data Request ✅

1. Request data export from Apple via privacy.apple.com
2. Document the request process (screenshots, timeline)
3. Inventory what Apple provides vs. what's missing

**Completed:** February 7, 2026. Apple delivered 42 zip files (~780GB) to `~/Desktop/Personal Data/`. Export includes iCloud Photos (20 parts), iCloud Drive, Notes, Contacts, Mail, Bookmarks, Calendars & Reminders, Apple Media Services, and various metadata archives.

### Phase 2: Initial Organization ✅

1. Download and extract all provided data
2. Catalog by data type (photos, documents, notes, etc.)
3. Identify date ranges and gaps
4. Cross-reference with Day One archive timeline

**Completed:** February 9–10, 2026. All 42 zips extracted to NAS via `ditto -x -k` over AFP. 25 nested zips within the archives were also extracted in-place. Originals moved to macOS Trash.

**NAS structure established:**
```
/Volumes/MNEME/05_PROJECTS/Living Archive/
├── Family/
│   ├── Documents/   (2.7GB — existing Liu family archive)
│   └── Media/       (286GB — existing family scans)
└── Personal/
    ├── iCloud Photos Part 1–20 of 20/
    ├── iCloud Drive/
    ├── iCloud Notes/
    ├── iCloud Contacts/
    ├── iCloud Mail/
    ├── iCloud Bookmarks/
    ├── iCloud Calendars and Reminders/
    ├── Apple Media Services Information Part 1 of 2/
    ├── Game Center/  (from Apple Media Services Part 2)
    ├── Other Data Part 1–6 of 7/
    ├── Devices Registered with Apple Messaging.json  (from Other Data Part 7)
    ├── Apple Account and device information/
    ├── Apple.com and Apple Store/
    ├── AppleCare/
    ├── App install and push notification activity/
    ├── Feedback Assistant activity/
    ├── Marketing communications/
    └── Wallet Activity/
```

**Extraction stats:** 39,959 files, 726GB on NAS. Zero failures. Full log at `~/Desktop/apple-extract-20260209-171534.log`.

### Phase 3: Photo Integration

1. Deduplicate against Day One attachments (hash comparison)
2. Identify photos that exist in both sources
3. Organize by date with consistent naming
4. Decide on storage location (local archive vs. cloud backup)

### Phase 4: Metadata Enrichment

1. Extract EXIF data from photos
2. Use Day One entries to add context to photos from same dates
3. Tag photos with people, locations, events where identifiable
4. Link to Liu family archive where family members appear

### Phase 5: Integration with Obsidian

1. Determine final location within Obsidian vault structure
2. Create index/MOC files for navigation
3. Link journal entries to corresponding photos
4. Build "on this day" or timeline views

---

## Technical Considerations

**Storage**
- Raw exports preserved as-is (data layer principle)
- Working copies organized for daily use
- Backup strategy aligned with Living Archive standards

**Deduplication**
- SHA-256 hashing (matches Day One attachment naming)
- Keep originals, mark duplicates rather than delete

**Privacy**
- Personal data stays local (not in public repo)
- Document methodology publicly, not content
- Consider what's shareable vs. private in eventual archive

---

## Success Criteria

- [x] Complete iCloud data export received and inventoried
- [ ] Photos deduplicated against Day One archive
- [x] Organized folder structure established
- [ ] At least one blog post documenting the process
- [ ] Reusable workflow template added to public repo

---

## Open Questions

1. **Storage location:** ~~Should personal cloud exports live alongside Day One archive, or in a separate location?~~ **Resolved:** Personal data lives on MNEME NAS at `Living Archive/Personal/`, alongside the family archive at `Living Archive/Family/`. Both tracks share the same project root.

2. **Photo management:** Use existing tools (Apple Photos, Google Photos) for viewing, or build custom solution?

3. **Obsidian integration depth:** Full integration with daily notes, or standalone archive?

4. **Scope expansion:** Include other services (Google, Dropbox, social media) in this effort?

---

## Timeline

- **Phase 1 completed:** February 7, 2026 (Apple data export delivered)
- **Phase 2 completed:** February 9–10, 2026 (extraction and NAS organization)
- **Phase 3–5:** Not yet scheduled — proceeds alongside family archive work

---

*This document is part of the Living Archive `_dev` folder for process documentation and planning.*
