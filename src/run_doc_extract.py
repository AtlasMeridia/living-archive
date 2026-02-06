"""Orchestrator for Claude Code document extraction sessions.

This script prepares the work list and tracks progress. Claude Code handles
the actual PDF reading, text extraction, and analysis interactively.

Usage:
    python -m src.run_doc_extract              # Show work to do
    python -m src.run_doc_extract --status      # Show progress on current run
    python -m src.run_doc_extract --new-run     # Start a new run
    python -m src.run_doc_extract --resume RUN  # Resume a specific run
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .convert import sha256_file
from .doc_manifest import (
    get_processed_hashes,
    list_manifests,
    text_dir,
    write_extracted_text,
    write_manifest,
    write_run_meta,
)
from .doc_scan import find_pdfs, get_page_count, scan_pdfs


def get_or_create_run_id(resume: str | None = None) -> str:
    """Get a run ID — either resume an existing one or create new."""
    if resume:
        run_path = config.DOC_AI_LAYER_DIR / "runs" / resume
        if not run_path.exists():
            print(f"ERROR: Run not found: {resume}")
            sys.exit(1)
        return resume
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_work_list(run_id: str) -> list[dict]:
    """Scan PDFs and determine which ones still need processing.

    Returns list of dicts for unprocessed files, sorted by size (smallest first).
    """
    print("Scanning source PDFs...")
    all_pdfs = scan_pdfs(config.DOC_SLICE_DIR)
    print(f"  Found {len(all_pdfs)} PDFs total")

    processed = get_processed_hashes(run_id)
    print(f"  Already processed: {len(processed)}")

    remaining = [p for p in all_pdfs if p["sha256"] not in processed]
    remaining.sort(key=lambda r: r["file_size_bytes"])

    print(f"  Remaining: {len(remaining)}")
    return remaining


def print_work_list(work: list[dict]) -> None:
    """Print the work list in a readable format."""
    if not work:
        print("\nAll documents have been processed!")
        return

    total_size = sum(w["file_size_bytes"] for w in work)
    total_pages = sum(w["page_count"] for w in work)

    print(f"\n{'='*60}")
    print(f"Documents to process: {len(work)}")
    print(f"Total size: {total_size / (1024**3):.2f} GB")
    print(f"Total pages: {total_pages}")
    print(f"{'='*60}")

    # Group by size category
    small = [w for w in work if w["file_size_bytes"] < 10 * 1024 * 1024]
    medium = [w for w in work if 10 * 1024 * 1024 <= w["file_size_bytes"] < 100 * 1024 * 1024]
    large = [w for w in work if w["file_size_bytes"] >= 100 * 1024 * 1024]

    if small:
        print(f"\nSmall (<10MB): {len(small)} files")
        for w in small:
            mb = w["file_size_bytes"] / (1024**2)
            print(f"  {mb:6.1f} MB  ({w['page_count']:4d} pp)  {w['rel_path']}")

    if medium:
        print(f"\nMedium (10-100MB): {len(medium)} files")
        for w in medium:
            mb = w["file_size_bytes"] / (1024**2)
            print(f"  {mb:6.1f} MB  ({w['page_count']:4d} pp)  {w['rel_path']}")

    if large:
        print(f"\nLarge (>100MB): {len(large)} files — process in page chunks")
        for w in large:
            mb = w["file_size_bytes"] / (1024**2)
            print(f"  {mb:6.1f} MB  ({w['page_count']:4d} pp)  {w['rel_path']}")


def print_status(run_id: str) -> None:
    """Print status of a run."""
    manifests = list_manifests(run_id)
    td = text_dir(run_id)

    text_files = sorted(td.glob("*.txt")) if td.exists() else []

    print(f"\nRun: {run_id}")
    print(f"  Manifests: {len(manifests)}")
    print(f"  Text files: {len(text_files)}")

    if manifests:
        total_pages = 0
        doc_types = {}
        for mp in manifests:
            data = json.loads(mp.read_text())
            total_pages += data.get("page_count", 0)
            dt = data.get("analysis", {}).get("document_type", "unknown")
            doc_types[dt] = doc_types.get(dt, 0) + 1

        print(f"  Total pages covered: {total_pages}")
        print(f"  Document types:")
        for dt, count in sorted(doc_types.items(), key=lambda x: -x[1]):
            print(f"    {count:3d}  {dt}")


def print_extraction_instructions(work: list[dict], run_id: str) -> None:
    """Print instructions for Claude Code to follow during extraction."""
    if not work:
        return

    print(f"\n{'='*60}")
    print(f"EXTRACTION INSTRUCTIONS FOR CLAUDE CODE")
    print(f"{'='*60}")
    print(f"Run ID: {run_id}")
    print(f"AI Layer: {config.DOC_AI_LAYER_DIR / 'runs' / run_id}")
    print()
    print("For each PDF below, Claude Code should:")
    print("  1. Read the PDF with the Read tool (use pages param for large files)")
    print("  2. Extract all text, preserving page structure")
    print("  3. Analyze the document (type, dates, people, sensitivity)")
    print("  4. Call write_extracted_text() and write_manifest()")
    print()
    print(f"Prompt template: {config.DOC_PROMPT_FILE}")
    print()

    # Print the first few as immediate targets
    batch = work[:5]
    print(f"Start with these {len(batch)} documents:")
    for i, w in enumerate(batch, 1):
        mb = w["file_size_bytes"] / (1024**2)
        print(f"\n  [{i}] {w['rel_path']}")
        print(f"      Size: {mb:.1f} MB, Pages: {w['page_count']}, SHA: {w['sha256'][:12]}")
        print(f"      Full path: {w['path']}")

    if len(work) > 5:
        print(f"\n  ... and {len(work) - 5} more (re-run to see updated list)")


def main():
    parser = argparse.ArgumentParser(
        description="Document extraction orchestrator for Claude Code"
    )
    parser.add_argument("--status", metavar="RUN_ID", nargs="?", const="latest",
                        help="Show status of a run (default: latest)")
    parser.add_argument("--new-run", action="store_true",
                        help="Start a new extraction run")
    parser.add_argument("--resume", metavar="RUN_ID",
                        help="Resume a specific run")
    args = parser.parse_args()

    print(f"Living Archive — Document Extraction Pipeline")
    print(f"  Source: {config.DOC_SLICE_DIR}")
    print(f"  AI Layer: {config.DOC_AI_LAYER_DIR}")
    print()

    if not config.DOC_SLICE_DIR.exists():
        print(f"ERROR: Source directory not found: {config.DOC_SLICE_DIR}")
        print("Is the NAS mounted? Try: Cmd+K in Finder, smb://mneme.local/MNEME")
        sys.exit(1)

    if args.status:
        if args.status == "latest":
            from .doc_scan import find_latest_run
            latest = find_latest_run()
            if not latest:
                print("No runs found.")
                sys.exit(0)
            run_id = latest.name
        else:
            run_id = args.status
        print_status(run_id)
        return

    if args.resume:
        run_id = get_or_create_run_id(resume=args.resume)
    elif args.new_run:
        run_id = get_or_create_run_id()
        # Create the run directory
        run_path = config.DOC_AI_LAYER_DIR / "runs" / run_id
        run_path.mkdir(parents=True, exist_ok=True)
        print(f"Created new run: {run_id}")
    else:
        # Default: just show what needs to be done
        # Use latest run if it exists, otherwise show all as new
        from .doc_scan import find_latest_run
        latest = find_latest_run()
        run_id = latest.name if latest else "preview"

    work = build_work_list(run_id) if run_id != "preview" else []
    if run_id == "preview":
        # No existing run — show all PDFs
        print("Scanning source PDFs...")
        all_pdfs = scan_pdfs(config.DOC_SLICE_DIR)
        work = sorted(all_pdfs, key=lambda r: r["file_size_bytes"])
        print(f"  Found {len(work)} PDFs (no previous runs)")

    print_work_list(work)

    if args.new_run or args.resume:
        print_extraction_instructions(work, run_id)


if __name__ == "__main__":
    main()
