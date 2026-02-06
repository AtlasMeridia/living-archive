"""PDF discovery, SHA-256 hashing, page counting, and change detection."""

import json
import logging
from pathlib import Path

from pypdf import PdfReader

from . import config
from .convert import sha256_file

log = logging.getLogger(__name__)


def find_pdfs(directory: Path) -> list[Path]:
    """Find all PDF files recursively in a directory."""
    pdfs = []
    for p in sorted(directory.rglob("*")):
        if p.suffix.lower() == ".pdf" and not p.name.startswith("."):
            pdfs.append(p)
    return pdfs


def get_page_count(pdf_path: Path) -> int:
    """Return the number of pages in a PDF."""
    reader = PdfReader(pdf_path)
    return len(reader.pages)


def scan_pdfs(directory: Path) -> list[dict]:
    """Scan all PDFs in directory: path, hash, size, page count.

    Returns list of dicts with keys:
        path, rel_path, sha256, file_size_bytes, page_count
    """
    pdfs = find_pdfs(directory)
    results = []
    for pdf in pdfs:
        rel = pdf.relative_to(config.DOCUMENTS_ROOT)
        log.info("  Scanning: %s", rel)
        sha = sha256_file(pdf)
        size = pdf.stat().st_size
        try:
            pages = get_page_count(pdf)
        except Exception as e:
            log.warning("    Warning: could not read page count: %s", e)
            pages = 0
        results.append({
            "path": pdf,
            "rel_path": str(rel),
            "sha256": sha,
            "file_size_bytes": size,
            "page_count": pages,
        })
    return results


def load_previous_run(run_dir: Path) -> dict[str, str]:
    """Load SHA-256 map from a previous run's manifests.

    Returns dict of {rel_path: sha256}.
    """
    manifest_dir = run_dir / "manifests"
    if not manifest_dir.exists():
        return {}
    result = {}
    for f in manifest_dir.glob("*.json"):
        data = json.loads(f.read_text())
        result[data["source_file"]] = data["source_sha256"]
    return result


def detect_changes(
    current: list[dict], previous: dict[str, str]
) -> dict[str, list[dict]]:
    """Compare current scan against previous run.

    Returns dict with keys: new, modified, unchanged, deleted.
    """
    current_map = {item["rel_path"]: item for item in current}
    prev_paths = set(previous.keys())
    curr_paths = set(current_map.keys())

    new = [current_map[p] for p in sorted(curr_paths - prev_paths)]
    deleted_paths = sorted(prev_paths - curr_paths)
    modified = []
    unchanged = []

    for p in sorted(curr_paths & prev_paths):
        if current_map[p]["sha256"] != previous[p]:
            modified.append(current_map[p])
        else:
            unchanged.append(current_map[p])

    return {
        "new": new,
        "modified": modified,
        "unchanged": unchanged,
        "deleted": [{"rel_path": p} for p in deleted_paths],
    }


def find_latest_run() -> Path | None:
    """Find the most recent run directory under DOC_AI_LAYER_DIR."""
    runs_dir = config.DOC_AI_LAYER_DIR / "runs"
    if not runs_dir.exists():
        return None
    runs = sorted(runs_dir.iterdir(), reverse=True)
    return runs[0] if runs else None


def main():
    """CLI entry point: scan PDFs and report."""
    import sys
    from . import config as _cfg
    _log = _cfg.setup_logging()

    _log.info("Document Scanner")
    _log.info("  Source: %s", config.DOC_SLICE_DIR)
    _log.info("")

    if not config.DOC_SLICE_DIR.exists():
        _log.error("ERROR: Directory not found: %s", config.DOC_SLICE_DIR)
        _log.error("Is the NAS mounted? Try: Cmd+K in Finder, smb://mneme.local/MNEME")
        sys.exit(1)

    _log.info("Scanning PDFs...")
    results = scan_pdfs(config.DOC_SLICE_DIR)
    _log.info("")
    _log.info("Found %d PDFs", len(results))

    total_size = sum(r["file_size_bytes"] for r in results)
    total_pages = sum(r["page_count"] for r in results)
    _log.info("  Total size: %.2f GB", total_size / (1024**3))
    _log.info("  Total pages: %d", total_pages)

    # Check for changes vs last run
    latest = find_latest_run()
    if latest:
        _log.info("")
        _log.info("Comparing against last run: %s", latest.name)
        previous = load_previous_run(latest)
        changes = detect_changes(results, previous)
        _log.info("  New:       %d", len(changes["new"]))
        _log.info("  Modified:  %d", len(changes["modified"]))
        _log.info("  Unchanged: %d", len(changes["unchanged"]))
        _log.info("  Deleted:   %d", len(changes["deleted"]))
    else:
        _log.info("")
        _log.info("No previous runs found — all files are new.")

    # Print largest files
    by_size = sorted(results, key=lambda r: r["file_size_bytes"], reverse=True)
    _log.info("")
    _log.info("Largest files:")
    for r in by_size[:10]:
        mb = r["file_size_bytes"] / (1024**2)
        _log.info("  %7.1f MB  (%4d pp)  %s", mb, r["page_count"], r["rel_path"])


if __name__ == "__main__":
    main()
