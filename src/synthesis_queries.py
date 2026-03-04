"""Shared synthesis data-access helpers.

This module centralizes synthesis-layer query logic so CLI commands and
dashboard APIs share one schema boundary.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import config


def synthesis_db_path() -> Path:
    return config.DATA_DIR / "synthesis.db"


def chronology_path() -> Path:
    return config.DATA_DIR / "chronology.json"


def open_synthesis_db() -> sqlite3.Connection:
    """Open synthesis DB with row access by column name."""
    db_path = synthesis_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Synthesis DB not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def query_overview(conn: sqlite3.Connection, top_people_limit: int = 10) -> dict:
    """Return top-level synthesis metrics."""
    entity_counts_rows = conn.execute(
        """
        SELECT entity_type, COUNT(*) AS cnt
        FROM entities
        GROUP BY entity_type
        """
    ).fetchall()
    entity_counts = {r["entity_type"]: r["cnt"] for r in entity_counts_rows}
    total_entities = sum(entity_counts.values())
    total_links = conn.execute("SELECT COUNT(*) FROM entity_assets").fetchone()[0]
    total_events = conn.execute("SELECT COUNT(*) FROM timeline_events").fetchone()[0]
    top_people_rows = conn.execute(
        """
        SELECT e.entity_value, e.name_zh, COUNT(ea.asset_sha256) AS link_count
        FROM entities e
        JOIN entity_assets ea ON e.entity_id = ea.entity_id
        WHERE e.entity_type = 'person'
        GROUP BY e.entity_id
        ORDER BY link_count DESC
        LIMIT ?
        """,
        (top_people_limit,),
    ).fetchall()
    return {
        "entity_counts": entity_counts,
        "total_entities": total_entities,
        "entity_asset_links": total_links,
        "timeline_events": total_events,
        "top_people": [
            {
                "name_en": r["entity_value"],
                "name_zh": r["name_zh"],
                "link_count": r["link_count"],
            }
            for r in top_people_rows
        ],
    }


def query_person_entity(conn: sqlite3.Connection, name: str) -> dict | None:
    """Find the best-matching person entity and its linked assets."""
    rows = conn.execute(
        """
        SELECT entity_id, entity_value, name_zh, metadata
        FROM entities
        WHERE entity_type = 'person'
          AND (entity_value LIKE ? OR name_zh LIKE ? OR normalized_value LIKE ?)
        ORDER BY LENGTH(entity_value) ASC
        LIMIT 1
        """,
        (f"%{name}%", f"%{name}%", f"%{name.lower()}%"),
    ).fetchall()
    if not rows:
        return None

    row = rows[0]
    metadata: dict = {}
    if row["metadata"]:
        try:
            metadata = json.loads(row["metadata"])
        except json.JSONDecodeError:
            metadata = {}

    links = conn.execute(
        """
        SELECT asset_sha256, source, confidence, context
        FROM entity_assets
        WHERE entity_id = ?
        ORDER BY confidence DESC
        """,
        (row["entity_id"],),
    ).fetchall()

    return {
        "entity_id": row["entity_id"],
        "entity_value": row["entity_value"],
        "name_zh": row["name_zh"],
        "family_role": metadata.get("family_role"),
        "links": [
            {
                "asset_sha256": link["asset_sha256"],
                "source": link["source"],
                "confidence": link["confidence"],
                "context": link["context"],
            }
            for link in links
        ],
    }


def query_date_entities(conn: sqlite3.Connection, year: str) -> dict | None:
    """Find date entities for a year and all linked assets."""
    date_rows = conn.execute(
        """
        SELECT entity_id, normalized_value
        FROM entities
        WHERE entity_type = 'date'
          AND normalized_value LIKE ?
        """,
        (f"{year}%",),
    ).fetchall()
    if not date_rows:
        return None

    entity_ids = [r["entity_id"] for r in date_rows]
    placeholders = ",".join("?" * len(entity_ids))
    links = conn.execute(
        f"""
        SELECT ea.asset_sha256, ea.source, ea.confidence, e.normalized_value
        FROM entity_assets ea
        JOIN entities e ON ea.entity_id = e.entity_id
        WHERE ea.entity_id IN ({placeholders})
        ORDER BY e.normalized_value
        """,
        entity_ids,
    ).fetchall()

    return {
        "query": year,
        "dates_matched": sorted({r["normalized_value"] for r in date_rows}),
        "links": [
            {
                "asset_sha256": link["asset_sha256"],
                "source": link["source"],
                "confidence": link["confidence"],
                "normalized_value": link["normalized_value"],
            }
            for link in links
        ],
    }


def query_location_entity(conn: sqlite3.Connection, country: str) -> dict | None:
    """Find best-matching location entity and linked assets."""
    loc_rows = conn.execute(
        """
        SELECT entity_id, entity_value
        FROM entities
        WHERE entity_type = 'location'
          AND (entity_value LIKE ? OR normalized_value LIKE ?)
        ORDER BY entity_value
        LIMIT 1
        """,
        (f"%{country}%", f"%{country.lower()}%"),
    ).fetchall()
    if not loc_rows:
        return None

    row = loc_rows[0]
    links = conn.execute(
        """
        SELECT asset_sha256, confidence, context
        FROM entity_assets
        WHERE entity_id = ?
        ORDER BY confidence DESC
        """,
        (row["entity_id"],),
    ).fetchall()
    return {
        "location": row["entity_value"],
        "links": [
            {
                "asset_sha256": link["asset_sha256"],
                "confidence": link["confidence"],
                "context": link["context"],
            }
            for link in links
        ],
    }


def chronology_metadata() -> dict:
    """Return chronology file status and lightweight metadata."""
    path = chronology_path()
    if not path.exists():
        return {"exists": False, "meta": None, "path": str(path)}

    try:
        payload = json.loads(path.read_text())
    except Exception:
        return {
            "exists": True,
            "meta": {"error": "Failed to parse chronology.json"},
            "path": str(path),
        }

    return {
        "exists": True,
        "meta": {
            "generated_at": payload.get("generated_at"),
            "decade_count": payload.get("decade_count"),
            "total_events": payload.get("total_events"),
        },
        "path": str(path),
    }


def chronology_payload() -> dict:
    """Return full chronology payload with availability marker."""
    path = chronology_path()
    if not path.exists():
        return {
            "available": False,
            "error": f"Chronology not found: {path}. Run `python -m src.synthesis chronology`.",
        }
    try:
        payload = json.loads(path.read_text())
    except Exception as e:
        return {"available": False, "error": f"Failed to parse chronology: {e}"}
    payload["available"] = True
    return payload
