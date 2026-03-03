"""Dedup report: find duplicates within and across media sources.

Compares two source trees on the NAS:
  - 2009 Scanned Media (TIFFs)
  - Unsorted Archival (JPEGs)

SHA-256 catches exact intra-source dupes. Cross-source comparison uses
folder name matching + filename stem overlap (since formats differ).

Usage:
    python -m src.dedup_report
    python -m src.dedup_report --output report.json
"""

import argparse
import json
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .convert import sha256_file

log = logging.getLogger(__name__)

SOURCE_A = "2009 Scanned Media"
SOURCE_B = "Unsorted Archival"


@dataclass
class FileInfo:
    path: Path
    name: str
    stem: str
    size: int
    sha256: str
    folder: str  # immediate parent relative to source root


def inventory_source(root: Path, source_rel: str) -> dict[str, list[FileInfo]]:
    """Walk a source tree and inventory all files by folder.

    Returns {folder_name: [FileInfo, ...]}.
    """
    source_dir = root / source_rel
    if not source_dir.exists():
        log.warning("Source not found: %s", source_dir)
        return {}

    inventory: dict[str, list[FileInfo]] = defaultdict(list)
    for p in sorted(source_dir.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        folder = str(p.parent.relative_to(source_dir))
        sha = sha256_file(p)
        info = FileInfo(
            path=p,
            name=p.name,
            stem=p.stem,
            size=p.stat().st_size,
            sha256=sha,
            folder=folder,
        )
        inventory[folder].append(info)

    return dict(inventory)


def find_intra_dupes(inventory: dict[str, list[FileInfo]]) -> list[list[FileInfo]]:
    """Find exact SHA-256 duplicates within a single source.

    Returns list of dupe groups (each group has 2+ files with same hash).
    """
    by_hash: dict[str, list[FileInfo]] = defaultdict(list)
    for files in inventory.values():
        for f in files:
            by_hash[f.sha256].append(f)

    return [group for group in by_hash.values() if len(group) > 1]


def compare_overlapping_folders(
    inv_a: dict[str, list[FileInfo]],
    inv_b: dict[str, list[FileInfo]],
) -> list[dict]:
    """Compare folders with matching names across two sources.

    Since formats differ (TIFF vs JPEG), compares by:
    - File count
    - Filename stem overlap
    """
    folders_a = set(inv_a.keys())
    folders_b = set(inv_b.keys())
    overlap = sorted(folders_a & folders_b)

    results = []
    for folder in overlap:
        files_a = inv_a[folder]
        files_b = inv_b[folder]
        stems_a = {f.stem for f in files_a}
        stems_b = {f.stem for f in files_b}
        common_stems = stems_a & stems_b
        only_a = stems_a - stems_b
        only_b = stems_b - stems_a

        results.append({
            "folder": folder,
            "count_a": len(files_a),
            "count_b": len(files_b),
            "common_stems": len(common_stems),
            "only_in_a": len(only_a),
            "only_in_b": len(only_b),
            "stem_overlap_pct": round(
                len(common_stems) / max(len(stems_a), len(stems_b)) * 100, 1
            ) if stems_a or stems_b else 0,
            "only_in_a_names": sorted(only_a)[:10],
            "only_in_b_names": sorted(only_b)[:10],
        })

    return results


def generate_report(root: Path) -> dict:
    """Run full dedup analysis and return structured report."""
    log.info("Inventorying %s ...", SOURCE_A)
    inv_a = inventory_source(root, SOURCE_A)
    total_a = sum(len(files) for files in inv_a.values())
    log.info("  %d folders, %d files", len(inv_a), total_a)

    log.info("Inventorying %s ...", SOURCE_B)
    inv_b = inventory_source(root, SOURCE_B)
    total_b = sum(len(files) for files in inv_b.values())
    log.info("  %d folders, %d files", len(inv_b), total_b)

    log.info("Finding intra-source duplicates...")
    dupes_a = find_intra_dupes(inv_a)
    dupes_b = find_intra_dupes(inv_b)
    log.info("  %s: %d dupe groups", SOURCE_A, len(dupes_a))
    log.info("  %s: %d dupe groups", SOURCE_B, len(dupes_b))

    log.info("Comparing overlapping folders...")
    overlaps = compare_overlapping_folders(inv_a, inv_b)
    log.info("  %d overlapping folders found", len(overlaps))

    return {
        "sources": {
            SOURCE_A: {"folders": len(inv_a), "files": total_a},
            SOURCE_B: {"folders": len(inv_b), "files": total_b},
        },
        "intra_dupes": {
            SOURCE_A: [
                {"sha256": g[0].sha256, "files": [str(f.path) for f in g]}
                for g in dupes_a
            ],
            SOURCE_B: [
                {"sha256": g[0].sha256, "files": [str(f.path) for f in g]}
                for g in dupes_b
            ],
        },
        "overlapping_folders": overlaps,
    }


def print_report(report: dict) -> None:
    """Print human-readable summary of dedup report."""
    log.info("")
    log.info("=" * 60)
    log.info("DEDUP REPORT")
    log.info("=" * 60)

    for name, stats in report["sources"].items():
        log.info("  %s: %d folders, %d files", name, stats["folders"], stats["files"])

    # Intra-source dupes
    for name, dupes in report["intra_dupes"].items():
        if dupes:
            log.info("")
            log.info("Exact duplicates within %s: %d groups", name, len(dupes))
            for g in dupes[:10]:
                log.info("  SHA %s:", g["sha256"][:12])
                for f in g["files"]:
                    log.info("    %s", f)
            if len(dupes) > 10:
                log.info("  ... and %d more groups", len(dupes) - 10)
        else:
            log.info("")
            log.info("No exact duplicates within %s", name)

    # Cross-source overlapping folders
    overlaps = report["overlapping_folders"]
    if overlaps:
        log.info("")
        log.info("Overlapping folders (%d):", len(overlaps))
        log.info("  %-35s  %5s  %5s  %5s  %s", "Folder", "SrcA", "SrcB", "Match", "Overlap")
        for o in overlaps:
            log.info(
                "  %-35s  %5d  %5d  %5d  %5.1f%%",
                o["folder"][:35], o["count_a"], o["count_b"],
                o["common_stems"], o["stem_overlap_pct"],
            )
            if o["only_in_a_names"]:
                log.info("    Only in A: %s", ", ".join(o["only_in_a_names"][:5]))
            if o["only_in_b_names"]:
                log.info("    Only in B: %s", ", ".join(o["only_in_b_names"][:5]))
    else:
        log.info("")
        log.info("No overlapping folder names found.")


def main():
    parser = argparse.ArgumentParser(description="Dedup report across media sources")
    parser.add_argument("--output", metavar="FILE",
                        help="Write JSON report to file")
    args = parser.parse_args()

    _log = config.setup_logging()

    _log.info("Living Archive — Dedup Report")
    _log.info("  Media root: %s", config.MEDIA_ROOT)
    _log.info("")

    from .preflight import ensure_nas_mounted
    if not ensure_nas_mounted(config.MEDIA_ROOT):
        _log.error("NAS not mounted. Aborting.")
        sys.exit(1)

    report = generate_report(config.MEDIA_ROOT)
    print_report(report)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(report, indent=2))
        _log.info("")
        _log.info("JSON report written to: %s", output_path)


if __name__ == "__main__":
    main()
