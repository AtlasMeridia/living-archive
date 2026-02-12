# Living Archive — Project Brief

**Project Name:** Living Archive
**Project Owner:** Kenny Liu / ATLAS Meridia LLC
**Last Updated:** February 11, 2026
**Status:** Active — pipelines running, documentation catching up

---

## What This Is

Living Archive is two things at once:

1. **A working system** — AI-assisted pipelines that analyze scanned photos and family documents, produce structured metadata, and push it into Immich for browsing and sharing. Built on a Synology NAS with a three-layer architecture separating source data, AI-generated metadata, and presentation.

2. **A methodology experiment** — can a single person, aided by AI, meaningfully organize a family's worth of analog and digital records? The system validates the methodology; the methodology gives the system purpose.

The code is real infrastructure that runs against real family archives. The methodology is documented in the repo and (eventually) the blog, so others can adapt the approach to their own families.

---

## The Problem

People accumulate:
- Thousands of photos across devices and cloud services
- Hundreds of online accounts with no documentation
- Physical documents with no digital backup
- Family knowledge that exists only in elders' memories
- No clear plan for what happens to any of it

The "green box" concept from estate planning — an organized collection of documents and instructions for survivors — doesn't scale to digital life. And preparing for death feels morbid, so people procrastinate indefinitely.

**Reframe:** This isn't about preparing to die. It's about knowing where everything is. The person who has their digital life organized is incidentally prepared for incapacity or death.

AI changes the equation. An agent can analyze photos, extract text from documents, and produce structured metadata at a scale that makes archival work practical for individuals. The methodology stays relevant as the AI improves — manifests are versioned per inference run and designed to be regenerated.

---

## What's Been Built

### Architecture

Three-layer separation on a Synology NAS (DS923+), with inference running on a MacBook Pro (M3 Pro):

| Layer | Location | Contents |
|-------|----------|----------|
| **Data** | NAS (read-only) | Source TIFFs, PDFs — canonical, never modified |
| **AI** | NAS (regeneratable) | JSON manifests, extracted text, FTS5 index, people registry — keyed by SHA-256 |
| **Presentation** | Immich | Metadata, albums, face tags — populated via API |

### Photo Pipeline

TIFF scans → JPEG conversion → Claude Vision API (Sonnet) → structured JSON manifests → Immich metadata push. Confidence-based routing: high (≥0.8) auto-applies, medium (0.5–0.8) routes to "Needs Review" album, low (<0.5) routes to "Low Confidence" album.

### Document Pipeline

PDFs → Claude text extraction and analysis (document type, dates, key people, sensitivity) → manifests + extracted text files → SQLite FTS5 full-text search index.

### Face Recognition

Immich's ML-based face clustering (buffalo_l model) linked to a people registry in the AI layer, with a sync script to map clusters to named people.

### Infrastructure

- NAS auto-mount via AFP with retry logic
- Preflight checks (NAS mount, Immich health, config validation)
- CLI entry points for each pipeline stage
- Pydantic models, structured logging, 37 tests

---

## The Case Study: Liu Family Archive

The ongoing work of digitizing and organizing the Liu family history drives development and serves as proof of concept.

**Completed:**
- 62 scanned photos processed (1978, 1980–1982 slices) with bilingual metadata
- 72 family documents analyzed (Liu Family Trust — 468 pages, 26 document types)
- Full-text search index built over extracted document text
- Face recognition running — 1,241 clusters from Immich ML, people registry seeded
- Metadata live in Immich with confidence-based review albums

**In progress:**
- 6 more photo slices from 2009 Scanned Media (~133 photos)
- 44 medium/large documents needing page-range chunking
- Elder knowledge capture for face identification
- Epson FastFoto FF-680W acquired for bulk scanning of remaining physical photos

**Future:**
- 726 GB Apple data export (personal photos, iCloud Drive, Notes, Mail)
- Red book (族譜) — traditional Chinese genealogy OCR (April 2026)
- Elder interview capture — oral history
- Day One journal cross-referencing (918 entries, 1999–2024)

---

## Audience

**Primary:** Individuals organizing their own digital lives — the methodology and prompts are reusable even if the specific infrastructure differs.

**Secondary:**
- Families dealing with a deceased relative's digital estate
- People helping aging parents get organized
- Estate planners and professionals

---

## Relationship to Other Projects

| Project | Relationship |
|---------|--------------|
| **Hinterland Atlas** | Living Archive may become a vertical within HA. Both involve documentation, memory, place. |
| **ATLAS Meridia** | Living Archive is developed under ATLASM for business/expense purposes |
| **AEON** | Separate project — both use AI for organization but different domains |

---

## Open Questions

1. **Personal data branch:** The system was built for the family archive. 726 GB of personal Apple data needs a different approach — HEIC not TIFF, different directory structure, dedup against existing family photos. How does the three-layer model extend?

2. **UI beyond Immich:** Immich covers photo browsing, but there's no interface for document search (FTS5 index is SQLite-only), no cross-collection browsing, no unified dashboard. What does "showing this publicly" look like?

3. **Public vs. private:** The methodology and code are public. Family-specific data (manifests, registry, extracted text) stays on the NAS. But where's the line for blog content? How much of the family story is shareable?

4. **Content strategy:** The blog exists in concept but has zero posts. What's the first piece — a methodology overview, a technical walkthrough of the pipeline, or a personal narrative about why this matters?

---

## Success Criteria

**Minimum:**
- All family photo slices processed with metadata in Immich
- Document search functional for Liu Family Trust collection
- Family members can browse the archive remotely
- At least one published blog post documenting the approach

**Aspirational:**
- Personal data integrated alongside family archive
- Red book digitized and cross-referenced with photo metadata
- Recognized resource in the "digital estate" / "digital organization" space
- Methodology adopted by at least one other family

---

## Revision History

| Date | Changes |
|------|---------|
| 2025-12-16 | Initial project brief as "Every Branch Archive" |
| 2026-01-11 | Major reframe: renamed to "Living Archive," shifted from family archive to methodology/content project |
| 2026-02-11 | Reconciled with reality: acknowledged working system alongside methodology, added architecture and case study sections, removed completed action items (now in BACKLOG.md) |

---

*This document defines what Living Archive is and where it's headed. Task tracking lives in BACKLOG.md.*
