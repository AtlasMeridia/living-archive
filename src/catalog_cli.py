"""Catalog CLI — command-line interface for the asset catalog.

Usage:
    python -m src.catalog stats              # counts by type/status
    python -m src.catalog backfill           # populate from existing manifests
    python -m src.catalog scan               # discover new files on disk
    python -m src.catalog scan --type photo  # discover only photos
    python -m src.catalog refresh            # ingest runs/manifests into cache tables
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .catalog import (
    PHOTO_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    get_catalog_db,
    init_catalog,
    get_stats,
    set_meta,
    upsert_asset,
)
from .convert import sha256_file

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backfill from existing manifests
# ---------------------------------------------------------------------------

def backfill_from_manifests(
    conn,
    manifest_dir: Path,
    content_type: str,
) -> int:
    """Read all manifest JSON files under manifest_dir, insert into catalog.

    Walks all runs/<run_id>/manifests/*.json under the given data dir.
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

def scan_directory(conn, directory: Path, content_type: str,
                   extensions: set[str], base_path: Path | None = None) -> dict:
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

        existing = conn.execute(
            "SELECT sha256, file_size, file_mtime, status, manifest_path FROM assets WHERE path=?",
            (rel_path,),
        ).fetchone()

        if existing:
            if (existing["file_size"] == file_size
                    and existing["file_mtime"] == file_mtime):
                result["unchanged"] += 1
                continue
            sha = sha256_file(f)
            if sha == existing["sha256"]:
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
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """CLI entry point."""
    _log = config.setup_logging()

    if len(sys.argv) < 2:
        _log.info("Usage:")
        _log.info("  python -m src.catalog stats")
        _log.info("  python -m src.catalog backfill")
        _log.info("  python -m src.catalog scan [--type photo|document]")
        _log.info("  python -m src.catalog refresh")
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

        set_meta(conn, "last_scan_at", datetime.now(timezone.utc).isoformat())
        conn.close()

    elif command == "refresh":
        from .catalog_refresh import refresh_all

        conn = init_catalog(db_path)
        refresh_all(conn)
        conn.close()

    else:
        _log.error("Unknown command: %s", command)
        sys.exit(1)


if __name__ == "__main__":
    main()
