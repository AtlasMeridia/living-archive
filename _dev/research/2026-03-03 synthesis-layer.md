# Synthesis Layer — Entity Index, Timeline, and Cross-Reference

**Date:** 2026-03-03
**Status:** Design — pending implementation
**Depends on:** Unified catalog (Phase 1, live), manifest schemas (stable)

---

## Problem

The pipeline collects rich per-asset metadata — photo analysis with dates, people, locations, and tags; document analysis with key people, key dates, sensitivity flags, and summaries; a people registry with bilingual names and relationships. But none of this connects across assets. There's no way to ask "show me everything about Grandma" or "what happened in 1978" and get a unified answer spanning photos, documents, and (eventually) journals.

The unified catalog design (2026-02-12) proposed an entity index as Phase 2. This document designs that index and the layers built on top of it: cross-reference queries, a timeline reconstruction layer, and a generated chronology artifact.

## Audience

Two concurrent audiences shape all design decisions:

1. **Family elders** — Chinese-first, visual, story-oriented. They contribute knowledge (face IDs, date corrections) and consume synthesized views. Elder-facing outputs default to Traditional Chinese (繁體中文).
2. **Future generations** — the archive must be self-explanatory to someone with no living context in 20+ years. Durable, well-structured, navigable without a guide.

## Architecture: Fully Separate Derivation Layer

The synthesis layer is **completely decoupled** from the analysis pipeline and asset catalog.

**`synthesis.db`** — its own SQLite database, separate from `catalog.db`. Own schema, no shared migration path. Can be deleted and rebuilt at any time from manifests + people registry.

**`src/synthesis.py`** — its own module. Does not import from `catalog.py`, `analyze.py`, or any pipeline code. Reads manifest JSON files directly from `data/`. The analysis pipeline does not know it exists.

**Batch rebuild, not inline hooks.** Synthesis is never called during photo/document analysis. It's a post-processing step you run when you want a fresh view:

```
python -m src.synthesis rebuild     # full rebuild from all manifests
python -m src.synthesis stats       # entity/timeline counts
python -m src.synthesis chronology  # generate timeline artifacts
```

**Why this separation matters:**
- The extraction rules are the thing that iterates most — "also pull locations from doc text", "fuzzy-match person names differently". Changing them = rerun rebuild, no risk to the pipeline.
- Schema changes are free. No migrations to maintain — drop and recreate.
- The pipeline stays stable and fast. Synthesis is experimental and will change.
- Testable in isolation. Feed it test manifests, check entity output.
- Clear mental model: `catalog.db` = "what do I have?", `synthesis.db` = "what does it all mean?"

**Dashboard joins:** The dashboard API uses SQLite `ATTACH DATABASE` to query across both files when needed (e.g., joining entity_assets to photo_quality for a person dossier).

**Staleness is acceptable.** The synthesis layer is always a snapshot. You run `rebuild` after a batch session. This matches the existing workflow — `catalog refresh` works the same way.

## Design Decisions

### Bilingual entities are first-class

Chinese and English names are not display variants — they're both identity. The entity system stores `name_en` and `name_zh` on person entities, and queries match against both. 劉 and Liu resolve to the same entity. Entity normalization handles this.

### Bridge documents and photos selectively

Not every connection is meaningful. Immigration papers + arrival photos = a real story. A trust amendment and a random family photo from the same year = noise. The entity system captures all connections via confidence scores, but synthesis outputs (timeline, dossier) should surface high-confidence connections and let low-confidence ones be discoverable but not prominent.

### Family graph: seed from documents, curate manually

Trust documents explicitly name beneficiaries, trustees, grantors — these are high-confidence relationship edges. Photo co-occurrence and people_notes can suggest relationships but shouldn't auto-create edges. The graph grows through document extraction + human curation, not inference.

### Manifests stay canonical

The entity index is derived, like the catalog. It can be rebuilt from manifests + people registry at any time. No entity data is stored only in the index.

---

## Schema: Entity Index

Stored in `data/synthesis.db`. Two tables, extending the Phase 2 design from the unified catalog document. Schema is defined in `src/synthesis.py` and created on every `rebuild` (drop + recreate).

```sql
-- Entity: a person, date, or location mentioned across assets
CREATE TABLE entities (
    entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,         -- 'person' | 'date' | 'location'
    entity_value TEXT NOT NULL,        -- display value: "Grandma Liu" or "1978-03"
    normalized_value TEXT NOT NULL,    -- canonical key for dedup
    name_en TEXT,                      -- person entities: English name
    name_zh TEXT,                      -- person entities: 繁體中文 name
    person_id TEXT,                    -- FK to people registry (person entities only)
    metadata TEXT,                     -- JSON blob for type-specific data
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(entity_type, normalized_value)
);

CREATE INDEX idx_entities_type ON entities(entity_type);
CREATE INDEX idx_entities_person_id ON entities(person_id);
CREATE INDEX idx_entities_name_en ON entities(name_en);
CREATE INDEX idx_entities_name_zh ON entities(name_zh);

-- Link: connects an entity to an asset with source and confidence
CREATE TABLE entity_assets (
    entity_id INTEGER NOT NULL REFERENCES entities(entity_id),
    asset_sha256 TEXT NOT NULL REFERENCES assets(sha256),
    source TEXT NOT NULL,              -- 'vision' | 'ocr' | 'document' | 'manual' | 'face'
    confidence REAL DEFAULT 1.0,
    context TEXT,                      -- snippet or note about this link
    created_at TEXT NOT NULL,
    PRIMARY KEY (entity_id, asset_sha256, source)
);

CREATE INDEX idx_ea_asset ON entity_assets(asset_sha256);
CREATE INDEX idx_ea_entity ON entity_assets(entity_id);
```

### Entity types

**person** — Maps to people registry. `normalized_value` is the `person_id` UUID. `name_en`/`name_zh` duplicated from registry for fast queries. Linked to assets via:
- `face`: Immich face cluster matched this person in the photo
- `vision`: Claude's photo analysis mentioned someone matching this person
- `document`: `key_people` list in document manifest
- `manual`: Human-assigned

**date** — Normalized to the most specific form available. `normalized_value` uses ISO format: `1978`, `1978-03`, `1978-03-15`. Linked to assets via:
- `vision`: `date_estimate` from photo manifest
- `document`: `date` or `key_dates` from document manifest
- `manual`: Human-corrected date

**location** — Normalized location strings. `normalized_value` is lowercased, simplified (e.g., `taiwan`, `san-francisco-ca`, `indoors-home`). Linked via:
- `vision`: `location_estimate` from photo manifest
- `document`: extracted location mentions (future)

### Normalization rules

| Entity type | Raw value | Normalized |
|---|---|---|
| person | "Grandma Liu", "劉奶奶" | `{person_id UUID}` (via registry lookup) |
| person (unresolved) | "John Smith" (not in registry) | `_unresolved:john-smith` |
| date | "1978-03", "March 1978" | `1978-03` |
| date | "1970s" (decade) | `197x` |
| location | "Taiwan", "台灣" | `taiwan` |
| location | "indoors - home" | `indoors-home` |

Unresolved person mentions are kept with `_unresolved:` prefix. As the registry grows, a reconciliation pass can promote them to real person entities.

---

## Component 1: Entity Extraction

A standalone step that reads all manifests and populates the entity index. Runs as part of `rebuild`, not during analysis.

```
python -m src.synthesis rebuild
```

Walks all manifests in `data/photos/runs/` and `data/documents/runs/`. Drops and recreates all synthesis tables, then populates from scratch. For each manifest:

**Photo manifests:**
- `date_estimate` → date entity, source=`vision`, confidence=`date_confidence`
- `location_estimate` → location entity, source=`vision`, confidence=`location_confidence`
- `people_notes` → attempt person matching against registry (fuzzy on name_en/name_zh), source=`vision`
- `ocr_text` → scan for person names from registry, source=`ocr`

**Document manifests:**
- `key_people` → person entities, source=`document`, confidence=1.0 (explicitly extracted)
- `date` → date entity, source=`document`, confidence=`date_confidence`
- `key_dates` → additional date entities, source=`document`, confidence=0.9
- `document_type` → stored in entity_assets.context for person links (e.g., "trust beneficiary")

No pipeline integration. The analysis pipeline writes manifests; synthesis reads them later. Run `rebuild` after a batch session to refresh.

---

## Component 2: Cross-Reference Queries

SQL queries against synthesis.db, exposed through the dashboard API. The dashboard uses `ATTACH DATABASE 'data/synthesis.db' AS syn` to join synthesis entities with catalog asset/quality data.

### Person dossier

"Show me everything about 劉奶奶":

```sql
-- With catalog.db as main, synthesis.db attached as syn
SELECT a.*, ea.source, ea.confidence, ea.context
FROM syn.entity_assets ea
JOIN assets a ON a.sha256 = ea.asset_sha256
JOIN syn.entities e ON e.entity_id = ea.entity_id
WHERE e.entity_type = 'person'
  AND (e.name_zh = ? OR e.name_en = ? OR e.person_id = ?)
ORDER BY
  COALESCE(
    (SELECT date_estimate FROM photo_quality WHERE sha256 = a.sha256),
    (SELECT doc_date FROM doc_quality WHERE sha256 = a.sha256)
  )
```

Returns: all photos with this person (face + vision), all documents mentioning them, sorted chronologically. Each result includes the source (how we know they're connected) and confidence.

### Date query

"Show me 1978":

```sql
SELECT a.*, ea.source, ea.confidence, e.entity_value
FROM syn.entity_assets ea
JOIN assets a ON a.sha256 = ea.asset_sha256
JOIN syn.entities e ON e.entity_id = ea.entity_id
WHERE e.entity_type = 'date'
  AND e.normalized_value LIKE '1978%'
ORDER BY e.normalized_value, a.content_type
```

Matches `1978`, `1978-03`, `1978-03-15` — any date within that year.

### Location query

Similar pattern: all assets linked to a location entity.

---

## Component 3: Timeline Layer

### Data layer: timeline_events table

```sql
CREATE TABLE timeline_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_normalized TEXT NOT NULL,     -- ISO: '1978', '1978-03', '1978-03-15'
    date_precision TEXT NOT NULL,      -- 'day' | 'month' | 'year' | 'decade'
    era_decade TEXT,                   -- '1970s', '1980s', etc.
    label_en TEXT,                     -- short description
    label_zh TEXT,
    event_type TEXT NOT NULL,          -- 'photo' | 'document' | 'milestone' | 'manual'
    asset_sha256 TEXT,                 -- NULL for manual milestone events
    source TEXT NOT NULL,              -- 'auto' | 'manual'
    created_at TEXT NOT NULL
);

CREATE INDEX idx_te_date ON timeline_events(date_normalized);
CREATE INDEX idx_te_decade ON timeline_events(era_decade);
CREATE INDEX idx_te_type ON timeline_events(event_type);
```

Populated by:
- **Auto-extraction** from manifests: each photo/document with a date becomes a timeline event. Label derived from `description_en`/`summary_en` (truncated to ~100 chars).
- **Manual milestones**: human-entered events that don't correspond to a specific asset ("Family immigrated to the US", "Grandpa passed away"). These are the spine of the timeline that photos and documents cluster around.

### Generated chronology artifact

A synthesis command that reads timeline_events and produces a structured JSON + human-readable markdown:

```
python -m src.synthesis chronology
```

Output: `data/chronology.json` + `data/chronology.md`

Structure:
```json
{
  "generated_at": "2026-03-03T...",
  "decades": [
    {
      "decade": "1970s",
      "summary_en": "...",
      "summary_zh": "...",
      "photo_count": 42,
      "document_count": 3,
      "events": [
        {
          "date": "1978-03",
          "precision": "month",
          "label_en": "Family portrait at home in Taipei",
          "label_zh": "台北家中全家福",
          "type": "photo",
          "asset_count": 5
        }
      ],
      "key_people": ["劉奶奶", "劉爺爺"]
    }
  ]
}
```

The markdown version is the "table of contents for the archive" — readable by a human with no tooling. Bilingual, with Chinese-first for elder accessibility.

### AI summarization (optional, deferred)

Once enough events exist per decade, Claude can generate decade summaries: "The 1970s for the Liu family were defined by..." This is narrative generation but scoped and structured — a paragraph per decade, not free-form essays. Deferred until the timeline has enough data to be meaningful.

---

## Component 4: Family Graph (Future)

Not in initial build. Documented here for completeness.

The people registry already stores `relationship` as a free-text field. A future `relationships` table would formalize this:

```sql
CREATE TABLE relationships (
    person_id_1 TEXT NOT NULL,
    person_id_2 TEXT NOT NULL,
    relationship_type TEXT NOT NULL,   -- 'parent' | 'spouse' | 'sibling' | 'child'
    source TEXT NOT NULL,              -- 'document' | 'manual'
    confidence REAL DEFAULT 1.0,
    document_sha256 TEXT,              -- source document if extracted
    PRIMARY KEY (person_id_1, person_id_2, relationship_type)
);
```

Seeded from trust documents (beneficiary/trustee/grantor roles imply family relationships). Extended by manual entry. Not built until the entity index and cross-referencing prove their value.

---

## Schema Lifecycle

No migrations. `synthesis.db` is created fresh on every `rebuild`:

```python
def rebuild(data_dir: Path):
    db_path = data_dir / "synthesis.db"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)  # all CREATE TABLE statements
    # ... walk manifests, populate ...
    conn.close()
```

Schema changes = edit `SCHEMA_SQL` in `src/synthesis.py`, run `rebuild`. No migration code to maintain.

---

## Build Order

1. **`src/synthesis.py`** — module with schema, rebuild logic, entity extraction from manifests
2. **First rebuild** — run against existing 121 documents + ~195 photos, validate entity counts
3. **Cross-reference queries** — person dossier, date query, location query (can be CLI first, API later)
4. **Timeline population** — timeline_events from entity dates
5. **Generated chronology** — JSON + markdown artifact (`python -m src.synthesis chronology`)
6. **Dashboard integration** — ATTACH synthesis.db, wire cross-reference and timeline into API
7. **(Future) Family graph** — relationships table, seeded from trust docs
8. **(Future) AI decade summaries** — Claude-generated per-decade narratives

Step 1-2 is the foundation. Step 3 is the first payoff ("show me everything about Grandma"). Steps 4-5 produce the timeline. Step 6 is presentation. Each step is independently useful and testable.

---

## Open Questions

1. **Face cluster → entity linking:** When Immich is deprecated, how do face clusters link to person entities? The people registry's `immich_person_ids` field is the current bridge. If face recognition moves to the pipeline, person entities need a new linkage mechanism.
2. **Unresolved entity reconciliation:** How often to run the "promote unresolved persons to registry matches" pass? On every backfill, or as a separate maintenance command?
3. **Location normalization:** The current `location_estimate` field is free-text ("Taiwan", "indoors - home", "United States"). Need a normalization strategy that's useful without being over-engineered. Start simple (lowercase, strip whitespace, hyphenate), evolve if needed.
4. **Timeline milestone entry UX:** Manual milestones ("Family immigrated to US, 1982") need an entry mechanism. CLI command? Dashboard form? Part of the elder tagging UX?

---

*Design session with Kenny. Implementation tracked in BACKLOG.md.*
