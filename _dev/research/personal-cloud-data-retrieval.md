# Personal Cloud Data Retrieval — Intent Document

**Created:** January 19, 2026
**Status:** Planning
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

### Phase 1: Data Request

1. Request data export from Apple via privacy.apple.com
2. Document the request process (screenshots, timeline)
3. Inventory what Apple provides vs. what's missing

### Phase 2: Initial Organization

1. Download and extract all provided data
2. Catalog by data type (photos, documents, notes, etc.)
3. Identify date ranges and gaps
4. Cross-reference with Day One archive timeline

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

- [ ] Complete iCloud data export received and inventoried
- [ ] Photos deduplicated against Day One archive
- [ ] Organized folder structure established
- [ ] At least one blog post documenting the process
- [ ] Reusable workflow template added to public repo

---

## Open Questions

1. **Storage location:** Should personal cloud exports live alongside Day One archive, or in a separate location?

2. **Photo management:** Use existing tools (Apple Photos, Google Photos) for viewing, or build custom solution?

3. **Obsidian integration depth:** Full integration with daily notes, or standalone archive?

4. **Scope expansion:** Include other services (Google, Dropbox, social media) in this effort?

---

## Timeline

No specific dates—progress tracked by milestones above. This work proceeds alongside family archive scanning, which is nearly complete.

---

*This document is part of the Living Archive `_dev` folder for process documentation and planning.*
