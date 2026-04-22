"""Living Archive pipelines — unified photo + document orchestrator.

Usage:
    python -m src.pipeline photo --hours 2 --push
    python -m src.pipeline photo --dry-run
    python -m src.pipeline photo --slices "2009*/1978"
    python -m src.pipeline photo --resume RUN_ID
    python -m src.pipeline doc --auto --batch 20 --delay 2
    python -m src.pipeline doc --auto --dry-run
    python -m src.pipeline doc --status
    python -m src.pipeline doc
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

from . import config
from .analyze import analyze_photo
from .convert import find_photos, needs_conversion, prepare_for_analysis, sha256_file
from .cost import estimate_doc_cost, estimate_photo_cost, format_cost_summary
from .discover import build_batch_work_list, filter_work_list
from .doc_analyze import analyze_document
from .doc_extract_text import extract_text
from .doc_manifest import (
    get_processed_hashes,
    list_manifests as list_doc_manifests,
    text_dir as doc_text_dir,
    write_extracted_text,
    write_manifest as write_doc_manifest,
    write_run_meta as write_doc_run_meta,
)
from .immich import (
    _client as immich_client,
    build_path_lookup,
    create_album,
    date_estimate_to_iso,
    search_assets_by_path,
    update_asset,
)
from .manifest import load_manifest, list_manifests, write_manifest, write_run_meta
from .preflight import check_immich, ensure_nas_mounted

log = config.setup_logging()

# Estimated seconds per photo (used for time estimates in dry-run)
EST_SECONDS_PER_PHOTO = 32


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _mode_label() -> str:
    """Human-readable label for the inference dispatch path."""
    return f"OAuth / Max Plan ({config.OAUTH_MODEL})"


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ===========================================================================
# PHOTO PIPELINE
# ===========================================================================

def _workspace_for_slice(run_id: str, slice_path: str) -> Path:
    """Return a run-scoped workspace path to avoid cross-run collisions."""
    safe_slice = re.sub(r"[^A-Za-z0-9._-]+", "_", slice_path.strip("/")) or "slice"
    return config.WORKSPACE_DIR / run_id / safe_slice


def _cleanup_workspace(workspace: Path) -> None:
    """Remove the workspace directory between slices."""
    if workspace.exists():
        shutil.rmtree(workspace)


def _cleanup_workspace_safe(workspace: Path) -> None:
    """Best-effort cleanup that never aborts the batch summary path."""
    try:
        _cleanup_workspace(workspace)
    except OSError as e:
        log.warning("  Workspace cleanup failed for %s: %s", workspace, e)


def _push_to_immich(run_id: str, slice_path: str | None = None) -> dict:
    """Push manifest data to Immich: update dates/descriptions, create review albums."""
    slice_path = slice_path or config.SLICE_PATH

    manifests = list_manifests(run_id)
    if not manifests:
        log.info("  No manifests to push.")
        return {"matched": 0, "updated": 0, "skipped": 0}

    client = immich_client()

    log.info("  Searching Immich for assets matching '%s'...", slice_path)
    assets = search_assets_by_path(client, slice_path)
    log.info("  Found %d assets in Immich.", len(assets))

    path_lookup = build_path_lookup(assets)

    matched = 0
    updated = 0
    skipped = 0
    needs_review_ids: list[str] = []
    low_confidence_ids: list[str] = []

    for manifest_path in manifests:
        m = load_manifest(manifest_path)
        source_file = m.source_file
        analysis = m.analysis

        asset_id = None
        source_name = Path(source_file).name
        for immich_path, aid in path_lookup.items():
            if immich_path.endswith(source_name):
                asset_id = aid
                break

        if not asset_id:
            log.info("    No Immich match for: %s", source_name)
            skipped += 1
            continue

        matched += 1

        date_est = analysis.date_estimate
        desc = analysis.description_en
        desc_zh = analysis.description_zh
        if desc_zh:
            desc = f"{desc}\n\n{desc_zh}"

        try:
            update_asset(
                client,
                asset_id,
                date_time_original=date_estimate_to_iso(date_est) if date_est else None,
                description=desc if desc else None,
            )
            updated += 1
        except Exception as e:
            log.error("    Failed to update %s: %s", source_name, e)

        confidence = analysis.date_confidence
        if confidence < config.CONFIDENCE_LOW:
            low_confidence_ids.append(asset_id)
        elif confidence < config.CONFIDENCE_HIGH:
            needs_review_ids.append(asset_id)

    if needs_review_ids:
        try:
            create_album(
                client,
                f"Needs Review (run {run_id[:13]})",
                description=f"Photos with date confidence {config.CONFIDENCE_LOW}-{config.CONFIDENCE_HIGH}",
                asset_ids=needs_review_ids,
            )
            log.info("  Created 'Needs Review' album with %d photos", len(needs_review_ids))
        except Exception as e:
            log.error("  Failed to create Needs Review album: %s", e)

    if low_confidence_ids:
        try:
            create_album(
                client,
                f"Low Confidence (run {run_id[:13]})",
                description=f"Photos with date confidence below {config.CONFIDENCE_LOW}",
                asset_ids=low_confidence_ids,
            )
            log.info("  Created 'Low Confidence' album with %d photos", len(low_confidence_ids))
        except Exception as e:
            log.error("  Failed to create Low Confidence album: %s", e)

    return {"matched": matched, "updated": updated, "skipped": skipped}


def process_slice(
    slice_path: str,
    slice_dir: Path,
    run_id: str,
    budget_remaining: float,
    push: bool,
) -> dict:
    """Process a single slice within the batch.

    Converts photos, analyzes each with budget checks, optionally pushes to
    Immich. Returns stats dict.
    """
    start = time.time()
    log.info("--- Slice: %s ---", slice_path)

    sources = find_photos(slice_dir)

    if not sources:
        log.info("  No photos found in %s, skipping.", slice_dir)
        return {
            "slice_path": slice_path,
            "photos_found": 0,
            "photos_considered": 0,
            "succeeded": 0,
            "failed": 0,
            "elapsed": 0,
            "budget_exhausted": False,
        }

    log.info("  Found %d photos. Preparing...", len(sources))

    workspace = _workspace_for_slice(run_id, slice_path)
    workspace.mkdir(parents=True, exist_ok=True)

    photos = []
    for src in sources:
        rel = src.relative_to(config.MEDIA_ROOT)
        jpeg_name = src.stem + ".jpg"
        jpeg_path = workspace / jpeg_name
        sha = sha256_file(src)

        if needs_conversion(src):
            prepare_for_analysis(src, jpeg_path)
        else:
            jpeg_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, jpeg_path)

        photos.append({
            "source_path": src,
            "jpeg_path": jpeg_path,
            "sha256": sha,
            "rel_path": str(rel),
        })

    # Check for already-processed photos (skip them)
    unprocessed = []
    for photo in photos:
        manifest_name = f"{photo['sha256'][:12]}.json"
        ai_runs = config.AI_LAYER_DIR / "runs"
        already_done = False
        if ai_runs.exists():
            for run_dir in ai_runs.iterdir():
                if (run_dir / "manifests" / manifest_name).exists():
                    already_done = True
                    break
        if already_done:
            log.info("  Skipping (already processed): %s", Path(photo["rel_path"]).name)
        else:
            unprocessed.append(photo)

    if not unprocessed:
        log.info("  All %d photos already processed, skipping slice.", len(photos))
        _cleanup_workspace_safe(workspace)
        return {
            "slice_path": slice_path,
            "photos_found": len(sources),
            "photos_considered": len(photos),
            "succeeded": 0,
            "failed": 0,
            "elapsed": time.time() - start,
            "budget_exhausted": False,
        }

    log.info("  %d to analyze (%d already done).", len(unprocessed), len(photos) - len(unprocessed))

    succeeded = 0
    failed = 0
    budget_exhausted = False

    for i, photo in enumerate(unprocessed):
        elapsed_so_far = time.time() - start
        time_left = budget_remaining - elapsed_so_far
        if time_left < EST_SECONDS_PER_PHOTO and i > 0:
            log.info("  Budget exhausted (%.0fs left). Stopping slice.", time_left)
            budget_exhausted = True
            break

        name = Path(photo["rel_path"]).name
        log.info("  [%d/%d] Analyzing: %s", i + 1, len(unprocessed), name)

        try:
            analysis, inference_meta = analyze_photo(photo["jpeg_path"], slice_path)
            write_manifest(
                run_id=run_id,
                source_file_rel=photo["rel_path"],
                source_sha256=photo["sha256"],
                analysis=analysis,
                inference=inference_meta,
            )
            succeeded += 1
            log.info("           -> %s (confidence: %s)",
                     analysis.date_estimate or "?", analysis.date_confidence)
        except Exception as e:
            failed += 1
            log.error("           -> FAILED: %s", e)

        if i < len(unprocessed) - 1:
            time.sleep(0.5)

    if push and succeeded > 0:
        immich_errors = config.validate_immich_config()
        if immich_errors:
            log.warning("  Immich push skipped: %s", immich_errors[0])
        else:
            log.info("  Pushing %d manifests to Immich...", succeeded)
            try:
                _push_to_immich(run_id, slice_path=slice_path)
            except Exception as e:
                log.error("  Immich push failed: %s", e)

    _cleanup_workspace_safe(workspace)

    elapsed = time.time() - start
    log.info("  Slice done: %d succeeded, %d failed, %.0fs", succeeded, failed, elapsed)
    log.info("")

    return {
        "slice_path": slice_path,
        "photos_found": len(sources),
        "photos_considered": len(photos),
        "succeeded": succeeded,
        "failed": failed,
        "elapsed": round(elapsed, 1),
        "budget_exhausted": budget_exhausted,
    }


def _append_photo_run_log(results: list[dict], run_id: str, elapsed: float) -> None:
    """Append photo batch summary to _dev/dev-log.md."""
    total_photos = sum(r["succeeded"] for r in results)
    total_failed = sum(r["failed"] for r in results)
    total_found = sum(r.get("photos_considered", r["photos_found"]) for r in results)
    slices_completed = sum(1 for r in results if not r["budget_exhausted"] and r["succeeded"] > 0)
    slices_partial = sum(1 for r in results if r["budget_exhausted"])
    date_str = datetime.now().strftime("%Y-%m-%d")
    hours = elapsed / 3600

    lines = [
        f"\n## {date_str} — Batch run\n",
        f"**Run:** `{run_id}` — batch mode, {len(results)} slices attempted\n",
        f"**Result:** {total_photos}/{total_found} succeeded, {total_failed} failures\n",
        f"**Elapsed:** {elapsed:,.0f}s (~{hours:.1f} hours)\n",
        f"**Model:** {_mode_label()}\n",
        "\n| Slice | Photos | Result | Time |\n",
        "|-------|--------|--------|------|\n",
    ]

    for r in results:
        if r["succeeded"] == 0 and r["failed"] == 0:
            continue
        considered = r.get("photos_considered", r["photos_found"])
        status = f"{r['succeeded']}/{considered}"
        if r["budget_exhausted"]:
            status += " (partial)"
        elapsed_str = f"{r['elapsed']:.0f}s"
        lines.append(f"| `{r['slice_path']}` | {r['photos_found']} | {status} | {elapsed_str} |\n")

    if slices_partial:
        lines.append(f"\n{slices_completed} slices completed, {slices_partial} partial (budget exhausted).\n")

    lines.append("\n---\n")

    run_log = config.REPO_ROOT / "_dev" / "dev-log.md"
    if run_log.exists():
        content = run_log.read_text()
        header_end = content.find("\n\n## ")
        if header_end == -1:
            header_end = content.find("\n\n")
        if header_end != -1:
            new_content = content[:header_end + 1] + "".join(lines) + content[header_end + 1:]
        else:
            new_content = content + "\n" + "".join(lines)
        run_log.write_text(new_content)
    else:
        run_log.parent.mkdir(parents=True, exist_ok=True)
        run_log.write_text("# Run Log\n" + "".join(lines))


def run_photo(args: argparse.Namespace) -> int:
    """Run the photo batch pipeline. Returns an exit code."""
    budget_seconds = args.hours * 3600
    run_id = args.resume or _new_run_id()
    batch_start = time.time()

    log.info("Living Archive — Photo Pipeline")
    log.info("  Run ID: %s", run_id)
    log.info("  Budget: %.1f hours (%.0fs)", args.hours, budget_seconds)
    log.info("  Push to Immich: %s", "yes" if args.push else "no")
    if args.resume:
        log.info("  Resuming from: %s", args.resume)
    log.info("")

    log.info("Preflight...")
    if not ensure_nas_mounted():
        return 1

    if args.push and not check_immich():
        log.error("  Immich required for --push but not available.")
        return 1

    log.info("")
    log.info("Discovering unprocessed albums...")
    work_list = build_batch_work_list(config.MEDIA_ROOT)

    if args.slices:
        work_list = filter_work_list(work_list, args.slices)
        log.info("  Filtered by --slices %s: %d albums match", args.slices, len(work_list))

    if not work_list:
        log.info("  No unprocessed albums found. Nothing to do.")
        return 0

    total_remaining = sum(w["remaining"] for w in work_list)
    est_hours = (total_remaining * EST_SECONDS_PER_PHOTO) / 3600

    log.info("")
    log.info("Work list: %d albums, %d photos remaining", len(work_list), total_remaining)
    log.info("Estimated time: %.1f hours (at ~%ds/photo)", est_hours, EST_SECONDS_PER_PHOTO)
    log.info("")

    for i, w in enumerate(work_list):
        log.info("  %2d. %-50s %d remaining (%d done)",
                 i + 1, w["slice_path"], w["remaining"], w["done"])
    log.info("")

    if args.dry_run:
        estimate = estimate_photo_cost(total_remaining)
        log.info(format_cost_summary(estimate))
        log.info("")
        log.info("Dry run — exiting without processing.")
        return 0

    results = []
    for w in work_list:
        elapsed_total = time.time() - batch_start
        budget_left = budget_seconds - elapsed_total

        if budget_left < EST_SECONDS_PER_PHOTO:
            log.info("Budget exhausted (%.0fs remaining). Stopping.", budget_left)
            break

        result = process_slice(
            slice_path=w["slice_path"],
            slice_dir=w["slice_dir"],
            run_id=run_id,
            budget_remaining=budget_left,
            push=args.push,
        )
        results.append(result)

        if result["budget_exhausted"]:
            log.info("Budget exhausted during slice. Stopping.")
            break

    total_elapsed = time.time() - batch_start
    total_succeeded = sum(r["succeeded"] for r in results)
    total_failed = sum(r["failed"] for r in results)
    slices_with_work = [r for r in results if r["succeeded"] > 0 or r["failed"] > 0]

    log.info("=" * 60)
    log.info("Batch complete: %s", run_id)
    log.info("  Elapsed: %.0fs (%.1f hours)", total_elapsed, total_elapsed / 3600)
    log.info("  Slices processed: %d", len(slices_with_work))
    log.info("  Photos: %d succeeded, %d failed", total_succeeded, total_failed)
    log.info("=" * 60)

    write_run_meta(
        run_id=run_id,
        total=total_succeeded + total_failed,
        succeeded=total_succeeded,
        failed=total_failed,
        failures=[],
        elapsed_seconds=total_elapsed,
        slice_path="batch",
        batch_slices=[{
            "slice_path": r["slice_path"],
            "photos_found": r["photos_found"],
            "photos_considered": r.get("photos_considered", r["photos_found"]),
            "succeeded": r["succeeded"],
            "failed": r["failed"],
            "elapsed": r["elapsed"],
            "budget_exhausted": r["budget_exhausted"],
        } for r in results],
    )

    if results:
        _append_photo_run_log(results, run_id, total_elapsed)
        log.info("Run log updated: _dev/dev-log.md")

    return 1 if total_failed > 0 else 0


# ===========================================================================
# DOCUMENT PIPELINE
# ===========================================================================

def _scan_pdfs(directory: Path) -> list[dict]:
    """Scan all PDFs in directory: path, hash, size, page count."""
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


def _find_latest_doc_run() -> Path | None:
    """Find the most recent document run directory."""
    runs_dir = config.DOC_AI_LAYER_DIR / "runs"
    if not runs_dir.exists():
        return None
    runs = sorted((p for p in runs_dir.iterdir() if p.is_dir()), reverse=True)
    return runs[0] if runs else None


def _build_doc_work_list(run_id: str) -> list[dict]:
    """Scan PDFs and determine which still need processing."""
    log.info("Scanning source PDFs...")
    all_pdfs = _scan_pdfs(config.DOC_SLICE_DIR)
    log.info("  Found %d PDFs total", len(all_pdfs))

    processed = get_processed_hashes(run_id)
    log.info("  Already processed: %d", len(processed))

    remaining = [p for p in all_pdfs if p["sha256"] not in processed]
    remaining.sort(key=lambda r: r["file_size_bytes"])

    log.info("  Remaining: %d", len(remaining))
    return remaining


def _print_doc_work_list(work: list[dict]) -> None:
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


def _print_doc_status(run_id: str) -> None:
    """Print status of a doc run: manifest + text-file counts, doc-type breakdown."""
    manifests = list_doc_manifests(run_id)
    td = doc_text_dir(run_id)
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


def _doc_dry_run(work: list[dict], batch_size: int) -> None:
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


def _auto_extract(run_id: str, work: list[dict], batch_size: int, pacing_delay: float) -> int:
    """Extract text + analyze each document, writing manifest on success.

    Returns an exit code (0 ok, 1 if any failed).
    """
    full_remaining = len(work)
    if batch_size > 0:
        work = work[:batch_size]

    log.info("")
    log.info("=" * 60)
    log.info("AUTOMATED EXTRACTION — %s", _mode_label())
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

            write_doc_manifest(
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
        log.info("    python -m src.pipeline doc --auto --resume %s --batch %d",
                 run_id, batch_size)

    write_doc_run_meta(
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

    return 1 if failed > 0 else 0


def run_doc(args: argparse.Namespace) -> int:
    """Run the document pipeline. Returns an exit code."""
    log.info("Living Archive — Document Pipeline")
    log.info("  Source: %s", config.DOC_SLICE_DIR)
    log.info("  AI Layer: %s", config.DOC_AI_LAYER_DIR)
    log.info("")

    try:
        config.DOC_SLICE_DIR.relative_to(config.DOCUMENTS_ROOT)
        nas_check = config.DOCUMENTS_ROOT
    except ValueError:
        nas_check = config.FAMILY_ROOT
    if not ensure_nas_mounted(nas_check):
        log.error("  Cannot reach NAS. Aborting.")
        return 1

    errors = config.validate_doc_config()
    if not config.DOC_SLICE_DIR.exists():
        errors.append(f"Doc slice directory not found: {config.DOC_SLICE_DIR}")
    if errors:
        for err in errors:
            log.error("CONFIG: %s", err)
        return 1

    if args.status is not None:
        if args.status == "latest":
            latest = _find_latest_doc_run()
            if not latest:
                log.info("No runs found.")
                return 0
            run_id = latest.name
        else:
            run_id = args.status
        _print_doc_status(run_id)
        return 0

    if args.resume:
        run_path = config.DOC_AI_LAYER_DIR / "runs" / args.resume
        if not run_path.exists():
            log.error("Run not found: %s", args.resume)
            return 1
        run_id = args.resume
    elif args.auto:
        run_id = _new_run_id()
        (config.DOC_AI_LAYER_DIR / "runs" / run_id).mkdir(parents=True, exist_ok=True)
        log.info("Created new run: %s", run_id)
    else:
        latest = _find_latest_doc_run()
        run_id = latest.name if latest else "preview"

    if run_id == "preview":
        log.info("Scanning source PDFs...")
        work = sorted(_scan_pdfs(config.DOC_SLICE_DIR),
                      key=lambda r: r["file_size_bytes"])
        log.info("  Found %d PDFs (no previous runs)", len(work))
    else:
        work = _build_doc_work_list(run_id)

    batch_size = args.batch or config.DOC_BATCH_SIZE
    pacing_delay = args.delay or config.DOC_PACING_DELAY

    if args.dry_run:
        _doc_dry_run(work, batch_size)
        return 0

    if args.auto:
        if not work:
            log.info("No documents to process.")
            return 0
        return _auto_extract(run_id, work, batch_size=batch_size, pacing_delay=pacing_delay)

    _print_doc_work_list(work)
    return 0


# ===========================================================================
# CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Living Archive unified pipeline (photo + document)"
    )
    subparsers = parser.add_subparsers(dest="pipeline", required=True, metavar="PIPELINE")

    # photo subparser
    photo = subparsers.add_parser("photo", help="Run the photo pipeline")
    photo.add_argument("--hours", type=float, default=1,
                       help="Time budget in hours (default: 1)")
    photo.add_argument("--push", action="store_true",
                       help="Push metadata to Immich after each slice")
    photo.add_argument("--dry-run", action="store_true",
                       help="Preview work list without processing")
    photo.add_argument("--resume", metavar="RUN_ID",
                       help="Resume an interrupted batch run")
    photo.add_argument("--slices", nargs="+", metavar="PATTERN",
                       help="Filter slices by glob pattern (e.g. '2009*' '*/Album')")

    # document subparser
    doc = subparsers.add_parser("doc", help="Run the document pipeline")
    doc.add_argument("--status", metavar="RUN_ID", nargs="?", const="latest", default=None,
                     help="Show status of a run (default: latest)")
    doc.add_argument("--resume", metavar="RUN_ID",
                     help="Resume a specific run")
    doc.add_argument("--auto", action="store_true",
                     help="Run automated extraction + analysis")
    doc.add_argument("--batch", metavar="N", type=int, default=0,
                     help="Process at most N documents (0 = all)")
    doc.add_argument("--delay", metavar="SECS", type=float, default=0,
                     help="Seconds to pause between documents")
    doc.add_argument("--dry-run", action="store_true",
                     help="Show what would be processed without calling LLM")

    args = parser.parse_args()

    if args.pipeline == "photo":
        sys.exit(run_photo(args))
    elif args.pipeline == "doc":
        sys.exit(run_doc(args))


if __name__ == "__main__":
    main()
