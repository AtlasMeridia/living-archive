# Living Archive

AI-assisted pipeline for organizing family photos, documents, and personal archives. Scanned photos and PDFs on a NAS are analyzed by Claude, producing structured metadata that flows into [Immich](https://immich.app/) for browsing and sharing.

## What It Does

**Photo pipeline** — TIFF scans are converted to JPEG, sent to Claude Vision for analysis (date estimation, bilingual descriptions, people/location identification), and the resulting metadata is pushed to Immich with confidence-based routing:

- High confidence (≥0.8): auto-applied
- Medium (0.5–0.8): routed to "Needs Review" album
- Low (<0.5): routed to "Low Confidence" album

**Document pipeline** — PDFs are read by Claude for text extraction and analysis (document type, dates, key people, sensitivity). Extracted text is indexed in SQLite FTS5 for full-text search.

**Face recognition sync** — Immich's face clustering is linked to a people registry in the AI layer, enabling family-wide face tagging.

## Architecture

Three-layer separation:

| Layer | Location | Contents |
|-------|----------|----------|
| **Data** | NAS (read-only) | Source TIFFs, PDFs — never modified |
| **AI** | NAS (regeneratable) | JSON manifests, extracted text, FTS index, asset catalog — keyed by SHA-256 |
| **Presentation** | Immich | Metadata, albums, face tags — populated via API |

AI outputs are versioned per inference run and designed to be regenerated as models improve.

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

# Run photo pipeline on a slice
SLICE_PATH="2009 Scanned Media/1978" python -m src.run_slice

# Run document pipeline
python -m src.run_doc_extract --new-run
```

## Repository Structure

```
src/
├── run_slice.py          # Photo pipeline orchestrator
├── run_doc_extract.py    # Document pipeline orchestrator
├── analyze.py            # Claude Vision API integration
├── convert.py            # TIFF → JPEG conversion, SHA-256 hashing
├── manifest.py           # Photo manifest read/write (AI layer)
├── doc_manifest.py       # Document manifest read/write
├── doc_scan.py           # PDF discovery and change detection
├── doc_index.py          # SQLite FTS5 index builder
├── catalog.py            # Unified asset catalog (SQLite)
├── immich.py             # Immich API client (metadata push, albums)
├── people.py             # People registry management
├── sync_people.py        # Immich face ↔ registry sync
├── review.py             # Review dashboard generator
├── preflight.py          # NAS mount, Immich health, config checks
├── config.py             # Environment and path configuration
└── models.py             # Pydantic models for manifests
prompts/
├── photo_analysis_v1.txt # Vision prompt for photo analysis
└── document_analysis_v1.txt # Prompt for document extraction
tests/                    # pytest suite (37 tests)
docs/
└── architecture.md       # Infrastructure and data flow
_dev/                     # Development notes and research
```

## Requirements

- Python 3.11+
- Anthropic API key (Claude Sonnet for vision analysis)
- Synology NAS with AFP mount (stores source media and AI layer)
- Immich instance (for photo browsing and metadata)

## CLI Entry Points

| Command | Description |
|---------|-------------|
| `python -m src.run_slice` | Run photo pipeline on a configured slice |
| `python -m src.run_doc_extract` | Document extraction orchestrator |
| `python -m src.doc_scan` | Scan and inventory PDFs |
| `python -m src.doc_index` | Build/rebuild FTS5 search index |
| `python -m src.catalog` | Asset catalog: stats, backfill, scan |
| `python -m src.preflight` | Run all preflight checks |
| `python -m src.review` | Generate review dashboard |
| `python -m src.sync_people` | Sync people registry to Immich faces |

## Background

People accumulate decades of photos, documents, and digital accounts with no plan for organizing or transferring any of it. AI changes the equation — an agent can analyze photos, extract text from documents, and produce structured metadata at a scale that makes archival work practical for individuals.

Living Archive is both working infrastructure and a methodology experiment: can a single person, aided by AI, meaningfully organize a family's worth of analog and digital records?

## Blog

Follow the project at [kennyliu.io/notes](https://kennyliu.io/notes) (tagged `living-archive`).

## License

MIT

## Author

Kenny Liu / ATLAS Meridia LLC
