"""Rebuild synthesis.db from experiment manifests for Phase 4.

Replicates the entity extraction logic from src/synthesis.py but reads
from experiment manifest directories instead of production data paths.

Usage:
    python -m experiments.0004-model-comparison.src.synthesis_rebuild --provider claude
    python -m experiments.0004-model-comparison.src.synthesis_rebuild --provider gpt
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

from . import config

SCHEMA_SQL = """
CREATE TABLE entities (
    entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    name_en TEXT,
    name_zh TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(entity_type, normalized_value)
);
CREATE INDEX idx_entities_type ON entities(entity_type);

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
"""

# --- Country extraction (mirrors src/synthesis.py) ---

COUNTRY_PATTERNS = [
    (r"\bTaiwan\b|\b台[灣湾]\b|\bTaipei\b", "Taiwan"),
    (r"\bUnited States\b|, USA\b|, US\b|, CA\b|\bCalifornia\b", "United States"),
    (r"\bSan Francisco\b|\bLos Angeles\b|\bNew York\b", "United States"),
    (r"\bJapan\b|\b日本\b|\bTokyo\b", "Japan"),
    (r"\bChina\b|\b中[国國]\b|\bBeijing\b|\bShanghai\b", "China"),
    (r"\bHong Kong\b|\b香港\b", "Hong Kong"),
    (r"\bCanada\b|\bToronto\b|\bVancouver\b", "Canada"),
]
COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE), c) for p, c in COUNTRY_PATTERNS]


def extract_countries(location: str) -> list[str]:
    found = set()
    for pattern, country in COMPILED_PATTERNS:
        if pattern.search(location):
            found.add(country)
    return sorted(found)


# --- Name normalization (mirrors src/synthesis.py) ---

def normalize_person_name(name: str) -> str:
    s = name.strip()
    s = re.sub(r"\s*\([^)]*\)", "", s)
    s = re.sub(r",?\s+(MD|M\.D\.|Jr\.?|III|CFP|MA)\.?\s*$", "", s, flags=re.I)
    s = re.sub(r"^(Dr\.?|Mr\.?|Mrs\.?|Ms\.?)\s+", "", s, flags=re.I)
    s = s.lower().replace("-", " ").replace(".", " ")
    return re.sub(r"\s+", " ", s).strip()


# --- Date normalization ---

def normalize_date(date_str: str) -> tuple[str, str]:
    s = date_str.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s, "day"
    if re.match(r"^\d{4}-\d{2}$", s):
        return s, "month"
    if re.match(r"^\d{4}$", s):
        return s, "year"
    m = re.match(r"^(\d{3})0s$", s)
    if m:
        return f"{m.group(1)}0", "decade"
    return s, "unknown"


def date_to_decade(date_str: str) -> str | None:
    m = re.match(r"^(\d{3})", date_str)
    return f"{m.group(1)}0s" if m else None


# --- DB helpers ---

def init_db(db_path: Path) -> sqlite3.Connection:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    return conn


def get_or_create_entity(conn, entity_type, entity_value, normalized_value,
                         name_en=None, name_zh=None, metadata=None) -> int:
    row = conn.execute(
        "SELECT entity_id FROM entities "
        "WHERE entity_type = ? AND normalized_value = ?",
        (entity_type, normalized_value),
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO entities (entity_type, entity_value, normalized_value, "
        "name_en, name_zh, metadata) VALUES (?, ?, ?, ?, ?, ?)",
        (entity_type, entity_value, normalized_value, name_en, name_zh,
         json.dumps(metadata) if metadata else None),
    )
    return cur.lastrowid


def link_entity_asset(conn, entity_id, sha256, source, confidence=1.0, context=None):
    conn.execute(
        "INSERT OR IGNORE INTO entity_assets "
        "(entity_id, asset_sha256, source, confidence, context) "
        "VALUES (?, ?, ?, ?, ?)",
        (entity_id, sha256, source, confidence, context),
    )


# --- Extraction ---

def extract_from_photo(conn, manifest: dict, sha256: str):
    analysis = manifest.get("analysis", {})

    date_est = analysis.get("date_estimate")
    if date_est:
        norm, prec = normalize_date(date_est)
        if prec != "unknown":
            conf = analysis.get("date_confidence", 0.5)
            eid = get_or_create_entity(conn, "date", date_est, norm)
            link_entity_asset(conn, eid, sha256, "vision", conf)

    loc_est = analysis.get("location_estimate")
    if loc_est:
        loc_conf = analysis.get("location_confidence", 0.5)
        for country in extract_countries(loc_est):
            norm_loc = country.lower().replace(" ", "-")
            eid = get_or_create_entity(conn, "location", country, norm_loc)
            link_entity_asset(conn, eid, sha256, "vision", loc_conf, loc_est)


def extract_from_document(conn, manifest: dict, sha256: str):
    analysis = manifest.get("analysis", {})

    for raw_name in analysis.get("key_people", []):
        norm = normalize_person_name(raw_name)
        if not norm:
            continue
        eid = get_or_create_entity(conn, "person", raw_name, norm, name_en=raw_name)
        doc_type = analysis.get("document_type", "")
        link_entity_asset(conn, eid, sha256, "document", 1.0, doc_type)

    doc_date = analysis.get("date")
    if doc_date:
        norm, prec = normalize_date(doc_date)
        if prec != "unknown":
            conf = analysis.get("date_confidence", 0.9)
            eid = get_or_create_entity(conn, "date", doc_date, norm)
            link_entity_asset(conn, eid, sha256, "document", conf)

    for kd in analysis.get("key_dates", []):
        norm, prec = normalize_date(kd)
        if prec != "unknown":
            eid = get_or_create_entity(conn, "date", kd, norm)
            link_entity_asset(conn, eid, sha256, "document", 0.9)


def populate_timeline(conn, manifests: dict[str, dict]) -> int:
    inserted = 0
    for sha12, manifest in manifests.items():
        sha = manifest.get("source_sha256", sha12)
        ct = manifest.get("content_type", "photo")
        analysis = manifest.get("analysis", {})

        date_field = "date_estimate" if ct == "photo" else "date"
        date_val = analysis.get(date_field, "")
        if not date_val:
            continue

        norm, prec = normalize_date(date_val)
        if prec == "unknown":
            continue

        if ct == "photo":
            label_en = analysis.get("description_en", "Family photo")[:120]
            label_zh = analysis.get("description_zh", "")[:120]
            event_type = "photo"
        else:
            label_en = (analysis.get("summary_en") or analysis.get("title", ""))[:120]
            label_zh = analysis.get("summary_zh", "")[:120]
            event_type = "document"

        conn.execute(
            "INSERT INTO timeline_events "
            "(date_normalized, date_precision, era_decade, label_en, label_zh, "
            "event_type, asset_sha256, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (norm, prec, date_to_decade(norm), label_en or None, label_zh or None,
             event_type, sha, "experiment"),
        )
        inserted += 1
    return inserted


# --- Main ---

def rebuild(provider_name: str):
    phase = {"claude": "p1-claude", "gpt": "p2-gpt"}[provider_name]
    phase_dir = config.RUNS_DIR / phase
    out_dir = config.RUNS_DIR / "p4-synthesis"
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / f"{provider_name}-synthesis.db"

    # Load all manifests
    manifests: dict[str, dict] = {}
    for subdir in ("photos", "documents"):
        d = phase_dir / subdir
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json")):
            data = json.loads(f.read_text())
            data["content_type"] = subdir.rstrip("s")
            manifests[f.stem] = data

    print(f"Rebuilding synthesis from {len(manifests)} {provider_name} manifests...")
    conn = init_db(db_path)

    for sha12, manifest in manifests.items():
        sha = manifest.get("source_sha256", sha12)
        ct = manifest.get("content_type", "photo")
        if ct == "photo":
            extract_from_photo(conn, manifest, sha)
        else:
            extract_from_document(conn, manifest, sha)

    events = populate_timeline(conn, manifests)
    conn.commit()

    # Stats
    counts = {}
    for row in conn.execute(
        "SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type"
    ):
        counts[row[0]] = row[1]

    print(f"  Entities: {counts}")
    print(f"  Timeline events: {events}")
    print(f"  Written to: {db_path}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Rebuild synthesis DB from manifests")
    parser.add_argument("--provider", required=True, choices=["claude", "gpt"])
    args = parser.parse_args()
    rebuild(args.provider)


if __name__ == "__main__":
    main()
