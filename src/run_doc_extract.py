"""Document extraction pipeline: pypdf text → Claude analysis → manifest.

Usage:
    python -m src.run_doc_extract                    # Show remaining work
    python -m src.run_doc_extract --status           # Show status of latest run
    python -m src.run_doc_extract --auto             # Run extraction + analysis
    python -m src.run_doc_extract --auto --batch 20  # Cap at 20 documents
    python -m src.run_doc_extract --auto --batch 20 --delay 2  # With pacing
    python -m src.run_doc_extract --auto --dry-run   # Preview without LLM calls
    python -m src.run_doc_extract --auto --resume RUN_ID
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

from . import config
from .convert import sha256_file
from .doc_analyze import analyze_document
from .doc_extract_text import extract_text
from .doc_manifest import (
    get_processed_hashes,
    list_manifests,
    text_dir,
    write_extracted_text,
    write_manifest,
    write_run_meta,
)
from .cost import estimate_doc_cost, format_cost_summary

log = config.setup_logging()


# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------

def _scan_pdfs(directory: Path) -> list[dict]:
    """Scan all PDFs in directory: path, hash, size, page count.

    Returns list of dicts with keys:
        path, rel_path, sha256, file_size_bytes, page_count
    """
    pdfs = sorted(p for p in directory.rglob("*")
                  if p.suffix.lower() == ".pdf" and not p.name.startswith("."))
    results = []
    for pdf in pdfs:
        try:
            rel = pdf.relative_to(config.DOCUMENTS_ROOT)
        except ValueError:
            rel = pdf.relative_to(config.DOC_SLICE_DIR)
        log.info("  Scanning: %s", rel)
        size = pdf.stat().st_size
        try:
            pages = len(PdfReader(pdf).pages)
        except Exception as e:
            log.warning("    Warning: could not read page count: %s", e)
            pages = 0
        results.append({
            "path": pdf,
            "rel_path": str(rel),
            "sha256": sha256_file(pdf),
            "file_size_bytes": size,
            "page_count": pages,
        })
    return results


def _find_latest_run() -> Path | None:
    """Find the most recent run directory under DOC_AI_LAYER_DIR."""
    runs_dir = config.DOC_AI_LAYER_DIR / "runs"
    if not runs_dir.exists():
        return None
    runs = sorted((p for p in runs_dir.iterdir() if p.is_dir()), reverse=True)
    return runs[0] if runs else None


# ---------------------------------------------------------------------------
# Work list
# ---------------------------------------------------------------------------

def _build_work_list(run_id: str) -> list[dict]:
    """Scan PDFs and determine which still need processing.

    Returns list of dicts for unprocessed files, sorted by size ascending.
    """
    log.info("Scanning source PDFs...")
    all_pdfs = _scan_pdfs(config.DOC_SLICE_DIR)
    log.info("  Found %d PDFs total", len(all_pdfs))

    processed = get_processed_hashes(run_id)
    log.info("  Already processed: %d", len(processed))

    remaining = [p for p in all_pdfs if p["sha256"] not in processed]
    remaining.sort(key=lambda r: r["file_size_bytes"])

    log.info("  Remaining: %d", len(remaining))
    return remaining


def _print_work_list(work: list[dict]) -> None:
    """Print the work list as a flat sorted table."""
    if not work:
        log.info("")
        log.info("All documents have been processed.")
        return

    total_size = sum(w["file_size_bytes"] for w in work)
    total_pages = sum(w["page_count"] for w in work)

    log.info("")
    log.info("Documents to process: %d (%.2f GB, %d pages)",
             len(work), total_size / (1024**3), total_pages)
    for w in work:
        mb = w["file_size_bytes"] / (1024**2)
        log.info("  %6.1f MB  (%4d pp)  %s", mb, w["page_count"], w["rel_path"])


def _print_status(run_id: str) -> None:
    """Print status of a run: manifest + text-file counts, doc-type breakdown."""
    import json

    manifests = list_manifests(run_id)
    td = text_dir(run_id)
    text_files = sorted(td.glob("*.txt")) if td.exists() else []

    log.info("")
    log.info("Run: %s", run_id)
    log.info("  Manifests: %d", len(manifests))
    log.info("  Text files: %d", len(text_files))

    if manifests:
        total_pages = 0
        doc_types: dict[str, int] = {}
        for mp in manifests:
            data = json.loads(mp.read_text())
            total_pages += data.get("page_count", 0)
            dt = data.get("analysis", {}).get("document_type", "unknown")
            doc_types[dt] = doc_types.get(dt, 0) + 1

        log.info("  Total pages covered: %d", total_pages)
        log.info("  Document types:")
        for dt, count in sorted(doc_types.items(), key=lambda x: -x[1]):
            log.info("    %3d  %s", count, dt)


def _dry_run(work: list[dict], batch_size: int) -> None:
    """Show what would be processed without calling the LLM."""
    batch = work[:batch_size] if batch_size > 0 else work

    total_chars = sum(w["file_size_bytes"] for w in batch)
    total_pages = sum(w["page_count"] for w in batch)
    est_tokens = total_chars // 4

    log.info("")
    log.info("DRY RUN — %d of %d remaining documents", len(batch), len(work))
    log.info("  Total file size: %.2f MB", total_chars / (1024**2))
    log.info("  Total pages: %d", total_pages)
    log.info("  Estimated input tokens: ~%d (%.0fk)", est_tokens, est_tokens / 1000)
    log.info("")

    for i, w in enumerate(batch, 1):
        mb = w["file_size_bytes"] / (1024**2)
        est = w["file_size_bytes"] // 4
        log.info(
            "  [%d] %s  (%.1f MB, %d pp, ~%dk tokens)",
            i, w["rel_path"], mb, w["page_count"], est // 1000,
        )

    estimate = estimate_doc_cost(total_chars, len(batch))
    log.info("")
    log.info(format_cost_summary(estimate))

    if len(work) > len(batch):
        log.info("")
        log.info("  ... %d more documents remain after this batch", len(work) - len(batch))


# ---------------------------------------------------------------------------
# Auto-extract loop
# ---------------------------------------------------------------------------

def _auto_extract(
    run_id: str,
    work: list[dict],
    batch_size: int = 0,
    pacing_delay: float = 0,
) -> None:
    """Extract text + analyze each document, writing manifest on success."""
    full_remaining = len(work)
    if batch_size > 0:
        work = work[:batch_size]

    log.info("")
    log.info("=" * 60)
    log.info("AUTOMATED EXTRACTION — OAuth / Max Plan (%s)", config.OAUTH_MODEL)
    log.info("Run ID: %s", run_id)
    log.info("Documents: %d%s", len(work),
             f" (batch of {batch_size}, {full_remaining} remaining)" if batch_size > 0 else "")
    if pacing_delay > 0:
        log.info("Pacing delay: %.1fs between documents", pacing_delay)
    log.info("=" * 60)

    succeeded = 0
    failed = 0
    skipped = 0
    failures: list[dict] = []
    total_input_tokens = 0
    total_output_tokens = 0
    total_estimated_tokens = 0
    total_chars = 0
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
            doc_start = time.monotonic()
            result = extract_text(pdf_path)

            if result.is_empty:
                log.warning("  SKIP: no text extracted (scanned image PDF, OCR needed)")
                skipped += 1
                continue

            log.info("  Extracted %d chars from %d pages", result.chars_extracted, result.total_pages)
            write_extracted_text(run_id, sha, result.full_text)

            log.info("  Analyzing...")
            analysis, inference = analyze_document(
                text=result.full_text,
                source_file=rel_path,
                page_count=pages,
            )

            write_manifest(
                run_id=run_id,
                source_file_rel=rel_path,
                source_sha256=sha,
                file_size_bytes=w["file_size_bytes"],
                page_count=pages,
                extraction={"chars_extracted": result.chars_extracted},
                analysis=analysis.model_dump(),
                inference=inference.model_dump(),
            )

            elapsed = time.monotonic() - doc_start

            total_input_tokens += inference.input_tokens
            total_output_tokens += inference.output_tokens
            total_estimated_tokens += inference.estimated_input_tokens
            total_chars += result.chars_extracted

            log.info("  OK: %s — %s (%.1fs)",
                     analysis.document_type, analysis.title[:60], elapsed)
            log.info("  Usage so far: %d input / %d output tokens (est. ~%dk input)",
                     total_input_tokens, total_output_tokens,
                     total_estimated_tokens // 1000)
            succeeded += 1

        except Exception as exc:
            log.error("  FAIL: %s: %s", type(exc).__name__, exc)
            failed += 1
            failures.append({
                "source_file": rel_path,
                "sha256": sha,
                "error": f"{type(exc).__name__}: {exc}",
            })

        if pacing_delay > 0 and i < len(work):
            time.sleep(pacing_delay)

    total_elapsed = time.monotonic() - start_time

    usage = {
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "estimated_input_tokens": total_estimated_tokens,
        "total_chars_processed": total_chars,
    }

    log.info("")
    log.info("=" * 60)
    log.info("Run complete: %s", run_id)
    log.info("  Succeeded: %d", succeeded)
    log.info("  Failed: %d", failed)
    log.info("  Skipped: %d (no text)", skipped)
    log.info("  Elapsed: %.1fs", total_elapsed)
    log.info("  Tokens: %d input / %d output (est. ~%dk input)",
             total_input_tokens, total_output_tokens,
             total_estimated_tokens // 1000)
    log.info("=" * 60)

    remaining_after = full_remaining - len(work)
    if batch_size > 0 and remaining_after > 0:
        log.info("")
        log.info("  %d documents remain. Resume with:", remaining_after)
        log.info("    python -m src.run_doc_extract --auto --resume %s --batch %d",
                 run_id, batch_size)

    write_run_meta(
        run_id=run_id,
        total=len(work),
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        failures=failures,
        elapsed_seconds=total_elapsed,
        method="auto",
        provider="oauth",
        usage=usage,
        batch_size=batch_size,
    )

    if failed > 0:
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Document extraction orchestrator")
    parser.add_argument("--status", metavar="RUN_ID", nargs="?", const="latest",
                        help="Show status of a run (default: latest)")
    parser.add_argument("--resume", metavar="RUN_ID",
                        help="Resume a specific run")
    parser.add_argument("--auto", action="store_true",
                        help="Run automated extraction + analysis")
    parser.add_argument("--batch", metavar="N", type=int, default=0,
                        help="Process at most N documents (0 = all)")
    parser.add_argument("--delay", metavar="SECS", type=float, default=0,
                        help="Seconds to pause between documents")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be processed without calling LLM")
    args = parser.parse_args()

    log.info("Living Archive — Document Extraction Pipeline")
    log.info("  Source: %s", config.DOC_SLICE_DIR)
    log.info("  AI Layer: %s", config.DOC_AI_LAYER_DIR)
    log.info("")

    from .preflight import ensure_nas_mounted
    try:
        config.DOC_SLICE_DIR.relative_to(config.DOCUMENTS_ROOT)
        nas_check = config.DOCUMENTS_ROOT
    except ValueError:
        nas_check = config.FAMILY_ROOT
    if not ensure_nas_mounted(nas_check):
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
            latest = _find_latest_run()
            if not latest:
                log.info("No runs found.")
                sys.exit(0)
            run_id = latest.name
        else:
            run_id = args.status
        _print_status(run_id)
        return

    # Determine run ID
    if args.resume:
        run_path = config.DOC_AI_LAYER_DIR / "runs" / args.resume
        if not run_path.exists():
            log.error("Run not found: %s", args.resume)
            sys.exit(1)
        run_id = args.resume
    elif args.auto:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (config.DOC_AI_LAYER_DIR / "runs" / run_id).mkdir(parents=True, exist_ok=True)
        log.info("Created new run: %s", run_id)
    else:
        latest = _find_latest_run()
        run_id = latest.name if latest else "preview"

    if run_id == "preview":
        log.info("Scanning source PDFs...")
        work = sorted(_scan_pdfs(config.DOC_SLICE_DIR),
                      key=lambda r: r["file_size_bytes"])
        log.info("  Found %d PDFs (no previous runs)", len(work))
    else:
        work = _build_work_list(run_id)

    batch_size = args.batch or config.DOC_BATCH_SIZE
    pacing_delay = args.delay or config.DOC_PACING_DELAY

    if args.dry_run:
        _dry_run(work, batch_size)
        return

    if args.auto:
        if not work:
            log.info("No documents to process.")
            return
        _auto_extract(run_id, work, batch_size=batch_size, pacing_delay=pacing_delay)
    else:
        _print_work_list(work)


if __name__ == "__main__":
    main()
