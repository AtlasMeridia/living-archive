# Living Archive Architecture

Infrastructure documentation for the Living Archive project.

## Four-Machine Topology

| Machine | Hostname | Role | Access |
|---------|----------|------|--------|
| **NAS (DS923+)** | `mneme` | Storage (source media, read-only) | SSH, Tailscale |
| **EllisAgent (M3 Pro)** | `ellis-mbp` | Secondary / legacy execution node | Local, Tailscale |
| **Atlas (M4 Max)** | `atlas` | Primary execution host, strategy, Claude/Hermes | Local, Tailscale |
| **VPS (Hetzner CPX21)** | `living-archive-vps` | Immich v2.6.3 + Dashboard, presentation | Tailscale, Cloudflare Tunnel |

## Data Flow

```
DATA LAYER (NAS, read-only)                    AI LAYER (local, regeneratable)            PRESENTATION (VPS)
/Living Archive/Family/Media/            →    data/photos/runs/manifests/         →    Immich v2.6.3 REST API
  Source TIFFs/JPEGs, never modified           one JSON per photo, keyed by SHA-256     PUT /assets, POST /albums
/Living Archive/Family/Documents/        →    data/documents/runs/manifests/           https://living-archive.dev
  Source PDFs, never modified                  doc manifests, extracted text, FTS5

                                         →    data/catalog.db (schema v2)
                                               assets table (inventory + slice grouping)
                                               runs, photo_quality, doc_quality (cache)
                                               → dashboard core metrics

                                         →    data/synthesis.db + data/chronology.json
                                               entity graph, cross-reference queries,
                                               timeline/chronology artifacts
                                               → dashboard synthesis APIs
```

Inference currently runs on ATLASM via Max Plan-backed Claude (photos default to OAuth SDK mode; document pipeline remains provider-selectable, with `claude-cli`/Opus as the common default). Source files are read from NAS, results are written locally to `data/`, photos are uploaded to VPS Immich via CLI, and metadata is pushed via API.

**NAS dependency:** Only `scan` (inventorying source files) and pipeline runs (reading sources for analysis) require NAS. The dashboard, stats, search, and synthesis APIs are fully offline — they query local `catalog.db`/`synthesis.db` artifacts.

```
[Scanned Photos]
    → NAS: /volume1/MNEME/05_PROJECTS/Living Archive/Family/Media/
    → Pipeline: TIFF→JPEG conversion + Claude Vision analysis (local Mac)
    → AI Layer: local data/ directory (manifests, catalog, synthesis)
    → Immich CLI upload: processed JPEGs → VPS Immich (living-archive-vps)
    → Immich API: metadata push (dates, descriptions, albums)
    → Public Access: https://living-archive.dev (Cloudflare Tunnel)
    → Dashboard: https://dashboard.living-archive.dev (stats, synthesis, people, search)
```

## Code vs Data Separation

| What | Where | Why |
|------|-------|-----|
| Source photos | NAS `/volume1/MNEME/05_PROJECTS/Living Archive/Family/Media/` | Canonical, never modified |
| AI manifests/outputs | Local `data/photos/runs/<timestamp>/` | Regeneratable, fast local reads |
| Document AI outputs | Local `data/documents/runs/<timestamp>/` | Regeneratable, fast local reads |
| Asset catalog | Local `data/catalog.db` (schema v2) | Derived index + cache tables for dashboard core views |
| Synthesis layer | Local `data/synthesis.db`, `data/chronology.json` | Derived entity graph, cross-reference, chronology outputs |
| People registry | Local `data/people/` | Face clusters and registry |
| Inference scripts | Repo `src/` | Version controlled |
| Prompts | Repo `prompts/` | Version controlled, referenced by manifest |
| Methodology docs | Repo `docs/` | Public-facing content source |

## Access Patterns

**Kenny (admin):**
- `https://living-archive.dev` for Immich admin (Cloudflare Tunnel → VPS)
- `https://dashboard.living-archive.dev` for dashboard (stats, synthesis, people, search)
- Tailscale → `living-archive-vps` for SSH/direct access
- SSH → `mneme_admin@mneme.local` for NAS source media operations
- Local Mac runs pipeline scripts

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
  catalog.db                                       # Asset catalog (schema v2)
                                                   #   assets (inventory + slice)
                                                   #   runs, photo_quality, doc_quality (cache)
  photos/runs/<timestamp>/manifests/               # Photo manifests
  documents/runs/<timestamp>/manifests/            # Doc manifests + extracted text
  people/registry.json                             # People registry (linked to VPS Immich IDs)

# VPS (Hetzner CPX21 — living-archive-vps)
/opt/stacks/immich/                                # Immich Docker Compose stack
/opt/stacks/immich/upload/                         # Uploaded photo storage
/opt/stacks/immich/.env                            # DB credentials (chmod 600)
/opt/stacks/dashboard/                             # Dashboard Docker Compose stack
/opt/stacks/dashboard/.env                         # IMMICH_API_KEY, readonly/headless flags
/home/atlas/living-archive/                        # Git clone (deploy key, read-only)
/home/atlas/living-archive-data/                   # Synced AI layer mirror (rsync from Mac)

# Local
~/Projects/living-archive/                         # This repo
.env                                               # IMMICH_URL + API keys (gitignored)
```

Note: NAS `_ai-layer/` directories are inert backups from before the local migration. All new AI output writes to `data/`. NAS Immich installation (`/volume1/docker/immich/`, v2.4.1) is superseded by VPS Immich (v2.6.3).

## Architectural Principles

These are captured in AutoMem but documented here for reference:

1. **Data/AI layer separation**: Source photos at full fidelity (TIFF, PDF) live on NAS and are never modified. AI layer (manifests, catalog, extracted text) lives locally in `data/` for fast reads — all regeneratable as better models emerge.

2. **Local derived caches**: Interactive tools read local derived databases (`catalog.db`, `synthesis.db`) plus generated chronology artifacts. Cache tables (`runs`, `photo_quality`, `doc_quality`) are populated by `python -m src.catalog refresh`; synthesis entities/timeline are populated by `python -m src.synthesis rebuild`. NAS is only needed for `scan` (source inventory) and pipeline runs (reading sources). This keeps dashboard workflows offline-capable.

3. **Confidence-based automation**: AI dating uses thresholds:
   - ≥0.8: Auto-apply to Immich
   - 0.5-0.8: Flag for human review
   - <0.5: Mark as undated

4. **Hybrid access model**: Tailscale for admin SSH, Cloudflare Tunnel for public access. Domain `living-archive.dev` serves Immich (photos) and `dashboard.living-archive.dev` serves the dashboard (stats, synthesis, search). Family/friends invited as Immich users.

5. **Quarterly reindex**: AI manifests are versioned per inference run. Plan to reindex as models improve.

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
├── documents/runs/               # Doc manifests, extracted text, FTS5
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
- **Scale** — 726 GB vs. ~2 GB of scanned media. Batch mode and cost estimation become essential.
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

Cross-referencing opportunities:
- Day One journal entries (with dates) enrich photos from the same period
- Family faces appear in personal photos and vice versa
- Family trust documents reference events documented in personal records

### Why This Matters for Pipeline Development

Every pipeline improvement benefits both branches:
- Better models → reindex both branches (quarterly reindex principle)
- Batch mode for `SLICE_PATH` → required for personal branch's scale
- Page-range chunking → needed for both large trust docs and Apple export documents
- Cost estimation → essential before running personal branch at 726 GB

The personal branch doesn't need its own pipeline — it needs the family pipeline to be configurable enough to point at different roots and handle different source formats.

## Inference Routing

The photo pipeline no longer defaults to CLI mode. It now defaults to Max Plan OAuth SDK calls (`INFERENCE_MODE=oauth`) to avoid subprocess overhead, while CLI mode remains available as a legacy fallback and for comparison/debugging. The document pipeline remains provider-selectable and commonly runs via `claude-cli` with `--output-format json --json-schema <schema>` and `--no-session-persistence`.

**Photo pipeline** (`src/analyze.py`):
- Default: OAuth mode (`INFERENCE_MODE=oauth`), model `claude-sonnet-4-20250514`
- Legacy CLI mode: `INFERENCE_MODE=cli`
- Standard API fallback: `INFERENCE_MODE=api`
- CLI mode still passes `--allowedTools Read` so Claude can read the JPEG file directly

**Document pipeline** (`src/doc_analyze.py`):
- Provider abstraction with three backends: `claude-cli` (default), `codex`, `ollama`
- Default model: `opus` (switched from `sonnet` after experiment 0001 showed Opus is 25% faster, 30% fewer tokens, and extracts more detail)
- Documents >100k chars are split into 50-page chunks; results are merged via `merge_chunk_analyses()` (union of people/dates/tags, OR of sensitivity flags, highest-confidence date)
- Rate limit detection: CLI stderr is scanned for limit signals; `CliRateLimitError` triggers a 60s retry cooldown

Key implementation detail: CLI providers must unset the `CLAUDECODE` env var before spawning the subprocess, otherwise the nested CLI session fails.

## Photo Pipeline

Run via `python -m src.run_slice` from repo root.

1. **Convert** — Read TIFFs from NAS, convert to JPEG (quality 85, max 2048px) in `private/slice_workspace/`, compute SHA-256 of originals
2. **Analyze** — Send JPEGs to Claude via CLI or API, parse structured JSON response (date, descriptions, tags, confidence)
3. **Write Manifests** — Write per-photo JSON to `data/photos/runs/<timestamp>/manifests/<sha256-first12>.json`, crash-safe (one write per photo)
4. **Push to Immich** — Match manifests to Immich assets by filename, update dateTimeOriginal + description, create "Needs Review" and "Low Confidence" albums by confidence threshold
5. **Verify** — Re-hash source TIFFs to confirm they were not modified

## Manifest Format

Per-photo JSON keyed by SHA-256 of the original TIFF. Contains `analysis` (date estimate, bilingual descriptions, people/location notes, tags) and `inference` (model, prompt version, token counts, timestamp). See `prompts/photo_analysis_v1.txt` for the prompt template.

## VPS Deployment

Two Docker Compose stacks run on the VPS:

| Stack | Path | Port | Public URL |
|-------|------|------|------------|
| **Immich** | `/opt/stacks/immich/` | 2283 | `https://living-archive.dev` |
| **Dashboard** | `/opt/stacks/dashboard/` | 8378 | `https://dashboard.living-archive.dev` |

Both are exposed via the `atlas-archive` Cloudflare Tunnel (ID `4e9bde29`). The dashboard runs in read-only mode (`DASHBOARD_READONLY=true`) — people naming and cache flush are disabled on the VPS to avoid sync conflicts with the local Mac.

**Deploy workflow:**

Code is deployed via `git pull` from a read-only clone at `~/living-archive` (GitHub deploy key). Data files (catalog.db, synthesis.db, manifests, thumbnails) are rsynced from the Mac since they're gitignored.

```bash
# Full deploy (code + data + restart):
./deploy/sync.sh

# Code only:
ssh atlas@living-archive-vps 'cd ~/living-archive && git pull && cd /opt/stacks/dashboard && docker compose restart'
```

The dashboard container mounts the git clone read-only at `/app` and the data directory read-only at `/data`. It needs only `httpx`, `pydantic`, and `python-dotenv` — no pipeline dependencies.

---

*Last updated: 2026-03-20*
