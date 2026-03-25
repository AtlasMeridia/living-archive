"""Deterministic retrieval layer — SQL queries against the archive's databases.

No LLM calls here. Every function takes structured parameters and returns
structured data with provenance (SHA-256 hashes, source fields, confidence).

Data sources:
  synthesis.db — entities, entity_assets, timeline_events
  catalog.db   — assets, photo_quality, doc_quality
  index.db     — documents table + documents_fts (full-text search)
  manifest JSON files — per-photo analysis details
"""

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# --- Paths ---
# Use project config.DATA_DIR if available (production), else derive from file location
import os as _os
_env_data_dir = _os.environ.get("DATA_DIR", "")
if _env_data_dir:
    DATA_DIR = Path(_env_data_dir)
else:
    try:
        from src import config as _cfg
        DATA_DIR = _cfg.DATA_DIR
    except ImportError:
        DATA_DIR = Path(__file__).resolve().parents[3] / "data"

SYNTHESIS_DB = DATA_DIR / "synthesis.db"
CATALOG_DB = DATA_DIR / "catalog.db"
PHOTO_RUNS_DIR = DATA_DIR / "photos" / "runs"
PEOPLE_REGISTRY = DATA_DIR / "people" / "registry.json"
CHRONOLOGY_JSON = DATA_DIR / "chronology.json"

# FTS index — find the most recent doc run dynamically
_doc_runs_dir = DATA_DIR / "documents" / "runs"
_DOC_INDEX_FALLBACK = DATA_DIR / "documents" / "runs" / "20260207T044501Z" / "index.db"
def _find_doc_index() -> Path:
    if _doc_runs_dir.exists():
        runs = sorted(_doc_runs_dir.iterdir(), reverse=True)
        for run in runs:
            idx = run / "index.db"
            if idx.exists():
                return idx
    return _DOC_INDEX_FALLBACK
DOC_INDEX_DB = _find_doc_index()


# --- Result types ---


@dataclass
class EntityMatch:
    entity_id: int
    entity_type: str  # person, date, location
    entity_value: str
    asset_count: int = 0


@dataclass
class AssetSummary:
    sha256: str
    content_type: str  # photo, document
    path: str = ""
    description_en: str = ""
    description_zh: str = ""
    date: str = ""
    confidence: float = 0.0
    source_field: str = ""  # how this asset was found


@dataclass
class TimelineEvent:
    date: str
    precision: str
    decade: str
    label_en: str
    label_zh: str
    event_type: str
    asset_sha256: str


@dataclass
class DocumentHit:
    sha256: str
    source_file: str
    title: str
    summary_en: str
    summary_zh: str
    date: str
    snippet: str = ""  # FTS snippet if from text search


@dataclass
class PersonProfile:
    entity_id: int
    name_en: str
    name_zh: str = ""
    relationship: str = ""
    birth_year: str = ""
    photo_count: int = 0
    doc_count: int = 0
    timeline_events: list = field(default_factory=list)


@dataclass
class RetrievalResult:
    """Aggregated retrieval output for one query."""
    query_type: str  # person, date, location, topic, general
    entities: list[EntityMatch] = field(default_factory=list)
    assets: list[AssetSummary] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    documents: list[DocumentHit] = field(default_factory=list)
    person_profiles: list[PersonProfile] = field(default_factory=list)
    raw_facts: list[str] = field(default_factory=list)


# --- Database connections ---


def _connect(db_path: Path) -> Optional[sqlite3.Connection]:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# --- Entity search ---


def search_entities(
    query: str,
    entity_type: Optional[str] = None,
    limit: int = 20,
) -> list[EntityMatch]:
    """Search entities by name (case-insensitive LIKE match)."""
    conn = _connect(SYNTHESIS_DB)
    if not conn:
        return []

    sql = """
        SELECT e.entity_id, e.entity_type, e.entity_value,
               COUNT(ea.asset_sha256) as asset_count
        FROM entities e
        LEFT JOIN entity_assets ea ON ea.entity_id = e.entity_id
        WHERE e.entity_value LIKE ?
    """
    params = [f"%{query}%"]

    if entity_type:
        sql += " AND e.entity_type = ?"
        params.append(entity_type)

    sql += " GROUP BY e.entity_id ORDER BY asset_count DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [
        EntityMatch(
            entity_id=r["entity_id"],
            entity_type=r["entity_type"],
            entity_value=r["entity_value"],
            asset_count=r["asset_count"],
        )
        for r in rows
    ]


# --- Person retrieval ---


def get_person_profile(entity_value: str) -> Optional[PersonProfile]:
    """Build a person profile from synthesis + people registry + catalog."""
    conn = _connect(SYNTHESIS_DB)
    if not conn:
        return None

    # Find the entity
    row = conn.execute(
        "SELECT entity_id, entity_value FROM entities "
        "WHERE entity_type = 'person' AND entity_value LIKE ? LIMIT 1",
        (f"%{entity_value}%",),
    ).fetchone()
    if not row:
        return None

    eid = row["entity_id"]
    name_en = row["entity_value"]

    # Count linked assets by type
    counts = conn.execute("""
        SELECT ea.source, COUNT(DISTINCT ea.asset_sha256) as cnt
        FROM entity_assets ea
        WHERE ea.entity_id = ?
        GROUP BY ea.source
    """, (eid,)).fetchall()

    photo_count = sum(r["cnt"] for r in counts if r["source"] in ("vision", "photo"))
    doc_count = sum(r["cnt"] for r in counts if r["source"] in ("document",))

    # Get timeline events for this person's linked assets
    events = conn.execute("""
        SELECT DISTINCT t.date_normalized, t.date_precision, t.era_decade,
               t.label_en, t.label_zh, t.event_type, t.asset_sha256
        FROM timeline_events t
        JOIN entity_assets ea ON ea.asset_sha256 = t.asset_sha256
        WHERE ea.entity_id = ?
        ORDER BY t.date_normalized
        LIMIT 20
    """, (eid,)).fetchall()

    timeline = [
        TimelineEvent(
            date=e["date_normalized"], precision=e["date_precision"],
            decade=e["era_decade"], label_en=e["label_en"],
            label_zh=e["label_zh"], event_type=e["event_type"],
            asset_sha256=e["asset_sha256"],
        )
        for e in events
    ]

    # Check people registry for additional info (list format, v2)
    name_zh = ""
    relationship = ""
    birth_year = ""
    registry = _load_people_registry()
    if registry:
        people_list = registry.get("people", []) if isinstance(registry, dict) else registry
        for person in people_list:
            if not isinstance(person, dict):
                continue
            if person.get("name_en", "").lower() == name_en.lower():
                name_zh = person.get("name_zh", "")
                relationship = person.get("relationship", "")
                birth_year = str(person.get("birth_year", "") or "")
                break

    return PersonProfile(
        entity_id=eid,
        name_en=name_en,
        name_zh=name_zh,
        relationship=relationship,
        birth_year=birth_year,
        photo_count=photo_count,
        doc_count=doc_count,
        timeline_events=timeline,
    )


# --- Timeline queries ---


def get_timeline_for_period(
    start: str = "",
    end: str = "",
    decade: str = "",
    limit: int = 30,
) -> list[TimelineEvent]:
    """Retrieve timeline events for a date range or decade."""
    conn = _connect(SYNTHESIS_DB)
    if not conn:
        return []

    sql = "SELECT * FROM timeline_events WHERE 1=1"
    params = []

    if decade:
        sql += " AND era_decade = ?"
        params.append(decade)
    if start:
        sql += " AND date_normalized >= ?"
        params.append(start)
    if end:
        sql += " AND date_normalized <= ?"
        params.append(end)

    sql += " ORDER BY date_normalized LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [
        TimelineEvent(
            date=r["date_normalized"], precision=r["date_precision"],
            decade=r["era_decade"], label_en=r["label_en"],
            label_zh=r["label_zh"], event_type=r["event_type"],
            asset_sha256=r["asset_sha256"],
        )
        for r in rows
    ]


# --- Document search ---


def _sanitize_fts_query(query: str) -> str:
    """Sanitize a query string for FTS5 MATCH syntax."""
    import re
    # Remove characters that FTS5 treats as syntax
    clean = re.sub(r'[^\w\s]', ' ', query)
    # Split into words, wrap each in quotes for exact matching
    words = [w.strip() for w in clean.split() if w.strip()]
    if not words:
        return '""'
    return " OR ".join(f'"{w}"' for w in words)


def search_documents(query: str, limit: int = 10) -> list[DocumentHit]:
    """Full-text search over extracted document text."""
    conn = _connect(DOC_INDEX_DB)
    if not conn:
        return []

    query = _sanitize_fts_query(query)

    # FTS columns: 0=sha256 1=source_file 2=title 3=summary_en
    # 4=summary_zh 5=extracted_text 6=tags 7=key_people
    rows = conn.execute("""
        SELECT d.sha256, d.source_file, d.title, d.summary_en, d.summary_zh,
               d.date,
               snippet(documents_fts, 5, '>>>','<<<', '...', 40) as snippet
        FROM documents_fts
        JOIN documents d ON d.sha256 = documents_fts.sha256
        WHERE documents_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, limit)).fetchall()

    return [
        DocumentHit(
            sha256=r["sha256"], source_file=r["source_file"],
            title=r["title"], summary_en=r["summary_en"],
            summary_zh=r["summary_zh"], date=r["date"],
            snippet=r["snippet"] or "",
        )
        for r in rows
    ]


# --- Asset details ---


def get_asset_details(sha256: str) -> Optional[AssetSummary]:
    """Get asset info from catalog + photo manifest if available."""
    conn = _connect(CATALOG_DB)
    if not conn:
        return None

    row = conn.execute(
        "SELECT sha256, path, content_type FROM assets WHERE sha256 LIKE ?",
        (f"{sha256}%",),
    ).fetchone()
    if not row:
        return None

    full_sha = row["sha256"]
    summary = AssetSummary(
        sha256=full_sha,
        content_type=row["content_type"],
        path=row["path"],
    )

    # Enrich from photo_quality
    if row["content_type"] == "photo":
        pq = conn.execute(
            "SELECT date_estimate, date_confidence, tags FROM photo_quality WHERE sha256 = ?",
            (full_sha,),
        ).fetchone()
        if pq:
            summary.date = pq["date_estimate"] or ""
            summary.confidence = pq["date_confidence"] or 0.0

        # Try to find manifest for full description
        manifest = _find_manifest(full_sha)
        if manifest:
            analysis = manifest.get("analysis", {})
            summary.description_en = analysis.get("description_en", "")
            summary.description_zh = analysis.get("description_zh", "")

    # Enrich from doc_quality
    elif row["content_type"] == "document":
        dq = conn.execute(
            "SELECT doc_date, document_type FROM doc_quality WHERE sha256 = ?",
            (full_sha,),
        ).fetchone()
        if dq:
            summary.date = dq["doc_date"] or ""

        # Get doc summary from FTS index
        doc_conn = _connect(DOC_INDEX_DB)
        if doc_conn:
            doc = doc_conn.execute(
                "SELECT summary_en, summary_zh FROM documents WHERE sha256 = ?",
                (full_sha,),
            ).fetchone()
            if doc:
                summary.description_en = doc["summary_en"] or ""
                summary.description_zh = doc["summary_zh"] or ""

    return summary


def get_assets_for_entity(entity_id: int, limit: int = 10) -> list[AssetSummary]:
    """Get assets linked to an entity via synthesis."""
    conn = _connect(SYNTHESIS_DB)
    if not conn:
        return []

    rows = conn.execute("""
        SELECT DISTINCT ea.asset_sha256, ea.source, ea.confidence, ea.context
        FROM entity_assets ea
        WHERE ea.entity_id = ?
        ORDER BY ea.confidence DESC
        LIMIT ?
    """, (entity_id, limit)).fetchall()

    assets = []
    for r in rows:
        detail = get_asset_details(r["asset_sha256"])
        if detail:
            detail.source_field = r["source"]
            detail.confidence = r["confidence"]
            assets.append(detail)
    return assets


# --- Location queries ---


def get_location_entities(limit: int = 20) -> list[EntityMatch]:
    """Get all location entities with counts."""
    return search_entities("", entity_type="location", limit=limit)


# --- General stats ---


def get_archive_stats() -> dict:
    """Summary statistics for the archive."""
    stats = {}

    conn = _connect(CATALOG_DB)
    if conn:
        row = conn.execute("SELECT COUNT(*) as total FROM assets").fetchone()
        stats["total_assets"] = row["total"]
        row = conn.execute(
            "SELECT content_type, COUNT(*) as cnt FROM assets GROUP BY content_type"
        ).fetchall()
        stats["by_type"] = {r["content_type"]: r["cnt"] for r in row}

    conn2 = _connect(SYNTHESIS_DB)
    if conn2:
        row = conn2.execute(
            "SELECT entity_type, COUNT(*) as cnt FROM entities GROUP BY entity_type"
        ).fetchall()
        stats["entities"] = {r["entity_type"]: r["cnt"] for r in row}
        stats["timeline_events"] = conn2.execute(
            "SELECT COUNT(*) FROM timeline_events"
        ).fetchone()[0]

    return stats


# --- Helpers ---


_people_registry_cache = None


def _load_people_registry() -> Optional[dict]:
    global _people_registry_cache
    if _people_registry_cache is not None:
        return _people_registry_cache
    if not PEOPLE_REGISTRY.exists():
        return None
    _people_registry_cache = json.loads(PEOPLE_REGISTRY.read_text())
    return _people_registry_cache


def _find_manifest(sha256: str) -> Optional[dict]:
    """Find a photo manifest JSON by SHA-256 prefix."""
    short = sha256[:12]
    for run_dir in sorted(PHOTO_RUNS_DIR.iterdir(), reverse=True):
        manifest = run_dir / "manifests" / f"{short}.json"
        if manifest.exists():
            return json.loads(manifest.read_text())
    return None
