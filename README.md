# Living Archive

AI-assisted pipeline for organizing family photos and documents. Scanned photos and PDFs on a NAS are analyzed by Claude, producing structured metadata that flows into [Immich](https://immich.app/) for browsing and sharing. Live at `living-archive.dev` (legacy alias: `living-archive.kennyliu.io`).

## What It Does

**Photo pipeline** — TIFF scans are converted to JPEG, sent to Claude Vision (via Max Plan OAuth) for analysis (date estimation, bilingual descriptions, people/location identification), and the resulting metadata is pushed to Immich with confidence-based routing:

- High confidence (≥0.8): auto-applied
- Medium (0.5–0.8): routed to "Needs Review" album
- Low (<0.5): routed to "Low Confidence" album

**Document pipeline** — PDFs are text-extracted with `pypdf`, sent whole to Claude for analysis (document type, dates, key people, sensitivity), and the resulting manifest is written alongside the extracted text.

**Face registry sync** — Immich's face clusters can be pulled into a local registry and named values pushed back.

## Architecture

Four-machine topology with three logical layers:

| Layer | Location | Contents |
|-------|----------|----------|
| **Data** | NAS (read-only) | Source TIFFs, PDFs — never modified |
| **AI** | Local Mac (regeneratable) | JSON manifests, extracted text, asset catalog, people registry — keyed by SHA-256 |
| **Presentation** | VPS (Immich v2.6.3) | Photos, metadata, albums, face tags — public via Cloudflare Tunnel |

AI outputs are versioned per inference run and designed to be regenerated as models improve. Manifests are the contract between layers — everything else is rebuildable from them.

## Quick Start

```bash
# Clone and set up
git clone https://github.com/AtlasMeridia/living-archive.git
cd living-archive
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Configure (copy and fill in API keys, NAS paths)
cp .env.example .env

# Run preflight checks
python -m src.preflight

# Run the photo pipeline (2-hour budget, push to Immich)
python -m src.pipeline photo --hours 2 --push

# Run the document pipeline (automated, 20 at a time, 2s pacing)
python -m src.pipeline doc --auto --batch 20 --delay 2
```

## Repository Structure

```
src/                              # Pipeline code (17 modules, ~3,240 lines)
├── pipeline.py                   # Unified orchestrator (photo + doc subcommands)
├── analyze.py                    # Photo analysis via Max Plan OAuth
├── doc_analyze.py                # Document analysis via Max Plan OAuth
├── doc_extract_text.py           # pypdf text extraction
├── convert.py                    # TIFF → JPEG conversion, SHA-256 hashing
├── manifest.py / doc_manifest.py # Manifest read/write (per-asset JSON)
├── catalog.py                    # Unified SQLite asset catalog + CLI
├── immich.py                     # Immich REST API client
├── auth.py                       # Max Plan OAuth client (Hermes env lookup)
├── people.py / sync_people.py    # People registry + Immich face sync
├── discover.py                   # Unprocessed-album discovery
├── cost.py                       # Token + dollar estimation for --dry-run
├── preflight.py                  # NAS mount, Immich health, OAuth checks
├── config.py / models.py         # Environment config, Pydantic schemas
prompts/
├── photo_analysis_v1.txt         # Vision prompt for photo analysis
└── document_analysis_v2.txt      # Prompt for document extraction
tests/                            # pytest suite (50 tests)
experiments/                      # Self-contained trials (historical + active)
docs/
└── architecture.md               # Infrastructure topology and data flow
_dev/                             # Dev log, research, refactor notes
```

## Inference

Both pipelines dispatch through the Anthropic SDK using a Max Plan OAuth token (resolved in `src/auth.py`). Legacy Claude CLI, Codex CLI, Ollama, and direct-API modes were removed on 2026-04-21.

Token resolution order:
1. `ANTHROPIC_API_KEY` env var (standard API key)
2. `CLAUDE_CODE_OAUTH_TOKEN` env var
3. `~/.hermes/.env` or `~/.hermes/profiles/*/.env`

| Variable | Default | Description |
|----------|---------|-------------|
| `OAUTH_MODEL` | `claude-sonnet-4-20250514` | Anthropic model for both pipelines |
| `CLAUDE_CODE_OAUTH_TOKEN` | auto-detected | OAuth token (usually from Hermes env) |
| `ANTHROPIC_API_KEY` | — | Standard API key (optional, Hermes preferred) |

## Requirements

- Python 3.11+
- Claude Max Plan OAuth token (or Hermes profile env containing `CLAUDE_CODE_OAUTH_TOKEN`)
- Synology NAS with SMB mount (source media, read-only)
- Immich instance (VPS or local — for photo browsing and metadata)

## CLI Entry Points

| Command | Description |
|---------|-------------|
| `python -m src.pipeline photo` | Photo pipeline: `--hours N`, `--push`, `--dry-run`, `--slices`, `--resume` |
| `python -m src.pipeline doc` | Document pipeline: `--auto`, `--batch N`, `--delay S`, `--status`, `--dry-run`, `--resume` |
| `python -m src.catalog` | Asset catalog: `stats`, `backfill`, `scan` |
| `python -m src.preflight` | Run all preflight checks (NAS, Immich, OAuth) |
| `python -m src.sync_people` | People sync: `status`, `pull`, `push` |

## Background

People accumulate decades of photos, documents, and digital accounts with no plan for organizing or transferring any of it. AI changes the equation — an agent can analyze photos, extract text from documents, and produce structured metadata at a scale that makes archival work practical for individuals.

Living Archive is both working infrastructure and a methodology experiment: can a single person, aided by AI, meaningfully organize a family's worth of analog and digital records?

## Blog

Follow the project at [kennyliu.io/notes](https://kennyliu.io/notes) (tagged `living-archive`).

## License

MIT

## Author

Kenny Liu / ATLAS Meridia LLC
