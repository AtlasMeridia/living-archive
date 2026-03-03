"""Unified asset catalog — SQLite index of all pipeline assets.

Provides a single queryable view across photos, documents, and (future)
journals/notes. Manifests remain the source of truth; the catalog is a
derived, rebuildable aggregation.

CLI: see catalog_cli.py (python -m src.catalog)
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

SCHEMA_VERSION = "2"

PHOTO_EXTENSIONS = {".tif", ".tiff", ".jpg", ".jpeg", ".png"}
DOCUMENT_EXTENSIONS = {".pdf"}


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def get_catalog_db(branch: str = "family") -> Path:
    """Return the catalog.db path for a branch."""
    if branch == "personal":
        return config.DATA_DIR / "personal" / "catalog.db"
    return config.FAMILY_CATALOG_DB


# ---------------------------------------------------------------------------
# Database init
# ---------------------------------------------------------------------------

_V2_CACHE_TABLES = """
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        content_type TEXT NOT NULL,
        slice_path TEXT,
        completed TEXT,
        elapsed_seconds REAL,
        total INTEGER,
        succeeded INTEGER,
        failed INTEGER,
        model TEXT,
        photos_per_hour REAL,
        raw_meta TEXT
    );

    CREATE TABLE IF NOT EXISTS photo_quality (
        sha256 TEXT PRIMARY KEY,
        confidence_bucket TEXT,
        date_confidence REAL,
        has_location INTEGER,
        people_count INTEGER,
        date_estimate TEXT,
        era_decade TEXT,
        tags TEXT,
        run_id TEXT
    );

    CREATE TABLE IF NOT EXISTS doc_quality (
        sha256 TEXT PRIMARY KEY,
        document_type TEXT,
        page_count INTEGER,
        has_ssn INTEGER,
        has_financial INTEGER,
        has_medical INTEGER,
        language TEXT,
        quality TEXT,
        doc_date TEXT,
        run_id TEXT
    );
"""


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate schema from v1 to v2: add slice column and cache tables."""
    log.info("Migrating catalog schema v1 → v2")

    # Add slice column to assets
    conn.execute("ALTER TABLE assets ADD COLUMN slice TEXT")
    conn.execute("CREATE INDEX idx_assets_slice ON assets(slice)")

    # Backfill slice from existing path values
    rows = conn.execute("SELECT sha256, path FROM assets").fetchall()
    for r in rows:
        slice_val = str(Path(r["path"]).parent)
        if slice_val == ".":
            slice_val = ""
        conn.execute(
            "UPDATE assets SET slice=? WHERE sha256=?",
            (slice_val, r["sha256"]),
        )

    # Create cache tables
    conn.executescript(_V2_CACHE_TABLES)

    # Update version
    conn.execute(
        "UPDATE catalog_meta SET value=? WHERE key='schema_version'",
        (SCHEMA_VERSION,),
    )
    conn.commit()
    log.info("Migration complete")


def init_catalog(db_path: Path) -> sqlite3.Connection:
    """Create tables if needed, set WAL mode, return connection."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Check if schema already exists
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    if "catalog_meta" not in tables:
        # Fresh database — create v2 schema directly
        conn.executescript("""
            CREATE TABLE catalog_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE assets (
                sha256 TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                content_type TEXT NOT NULL,
                file_size INTEGER,
                file_mtime REAL,
                manifest_path TEXT,
                run_id TEXT,
                status TEXT NOT NULL DEFAULT 'discovered',
                slice TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX idx_assets_content_type ON assets(content_type);
            CREATE INDEX idx_assets_status ON assets(status);
            CREATE INDEX idx_assets_path ON assets(path);
            CREATE INDEX idx_assets_slice ON assets(slice);
        """)
        conn.executescript(_V2_CACHE_TABLES)
        conn.execute(
            "INSERT INTO catalog_meta (key, value) VALUES (?, ?)",
            ("schema_version", SCHEMA_VERSION),
        )
        conn.commit()
    else:
        row = conn.execute(
            "SELECT value FROM catalog_meta WHERE key='schema_version'"
        ).fetchone()
        version = row[0] if row else "1"
        if version == "1":
            _migrate_v1_to_v2(conn)
        elif version != SCHEMA_VERSION:
            raise RuntimeError(
                f"Catalog schema version mismatch: "
                f"expected {SCHEMA_VERSION}, got {version}"
            )

    return conn


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def upsert_asset(
    conn: sqlite3.Connection,
    *,
    sha256: str,
    path: str,
    content_type: str,
    file_size: int | None = None,
    file_mtime: float | None = None,
    manifest_path: str | None = None,
    run_id: str | None = None,
    status: str = "discovered",
    slice: str | None = None,
) -> None:
    """Insert or replace an asset row."""
    now = datetime.now(timezone.utc).isoformat()

    # Auto-compute slice from path if not provided
    if slice is None:
        parent = str(Path(path).parent)
        slice = "" if parent == "." else parent

    # Preserve created_at on updates
    existing = conn.execute(
        "SELECT created_at FROM assets WHERE sha256=?", (sha256,)
    ).fetchone()
    created_at = existing["created_at"] if existing else now

    conn.execute("""
        INSERT OR REPLACE INTO assets
            (sha256, path, content_type, file_size, file_mtime,
             manifest_path, run_id, status, slice, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        sha256, path, content_type, file_size, file_mtime,
        manifest_path, run_id, status, slice, created_at, now,
    ))
    conn.commit()


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Insert or update a catalog_meta key."""
    conn.execute(
        "INSERT OR REPLACE INTO catalog_meta (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    """Get a catalog_meta value by key."""
    row = conn.execute(
        "SELECT value FROM catalog_meta WHERE key=?", (key,)
    ).fetchone()
    return row[0] if row else None


def get_asset(conn: sqlite3.Connection, sha256: str) -> dict | None:
    """Fetch a single asset by SHA-256."""
    row = conn.execute(
        "SELECT * FROM assets WHERE sha256=?", (sha256,)
    ).fetchone()
    return dict(row) if row else None


def get_unprocessed(
    conn: sqlite3.Connection,
    content_type: str | None = None,
) -> list[dict]:
    """Return assets with status='discovered'."""
    if content_type:
        rows = conn.execute(
            "SELECT * FROM assets WHERE status='discovered' AND content_type=?",
            (content_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM assets WHERE status='discovered'"
        ).fetchall()
    return [dict(r) for r in rows]


def get_stats(conn: sqlite3.Connection) -> dict:
    """Return counts grouped by content_type and status."""
    rows = conn.execute("""
        SELECT content_type, status, COUNT(*) as count
        FROM assets GROUP BY content_type, status
        ORDER BY content_type, status
    """).fetchall()

    stats: dict = {}
    total = 0
    for r in rows:
        ct = r["content_type"]
        if ct not in stats:
            stats[ct] = {}
        stats[ct][r["status"]] = r["count"]
        total += r["count"]
    stats["_total"] = total
    return stats


if __name__ == "__main__":
    from .catalog_cli import main
    main()
