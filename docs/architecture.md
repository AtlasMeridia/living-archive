# Living Archive Architecture

Infrastructure documentation for the Living Archive project.

## Three-Machine Topology

| Machine | Hostname | Role | Access |
|---------|----------|------|--------|
| **NAS (DS923+)** | `mneme` | Storage + Immich runtime | SSH, Tailscale |
| **EllisAgent (M3 Pro)** | `ellis-mbp` | Execution, scripts, Claude Code | Local, Tailscale |
| **Atlas (M4 Max)** | `atlas` | Strategy, Claude Desktop | Local, Tailscale |

## Data Flow

```
DATA LAYER (NAS, read-only)                    AI LAYER (NAS, regeneratable)              PRESENTATION (Immich)
/Living Archive/Family/Media/            -->  .../Media/_ai-layer/               --> Immich REST API
  2009 Scanned Media/1978/                     runs/<run-id>/manifests/                PUT /assets (dates, descriptions)
  Source TIFFs, never modified                  one JSON per photo, keyed by SHA-256   POST /albums (review buckets)
```

Inference runs on M3 Pro via Claude API (Sonnet). Results written to NAS. Then pushed to Immich.

```
[Scanned Photos]
    → NAS: /volume1/MNEME/05_PROJECTS/Living Archive/Family/Media/
    → Immich (read-only external library, mounted at /external/photos)
    → AI Layer: /volume1/MNEME/05_PROJECTS/Living Archive/Family/Media/_ai-layer/
    → Immich API (date/description metadata sync)
    → Family Access: archives.kennyliu.io (Cloudflare Tunnel)
```

## Code vs Data Separation

| What | Where | Why |
|------|-------|-----|
| Source photos | NAS `/volume1/MNEME/05_PROJECTS/Living Archive/Family/Media/` | Canonical, never modified |
| AI manifests/outputs | NAS `Family/Media/_ai-layer/runs/<timestamp>/` | Regeneratable, lives with data |
| Inference scripts | Repo `src/` | Version controlled |
| Prompts | Repo `prompts/` | Version controlled, referenced by manifest |
| Methodology docs | Repo `docs/` | Public-facing content source |
| Working notes | Obsidian `10 AEON/MANIFOLD/Active/living-archive.md` | Transient state |

## Access Patterns

**Kenny (admin):**
- Tailscale → `http://mneme:2283` for Immich admin
- SSH → `mneme_admin@mneme.local` for NAS operations
- EllisAgent runs scripts that SSH to NAS

**Family (view/comment):**
- `https://archives.kennyliu.io` → Cloudflare Access (email OTP) → Immich

## Key Paths Reference

```
# NAS (Synology volume paths)
/volume1/MNEME/05_PROJECTS/Living Archive/Family/Media/           # Source photos
/volume1/MNEME/05_PROJECTS/Living Archive/Family/Media/_ai-layer/ # AI inference layer
/volume1/MNEME/05_PROJECTS/Living Archive/Family/Documents/       # Family documents
/volume1/MNEME/05_PROJECTS/Living Archive/Personal/               # Apple data export (726 GB)
/volume1/docker/immich/                                           # Immich installation

# Mac (AFP mount)
/Volumes/MNEME/05_PROJECTS/Living Archive/Family/Media/           # Mounted source
/Volumes/MNEME/05_PROJECTS/Living Archive/Family/Media/_ai-layer/ # Mounted AI layer

# EllisAgent
~/Projects/living-archive/                         # This repo
.env                                               # API keys (gitignored)

# Obsidian (synced via Dropbox)
10 AEON/MANIFOLD/Active/living-archive.md         # Working thread
10 AEON/_CHANNEL/from-web/                        # Handoffs to Local Claude
```

## Architectural Principles

These are captured in AutoMem but documented here for reference:

1. **Data/AI layer separation**: Source photos at full fidelity (TIFF, PDF) are never modified. AI layer contains extracted text, structured metadata, cross-references — all regeneratable as better models emerge.

2. **Confidence-based automation**: AI dating uses thresholds:
   - ≥0.8: Auto-apply to Immich
   - 0.5-0.8: Flag for human review
   - <0.5: Mark as undated

3. **Hybrid access model**: Tailscale for admin (technical users), Cloudflare Tunnel + Access for family (email OTP, minimal friction).

4. **Quarterly reindex**: AI manifests are versioned per inference run. Plan to reindex as models improve.

## Two Branches: Family and Personal

The project has two data branches sharing the same three-layer architecture and pipeline code.

### Family Branch (active)

The Liu family archive — scanned photos, trust documents, genealogy records. This is the working branch with pipelines running and metadata live in Immich.

```
Living Archive/Family/
├── Media/                    # Source TIFFs (2009 Scanned Media, etc.)
│   └── _ai-layer/           # Photo manifests, people registry
└── Documents/                # Source PDFs (Liu Family Trust, etc.)
    └── _ai-layer/           # Doc manifests, extracted text, FTS5 index
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
| **AI layer conventions** | Same `_ai-layer/runs/<timestamp>/manifests/` structure, same SHA-256 keying |
| **People registry** | `_ai-layer/people/registry.json` spans both branches — a face recognized in family photos can match personal photos |
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

## Pipeline (implemented)

Run via `python -m src.run_slice` from repo root.

1. **Convert** — Read TIFFs from NAS, convert to JPEG (quality 85, max 2048px) in `private/slice_workspace/`, compute SHA-256 of originals
2. **Analyze** — Send JPEGs to Claude Sonnet via vision API, parse structured JSON response (date, descriptions, tags, confidence)
3. **Write Manifests** — Write per-photo JSON to `_ai-layer/runs/<timestamp>/manifests/<sha256-first12>.json`, crash-safe (one write per photo)
4. **Push to Immich** — Match manifests to Immich assets by filename, update dateTimeOriginal + description, create "Needs Review" and "Low Confidence" albums by confidence threshold
5. **Verify** — Re-hash source TIFFs to confirm they were not modified

## Manifest Format

Per-photo JSON keyed by SHA-256 of the original TIFF. Contains `analysis` (date estimate, bilingual descriptions, people/location notes, tags) and `inference` (model, prompt version, token counts, timestamp). See `prompts/photo_analysis_v1.txt` for the prompt template.

---

*Last updated: 2026-02-12*
