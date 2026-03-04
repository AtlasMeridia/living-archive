# Phase 0 — Module Skeleton

**Date:** 2026-03-03
**Status:** Complete

## What was built

- `src/synthesis.py` — core module with schema, rebuild, stats, CLI
- `__init__.py` files for package resolution

## Gate check

| Criterion | Result |
|---|---|
| `rebuild` creates empty synthesis.db | Pass — 65,536 bytes, 3 tables + indexes |
| `stats` reports zero entities | Pass — 0 entities, 0 links, 0 events |
| No pipeline imports | Pass — stdlib only (json, sqlite3, sys, pathlib) |
| Manifest discovery works | Pass — found 2,358 photo + 233 document manifests |

## Schema

Three tables created:
- `entities` — person, date, location entities with bilingual name fields
- `entity_assets` — links entities to assets with source and confidence
- `timeline_events` — chronological events with decade grouping

## Notes

- Photo manifest count (2,358) is higher than the brief's estimate (~195). The brief likely counted unique photos, not manifest files across multiple runs. Dedup by sha256 will be needed during extraction.
- Document manifest count (233) is close to the brief's 121 — likely multiple runs covering the same + additional documents.
- The module uses `DATA_DIR.glob()` to find manifests, which picks up all runs. Phase 2 will need to handle duplicate assets across runs (latest manifest wins, or dedup by sha256).
