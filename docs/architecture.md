# Living Archive Architecture

Infrastructure documentation for the Living Archive project.

## Four-Machine Topology

| Machine | Hostname | Role | Access |
|---------|----------|------|--------|
| **NAS (DS923+)** | `mneme` | Storage (source media, read-only) | SSH, Tailscale |
| **EllisAgent (M3 Pro)** | `ellis-mbp` | Secondary / legacy execution node | Local, Tailscale |
| **Atlas (M4 Max)** | `atlas` | Primary execution host, strategy, Claude/Hermes | Local, Tailscale |
| **VPS (Hetzner CPX21)** | `living-archive-vps` | Immich v2.6.3, presentation | Tailscale, Cloudflare Tunnel |

## Data Flow

```
DATA LAYER (NAS, read-only)                    AI LAYER (local, regeneratable)            PRESENTATION (VPS)
/Living Archive/Family/Media/            →    data/photos/runs/manifests/         →    Immich v2.6.3 REST API
  Source TIFFs/JPEGs, never modified           one JSON per photo, keyed by SHA-256     PUT /assets, POST /albums
/Living Archive/Family/Documents/        →    data/documents/runs/manifests/           https://living-archive.dev
  Source PDFs, never modified                  doc manifests + extracted text

                                         →    data/catalog.db
                                               assets table (inventory + slice grouping)
                                               consumed by run_batch / discovery
```

Inference runs on Atlas via Max Plan-backed Claude through the Anthropic SDK (OAuth token resolved from Hermes envs). Source files are read from NAS, results are written locally to `data/`, photos are uploaded to VPS Immich via CLI, and metadata is pushed via API.

**NAS dependency:** Only `catalog scan` (inventorying source files) and pipeline runs (reading sources for analysis) require NAS. Catalog stats and manifest reads are fully offline — they query local artifacts.

```
[Scanned Photos]
    → NAS: /volume1/MNEME/05_PROJECTS/Living Archive/Family/Media/
    → Pipeline: TIFF→JPEG conversion + Claude Vision analysis (local Mac)
    → AI Layer: local data/ directory (manifests, catalog)
    → Immich CLI upload: processed JPEGs → VPS Immich (living-archive-vps)
    → Immich API: metadata push (dates, descriptions, albums)
    → Public Access: https://living-archive.dev (Cloudflare Tunnel)
```

## Code vs Data Separation

| What | Where | Why |
|------|-------|-----|
| Source photos | NAS `/volume1/MNEME/05_PROJECTS/Living Archive/Family/Media/` | Canonical, never modified |
| AI manifests/outputs | Local `data/photos/runs/<timestamp>/` | Regeneratable, fast local reads |
| Document AI outputs | Local `data/documents/runs/<timestamp>/` | Regeneratable, fast local reads |
| Asset catalog | Local `data/catalog.db` | Derived index of all manifests (rebuildable via `catalog backfill`) |
| People registry | Local `data/people/registry.json` | Face clusters + named people, synced to Immich |
| Inference scripts | Repo `src/` | Version controlled (17 modules, ~3,240 lines) |
| Prompts | Repo `prompts/` | Version controlled, referenced by manifest |
| Methodology docs | Repo `docs/` | Public-facing content source |

## Access Patterns

**Kenny (admin):**
- `https://living-archive.dev` for Immich admin (Cloudflare Tunnel → VPS)
- Tailscale → `living-archive-vps` for SSH/direct access
- SSH → `mneme_admin@mneme.local` for NAS source media operations
- Local Mac runs pipeline scripts via `python -m src.pipeline`

**Family/friends (view/comment):**
- `https://living-archive.dev` → Immich user accounts (invite-based)

Note: `living-archive.kennyliu.io` remains active as an alias for Immich.

## Key Paths Reference

```
# NAS (Synology volume paths) — source data, read-only
/volume1/MNEME/05_PROJECTS/Living Archive/Family/Media/           # Source photos
/volume1/MNEME/05_PROJECTS/Living Archive/Family/Documents/       # Family documents
/volume1/MNEME/05_PROJECTS/Living Archive/Personal/               # Apple data export (726 GB)

# Mac (SMB mount) — same NAS paths
/Volumes/MNEME/05_PROJECTS/Living Archive/Family/Media/           # Mounted source
/Volumes/MNEME/05_PROJECTS/Living Archive/Family/Documents/       # Mounted documents

# Local AI layer (repo-relative, gitignored)
~/Projects/living-archive/data/                    # AI layer root
  catalog.db                                       # Asset catalog
                                                   #   assets (inventory + slice grouping)
  photos/runs/<timestamp>/manifests/               # Photo manifests
  documents/runs/<timestamp>/manifests/            # Doc manifests + extracted text
  people/registry.json                             # People registry (linked to VPS Immich IDs)

# VPS (Hetzner CPX21 — living-archive-vps)
/opt/stacks/immich/                                # Immich Docker Compose stack
/opt/stacks/immich/upload/                         # Uploaded photo storage
/opt/stacks/immich/.env                            # DB credentials (chmod 600)

# Local
~/Projects/living-archive/                         # This repo
.env                                               # IMMICH_URL + API keys (gitignored)
```

Note: NAS `_ai-layer/` directories are inert backups from before the local migration (2026-03-02). All AI output writes to local `data/`. NAS Immich installation (`/volume1/docker/immich/`, v2.4.1) is superseded by VPS Immich (v2.6.3).

## Architectural Principles

1. **Data/AI layer separation**: Source photos at full fidelity (TIFF, PDF) live on NAS and are never modified. AI layer (manifests, catalog, extracted text) lives locally in `data/` for fast reads — all regeneratable as better models emerge.

2. **Manifest as contract**: The per-asset JSON manifest is the stable interface between producers (the pipeline) and consumers (catalog, Immich sync, any future surface). Everything else is either source data (NAS) or derived (catalog.db). Derived layers can be dropped and rebuilt at any time.

3. **Confidence-based automation**: AI dating uses thresholds:
   - ≥0.8: Auto-apply to Immich
   - 0.5-0.8: Flag for human review (routed to "Needs Review" album)
   - <0.5: Routed to "Low Confidence" album

4. **Hybrid access model**: Tailscale for admin SSH, Cloudflare Tunnel for public access. Domain `living-archive.dev` serves Immich. Family/friends invited as Immich users.

5. **Quarterly reindex**: AI manifests are versioned per inference run. Plan to reindex as models improve — a new run writes to a new directory, previous runs persist as historical record.

## Two Branches: Family and Personal

The project has two data branches sharing the same three-layer architecture and pipeline code.

### Family Branch (active)

The Liu family archive — scanned photos, trust documents, genealogy records. This is the working branch with pipelines running and metadata live in Immich.

```
Living Archive/Family/           # NAS — source data (read-only)
├── Media/                        # Source TIFFs and JPEGs
└── Documents/                    # Source PDFs

living-archive/data/             # Local — AI layer (regeneratable)
├── catalog.db                    # Unified asset catalog
├── photos/runs/                  # Photo manifests
├── documents/runs/               # Doc manifests, extracted text
└── people/                       # People registry
```

### Personal Branch (planned)

Kenny's personal digital history — 726 GB Apple data export (iCloud Photos, Drive, Notes, Mail) plus a Day One journal archive (918 entries, 1999–2024). Different source formats, different scale, same architectural pattern.

```
Living Archive/Personal/
├── Apple Export/             # Raw iCloud data (20 parts, HEIC photos, documents)
│   └── _ai-layer/           # Manifests, extracted text (when pipeline runs)
└── Day One/                  # Journal markdown archive (already converted)
```

Key differences from Family:
- **HEIC not TIFF** — iCloud Photos are HEIC/JPEG, not scanned TIFFs. Conversion step changes.
- **Deduplication** — Day One photo attachments overlap with iCloud Photos; needs hash-based dedup before processing.
- **Scale** — 726 GB vs. ~2 GB of scanned media.
- **Privacy boundary** — Personal data never enters the public repo or family-facing Immich. Separate Immich library or separate presentation layer TBD.

### Integration Points

The branches share infrastructure and cross-reference each other:

| Shared | How |
|--------|-----|
| **Pipeline code** | Same `src/` modules with configurable roots (`MEDIA_ROOT`, `DOCUMENTS_ROOT`, future `PERSONAL_ROOT`) |
| **AI layer conventions** | Same `data/<branch>/runs/<timestamp>/manifests/` structure, same SHA-256 keying |
| **People registry** | `data/people/registry.json` spans both branches — a face recognized in family photos can match personal photos |
| **Prompts** | Same vision prompt works for any photo; doc prompt works for any PDF |
| **Immich** | Family and personal could share one Immich instance with separate libraries, or use separate instances |

The personal branch doesn't need its own pipeline — it needs the family pipeline to be configurable enough to point at different roots and handle different source formats.

## Inference Routing

Both pipelines dispatch through the Anthropic SDK using a Max Plan OAuth token. Legacy Claude CLI, Codex CLI, Ollama, and direct-API modes were removed on 2026-04-21 during the aggressive pare-down.

- Model: `claude-sonnet-4-20250514` (configurable via `OAUTH_MODEL`)
- Auth: `src/auth.py` resolves the token from (in order) `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN` env var, or Hermes env files at `~/.hermes/.env` and `~/.hermes/profiles/*/.env`
- OAuth tokens get Bearer auth + Claude Code beta headers; a Claude Code system prompt prefix is added to route to Max Plan billing

## Photo Pipeline

Run via `python -m src.pipeline photo` from repo root.

1. **Discover** — Walk `MEDIA_ROOT` for leaf directories containing TIFF/JPEG files, compare against `catalog.db` to find unprocessed albums, sort by remaining count (smallest first).
2. **Prepare** — Per slice: read TIFFs from NAS, convert to JPEG (quality 85, max 2048px) in a run-scoped workspace, compute SHA-256 of originals.
3. **Analyze** — Send each JPEG to Claude, parse structured JSON response (date, descriptions, tags, confidence).
4. **Write Manifests** — One JSON per photo in `data/photos/runs/<timestamp>/manifests/<sha256-first12>.json`, crash-safe (one write per photo, atomic temp+rename).
5. **Push to Immich** — If `--push`: match manifests to Immich assets by filename, update `dateTimeOriginal` + description, create "Needs Review" and "Low Confidence" albums by confidence threshold.

Budget enforcement: `--hours N` sets a soft time budget; each slice exits early when the remaining time drops below the average photo-processing estimate.

## Document Pipeline

Run via `python -m src.pipeline doc --auto` from repo root.

1. **Scan** — Walk `DOC_SLICE_DIR` for PDFs, hash each, read page counts.
2. **Diff** — Load processed SHA-256s from the current run's manifests directory; remaining files get sorted by size ascending.
3. **Extract** — `pypdf` page-by-page text extraction. Image-only PDFs return zero characters and are logged as SKIP (OCR fallback would go here).
4. **Analyze** — Whole document sent to Claude in one call. Modern context windows handle 400+ page documents; chunking was removed on 2026-04-21.
5. **Write Manifests** — One JSON + one `.txt` per document in `data/documents/runs/<timestamp>/`.

Pacing: `--batch N` caps documents per invocation; `--delay S` adds sleep between documents.

## Manifest Format

Per-asset JSON keyed by SHA-256 of the original file. Contains `analysis` (date estimate, bilingual descriptions, people/location notes, tags) and `inference` (model, prompt version, token counts, timestamp). See `prompts/photo_analysis_v1.txt` and `prompts/document_analysis_v2.txt` for the prompt templates.

## VPS Deployment

One Docker Compose stack runs on the VPS:

| Stack | Path | Port | Public URL |
|-------|------|------|------------|
| **Immich** | `/opt/stacks/immich/` | 2283 | `https://living-archive.dev` |

Exposed via the `atlas-archive` Cloudflare Tunnel. The local dashboard that lived at `dashboard.living-archive.dev` was deleted on 2026-04-21 during the pare-down — Immich is the sole presentation surface.

---

*Last updated: 2026-04-21*
