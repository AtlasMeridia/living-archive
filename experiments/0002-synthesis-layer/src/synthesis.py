"""Synthesis layer — entity extraction, cross-reference, and timeline.

Reads photo and document manifests to build a derived entity graph
in data/synthesis.db. Fully decoupled from the analysis pipeline.

Usage (from project root):
    python -m experiments.0002-synthesis-layer.src.synthesis rebuild
    python -m experiments.0002-synthesis-layer.src.synthesis stats
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "synthesis.db"
CLUSTERS_PATH = Path(__file__).resolve().parent / "person_clusters.json"

PHOTO_MANIFEST_GLOB = "photos/runs/*/manifests/*.json"
DOC_MANIFEST_GLOB = "documents/runs/*/manifests/*.json"

SCHEMA_SQL = """
CREATE TABLE entities (
    entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    name_en TEXT,
    name_zh TEXT,
    person_id TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(entity_type, normalized_value)
);

CREATE INDEX idx_entities_type ON entities(entity_type);
CREATE INDEX idx_entities_person_id ON entities(person_id);
CREATE INDEX idx_entities_name_en ON entities(name_en);
CREATE INDEX idx_entities_name_zh ON entities(name_zh);

CREATE TABLE entity_assets (
    entity_id INTEGER NOT NULL REFERENCES entities(entity_id),
    asset_sha256 TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    context TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (entity_id, asset_sha256, source)
);

CREATE INDEX idx_ea_asset ON entity_assets(asset_sha256);
CREATE INDEX idx_ea_entity ON entity_assets(entity_id);

CREATE TABLE timeline_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_normalized TEXT NOT NULL,
    date_precision TEXT NOT NULL,
    era_decade TEXT,
    label_en TEXT,
    label_zh TEXT,
    event_type TEXT NOT NULL,
    asset_sha256 TEXT,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_te_date ON timeline_events(date_normalized);
CREATE INDEX idx_te_decade ON timeline_events(era_decade);
CREATE INDEX idx_te_type ON timeline_events(event_type);
"""

# --- Country extraction for location entities ---

COUNTRY_PATTERNS = [
    (r"\bTaiwan\b", "Taiwan"),
    (r"\b台[灣湾]\b", "Taiwan"),
    (r"\bTaipei\b", "Taiwan"),
    (r"\bKaohsiung\b", "Taiwan"),
    (r"\bTainan\b", "Taiwan"),
    (r"\bTaichung\b", "Taiwan"),
    (r"\bUnited States\b|, USA\b|, US\b|, California\b|, CA\b", "United States"),
    (r"\bSan Francisco\b|\bSan Jose\b|\bLos Angeles\b|\bLos Altos\b", "United States"),
    (r"\bCupertino\b|\bSunnyvale\b|\bSanta Clara\b|\bPalo Alto\b", "United States"),
    (r"\bNew York\b|\bWashington\b|\bChicago\b|\bSeattle\b", "United States"),
    (r"\bHawaii\b|\bAlaska\b|\bYosemite\b|\bYellowstone\b", "United States"),
    (r"\bDisneyland\b|\bGolden Gate\b|\bGrand Canyon\b", "United States"),
    (r"\bUtah\b|\bArizona\b|\bNevada\b|\bOregon\b", "United States"),
    (r"\bCanada\b|\bOttawa\b|\bToronto\b|\bVancouver\b|\bMontreal\b|\bQuebec\b", "Canada"),
    (r"\bAlberta\b|\bOntario\b|\bBritish Columbia\b|\bNova Scotia\b", "Canada"),
    (r"\bJapan\b|\b日本\b|\bTokyo\b|\bKyoto\b|\bOsaka\b", "Japan"),
    (r"\bChina\b|\b中[国國]\b|\bBeijing\b|\bShanghai\b|\bGuangzhou\b", "China"),
    (r"\bHong Kong\b|\b香港\b", "Hong Kong"),
    (r"\bEgypt\b|\bGiza\b|\bCairo\b|\bNile\b", "Egypt"),
    (r"\bGreece\b|\bAthens\b|\bAcropolis\b|\bSantorini\b", "Greece"),
    (r"\bItaly\b|\bRome\b|\bVenice\b|\bFlorence\b|\bMilan\b", "Italy"),
    (r"\bFrance\b|\bParis\b|\bVersailles\b", "France"),
    (r"\bSpain\b|\bMadrid\b|\bBarcelona\b", "Spain"),
    (r"\bGermany\b|\bBerlin\b|\bMunich\b", "Germany"),
    (r"\bEngland\b|\bLondon\b|\bUnited Kingdom\b|\bBritain\b", "United Kingdom"),
    (r"\bAustralia\b|\bSydney\b|\bMelbourne\b", "Australia"),
    (r"\bMexico\b", "Mexico"),
    (r"\bKorea\b|\bSeoul\b", "South Korea"),
    (r"\bThailand\b|\bBangkok\b", "Thailand"),
    (r"\bSingapore\b", "Singapore"),
    (r"\bIreland\b|\bDublin\b", "Ireland"),
    (r"\bSwitzerland\b|\bZurich\b|\bGeneva\b", "Switzerland"),
    (r"\bAustria\b|\bVienna\b|\bSalzburg\b", "Austria"),
    (r"\bBelgium\b|\bBrussels\b|\bBruges\b", "Belgium"),
    (r"\bNetherlands\b|\bAmsterdam\b", "Netherlands"),
    (r"\bPortugal\b|\bLisbon\b", "Portugal"),
    (r"\bTurkey\b|\bIstanbul\b", "Turkey"),
    (r"\bIndia\b|\bDelhi\b|\bMumbai\b", "India"),
    (r"\bPhilippines\b|\bManila\b", "Philippines"),
]

COMPILED_COUNTRY_PATTERNS = [(re.compile(pat, re.IGNORECASE), country)
                              for pat, country in COUNTRY_PATTERNS]


def extract_countries(location_text: str) -> list[str]:
    """Extract country names from a location_estimate string."""
    found = set()
    for pattern, country in COMPILED_COUNTRY_PATTERNS:
        if pattern.search(location_text):
            found.add(country)
    return sorted(found)


# --- Person name normalization (Branch A) ---

def normalize_person_name(name: str) -> str:
    """Normalize a person name string (Branch A rules)."""
    s = name.strip()
    s = re.sub(r"\s*\([^)]*\)", "", s)
    s = re.sub(r",?\s+(MD|M\.D\.|Jr\.?|III|CFP|MA|RBM|JMK)\.?\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^(Dr\.?|Mr\.?|Mrs\.?|Ms\.?|Rev\.?|Elder|Col)\s+", "", s, flags=re.IGNORECASE)
    s = s.lower()
    s = s.replace("-", " ").replace(".", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


# --- Person cluster lookup ---

_cluster_lookup: dict | None = None
_cluster_info: dict | None = None
_cluster_lookup_normalized: dict | None = None
_cluster_norm_ambiguous: set[str] | None = None


def _resolved_person(info: dict) -> dict:
    """Build a resolved-person payload from cluster lookup info."""
    canonical = info["canonical"]
    cluster = _cluster_info.get(canonical, {})
    return {
        "canonical": canonical,
        "canonical_zh": info.get("canonical_zh"),
        "family_role": cluster.get("family_role"),
        "is_resolved": True,
    }


def _load_clusters():
    global _cluster_lookup, _cluster_info
    global _cluster_lookup_normalized, _cluster_norm_ambiguous
    if _cluster_lookup is not None:
        return

    data = json.loads(CLUSTERS_PATH.read_text())
    _cluster_lookup = data["lookup"]
    _cluster_info = {}
    for c in data["clusters"]:
        _cluster_info[c["canonical"]] = c

    # Secondary index: Branch A-normalized variant -> canonical cluster.
    # If multiple canonicals share the same normalized key, mark ambiguous and skip.
    _cluster_lookup_normalized = {}
    _cluster_norm_ambiguous = set()
    for raw_variant, info in _cluster_lookup.items():
        norm_variant = normalize_person_name(raw_variant)
        if not norm_variant:
            continue
        existing = _cluster_lookup_normalized.get(norm_variant)
        if existing is None:
            _cluster_lookup_normalized[norm_variant] = info
            continue
        if existing["canonical"] != info["canonical"]:
            _cluster_norm_ambiguous.add(norm_variant)

    for ambiguous_key in _cluster_norm_ambiguous:
        _cluster_lookup_normalized.pop(ambiguous_key, None)


def resolve_person(raw_name: str) -> dict:
    """Resolve a raw person name to a canonical identity.

    Returns dict with: canonical, canonical_zh, family_role, is_resolved.
    Matching order: exact curated variant -> Branch A-normalized variant.
    """
    _load_clusters()
    # Direct lookup first (exact variant match from curated clusters).
    if raw_name in _cluster_lookup:
        return _resolved_person(_cluster_lookup[raw_name])

    # Fallback: Branch A-normalized lookup to catch equivalent forms that were
    # not explicitly enumerated in person_clusters.json.
    norm_raw = normalize_person_name(raw_name)
    if norm_raw and norm_raw in _cluster_lookup_normalized:
        return _resolved_person(_cluster_lookup_normalized[norm_raw])

    # No match — unresolved
    return {
        "canonical": raw_name,
        "canonical_zh": None,
        "family_role": None,
        "is_resolved": False,
    }


# --- Date normalization ---

def normalize_date(date_str: str) -> tuple[str, str]:
    """Normalize a date string. Returns (normalized, precision)."""
    s = date_str.strip()
    # Full date: 1978-03-15
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s, "day"
    # Month: 1978-03
    if re.match(r"^\d{4}-\d{2}$", s):
        return s, "month"
    # Year: 1978
    if re.match(r"^\d{4}$", s):
        return s, "year"
    # Decade: 1970s
    m = re.match(r"^(\d{3})0s$", s)
    if m:
        return f"{m.group(1)}0", "decade"
    return s, "unknown"


def date_to_decade(date_str: str) -> str | None:
    """Extract decade string from a date. '1978-03-15' → '1970s'."""
    m = re.match(r"^(\d{3})", date_str)
    if m:
        return f"{m.group(1)}0s"
    return None


# --- Manifest dedup ---

def dedup_manifests(manifest_paths: list[Path]) -> dict[str, Path]:
    """Dedup manifests by sha256, keeping the latest (last sorted) per asset."""
    by_sha = {}
    for p in manifest_paths:
        try:
            m = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        sha = m.get("source_sha256", "")
        if sha:
            by_sha[sha] = p  # last wins (sorted by run date)
    return by_sha


# --- Core functions ---

def find_manifests(content_type: str) -> list[Path]:
    """Find all manifest JSON files for a content type."""
    glob = PHOTO_MANIFEST_GLOB if content_type == "photos" else DOC_MANIFEST_GLOB
    return sorted(DATA_DIR.glob(glob))


def load_manifest(path: Path) -> dict | None:
    """Load and return a manifest JSON, or None on error."""
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"  warning: skipping {path.name}: {e}", file=sys.stderr)
        return None


def init_db() -> sqlite3.Connection:
    """Drop and recreate synthesis.db with empty schema."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA_SQL)
    return conn


def get_or_create_entity(conn, entity_type, entity_value, normalized_value,
                         name_en=None, name_zh=None, metadata=None) -> int:
    """Get existing entity_id or insert a new one."""
    row = conn.execute(
        "SELECT entity_id FROM entities WHERE entity_type = ? AND normalized_value = ?",
        (entity_type, normalized_value),
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        """INSERT INTO entities (entity_type, entity_value, normalized_value,
           name_en, name_zh, metadata) VALUES (?, ?, ?, ?, ?, ?)""",
        (entity_type, entity_value, normalized_value, name_en, name_zh,
         json.dumps(metadata) if metadata else None),
    )
    return cur.lastrowid


def link_entity_asset(conn, entity_id, asset_sha256, source, confidence=1.0, context=None):
    """Link an entity to an asset. Ignores duplicates."""
    conn.execute(
        """INSERT OR IGNORE INTO entity_assets
           (entity_id, asset_sha256, source, confidence, context)
           VALUES (?, ?, ?, ?, ?)""",
        (entity_id, asset_sha256, source, confidence, context),
    )


# --- Extraction ---

def extract_from_document(conn, manifest: dict, sha256: str):
    """Extract person, date, and location entities from a document manifest."""
    analysis = manifest.get("analysis", {})

    # Person entities from key_people
    for raw_name in analysis.get("key_people", []):
        person = resolve_person(raw_name)
        canonical = person["canonical"]
        norm = normalize_person_name(canonical)
        if not norm:
            continue
        eid = get_or_create_entity(
            conn, "person", canonical, norm,
            name_en=canonical,
            name_zh=person["canonical_zh"],
            metadata={"family_role": person["family_role"]} if person["family_role"] else None,
        )
        doc_type = analysis.get("document_type", "")
        link_entity_asset(conn, eid, sha256, "document", 1.0, doc_type)

    # Date entity from document date
    doc_date = analysis.get("date")
    if doc_date:
        norm_date, precision = normalize_date(doc_date)
        if precision != "unknown":
            date_conf = analysis.get("date_confidence", 0.9)
            eid = get_or_create_entity(conn, "date", doc_date, norm_date)
            link_entity_asset(conn, eid, sha256, "document", date_conf)

    # Additional date entities from key_dates
    for kd in analysis.get("key_dates", []):
        norm_date, precision = normalize_date(kd)
        if precision != "unknown":
            eid = get_or_create_entity(conn, "date", kd, norm_date)
            link_entity_asset(conn, eid, sha256, "document", 0.9)


def extract_from_photo(conn, manifest: dict, sha256: str):
    """Extract date and location entities from a photo manifest."""
    analysis = manifest.get("analysis", {})

    # Date entity from date_estimate
    date_est = analysis.get("date_estimate")
    if date_est:
        norm_date, precision = normalize_date(date_est)
        if precision != "unknown":
            date_conf = analysis.get("date_confidence", 0.5)
            eid = get_or_create_entity(conn, "date", date_est, norm_date)
            link_entity_asset(conn, eid, sha256, "vision", date_conf)

    # Location entities (country-level) from location_estimate
    loc_est = analysis.get("location_estimate")
    if loc_est:
        loc_conf = analysis.get("location_confidence", 0.5)
        countries = extract_countries(loc_est)
        for country in countries:
            norm_loc = country.lower().replace(" ", "-")
            eid = get_or_create_entity(conn, "location", country, norm_loc)
            link_entity_asset(conn, eid, sha256, "vision", loc_conf, loc_est)


# --- Commands ---

def rebuild():
    """Drop synthesis.db and rebuild from all manifests."""
    print(f"Rebuilding {DB_PATH} ...")
    conn = init_db()

    # Dedup manifests by sha256 (latest run wins)
    photo_paths = find_manifests("photos")
    doc_paths = find_manifests("documents")
    photos_by_sha = dedup_manifests(photo_paths)
    docs_by_sha = dedup_manifests(doc_paths)

    print(f"  Photo manifests: {len(photo_paths)} files → {len(photos_by_sha)} unique assets")
    print(f"  Doc manifests: {len(doc_paths)} files → {len(docs_by_sha)} unique assets")

    # Extract from documents
    doc_ok = 0
    for sha, path in docs_by_sha.items():
        manifest = load_manifest(path)
        if manifest:
            extract_from_document(conn, manifest, sha)
            doc_ok += 1
    print(f"  Extracted from {doc_ok} documents")

    # Extract from photos
    photo_ok = 0
    for sha, path in photos_by_sha.items():
        manifest = load_manifest(path)
        if manifest:
            extract_from_photo(conn, manifest, sha)
            photo_ok += 1
    print(f"  Extracted from {photo_ok} photos")

    conn.commit()
    conn.close()
    print(f"  Created {DB_PATH} ({DB_PATH.stat().st_size:,} bytes)")
    print("  Done. Run 'stats' for counts.")


def stats():
    """Report entity and timeline counts from synthesis.db."""
    if not DB_PATH.exists():
        print(f"No database at {DB_PATH}. Run 'rebuild' first.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))

    entity_counts = conn.execute(
        "SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type"
    ).fetchall()

    total_entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    total_links = conn.execute("SELECT COUNT(*) FROM entity_assets").fetchone()[0]
    total_events = conn.execute("SELECT COUNT(*) FROM timeline_events").fetchone()[0]

    print(f"Synthesis database: {DB_PATH}")
    print(f"  Size: {DB_PATH.stat().st_size:,} bytes")
    print(f"  Entities: {total_entities}")
    if entity_counts:
        for etype, count in entity_counts:
            print(f"    {etype}: {count}")
    print(f"  Entity-asset links: {total_links}")
    print(f"  Timeline events: {total_events}")

    # Person breakdown
    resolved = conn.execute(
        "SELECT COUNT(*) FROM entities WHERE entity_type='person' AND metadata IS NOT NULL"
    ).fetchone()[0]
    unresolved = conn.execute(
        "SELECT COUNT(*) FROM entities WHERE entity_type='person' AND metadata IS NULL"
    ).fetchone()[0]
    print(f"\n  Person entities: {resolved} with family_role, {unresolved} without")

    # Top people by link count
    top_people = conn.execute("""
        SELECT e.entity_value, e.name_zh, COUNT(ea.asset_sha256) as link_count
        FROM entities e JOIN entity_assets ea ON e.entity_id = ea.entity_id
        WHERE e.entity_type = 'person'
        GROUP BY e.entity_id ORDER BY link_count DESC LIMIT 10
    """).fetchall()
    if top_people:
        print("\n  Top 10 people by document mentions:")
        for name, zh, count in top_people:
            zh_str = f" / {zh}" if zh else ""
            print(f"    {count:3d}  {name}{zh_str}")

    # Date distribution by decade
    dates = conn.execute("""
        SELECT e.normalized_value FROM entities e WHERE e.entity_type = 'date'
    """).fetchall()
    decade_counts = {}
    for (d,) in dates:
        decade = date_to_decade(d)
        if decade:
            decade_counts[decade] = decade_counts.get(decade, 0) + 1
    if decade_counts:
        print("\n  Date entities by decade:")
        for decade in sorted(decade_counts):
            print(f"    {decade}: {decade_counts[decade]}")

    # Location inventory
    locations = conn.execute("""
        SELECT e.entity_value, COUNT(ea.asset_sha256)
        FROM entities e JOIN entity_assets ea ON e.entity_id = ea.entity_id
        WHERE e.entity_type = 'location'
        GROUP BY e.entity_id ORDER BY COUNT(ea.asset_sha256) DESC
    """).fetchall()
    if locations:
        print(f"\n  Location entities ({len(locations)} countries):")
        for loc, count in locations:
            print(f"    {count:4d}  {loc}")

    conn.close()


# --- Cross-reference queries ---

def _open_db():
    if not DB_PATH.exists():
        print(f"No database at {DB_PATH}. Run 'rebuild' first.", file=sys.stderr)
        sys.exit(1)
    return sqlite3.connect(str(DB_PATH))


def _manifest_summary(sha256: str) -> dict | None:
    """Load the manifest for an asset and return a compact summary."""
    # Try documents first, then photos
    for glob in [DOC_MANIFEST_GLOB, PHOTO_MANIFEST_GLOB]:
        for p in DATA_DIR.glob(glob):
            try:
                m = json.loads(p.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if m.get("source_sha256") == sha256:
                analysis = m.get("analysis", {})
                source_file = m.get("source_file", "")
                # Determine content type from glob
                is_photo = "photos" in str(p)
                if is_photo:
                    return {
                        "type": "photo",
                        "source_file": source_file,
                        "date": analysis.get("date_estimate"),
                        "description_en": analysis.get("description_en", "")[:150],
                        "description_zh": analysis.get("description_zh", "")[:150],
                        "location": analysis.get("location_estimate"),
                    }
                else:
                    return {
                        "type": "document",
                        "source_file": source_file,
                        "title": analysis.get("title", ""),
                        "date": analysis.get("date"),
                        "summary_en": analysis.get("summary_en", "")[:200],
                        "document_type": analysis.get("document_type", ""),
                    }
    return None


# Cache sha→manifest to avoid re-scanning for each asset
_manifest_cache: dict[str, dict | None] = {}


def _cached_manifest_summary(sha256: str) -> dict | None:
    if sha256 not in _manifest_cache:
        _manifest_cache[sha256] = _manifest_summary(sha256)
    return _manifest_cache[sha256]


def _build_manifest_index() -> dict[str, Path]:
    """Build sha256 → manifest path index for fast lookups."""
    index = {}
    for glob in [DOC_MANIFEST_GLOB, PHOTO_MANIFEST_GLOB]:
        for p in sorted(DATA_DIR.glob(glob)):
            try:
                m = json.loads(p.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            sha = m.get("source_sha256", "")
            if sha:
                index[sha] = p  # latest wins
    return index


_manifest_index: dict[str, Path] | None = None


def _fast_manifest_summary(sha256: str) -> dict | None:
    """Look up manifest using pre-built index."""
    global _manifest_index
    if _manifest_index is None:
        _manifest_index = _build_manifest_index()
    p = _manifest_index.get(sha256)
    if not p:
        return None
    try:
        m = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    analysis = m.get("analysis", {})
    source_file = m.get("source_file", "")
    is_photo = "photos" in str(p)
    if is_photo:
        return {
            "type": "photo",
            "source_file": source_file,
            "date": analysis.get("date_estimate"),
            "description_en": analysis.get("description_en", "")[:150],
            "description_zh": analysis.get("description_zh", "")[:150],
            "location": analysis.get("location_estimate"),
        }
    return {
        "type": "document",
        "source_file": source_file,
        "title": analysis.get("title", ""),
        "date": analysis.get("date"),
        "summary_en": analysis.get("summary_en", "")[:200],
        "document_type": analysis.get("document_type", ""),
    }


def dossier(name: str):
    """Person dossier — all documents and photos linked to a person."""
    conn = _open_db()

    # Find entity by name (case-insensitive partial match)
    rows = conn.execute("""
        SELECT entity_id, entity_value, name_zh, metadata
        FROM entities WHERE entity_type = 'person'
        AND (entity_value LIKE ? OR name_zh LIKE ? OR normalized_value LIKE ?)
    """, (f"%{name}%", f"%{name}%", f"%{name.lower()}%")).fetchall()

    if not rows:
        print(f"No person entity matching '{name}'")
        conn.close()
        return

    # Use first match (most specific)
    eid, ename, name_zh, metadata = rows[0]
    meta = json.loads(metadata) if metadata else {}

    # Get all linked assets
    links = conn.execute("""
        SELECT asset_sha256, source, confidence, context
        FROM entity_assets WHERE entity_id = ?
        ORDER BY confidence DESC
    """, (eid,)).fetchall()

    conn.close()

    # Build manifest index and resolve
    print(f"Building manifest index...", file=sys.stderr)
    assets = []
    for sha, source, conf, context in links:
        summary = _fast_manifest_summary(sha)
        assets.append({
            "sha256": sha[:12],
            "source": source,
            "confidence": conf,
            "context": context,
            **(summary or {"type": "unknown"}),
        })

    # Sort by date
    def sort_key(a):
        d = a.get("date") or ""
        return d
    assets.sort(key=sort_key)

    result = {
        "person": ename,
        "name_zh": name_zh,
        "family_role": meta.get("family_role"),
        "total_links": len(assets),
        "documents": [a for a in assets if a.get("type") == "document"],
        "photos": [a for a in assets if a.get("type") == "photo"],
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))


def date_query(year: str):
    """Date query — all assets linked to dates in a given year."""
    conn = _open_db()

    # Find date entities matching the year
    rows = conn.execute("""
        SELECT e.entity_id, e.normalized_value
        FROM entities e WHERE e.entity_type = 'date'
        AND e.normalized_value LIKE ?
    """, (f"{year}%",)).fetchall()

    if not rows:
        print(f"No date entities matching '{year}'")
        conn.close()
        return

    entity_ids = [r[0] for r in rows]
    dates_found = [r[1] for r in rows]

    # Get all linked assets
    placeholders = ",".join("?" * len(entity_ids))
    links = conn.execute(f"""
        SELECT ea.asset_sha256, ea.source, ea.confidence, e.normalized_value
        FROM entity_assets ea JOIN entities e ON ea.entity_id = e.entity_id
        WHERE ea.entity_id IN ({placeholders})
        ORDER BY e.normalized_value
    """, entity_ids).fetchall()

    conn.close()

    print(f"Building manifest index...", file=sys.stderr)
    assets = []
    for sha, source, conf, date_val in links:
        summary = _fast_manifest_summary(sha)
        assets.append({
            "sha256": sha[:12],
            "date": date_val,
            "source": source,
            "confidence": conf,
            **(summary or {"type": "unknown"}),
        })

    result = {
        "query": year,
        "dates_matched": sorted(set(dates_found)),
        "total_assets": len(assets),
        "documents": [a for a in assets if a.get("type") == "document"],
        "photos": [a for a in assets if a.get("type") == "photo"],
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))


def location_query(country: str):
    """Location query — all photos linked to a country."""
    conn = _open_db()

    rows = conn.execute("""
        SELECT entity_id, entity_value FROM entities
        WHERE entity_type = 'location'
        AND (entity_value LIKE ? OR normalized_value LIKE ?)
    """, (f"%{country}%", f"%{country.lower()}%")).fetchall()

    if not rows:
        print(f"No location entity matching '{country}'")
        conn.close()
        return

    eid, loc_name = rows[0]

    links = conn.execute("""
        SELECT asset_sha256, source, confidence, context
        FROM entity_assets WHERE entity_id = ?
        ORDER BY confidence DESC
    """, (eid,)).fetchall()

    conn.close()

    print(f"Building manifest index...", file=sys.stderr)
    assets = []
    for sha, source, conf, context in links:
        summary = _fast_manifest_summary(sha)
        assets.append({
            "sha256": sha[:12],
            "confidence": conf,
            "location_detail": context,
            **(summary or {"type": "unknown"}),
        })

    # Sort by date
    assets.sort(key=lambda a: a.get("date") or "")

    result = {
        "location": loc_name,
        "total_photos": len(assets),
        "photos": assets,
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))


COMMANDS = {
    "rebuild": rebuild,
    "stats": stats,
    "dossier": lambda: dossier(sys.argv[2]) if len(sys.argv) > 2 else print("Usage: ... dossier <name>"),
    "date": lambda: date_query(sys.argv[2]) if len(sys.argv) > 2 else print("Usage: ... date <year>"),
    "location": lambda: location_query(sys.argv[2]) if len(sys.argv) > 2 else print("Usage: ... location <country>"),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: python -m experiments.0002-synthesis-layer.src.synthesis <command>")
        print(f"Commands: {', '.join(COMMANDS)}")
        sys.exit(1)

    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
