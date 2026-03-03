# Architecture Layer Separation — Moving Off NAS

**Date:** 2026-03-02
**Trigger:** Dashboard latency. Loading the archive dashboard exposed how slow NAS-backed data access is for any interactive use case.

## The Problem

All three layers (data, AI, presentation) currently live on NAS. This was a natural starting point — source files are there, so AI output was written next to them, and Immich runs on the NAS too. But anything interactive (dashboard queries, image serving, catalog lookups) pays AFP network latency on every operation.

The dashboard made this visceral. It's not a bug — it's an architecture smell.

## Decisions

### Layer separation

**Keep the data layer on NAS.** Source TIFFs, PDFs, and raw scans are canonical and large. NAS is the right home. Pipeline runs mount NAS to read sources.

**Move the AI layer local.** `catalog.db`, manifests, extracted text, FTS5 index — all regeneratable, all small (tens of MB). These live in-repo under `data/` (gitignored). The pipeline reads from NAS but writes locally. Every dashboard query, search, and catalog operation becomes instant.

**Move presentation images local, then hosted.** The pipeline already converts TIFFs to JPEGs during analysis, then discards them. Instead, keep them as derived presentation assets in WebP format.

**New data flow:**

```
NAS (cold storage)          Local repo data/ (working)      Hosted (served)
─────────────────          ──────────────────────           ───────────────
Source TIFFs/PDFs    →     catalog.db                       WebP images (R2)
                           manifests/                       Blog (Vercel)
                           extracted text + FTS5            Family viewer
                           optimized images (dev)     →
```

### Local `data/` directory structure

The current NAS layout splits the AI layer across three locations because it was co-located with source data (`Family/Media/_ai-layer/`, `Family/Documents/_ai-layer/`, `Family/_ai-layer/catalog.db`). Moving local removes that reason. Consolidate under one root, but keep the internal structure (runs, manifests, SHA-256 keying) — it's well-designed.

```
data/                              # gitignored
├── catalog.db                     # unified asset index
├── people/
│   └── registry.json              # face cluster registry
├── photos/
│   └── runs/<timestamp>/
│       ├── manifests/             # per-photo JSON keyed by SHA-256[:12]
│       └── run_meta.json
├── documents/
│   └── runs/<timestamp>/
│       ├── manifests/             # per-doc JSON keyed by SHA-256[:12]
│       ├── extracted-text/        # raw OCR output
│       ├── index.db               # FTS5 search index
│       └── run_meta.json
└── images/                        # derived presentation images
    ├── thumb/                     # ~400px, WebP q75, ~40KB each
    ├── display/                   # ~1600px, WebP q80, ~200KB each
    └── full/                      # ~2048px, WebP q85, ~400KB each
```

Images keyed by same SHA-256[:12] as manifests: `data/images/thumb/abc123def45.webp`.

For ~8,000 photos: ~6GB total across all tiers. Trivially local during dev, trivially hostable (Cloudflare R2: 10GB free, zero egress).

### Pipeline migration — clean break

No dual-writing to NAS. The AI layer is defined as regeneratable — the NAS copies don't gain value by being kept current.

**Cutover:**
1. Copy existing manifests, catalog, extracted text, registry from NAS into local `data/`
2. Update `config.AI_LAYER_DIR` and `config.DOC_AI_LAYER_DIR` to point into `data/`
3. Next pipeline run writes locally

Old NAS `_ai-layer/` directories sit inert — a backup by default. Nothing reads or writes to them. The pipeline still mounts NAS to read source files; only the output side changes.

### Image generation — baked into pipeline + backfill command

The analysis pipeline already reads source files and converts to JPEG for Claude. The change: keep the converted image and also generate smaller sizes while the source is in memory. Negligible overhead (a couple of Pillow resize calls).

**During normal pipeline run:**
1. Read source from NAS (already happens)
2. Generate full → display → thumb WebP images, write to `data/images/{tier}/{sha256[:12]}.webp`
3. Send full to Claude for analysis (already happens)
4. Write manifest (already happens, just new path)

**For ~800 already-analyzed photos:**
```
python -m src.generate_images --backfill
```
Reads source files from NAS, generates three tiers, writes to `data/images/`. No inference, no manifests — just image conversion. Run once to catch up.

**Format/quality:** WebP everywhere. Thumb q75, display q80, full q85.

## Immich Evaluation

Immich is excellent software for its intended purpose (self-hosted Google Photos replacement). But this project has outgrown what it offers:

**What Immich provides that still matters:**
- Face clustering via InsightFace/buffalo_l — genuine ML infrastructure

**What Immich provides that we've already replaced or don't need:**
- Photo browsing/timeline — our catalog has richer metadata
- CLIP semantic search — our FTS5 over AI descriptions is more relevant
- Mobile auto-backup — sources are scanned media, not phone photos
- EXIF metadata storage — our manifests are far richer
- External library mounting — this is actually causing the NAS coupling

**What Immich can't do that we need:**
- Unified photo + document browsing
- Bilingual metadata display (EN/ZH from manifests)
- Blog/methodology integration
- Confidence-based workflow views
- Cross-collection FTS5 search
- Custom presentation matching our design system

**Conclusion:** Immich was the right bootstrapping choice. It gave us a viewer, face clustering, and family access quickly. But the project needs a bespoke presentation layer. Face cluster data is already extracted to `_ai-layer/people/registry.json`. Immich can stay running as a legacy viewer while the new presentation layer is built.

### Presentation layer — standalone app, merges dashboard + review

Two existing tools share the same pattern (single-file HTML + Python http.server + atlas-style-guide tokens):
- **Archive dashboard** (`dashboard.html` + `src/dashboard.py`, port 8378) — read-only stats, pipeline health, search. Currently slow because it reads from NAS.
- **Review dashboard** (`review.html` + `src/review.py`, port 8377) — human-in-the-loop for approving/correcting AI manifests. Serves images, writes back to manifests.

**Decision: merge into one app.** Both read from the same data, share the same design language, and will both benefit from reading local `data/`. One tool, tabbed views:

| View | Purpose | Access |
|------|---------|--------|
| Overview | Archive stats, health, pipeline history | Public |
| Browse | Photo grid, search, filters, bilingual metadata | Public |
| Search | FTS5 across photos + documents | Public |
| Review | Approve/correct AI analysis, confidence queues | Admin only |

**Standalone, not inside headless-atlas.** The data that drives it is separate from headless-atlas. headless-atlas serves as a launchpad (links to the archive app) but doesn't contain it. Own repo or directory, own deployment.

**Starts local, goes public.** During dev it reads from `data/` and serves locally. When ready, deploy with images hosted on R2/CDN. The review tab becomes auth-gated; everything else is open.

**Family access:** The family viewer was never launched via Immich. Instead of building a separate family view, the public app serves that purpose. Family members access the same browse/search interface as anyone else.

**Stack:** Next.js + Vercel is the natural fit (existing infrastructure, atlas-style-guide compatibility, easy auth for admin routes). Decision deferred to implementation time.

**Design:** Consumes atlas-style-guide tokens. Phosphor Icons (light weight). Dark theme as default (matching existing dashboards).

## What This Means for the Backlog

This session reshapes several backlog items:
- Pipeline output paths need to change (write to `data/` not NAS `_ai-layer/`)
- Image conversion step becomes a permanent output (keep derived images)
- `dashboard.html` + `review.html` merge into a new standalone app
- Blog/public view and family view collapse — one app serves both
- Immich push becomes optional rather than core
- headless-atlas links to the archive app at its own domain/subdomain

## Resolved Questions

- **Sync strategy:** Clean break. Local `data/` is canonical for the AI layer. NAS `_ai-layer/` sits inert as incidental backup.
- **Image generation timing:** Generate all three tiers during pipeline run (source is already in memory). Backfill command for existing assets.
- **Directory structure:** Consolidate three NAS `_ai-layer/` locations into one `data/` root. Mirror internal structure (runs/manifests/SHA-256 keying).
- **Image format:** WebP everywhere. Sensible quality defaults (thumb 75, display 80, full 85).
- **Presentation layer:** Standalone app merging dashboard + review. Not inside headless-atlas.
- **Family access:** No separate family viewer. Public app serves that purpose.

## Open Questions

- **App stack:** Next.js + Vercel is the leading candidate. Confirm at implementation time.
- **Face clustering future:** With Immich deprecated, do we run InsightFace independently, or is the current registry sufficient?
- **Image hosting:** R2 is the leading candidate. When does local-only dev transition to hosted? What triggers the push?
- **Domain:** Subdomain (`archive.kennyliu.io`) or path (`kennyliu.io/archive`)?
