"""One-time migration: copy AI layer data from NAS to local data/ directory.

Dry-run by default. Use --execute to perform the copy.

Usage:
    python -m src.migrate_local              # show what would be copied
    python -m src.migrate_local --execute    # perform the copy
"""

import shutil
import sys
from pathlib import Path

from . import config

# Hardcoded NAS source paths (not from config — config now points local)
NAS_MEDIA_AI = Path("/Volumes/MNEME/05_PROJECTS/Living Archive/Family/Media/_ai-layer")
NAS_DOC_AI = Path("/Volumes/MNEME/05_PROJECTS/Living Archive/Family/Documents/_ai-layer")
NAS_FAMILY_AI = Path("/Volumes/MNEME/05_PROJECTS/Living Archive/Family/_ai-layer")

COPY_PLAN = [
    # (source, destination, label)
    (NAS_MEDIA_AI / "runs", config.DATA_DIR / "photos" / "runs", "Photo manifests"),
    (NAS_MEDIA_AI / "people", config.DATA_DIR / "people", "People registry"),
    (NAS_DOC_AI / "runs", config.DATA_DIR / "documents" / "runs", "Document manifests"),
    (NAS_FAMILY_AI / "catalog.db", config.DATA_DIR / "catalog.db", "Family catalog"),
]


def _dir_stats(path: Path) -> tuple[int, int]:
    """Return (file_count, total_bytes) for a directory tree."""
    count = 0
    size = 0
    for f in path.rglob("*"):
        if f.is_file():
            count += 1
            size += f.stat().st_size
    return count, size


def _format_size(nbytes: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def main():
    log = config.setup_logging()
    execute = "--execute" in sys.argv

    # Check NAS is mounted
    nas_root = Path("/Volumes/MNEME/05_PROJECTS/Living Archive")
    if not nas_root.exists():
        log.error("NAS not mounted at %s", nas_root)
        log.error("Mount the NAS first: Cmd+K → smb://mneme.local/MNEME")
        sys.exit(1)

    log.info("Migration: NAS _ai-layer → local data/")
    log.info("Target: %s", config.DATA_DIR)
    if not execute:
        log.info("Mode: DRY RUN (use --execute to copy)\n")
    else:
        log.info("Mode: EXECUTE\n")

    total_files = 0
    total_bytes = 0

    for source, dest, label in COPY_PLAN:
        if not source.exists():
            log.warning("  SKIP %s — source not found: %s", label, source)
            continue

        if source.is_file():
            size = source.stat().st_size
            log.info("  %s: 1 file (%s)", label, _format_size(size))
            log.info("    %s → %s", source, dest)
            total_files += 1
            total_bytes += size

            if execute:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(source), str(dest))
                log.info("    ✓ copied")
        else:
            count, size = _dir_stats(source)
            log.info("  %s: %d files (%s)", label, count, _format_size(size))
            log.info("    %s → %s", source, dest)
            total_files += count
            total_bytes += size

            if execute:
                if dest.exists():
                    log.info("    destination exists, merging...")
                    shutil.copytree(
                        str(source), str(dest), dirs_exist_ok=True
                    )
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(str(source), str(dest))
                log.info("    ✓ copied")

    log.info("")
    log.info("Total: %d files, %s", total_files, _format_size(total_bytes))

    if not execute:
        log.info("\nRun with --execute to perform the copy.")


if __name__ == "__main__":
    main()
