"""PDF discovery, SHA-256 hashing, page counting, and change detection."""

import json
from pathlib import Path

from pypdf import PdfReader

from . import config
from .convert import sha256_file


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
        print(f"  Scanning: {rel}")
        sha = sha256_file(pdf)
        size = pdf.stat().st_size
        try:
            pages = get_page_count(pdf)
        except Exception as e:
            print(f"    Warning: could not read page count: {e}")
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

    print(f"Document Scanner")
    print(f"  Source: {config.DOC_SLICE_DIR}")
    print()

    if not config.DOC_SLICE_DIR.exists():
        print(f"ERROR: Directory not found: {config.DOC_SLICE_DIR}")
        print("Is the NAS mounted? Try: Cmd+K in Finder, smb://mneme.local/MNEME")
        sys.exit(1)

    print("Scanning PDFs...")
    results = scan_pdfs(config.DOC_SLICE_DIR)
    print(f"\nFound {len(results)} PDFs")

    total_size = sum(r["file_size_bytes"] for r in results)
    total_pages = sum(r["page_count"] for r in results)
    print(f"  Total size: {total_size / (1024**3):.2f} GB")
    print(f"  Total pages: {total_pages}")

    # Check for changes vs last run
    latest = find_latest_run()
    if latest:
        print(f"\nComparing against last run: {latest.name}")
        previous = load_previous_run(latest)
        changes = detect_changes(results, previous)
        print(f"  New:       {len(changes['new'])}")
        print(f"  Modified:  {len(changes['modified'])}")
        print(f"  Unchanged: {len(changes['unchanged'])}")
        print(f"  Deleted:   {len(changes['deleted'])}")
    else:
        print("\nNo previous runs found — all files are new.")

    # Print largest files
    by_size = sorted(results, key=lambda r: r["file_size_bytes"], reverse=True)
    print(f"\nLargest files:")
    for r in by_size[:10]:
        mb = r["file_size_bytes"] / (1024**2)
        print(f"  {mb:7.1f} MB  ({r['page_count']:4d} pp)  {r['rel_path']}")


if __name__ == "__main__":
    main()
