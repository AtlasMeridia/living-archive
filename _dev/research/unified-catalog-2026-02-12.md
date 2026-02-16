# Unified Catalog & Entity Index — Architecture Discussion

**Date:** 2026-02-12
**Status:** Phase 1 implemented (2026-02-16) — asset catalog live at `Family/_ai-layer/catalog.db`
**Council:** Claude Opus, GPT-4.1, Grok 4 (Gemini unavailable)

---

## Problem

The AI layer has siloed metadata stores: photo manifests (JSON), document manifests (JSON), FTS5 index (SQLite), and a people registry (JSON). No unified way to query across content types, detect what needs processing, or cross-reference entities (people, dates, places) across photos, documents, and journals.

## Decision: SQLite Unified Catalog

All three models agreed: SQLite is the right substrate. It's already in the stack (FTS5), zero deployment overhead, right scale for a single-person project with ~300 current assets scaling to thousands.

Two components, built in phases:

### Phase 1: Asset Catalog

One table tracking every item in the data layer:

```sql
CREATE TABLE assets (
    sha256 TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    content_type TEXT NOT NULL,  -- photo, document, journal, note
    file_size INTEGER,
    file_mtime REAL,
    indexed_at TEXT,
    manifest_path TEXT,
    run_id TEXT,
    status TEXT DEFAULT 'discovered'  -- discovered, processing, indexed, error
);
CREATE INDEX idx_assets_type ON assets(content_type);
CREATE INDEX idx_assets_status ON assets(status);
```

**Immediate value:** Turns the pipeline from "manually set SLICE_PATH" into "tell me what needs processing." `python -m src.scan` diffs the filesystem against the catalog and reports new/changed/stale items.

### Phase 2: Entity Index

Added after the catalog is proven with 500+ assets. Start with only two entity types: **people** and **dates** (the two clearly present in existing manifests). "Events" deferred — too fuzzy to define now.

```sql
CREATE TABLE entities (
    entity_id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,       -- person, date
    entity_value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,   -- canonical form for dedup
    UNIQUE(entity_type, normalized_value)
);

CREATE TABLE entity_assets (
    entity_id INTEGER REFERENCES entities(entity_id),
    asset_sha256 TEXT REFERENCES assets(sha256),
    source TEXT,          -- vision, ocr, exif, yaml, manual
    confidence REAL,
    PRIMARY KEY (entity_id, asset_sha256)
);
```

**Value:** Cross-content-type queries — "show me everything related to 1978" spanning photos, documents, and journal entries.

### Location

`_ai-layer/catalog.db` — separate from existing `index.db` until both are stable. Consolidation can come later.

---

## Key Design Decisions

### Manifests stay as source of truth
The catalog is derived, not canonical. Manifests remain the authoritative per-asset AI output. The catalog aggregates them into something queryable and can be rebuilt at any time — consistent with the "regeneratable AI layer" principle.

### Freshness detection: hybrid approach
- **Fast check:** mtime + file size (cheap filesystem stat)
- **Confirmation:** SHA-256 only when mtime/size changed
- **Discovery:** Full filesystem enumeration as a separate `scan` command, not on every pipeline run
- **Staleness:** Compare manifest timestamps against catalog `indexed_at`

### Day One journals: parse YAML, don't run through Claude
918 markdown files with YAML frontmatter are already structured data. Ingestion path: parse frontmatter (dates, tags, sources) → insert into catalog + entity index. Journal text goes into FTS5. No manifest needed — the markdown IS the source of truth.

### Temporal data as first-class concern
Dates should be indexed and queryable as ranges, not just exact matches. "Show me 1978" should work even when individual assets have specific dates (1978-03-15) or estimated date ranges. This prevents photo-centric thinking that's hard to unwind later.

### Schema versioning
Include a `schema_version` integer in the database metadata for clean future migrations.

---

## Council Insights Worth Preserving

### Catalog-as-orchestration-layer (Claude)
The most valuable near-term use isn't cross-referencing — it's giving the pipeline self-awareness. The catalog turns "what haven't I processed?" from a human memory task into a database query.

### Temporal scaffolding (GPT-4.1)
The long-term differentiator is not "which assets mention Grandma Liu" but "when and how did Grandma appear across time, and in what relationships?" Design for timeline reconstruction early.

### AI feedback loops (Grok 4)
Novel idea: periodically feed the entity index back into Claude to refine entity clusters. "Based on these 50 mentions of 'Grandma Liu', suggest disambiguations or relations." Turns static archives into a self-improving knowledge base. Interesting but deferred — adds complexity.

---

## Open Questions (for future sessions)

1. **FTS5 migration:** The document pipeline already writes to `index.db`. Should the catalog eventually absorb those tables, or stay separate?
2. **Immich as parallel store:** Immich already stores people, dates, descriptions. Is the catalog authoritative (syncs TO Immich), or should Immich corrections flow back?
3. **People registry migration:** `_ai-layer/people/registry.json` is already an entity store for people. How does it relate to the entity index's "person" type?
4. **Interoperability:** Grok suggested Dublin Core metadata standards and periodic JSON-LD exports. Worth considering if the methodology is meant to be reusable by others.

---

## Implementation (2026-02-16)

Phase 1 implemented in `src/catalog.py`:

- **Schema:** `catalog_meta` + `assets` table with indexes on content_type, status, path. Schema version tracked for future migrations.
- **Inline updates:** `manifest.py` and `doc_manifest.py` call `upsert_asset()` after every manifest write (try/except, non-fatal).
- **Backfill:** `python -m src.catalog backfill` reads all existing manifests and populates the catalog.
- **Scan:** `python -m src.catalog scan [--type photo|document]` walks the filesystem, diffs against catalog using mtime+size (fast) then SHA-256 (confirmation). New files get status `discovered`; unchanged indexed files keep their status.
- **Stats:** `python -m src.catalog stats` shows counts by content_type and status.
- **Preflight:** `preflight.py` checks catalog schema version if catalog.db exists (informational, not a blocker).

Initial population: 62 photo + 74 document manifests → 136 unique indexed assets. Document scan found 44 additional unprocessed files.

Schema evolved slightly from the design above: added `created_at`/`updated_at` timestamps, `catalog_meta` table for schema versioning, path index for scan performance.

## Next Steps

1. ~~Build the asset catalog table (`Phase 1`) — integrate with existing `run_slice` and `run_doc_extract`~~ Done
2. ~~Build a `scan` command that inventories the data layer and diffs against the catalog~~ Done
3. Run the remaining 6 photo slices through the catalog-aware pipeline
4. Evaluate whether the entity index is needed yet based on real usage

---

*This document captures the architectural discussion and council assessment. Implementation tracked in BACKLOG.md.*
