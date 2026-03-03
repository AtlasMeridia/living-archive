# Catalog Caching Pivot — Dashboard Independence from NAS

**Date:** 2026-03-03
**Trigger:** The 2026-03-02 architecture session identified "move all knowledge local, dashboard reads only from catalog.db" as the next step after moving the AI layer off NAS. This implements that.

## The Problem

After moving the AI layer local (2026-03-02), the dashboard was still slow:

| Endpoint | Before | Bottleneck |
|----------|--------|------------|
| `/api/batch-progress` | 30+ seconds cold | Walks entire NAS media tree via `discover.py` |
| `/api/photo-quality` | ~5 seconds | Reads every photo manifest JSON from disk |
| `/api/doc-corpus` | ~3 seconds | Reads every document manifest JSON from disk |
| `/api/photo-runs` | ~2 seconds | Reads every `run_meta.json` from disk |
| `/api/overview` | ~2 seconds | Counts run directories on filesystem |

The AI layer move helped (manifests are now local, not over AFP), but the dashboard was still doing full filesystem walks on every request. The in-memory TTL cache (60s) masked this for repeat visits but cold loads were painful.

The deeper issue: `batch-progress` imported `discover.py`, which walks the NAS to find photo directories. This meant the dashboard couldn't function at all without NAS mounted — defeating the purpose of the local AI layer.

## Solution: Catalog as Cache

Extend `catalog.db` to cache everything the dashboard needs. The NAS is only required for `scan` (inventorying source files). The dashboard reads exclusively from SQLite.

### Schema v2

Added to the existing catalog:

**`slice` column on `assets`** — the directory grouping (parent path). Computed automatically from the file path. Enables `GROUP BY slice` queries for batch progress without filesystem walks.

**`runs` table** — caches `run_meta.json` from every pipeline run:
- `run_id`, `content_type` (photo/document), `slice_path`, `completed`, `elapsed_seconds`
- `total`, `succeeded`, `failed`, `model`, `photos_per_hour`
- `raw_meta` (full JSON for future-proofing)

**`photo_quality` table** — caches photo manifest analysis fields:
- `sha256`, `confidence_bucket` (high/medium/low), `date_confidence`, `has_location`
- `people_count`, `date_estimate`, `era_decade`, `tags` (JSON array), `run_id`

**`doc_quality` table** — caches document manifest analysis fields:
- `sha256`, `document_type`, `page_count`, sensitivity flags
- `language`, `quality`, `doc_date`, `run_id`

**Metadata keys:** `last_scan_at`, `last_refresh_at` in `catalog_meta` for freshness tracking.

### Migration

`init_catalog()` auto-detects v1 databases and runs `_migrate_v1_to_v2()`:
1. `ALTER TABLE assets ADD COLUMN slice`
2. Backfill `slice` from existing `path` values
3. Create cache tables
4. Update schema version

No manual intervention needed — any code that calls `init_catalog()` transparently upgrades.

### The `refresh` Command

```
python -m src.catalog refresh
```

Walks local `data/` directories and upserts into cache tables:
- `refresh_runs()` — reads `run_meta.json` from photo and document run directories
- `refresh_photo_quality()` — reads photo manifest JSONs, extracts analysis fields
- `refresh_doc_quality()` — reads document manifest JSONs, extracts analysis fields

This is separate from `scan` (which inventories source files on NAS). The intended workflow:

```
# With NAS mounted — inventory source files
python -m src.catalog scan

# Without NAS — ingest local AI output
python -m src.catalog refresh
```

### Dashboard API Rewrite

Every slow endpoint became a SQL query:

| Endpoint | Before | After |
|----------|--------|-------|
| `batch-progress` | `build_batch_work_list(MEDIA_ROOT)` — NAS walk | `SELECT slice, status, COUNT(*) FROM assets GROUP BY slice, status` |
| `photo-quality` | Walk all manifest JSONs | `SELECT confidence_bucket, COUNT(*) FROM photo_quality GROUP BY ...` |
| `photo-runs` | Walk run dirs, read JSONs | `SELECT * FROM runs WHERE content_type='photo'` |
| `doc-corpus` | Walk all doc manifest JSONs | `SELECT document_type, COUNT(*) FROM doc_quality GROUP BY ...` |
| `overview` | Count run dirs on filesystem | `SELECT COUNT(*) FROM runs WHERE content_type=?` |

Unchanged endpoints: `doc-search` (already fast via FTS5), `people` (needs live Immich data), `health` (live checks by nature, but now includes data freshness).

### Code Restructure

Both `catalog.py` (421 lines) and `dashboard.py` (555 lines) exceeded the 300-line target:

| File | Before | After | Role |
|------|--------|-------|------|
| `catalog.py` | 421 lines | 281 lines | Schema, migration, CRUD |
| `catalog_cli.py` | — | 268 lines | CLI, scan, backfill |
| `catalog_refresh.py` | — | 207 lines | Cache table ingestion |
| `dashboard.py` | 555 lines | 181 lines | HTTP handler + routing |
| `dashboard_api.py` | — | 446 lines | All API data functions |

`dashboard.py` no longer imports from `discover.py`. That module stays for `run_batch.py` (which genuinely needs live NAS access during processing).

## Result

Dashboard loads are now instant (SQLite queries instead of filesystem walks). The dashboard works fully offline — no NAS mount required. Data freshness is visible in the health tab.

The NAS is only needed for two operations:
1. `python -m src.catalog scan` — inventory new/changed source files
2. Pipeline runs (`run_batch.py`, `run_doc_extract.py`) — read source files for analysis

Everything else (dashboard, stats, search) reads from local `data/`.

## What This Enables

- **Offline dashboard** — check archive status without NAS
- **Fast iteration** — sub-second API responses, no caching tricks needed
- **Decoupled deployment** — the presentation layer (when built) can query catalog.db directly without any NAS dependency
- **Data freshness awareness** — `last_scan_at` and `last_refresh_at` make staleness visible rather than hidden
