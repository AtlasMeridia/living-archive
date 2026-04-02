# Living Archive

AI-assisted pipeline for organizing family photos, documents, and personal archives. Scanned photos and PDFs on a NAS are analyzed by Claude, producing structured metadata that flows into [Immich](https://immich.app/) for browsing and sharing. Live at `living-archive.dev` (legacy alias: `living-archive.kennyliu.io`).

## What It Does

**Photo pipeline** — TIFF scans are converted to JPEG, sent to Claude Vision for analysis (date estimation, bilingual descriptions, people/location identification), and the resulting metadata is pushed to Immich with confidence-based routing:

- High confidence (≥0.8): auto-applied
- Medium (0.5–0.8): routed to "Needs Review" album
- Low (<0.5): routed to "Low Confidence" album

**Document pipeline** — PDFs are read by Claude for text extraction and analysis (document type, dates, key people, sensitivity). Extracted text is indexed in SQLite FTS5 for full-text search.

**Face recognition sync** — Immich's face clustering is linked to a people registry in the AI layer, enabling family-wide face tagging.

## Architecture

Four-machine topology with three logical layers:

| Layer | Location | Contents |
|-------|----------|----------|
| **Data** | NAS (read-only) | Source TIFFs, PDFs — never modified |
| **AI** | Local Mac (regeneratable) | JSON manifests, extracted text, FTS index, asset catalog, synthesis DB, people registry — keyed by SHA-256 |
| **Presentation** | VPS (Immich v2.6.3) | Photos, metadata, albums, face tags — public via Cloudflare Tunnel |

AI outputs are versioned per inference run and designed to be regenerated as models improve. The dashboard and synthesis APIs run fully offline from local databases — no NAS required.

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
src/                              # Pipeline code (35 modules)
├── run_slice.py                  # Photo pipeline orchestrator (single slice)
├── run_batch.py                  # Batch photo pipeline (multi-slice, triage-aware)
├── run_doc_extract.py            # Document pipeline orchestrator
├── analyze.py                    # Photo analysis (CLI or API mode)
├── convert.py                    # TIFF/JPEG → JPEG conversion, SHA-256 hashing
├── manifest.py / doc_manifest.py # Manifest read/write (per-asset JSON)
├── doc_analyze.py                # Document analysis (Claude CLI, Codex, Ollama)
├── doc_scan.py / doc_index.py    # PDF discovery, FTS5 index builder
├── catalog.py / catalog_cli.py   # Unified asset catalog (SQLite v2 schema)
├── catalog_refresh.py            # Cache population (runs, quality tables)
├── synthesis.py                  # Entity extraction, cross-reference, timeline
├── synthesis_queries.py          # Shared query service (synthesis + dashboard APIs)
├── dashboard.py / dashboard_api.py # Web UI + REST API (6 tabs)
├── haptic_api.py                 # Faceted review browser API
├── immich.py                     # Immich REST API client (upload, metadata, rotation)
├── people.py / sync_people.py    # People registry + Immich face sync + naming queue
├── contact_triage.py             # FastFoto scan triage (4×4 grids → Haiku)
├── dedup_report.py               # SHA-256 cross-source dedup analysis
├── cost.py                       # Token + dollar estimation for --dry-run
├── preflight.py                  # NAS mount, Immich health, config checks
├── config.py / models.py         # Environment config, Pydantic schemas
└── review.py                     # Review dashboard generator
prompts/
├── photo_analysis_v1.txt         # Vision prompt for photo analysis
└── document_analysis_v1.txt      # Prompt for document extraction
tests/                            # pytest suite (82 tests, 11 files)
experiments/                      # Self-contained trials with explicit promotion
├── 0002-synthesis-layer/         # Complete — promoted to src/synthesis.py
├── 0003-multimodal-embeddings/   # Complete — Gemini Embedding 2, semantic search
└── 0004-model-comparison/        # Active — Claude Opus 4.6 vs GPT 5.4
docs/
└── architecture.md               # Infrastructure topology and data flow
_dev/                             # Dev log, research sessions, utilities
```

## Inference Modes

The photo pipeline now defaults to **OAuth mode**, which uses the Anthropic SDK with a Claude Max Plan OAuth token (zero marginal cost, no CLI subprocess overhead). Legacy CLI mode and standard API mode still exist.

**Photo pipeline** (`src/analyze.py`):
- OAuth mode (default): Anthropic SDK + `CLAUDE_CODE_OAUTH_TOKEN` resolution via Hermes envs
- CLI mode: spawns `claude -p <prompt> --model ...` with `--json-schema` for structured output
- API mode: direct Anthropic API call with base64-encoded image (requires `ANTHROPIC_API_KEY`)
- Toggle: `INFERENCE_MODE=oauth|cli|api` in `.env`

**Document pipeline** (`src/doc_analyze.py`):
- Three providers, selected via `DOC_PROVIDER` env var:
  - `claude-cli` (default) — Claude Code CLI, same as photo pipeline
  - `codex` — OpenAI Codex CLI
  - `ollama` — local Ollama instance (OpenAI-compatible API)
- Default model: Opus (`DOC_CLI_MODEL=opus`), chosen after experiment 0001 showed it was faster and more detailed than Sonnet for document analysis

| Variable | Default | Description |
|----------|---------|-------------|
| `INFERENCE_MODE` | `oauth` | Photo pipeline: provider mode (`oauth`, `cli`, `api`) |
| `OAUTH_MODEL` | `claude-sonnet-4-20250514` | Photo pipeline: Anthropic model in OAuth mode |
| `CLI_MODEL` | `opus` | Photo pipeline: Claude CLI model alias when `INFERENCE_MODE=cli` |
| `DOC_PROVIDER` | `claude-cli` | Document pipeline: provider (`claude-cli`, `codex`, `ollama`) |
| `DOC_CLI_MODEL` | `opus` | Document pipeline: Claude model alias |
| `CLAUDE_CLI` | `~/.local/bin/claude` | Path to Claude Code CLI binary |
| `OLLAMA_URL` | `http://localhost:11434/v1` | Ollama API endpoint |
| `OLLAMA_MODEL` | `qwen3:32b` | Ollama model name |
| `DOC_TIMEOUT` | `300` | Document analysis timeout (seconds) |

## Requirements

- Python 3.11+
- Claude Max Plan OAuth token or Hermes profile env containing `CLAUDE_CODE_OAUTH_TOKEN` (default OAuth mode), **or** Claude Code CLI (legacy CLI mode), **or** Anthropic API key (API mode)
- Synology NAS with SMB mount (source media, read-only)
- Immich instance (VPS or local — for photo browsing and metadata)

## CLI Entry Points

| Command | Description |
|---------|-------------|
| `python -m src.run_slice` | Run photo pipeline on a configured slice |
| `python -m src.run_batch` | Batch photo pipeline over unprocessed albums (`--slices`, `--triage off|auto|require`) |
| `python -m src.run_doc_extract` | Document extraction orchestrator |
| `python -m src.doc_scan` | Scan and inventory PDFs |
| `python -m src.doc_index` | Build/rebuild FTS5 search index |
| `python -m src.catalog` | Asset catalog: stats, backfill, scan |
| `python -m src.synthesis` | Synthesis layer: rebuild, stats, dossier/date/location queries, chronology generation, unresolved-name reconciliation (`unresolved`, `reconcile`) |
| `python -m src.contact_triage` | Build contact sheets and generate keep/skip triage lists for FastFoto albums |
| `python -m src.preflight` | Run all preflight checks |
| `python -m src.dashboard` | Archive dashboard server (`http://localhost:8378`) |
| `python -m src.review` | Generate review dashboard |
| `python -m src.sync_people` | People sync toolkit: `status`, `pull`, `push`, `queue` (prioritized unknown-face naming list), `import-csv` (apply naming sheet updates) |

## Background

People accumulate decades of photos, documents, and digital accounts with no plan for organizing or transferring any of it. AI changes the equation — an agent can analyze photos, extract text from documents, and produce structured metadata at a scale that makes archival work practical for individuals.

Living Archive is both working infrastructure and a methodology experiment: can a single person, aided by AI, meaningfully organize a family's worth of analog and digital records?

## Blog

Follow the project at [kennyliu.io/notes](https://kennyliu.io/notes) (tagged `living-archive`).

## License

MIT

## Author

Kenny Liu / ATLAS Meridia LLC
