"""Synthesis layer — entity extraction, cross-reference, and timeline.

Reads photo and document manifests to build a derived entity graph
in data/synthesis.db. Fully decoupled from the analysis pipeline.

Usage (from project root):
    python -m experiments.0002-synthesis-layer.src.synthesis rebuild
    python -m experiments.0002-synthesis-layer.src.synthesis stats
"""

import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "synthesis.db"

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


def init_db() -> sqlite3.Connection:
    """Drop and recreate synthesis.db with empty schema."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA_SQL)
    return conn


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


def rebuild():
    """Drop synthesis.db and rebuild from all manifests."""
    print(f"Rebuilding {DB_PATH} ...")
    conn = init_db()

    photo_manifests = find_manifests("photos")
    doc_manifests = find_manifests("documents")

    print(f"  Found {len(photo_manifests)} photo manifests")
    print(f"  Found {len(doc_manifests)} document manifests")

    # Phase 0: schema only, no extraction logic yet.
    # Entity extraction will be added in Phase 1+.

    conn.close()
    print(f"  Created {DB_PATH} ({DB_PATH.stat().st_size:,} bytes)")
    print("  Done. No entities extracted (Phase 0 skeleton).")


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

    conn.close()


COMMANDS = {
    "rebuild": rebuild,
    "stats": stats,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: python -m experiments.0002-synthesis-layer.src.synthesis <command>")
        print(f"Commands: {', '.join(COMMANDS)}")
        sys.exit(1)

    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
