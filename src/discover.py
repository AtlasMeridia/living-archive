"""Auto-discover unprocessed photo directories for batch processing."""

import logging
from pathlib import Path

from . import config
from .catalog import PHOTO_EXTENSIONS, get_catalog_db, init_catalog
from .convert import find_photos

log = logging.getLogger(__name__)

EXCLUDE_PATTERNS = ["Unsorted Archival", "_ai-layer", "/TIFF/", "/TiIF/"]


def find_photo_dirs(root: Path) -> list[Path]:
    """Walk root for leaf directories containing TIFF/JPEG files.

    Skips directories matching EXCLUDE_PATTERNS.
    """
    dirs = []
    for dirpath in sorted(root.rglob("*")):
        if not dirpath.is_dir():
            continue
        if any(pat in str(dirpath) for pat in EXCLUDE_PATTERNS):
            continue
        photos = find_photos(dirpath)
        if photos:
            dirs.append(dirpath)
    return dirs


def build_batch_work_list(root: Path) -> list[dict]:
    """Build ordered work list of directories with unprocessed photos.

    Uses fast path-based lookups against the catalog (no hashing).
    Photos on disk whose paths aren't in the catalog are counted as
    unprocessed. Returns list sorted by remaining count ascending
    (smallest slices first).
    """
    db_path = get_catalog_db("family")
    conn = init_catalog(db_path)

    # Build set of all known indexed paths for fast lookup
    indexed_paths = set()
    rows = conn.execute(
        "SELECT path FROM assets WHERE content_type='photo' AND status='indexed'"
    ).fetchall()
    for r in rows:
        indexed_paths.add(r["path"])

    photo_dirs = find_photo_dirs(root)
    log.info("  Found %d photo directories under %s", len(photo_dirs), root)

    work_list = []
    for d in photo_dirs:
        photos = find_photos(d)
        rel_prefix = str(d.relative_to(root))

        # Count photos by checking path against catalog (no hashing)
        done = 0
        remaining = 0
        for p in photos:
            rel_path = str(p.relative_to(root))
            if rel_path in indexed_paths:
                done += 1
            else:
                remaining += 1

        if remaining > 0:
            work_list.append({
                "slice_path": rel_prefix,
                "slice_dir": d,
                "total": done + remaining,
                "remaining": remaining,
                "done": done,
            })

    conn.close()

    # Smallest slices first — maximize completed slices within time budget
    work_list.sort(key=lambda w: w["remaining"])
    return work_list
