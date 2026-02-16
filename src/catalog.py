"""Unified asset catalog — SQLite index of all pipeline assets.

Provides a single queryable view across photos, documents, and (future)
journals/notes. Manifests remain the source of truth; the catalog is a
derived, rebuildable aggregation.

Usage:
    python -m src.catalog stats              # counts by type/status
    python -m src.catalog backfill           # populate from existing manifests
    python -m src.catalog scan               # discover new files on disk
    python -m src.catalog scan --type photo  # discover only photos
"""

import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .convert import sha256_file

log = logging.getLogger(__name__)

SCHEMA_VERSION = "1"

PHOTO_EXTENSIONS = {".tif", ".tiff", ".jpg", ".jpeg", ".png"}
DOCUMENT_EXTENSIONS = {".pdf"}


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def get_catalog_db(branch: str = "family") -> Path:
    """Return the catalog.db path for a branch."""
    if branch == "personal":
        return config.PERSONAL_ROOT / "_ai-layer" / "catalog.db"
    return config.FAMILY_CATALOG_DB


# ---------------------------------------------------------------------------
# Database init
# ---------------------------------------------------------------------------

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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX idx_assets_content_type ON assets(content_type);
            CREATE INDEX idx_assets_status ON assets(status);
            CREATE INDEX idx_assets_path ON assets(path);
        """)
        conn.execute(
            "INSERT INTO catalog_meta (key, value) VALUES (?, ?)",
            ("schema_version", SCHEMA_VERSION),
        )
        conn.commit()
    else:
        # Verify schema version
        row = conn.execute(
            "SELECT value FROM catalog_meta WHERE key='schema_version'"
        ).fetchone()
        if row and row[0] != SCHEMA_VERSION:
            raise RuntimeError(
                f"Catalog schema version mismatch: "
                f"expected {SCHEMA_VERSION}, got {row[0]}"
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
) -> None:
    """Insert or replace an asset row."""
    now = datetime.now(timezone.utc).isoformat()

    # Preserve created_at on updates
    existing = conn.execute(
        "SELECT created_at FROM assets WHERE sha256=?", (sha256,)
    ).fetchone()
    created_at = existing["created_at"] if existing else now

    conn.execute("""
        INSERT OR REPLACE INTO assets
            (sha256, path, content_type, file_size, file_mtime,
             manifest_path, run_id, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        sha256, path, content_type, file_size, file_mtime,
        manifest_path, run_id, status, created_at, now,
    ))
    conn.commit()


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


# ---------------------------------------------------------------------------
# Backfill from existing manifests
# ---------------------------------------------------------------------------

def backfill_from_manifests(
    conn: sqlite3.Connection,
    manifest_dir: Path,
    content_type: str,
) -> int:
    """Read all manifest JSON files under manifest_dir, insert into catalog.

    Walks all runs/<run_id>/manifests/*.json under the given _ai-layer dir.
    Returns the number of manifests loaded.
    """
    count = 0
    runs_dir = manifest_dir / "runs"
    if not runs_dir.exists():
        log.warning("No runs directory found at %s", runs_dir)
        return 0

    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        manifests_dir = run_dir / "manifests"
        if not manifests_dir.exists():
            continue
        run_id = run_dir.name

        for mf in sorted(manifests_dir.glob("*.json")):
            try:
                data = json.loads(mf.read_text())
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Skipping %s: %s", mf, e)
                continue

            sha = data.get("source_sha256", "")
            source_file = data.get("source_file", "")
            if not sha or not source_file:
                log.warning("Skipping %s: missing sha256 or source_file", mf)
                continue

            upsert_asset(
                conn,
                sha256=sha,
                path=source_file,
                content_type=content_type,
                file_size=data.get("file_size_bytes"),
                file_mtime=None,
                manifest_path=str(mf.relative_to(manifest_dir)),
                run_id=run_id,
                status="indexed",
            )
            count += 1

    return count


# ---------------------------------------------------------------------------
# Filesystem scan
# ---------------------------------------------------------------------------

def scan_directory(
    conn: sqlite3.Connection,
    directory: Path,
    content_type: str,
    extensions: set[str],
    base_path: Path | None = None,
) -> dict:
    """Walk directory for files matching extensions, register in catalog.

    - New files (not in catalog) get status='discovered'
    - Existing files with changed mtime+size get status='discovered' (stale)
    - Already-indexed files are left untouched

    base_path: used to compute relative paths (defaults to directory parent).
    Returns {"new": N, "stale": N, "unchanged": N}.
    """
    base = base_path or directory.parent
    result = {"new": 0, "stale": 0, "unchanged": 0}

    for f in sorted(directory.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix.lower() not in extensions:
            continue
        if f.name.startswith("."):
            continue

        rel_path = str(f.relative_to(base))
        stat = f.stat()
        file_size = stat.st_size
        file_mtime = stat.st_mtime

        # Check by path first (faster than hashing)
        existing = conn.execute(
            "SELECT sha256, file_size, file_mtime, status, manifest_path FROM assets WHERE path=?",
            (rel_path,),
        ).fetchone()

        if existing:
            if (existing["file_size"] == file_size
                    and existing["file_mtime"] == file_mtime):
                result["unchanged"] += 1
                continue
            # mtime/size differ — hash to check if content actually changed
            sha = sha256_file(f)
            if sha == existing["sha256"]:
                # Same content, just update mtime/size, preserve status
                upsert_asset(
                    conn,
                    sha256=sha,
                    path=rel_path,
                    content_type=content_type,
                    file_size=file_size,
                    file_mtime=file_mtime,
                    status=existing["status"],
                    manifest_path=existing["manifest_path"],
                )
                result["unchanged"] += 1
            else:
                # Content actually changed — mark for reprocessing
                upsert_asset(
                    conn,
                    sha256=sha,
                    path=rel_path,
                    content_type=content_type,
                    file_size=file_size,
                    file_mtime=file_mtime,
                    status="discovered",
                )
                result["stale"] += 1
        else:
            sha = sha256_file(f)
            upsert_asset(
                conn,
                sha256=sha,
                path=rel_path,
                content_type=content_type,
                file_size=file_size,
                file_mtime=file_mtime,
                status="discovered",
            )
            result["new"] += 1

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point."""
    _log = config.setup_logging()

    if len(sys.argv) < 2:
        _log.info("Usage:")
        _log.info("  python -m src.catalog stats")
        _log.info("  python -m src.catalog backfill")
        _log.info("  python -m src.catalog scan [--type photo|document]")
        sys.exit(1)

    command = sys.argv[1]
    db_path = get_catalog_db("family")

    if command == "stats":
        if not db_path.exists():
            _log.error("Catalog not found: %s", db_path)
            _log.info("Run: python -m src.catalog backfill")
            sys.exit(1)

        conn = init_catalog(db_path)
        stats = get_stats(conn)
        total = stats.pop("_total", 0)

        _log.info("Catalog: %s", db_path)
        _log.info("Total assets: %d", total)
        _log.info("")
        for ct, statuses in sorted(stats.items()):
            ct_total = sum(statuses.values())
            _log.info("  %s: %d", ct, ct_total)
            for status, count in sorted(statuses.items()):
                _log.info("    %-12s %d", status, count)
        conn.close()

    elif command == "backfill":
        conn = init_catalog(db_path)

        photo_count = backfill_from_manifests(
            conn, config.AI_LAYER_DIR, "photo"
        )
        _log.info("Backfilled %d photo manifests", photo_count)

        doc_count = backfill_from_manifests(
            conn, config.DOC_AI_LAYER_DIR, "document"
        )
        _log.info("Backfilled %d document manifests", doc_count)

        _log.info("Total: %d assets loaded into %s", photo_count + doc_count, db_path)
        conn.close()

    elif command == "scan":
        # Parse --type flag
        content_type = None
        if "--type" in sys.argv:
            idx = sys.argv.index("--type")
            if idx + 1 < len(sys.argv):
                content_type = sys.argv[idx + 1]

        conn = init_catalog(db_path)

        if content_type is None or content_type == "photo":
            _log.info("Scanning photos: %s", config.MEDIA_ROOT)
            result = scan_directory(
                conn, config.MEDIA_ROOT, "photo", PHOTO_EXTENSIONS,
                base_path=config.MEDIA_ROOT,
            )
            _log.info("  Photos — new: %d, stale: %d, unchanged: %d",
                       result["new"], result["stale"], result["unchanged"])

        if content_type is None or content_type == "document":
            _log.info("Scanning documents: %s", config.DOCUMENTS_ROOT)
            result = scan_directory(
                conn, config.DOCUMENTS_ROOT, "document", DOCUMENT_EXTENSIONS,
                base_path=config.DOCUMENTS_ROOT,
            )
            _log.info("  Documents — new: %d, stale: %d, unchanged: %d",
                       result["new"], result["stale"], result["unchanged"])

        conn.close()

    else:
        _log.error("Unknown command: %s", command)
        sys.exit(1)


if __name__ == "__main__":
    main()
