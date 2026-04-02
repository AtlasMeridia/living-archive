# Living Archive — Project Brief

**Project Name:** Living Archive
**Project Owner:** Kenny Liu / ATLAS Meridia LLC
**Last Updated:** April 2, 2026
**Status:** Active — pipelines running, publicly accessible, family onboarding in progress

---

## What This Is

Living Archive is two things at once:

1. **A working system** — AI-assisted pipelines that analyze scanned photos and family documents, produce structured metadata, and push it into Immich for browsing and sharing. Four-machine architecture: NAS (source data), local Mac (pipeline execution), VPS (Immich at `living-archive.dev`, dashboard at `dashboard.living-archive.dev`), with AI-generated metadata stored locally and synced.

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

Four-machine topology: NAS for source data, Mac for pipeline execution, VPS for public presentation.

| Layer | Location | Contents |
|-------|----------|----------|
| **Data** | NAS (read-only) | Source TIFFs, PDFs — canonical, never modified |
| **AI** | Local Mac (regeneratable) | JSON manifests, extracted text, FTS5 index, asset catalog, synthesis DB, people registry — keyed by SHA-256 |
| **Presentation** | VPS (Immich v2.6.3) | Photos at `living-archive.dev`, dashboard at `dashboard.living-archive.dev` |

### Photo Pipeline

TIFF/JPEG scans → analysis-ready JPEG normalization → Max Plan-backed Claude (photo pipeline defaults to OAuth SDK mode) → structured JSON manifests → Immich metadata push. Confidence-based routing: high (≥0.8) auto-applies, medium (0.5–0.8) routes to "Needs Review" album, low (<0.5) routes to "Low Confidence" album.

### Document Pipeline

PDFs → Claude text extraction and analysis (document type, dates, key people, sensitivity) → manifests + extracted text files → SQLite FTS5 full-text search index.

### Face Recognition

Immich's ML-based face clustering (buffalo_l model) linked to a people registry in the AI layer, with a sync script to map clusters to named people.

### Synthesis Layer

Reads all manifests to build an entity graph — person deduplication (normalization, fuzzy matching, LLM clustering), timeline chronology with quality controls, and cross-referencing across people, photos, dates, and locations. Promoted from experiment 0002, fully integrated with the dashboard.

### Dashboard

Interactive single-page web UI with six tabs: Overview (stats, coverage), Photos, Documents, Synthesis (entity queries, chronology), People (face cluster naming), and Toolbox (CLI inventory). Runs locally, queries `catalog.db` and `synthesis.db` — fully offline, no NAS required.

### Infrastructure

- Immich v2.6.3 on Hetzner VPS, public via Cloudflare Tunnel
- NAS auto-mount via SMB with retry logic
- Preflight checks (NAS mount, Immich health, config validation)
- CLI entry points for each pipeline stage (12 commands)
- Pydantic models, structured logging, 82 tests across 11 files

---

## The Case Study: Liu Family Archive

The ongoing work of digitizing and organizing the Liu family history drives development and serves as proof of concept.

**Completed:**
- 3,687 photo assets currently indexed in the local AI layer catalog (as of 2026-04-02; recent no-push batches still require downstream Immich metadata push/sync)
- 121 family documents analyzed (Liu Family Trust — 468 pages, 26 document types)
- Full-text search index built over extracted document text (FTS5)
- Face recognition running on VPS Immich, people registry synced
- Synthesis layer operational — entity graph, timeline chronology, cross-referencing
- In-browser people naming modal ready for elder knowledge capture
- Immich live at `living-archive.dev` with invite-based family access
- Dashboard deployed at `dashboard.living-archive.dev` (stats, synthesis, people, conversational interface)

**In progress:**
- 2nd Round Digital Revolution Scans (3,599 photos, 10 albums)
- 3rd Round Digital Revolution Scans (2,372 photos, 6 albums)
- Liu Family Scans non-overlapping folders (~2,806 photos)
- Elder knowledge capture session for face naming (blocked on scheduling)

**Future:**
- 726 GB Apple data export (personal photos, iCloud Drive, Notes, Mail)
- Red book (族譜) — traditional Chinese genealogy OCR (April 2026)
- Elder interview capture — oral history
- Day One journal cross-referencing (918 entries, 1999–2024)
- Blog series at `kennyliu.io/living-archive` (Ghost CMS)

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

2. **Curation layer:** Immich shows everything including low-confidence and review-routed items. For family and public audiences, curated albums (by decade, event, or person) would make the first experience more meaningful than raw pipeline output.

3. **Public vs. private:** The methodology and code are public. Family-specific data (manifests, registry, extracted text) stays local. But where's the line for blog content? How much of the family story is shareable?

4. **Content strategy:** The blog exists in concept but has zero posts. What's the first piece — a methodology overview, a technical walkthrough of the pipeline, or a personal narrative about why this matters?

5. ~~**Dashboard deployment:**~~ Resolved 2026-03-20. Dashboard deployed at `dashboard.living-archive.dev` via Docker on VPS, git-based deploys.

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
| 2026-03-19 | Updated to reflect VPS migration, current scale (1,773 photos, 121 docs), synthesis layer, dashboard, and public access |
| 2026-03-25 | Domain migration: `living-archive.kennyliu.io` → `living-archive.dev`. Dashboard deployment resolved. All URLs updated. |
| 2026-04-02 | Updated runtime facts: Immich v2.6.3, SMB mount language, OAuth photo inference default, and local AI-layer asset counts. |

---

*This document defines what Living Archive is and where it's headed. Task tracking lives in BACKLOG.md.*
