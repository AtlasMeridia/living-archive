"""Orchestrator for document extraction — manual and automated modes.

Manual mode: prints instructions for interactive Claude Code sessions.
Auto mode: extracts text via pypdf, analyzes via configured LLM provider.

Usage:
    python -m src.run_doc_extract              # Show work to do
    python -m src.run_doc_extract --status      # Show progress on current run
    python -m src.run_doc_extract --new-run     # Start a new run (manual)
    python -m src.run_doc_extract --resume RUN  # Resume a specific run (manual)
    python -m src.run_doc_extract --auto        # Automated extraction + analysis
    python -m src.run_doc_extract --auto --resume RUN  # Resume automated run
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

log = config.setup_logging()


def get_or_create_run_id(resume: str | None = None) -> str:
    """Get a run ID — either resume an existing one or create new."""
    if resume:
        run_path = config.DOC_AI_LAYER_DIR / "runs" / resume
        if not run_path.exists():
            log.error("ERROR: Run not found: %s", resume)
            sys.exit(1)
        return resume
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_work_list(run_id: str) -> list[dict]:
    """Scan PDFs and determine which ones still need processing.

    Returns list of dicts for unprocessed files, sorted by size (smallest first).
    """
    log.info("Scanning source PDFs...")
    all_pdfs = scan_pdfs(config.DOC_SLICE_DIR)
    log.info("  Found %d PDFs total", len(all_pdfs))

    processed = get_processed_hashes(run_id)
    log.info("  Already processed: %d", len(processed))

    remaining = [p for p in all_pdfs if p["sha256"] not in processed]
    remaining.sort(key=lambda r: r["file_size_bytes"])

    log.info("  Remaining: %d", len(remaining))
    return remaining


def print_work_list(work: list[dict]) -> None:
    """Print the work list in a readable format."""
    if not work:
        log.info("")
        log.info("All documents have been processed!")
        return

    total_size = sum(w["file_size_bytes"] for w in work)
    total_pages = sum(w["page_count"] for w in work)

    log.info("")
    log.info("=" * 60)
    log.info("Documents to process: %d", len(work))
    log.info("Total size: %.2f GB", total_size / (1024**3))
    log.info("Total pages: %d", total_pages)
    log.info("=" * 60)

    # Group by size category
    small = [w for w in work if w["file_size_bytes"] < 10 * 1024 * 1024]
    medium = [w for w in work if 10 * 1024 * 1024 <= w["file_size_bytes"] < 100 * 1024 * 1024]
    large = [w for w in work if w["file_size_bytes"] >= 100 * 1024 * 1024]

    if small:
        log.info("")
        log.info("Small (<10MB): %d files", len(small))
        for w in small:
            mb = w["file_size_bytes"] / (1024**2)
            log.info("  %6.1f MB  (%4d pp)  %s", mb, w["page_count"], w["rel_path"])

    if medium:
        log.info("")
        log.info("Medium (10-100MB): %d files", len(medium))
        for w in medium:
            mb = w["file_size_bytes"] / (1024**2)
            log.info("  %6.1f MB  (%4d pp)  %s", mb, w["page_count"], w["rel_path"])

    if large:
        log.info("")
        log.info("Large (>100MB): %d files — process in page chunks", len(large))
        for w in large:
            mb = w["file_size_bytes"] / (1024**2)
            log.info("  %6.1f MB  (%4d pp)  %s", mb, w["page_count"], w["rel_path"])


def print_status(run_id: str) -> None:
    """Print status of a run."""
    manifests = list_manifests(run_id)
    td = text_dir(run_id)

    text_files = sorted(td.glob("*.txt")) if td.exists() else []

    log.info("")
    log.info("Run: %s", run_id)
    log.info("  Manifests: %d", len(manifests))
    log.info("  Text files: %d", len(text_files))

    if manifests:
        total_pages = 0
        doc_types = {}
        for mp in manifests:
            data = json.loads(mp.read_text())
            total_pages += data.get("page_count", 0)
            dt = data.get("analysis", {}).get("document_type", "unknown")
            doc_types[dt] = doc_types.get(dt, 0) + 1

        log.info("  Total pages covered: %d", total_pages)
        log.info("  Document types:")
        for dt, count in sorted(doc_types.items(), key=lambda x: -x[1]):
            log.info("    %3d  %s", count, dt)


def print_extraction_instructions(work: list[dict], run_id: str) -> None:
    """Print instructions for Claude Code to follow during extraction."""
    if not work:
        return

    log.info("")
    log.info("=" * 60)
    log.info("EXTRACTION INSTRUCTIONS FOR CLAUDE CODE")
    log.info("=" * 60)
    log.info("Run ID: %s", run_id)
    log.info("AI Layer: %s", config.DOC_AI_LAYER_DIR / "runs" / run_id)
    log.info("")
    log.info("For each PDF below, Claude Code should:")
    log.info("  1. Read the PDF with the Read tool (use pages param for large files)")
    log.info("  2. Extract all text, preserving page structure")
    log.info("  3. Analyze the document (type, dates, people, sensitivity)")
    log.info("  4. Call write_extracted_text() and write_manifest()")
    log.info("")
    log.info("Prompt template: %s", config.DOC_PROMPT_FILE)
    log.info("")

    # Print the first few as immediate targets
    batch = work[:5]
    log.info("Start with these %d documents:", len(batch))
    for i, w in enumerate(batch, 1):
        mb = w["file_size_bytes"] / (1024**2)
        log.info("")
        log.info("  [%d] %s", i, w["rel_path"])
        log.info("      Size: %.1f MB, Pages: %d, SHA: %s", mb, w["page_count"], w["sha256"][:12])
        log.info("      Full path: %s", w["path"])

    if len(work) > 5:
        log.info("")
        log.info("  ... and %d more (re-run to see updated list)", len(work) - 5)


def auto_extract(run_id: str, work: list[dict]) -> None:
    """Run automated extraction + analysis on the work list."""
    from .doc_analyze import analyze_document, get_provider, merge_chunk_analyses
    from .doc_extract_text import chunk_for_analysis, extract_text

    provider = get_provider()
    log.info("")
    log.info("=" * 60)
    log.info("AUTOMATED EXTRACTION — Provider: %s", provider.name)
    log.info("Run ID: %s", run_id)
    log.info("Documents: %d", len(work))
    log.info("=" * 60)

    succeeded = 0
    failed = 0
    skipped = 0
    failures: list[dict] = []
    start_time = time.monotonic()

    for i, w in enumerate(work, 1):
        pdf_path = Path(w["path"])
        rel_path = w["rel_path"]
        sha = w["sha256"]
        pages = w["page_count"]
        mb = w["file_size_bytes"] / (1024**2)

        log.info("")
        log.info("[%d/%d] %s (%.1f MB, %d pp)", i, len(work), rel_path, mb, pages)

        try:
            # 1. Extract text
            doc_start = time.monotonic()
            result = extract_text(pdf_path)

            if result.is_empty:
                log.warning("  SKIP: no text extracted (scanned image PDF, OCR needed)")
                skipped += 1
                continue

            log.info("  Extracted %d chars from %d pages", result.chars_extracted, result.total_pages)

            # 2. Save extracted text immediately (preserves work if analysis fails)
            write_extracted_text(run_id, sha, result.full_text)

            # 3. Chunk if large
            chunks = chunk_for_analysis(result)
            log.info("  Chunks: %d", len(chunks))

            # 4. Analyze each chunk
            chunk_results = []
            for chunk in chunks:
                if len(chunks) > 1:
                    log.info(
                        "  Analyzing chunk %d/%d (pages %d-%d)...",
                        chunk.chunk_index + 1, chunk.total_chunks,
                        chunk.page_start, chunk.page_end,
                    )
                else:
                    log.info("  Analyzing...")

                analysis, inference = analyze_document(
                    text=chunk.text,
                    source_file=rel_path,
                    page_count=pages,
                )
                chunk_results.append((analysis, inference))

            # 5. Merge if multi-chunk
            if len(chunk_results) > 1:
                analysis, inference = merge_chunk_analyses(chunk_results)
            else:
                analysis, inference = chunk_results[0]

            # 6. Write manifest
            inference_dict = inference.model_dump()
            inference_dict["chunk_count"] = len(chunks)
            write_manifest(
                run_id=run_id,
                source_file_rel=rel_path,
                source_sha256=sha,
                file_size_bytes=w["file_size_bytes"],
                page_count=pages,
                extraction={"chars_extracted": result.chars_extracted},
                analysis=analysis.model_dump(),
                inference=inference_dict,
            )

            elapsed = time.monotonic() - doc_start
            log.info(
                "  OK: %s — %s (%.1fs)",
                analysis.document_type,
                analysis.title[:60],
                elapsed,
            )
            succeeded += 1

        except Exception as exc:
            log.error("  FAIL: %s: %s", type(exc).__name__, exc)
            failed += 1
            failures.append({
                "source_file": rel_path,
                "sha256": sha,
                "error": f"{type(exc).__name__}: {exc}",
            })

    total_elapsed = time.monotonic() - start_time

    log.info("")
    log.info("=" * 60)
    log.info("Run complete: %s", run_id)
    log.info("  Succeeded: %d", succeeded)
    log.info("  Failed: %d", failed)
    log.info("  Skipped: %d (no text)", skipped)
    log.info("  Elapsed: %.1fs", total_elapsed)
    log.info("=" * 60)

    write_run_meta(
        run_id=run_id,
        total=len(work),
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        failures=failures,
        elapsed_seconds=total_elapsed,
        method="auto",
        provider=provider.name,
    )

    if failed > 0:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Document extraction orchestrator"
    )
    parser.add_argument("--status", metavar="RUN_ID", nargs="?", const="latest",
                        help="Show status of a run (default: latest)")
    parser.add_argument("--new-run", action="store_true",
                        help="Start a new extraction run")
    parser.add_argument("--resume", metavar="RUN_ID",
                        help="Resume a specific run")
    parser.add_argument("--auto", action="store_true",
                        help="Run automated extraction + analysis")
    args = parser.parse_args()

    log.info("Living Archive — Document Extraction Pipeline")
    log.info("  Source: %s", config.DOC_SLICE_DIR)
    log.info("  AI Layer: %s", config.DOC_AI_LAYER_DIR)
    log.info("")

    # Ensure NAS is mounted before checking paths
    from .preflight import ensure_nas_mounted
    if not ensure_nas_mounted(config.DOCUMENTS_ROOT):
        log.error("  Cannot reach NAS. Aborting.")
        sys.exit(1)

    errors = config.validate_doc_config()
    if not config.DOC_SLICE_DIR.exists():
        errors.append(f"Doc slice directory not found: {config.DOC_SLICE_DIR}")
    if errors:
        for err in errors:
            log.error("CONFIG: %s", err)
        sys.exit(1)

    if args.status:
        if args.status == "latest":
            from .doc_scan import find_latest_run
            latest = find_latest_run()
            if not latest:
                log.info("No runs found.")
                sys.exit(0)
            run_id = latest.name
        else:
            run_id = args.status
        print_status(run_id)
        return

    # Determine run ID
    if args.resume:
        run_id = get_or_create_run_id(resume=args.resume)
    elif args.new_run or args.auto:
        run_id = get_or_create_run_id()
        run_path = config.DOC_AI_LAYER_DIR / "runs" / run_id
        run_path.mkdir(parents=True, exist_ok=True)
        log.info("Created new run: %s", run_id)
    else:
        # Default: just show what needs to be done
        from .doc_scan import find_latest_run
        latest = find_latest_run()
        run_id = latest.name if latest else "preview"

    work = build_work_list(run_id) if run_id != "preview" else []
    if run_id == "preview":
        log.info("Scanning source PDFs...")
        all_pdfs = scan_pdfs(config.DOC_SLICE_DIR)
        work = sorted(all_pdfs, key=lambda r: r["file_size_bytes"])
        log.info("  Found %d PDFs (no previous runs)", len(work))

    if args.auto:
        if not work:
            log.info("No documents to process.")
            return
        auto_extract(run_id, work)
    else:
        print_work_list(work)
        if args.new_run or args.resume:
            print_extraction_instructions(work, run_id)


if __name__ == "__main__":
    main()
