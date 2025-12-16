# Every Branch Archive Project Brief

**Project Name:** Every Branch  
**Project Owner:** Kenny Liu  
**Last Updated:** December 16, 2025  
**Status:** In Development

---

## Naming Convention

| Version | Use Case |
|---------|----------|
| **Every Branch** | Site name, logo, what you say out loud |
| **Every Branch Archive** | Subtitle or tagline context |
| **The Every Branch Archive** | Formal reference in documents |
| **Every Branch Archive Project** | Internal project management |

---

## Project Purpose

A long-term archival project to digitize, organize, and preserve the Liu family history — correcting the historical omission of women from traditional patrilineal records, and creating an accessible, bilingual resource for current and future family members.

Secondary purpose: Personal learning in organizing complex bodies of information and building systems designed for multi-generational longevity.

---

## Background

The Liu family possesses a "red book" (族譜) originally printed in 1983, documenting the male lineage from the first recorded Liu ancestor to that date. A reprint with updated information through 2025 is planned for **April 2026**.

The traditional record excludes all female family members — mothers, daughters, sisters. Every Branch aims to digitize the existing record and systematically add the missing women, creating a more complete family history.

Additionally, thousands of family photos and historical documents exist in physical form. These are being digitized to create a preserved, searchable archive.

---

## Scope

### In Scope (V1 — Liu Side)
- Digitization of family photos (in progress, ~50% complete)
- Digitization of historical documents and letters
- Digitization and parsing of the 2026 red book reprint
- Genealogy database including women omitted from traditional records
- Bilingual presentation (English / Traditional Chinese)
- Archival website with tiered access (public/private)
- Elder interviews and oral history capture
- Documentation for long-term project succession

### Out of Scope (Deferred)
- Peng family (maternal side) genealogy
- AI model training on photo dataset (future phase, dependent on clean labeled data)
- Active outreach to distant relatives (to be evaluated after V1 foundation)

---

## Content Types

| Type | Description | Current Status |
|------|-------------|----------------|
| Photographs | Physical family photos spanning multiple generations | ~50% digitized |
| Red Book | Traditional genealogy record (1983, 2026 reprint) | Awaiting April 2026 |
| Letters & Documents | Historical family correspondence, immigration papers, etc. | Not started |
| Oral Histories | Recorded interviews with elders | Not started |
| Genealogy Data | Structured family tree including women | Not started |

---

## Key Constraints

### Privacy
- Some family members may object to having information/photos online
- Wealthy family members likely more sensitive about privacy
- Requires tiered access system and possibly individual consent process

### Language
- Red book is in Traditional Chinese
- Site must be fully bilingual (English / Traditional Chinese)
- Translation work required for documents and interface

### Longevity
The following must be addressed for multi-generational durability:
- [ ] Domain ownership succession plan
- [ ] Long-term hosting cost structure
- [ ] Maintenance documentation for non-technical family members
- [ ] Data backup and redundancy strategy
- [ ] "Bus factor" contingency (what happens if owner is incapacitated)
- [ ] Technology choices that minimize future migration needs

*These will be developed as the project progresses and documented in a dedicated succession plan.*

---

## People

### Project Owner
**Kenny Liu** — Currently serving all roles: archivist, developer, project coordinator, interviewer.

### Key Sources
- **Ryan Liu** — Custodian of the red book. Aware of project, potential collaborator.
- **Three living elders** — Priority for oral history interviews. Health/memory time-sensitive.

### Potential Collaborators
- Not yet identified. Family outreach not yet initiated.
- Skills that would be valuable: translation (Chinese), photography/scanning, genealogy research, web development.

---

## Technical Approach

### Current Infrastructure
- Ghost CMS (headless) — already in use for atlas.kennypliu.com
- Every Branch will initially piggyback on existing infrastructure

### Future Considerations
- Static site generation for longevity (less dependency on active maintenance)
- Database structure for genealogy queries
- Image hosting and CDN for large photo archive
- Search functionality across bilingual content
- GitHub sync for content version control and portability

### Software Research Needed
- Genealogy database software evaluation (Gramps, FamilySearch, custom solution)
- OCR/parsing tools for red book digitization
- Photo metadata and tagging systems
- Potential open-source contribution if custom tools are built

---

## Workstreams

| Workstream | Description | Status | Owner |
|------------|-------------|--------|-------|
| Media Digitization | Scanning photos and documents | In progress (~50%) | Kenny |
| Family Communications | Outreach, consent, collaboration | Not started | Kenny |
| Elder Interviews | Oral history capture | Planned (Taiwan trip April 2025?) | Kenny |
| Tech & Software Research | Evaluate tools, design data model | Early exploration | Kenny |
| Data Modeling | Structure for genealogy + photo metadata | Not started | Kenny |
| Website Development | Bilingual archival site with tiered access | Not started | Kenny |
| Succession Planning | Documentation for long-term handoff | Not started | Kenny |

---

## Timeline & Milestones

### Now → April 2026 (Red Book Arrival)
**Goal:** Foundation ready to receive and process the red book.

- [ ] Complete photo digitization (100%)
- [ ] Complete document digitization (letters, papers)
- [ ] Conduct elder interviews (Taiwan trip April 2025)
- [ ] Finalize genealogy data structure
- [ ] Establish photo metadata schema
- [ ] Research/select OCR solution for red book parsing
- [ ] Create basic website structure (even if minimal content)
- [ ] Publish project overview to atlas.kennypliu.com

### April 2026 → TBD
- [ ] Digitize and parse red book
- [ ] Begin systematic addition of women to genealogy
- [ ] Cross-reference photos with genealogy data
- [ ] Populate website with organized content
- [ ] Establish tiered access controls
- [ ] Document succession plan

---

## Open Questions

1. **Consent process:** How to handle family members who object to inclusion? Opt-out vs. opt-in?
2. **Red book parsing:** Is OCR sufficient, or will manual transcription be required for handwritten sections?
3. **Hosting longevity:** What's the 50-year hosting strategy? Endowment? Family contribution? Institutional partnership?
4. **Collaboration model:** If family members want to contribute, what's the workflow?
5. **Name reconciliation:** How to handle multiple romanizations of Chinese names, married names, generational names?

---

## Success Criteria

**Minimum Viable Archive:**
- All accessible photos and documents digitized and organized
- Red book digitized with women added to genealogy
- Bilingual website accessible to family members
- At least one elder interview captured

**Aspirational:**
- Comprehensive oral history collection
- Interactive family tree with photo integration
- Model for other families to fork/adapt (open source tooling)
- Sustained by family beyond original project owner

---

## Related Links

- Project page: https://atlas.kennypliu.com/tools
- *Every Branch site: TBD*
- *GitHub repo: TBD*
- *Photo archive location: TBD*
- *Genealogy database: TBD*

---

## Revision History

| Date | Changes |
|------|---------|
| 2025-12-16 | Initial project brief created |
| 2025-12-16 | Renamed from "Liu Family Archive" to "Every Branch" naming convention |

---

*This document serves as the living reference for project scope, decisions, and progress. Update as the project evolves.*
