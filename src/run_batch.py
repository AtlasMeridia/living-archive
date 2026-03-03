"""Batch orchestrator: auto-discover and process unprocessed photo slices.

Usage:
    python -m src.run_batch --hours 4              # 4-hour session
    python -m src.run_batch --hours 4 --push       # auto-push to Immich
    python -m src.run_batch --hours 4 --dry-run    # preview work list
    python -m src.run_batch --resume RUN_ID        # resume interrupted batch
"""

import argparse
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .analyze import analyze_photo
from .convert import find_photos, needs_conversion, prepare_for_analysis, sha256_file
from .discover import build_batch_work_list, filter_work_list
from .manifest import write_manifest, write_run_meta
from .cost import estimate_photo_cost, format_cost_summary
from .preflight import check_immich, ensure_nas_mounted
from .run_slice import step_push_to_immich

log = config.setup_logging()

# Estimated seconds per photo (used for time estimates in dry-run)
EST_SECONDS_PER_PHOTO = 32


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

    # Find and prepare photos
    sources = find_photos(slice_dir)
    if not sources:
        log.info("  No photos found in %s, skipping.", slice_dir)
        return {
            "slice_path": slice_path,
            "photos_found": 0,
            "succeeded": 0,
            "failed": 0,
            "elapsed": 0,
            "budget_exhausted": False,
        }

    log.info("  Found %d photos. Preparing...", len(sources))

    # Prepare workspace for this slice
    workspace = config.WORKSPACE_DIR
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
        # Check across all runs — if this sha already has a manifest, skip
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
        _cleanup_workspace(workspace)
        return {
            "slice_path": slice_path,
            "photos_found": len(photos),
            "succeeded": 0,
            "failed": 0,
            "elapsed": time.time() - start,
            "budget_exhausted": False,
        }

    log.info("  %d to analyze (%d already done).", len(unprocessed), len(photos) - len(unprocessed))

    # Analyze with per-photo budget checks
    client = None
    if not config.USE_CLI:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    succeeded = 0
    failed = 0
    budget_exhausted = False

    for i, photo in enumerate(unprocessed):
        # Budget check before each photo
        elapsed_so_far = time.time() - start
        time_left = budget_remaining - elapsed_so_far
        if time_left < EST_SECONDS_PER_PHOTO and i > 0:
            log.info("  Budget exhausted (%.0fs left). Stopping slice.", time_left)
            budget_exhausted = True
            break

        name = Path(photo["rel_path"]).name
        log.info("  [%d/%d] Analyzing: %s", i + 1, len(unprocessed), name)

        try:
            analysis, inference_meta = analyze_photo(
                photo["jpeg_path"], slice_path, client=client
            )
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

        # Rate limiting for API mode
        if not config.USE_CLI and i < len(unprocessed) - 1:
            time.sleep(0.5)

    # Push to Immich if requested
    if push and succeeded > 0:
        immich_errors = config.validate_immich_config()
        if immich_errors:
            log.warning("  Immich push skipped: %s", immich_errors[0])
        else:
            log.info("  Pushing %d manifests to Immich...", succeeded)
            try:
                step_push_to_immich(run_id, slice_path=slice_path)
            except Exception as e:
                log.error("  Immich push failed: %s", e)

    # Clean up workspace
    _cleanup_workspace(workspace)

    elapsed = time.time() - start
    log.info("  Slice done: %d succeeded, %d failed, %.0fs", succeeded, failed, elapsed)
    log.info("")

    return {
        "slice_path": slice_path,
        "photos_found": len(photos),
        "succeeded": succeeded,
        "failed": failed,
        "elapsed": round(elapsed, 1),
        "budget_exhausted": budget_exhausted,
    }


def _cleanup_workspace(workspace: Path) -> None:
    """Remove the workspace directory between slices."""
    if workspace.exists():
        shutil.rmtree(workspace)


def append_run_log(results: list[dict], run_id: str, elapsed: float) -> None:
    """Append batch summary to _dev/dev-log.md in existing format."""
    total_photos = sum(r["succeeded"] for r in results)
    total_failed = sum(r["failed"] for r in results)
    total_found = sum(r["photos_found"] for r in results)
    slices_completed = sum(1 for r in results if not r["budget_exhausted"] and r["succeeded"] > 0)
    slices_partial = sum(1 for r in results if r["budget_exhausted"])
    date_str = datetime.now().strftime("%Y-%m-%d")
    hours = elapsed / 3600

    lines = [
        f"\n## {date_str} — Batch run\n",
        f"**Run:** `{run_id}` — batch mode, {len(results)} slices attempted\n",
        f"**Result:** {total_photos}/{total_found} succeeded, {total_failed} failures\n",
        f"**Elapsed:** {elapsed:,.0f}s (~{hours:.1f} hours)\n",
        f"**Model:** {'CLI' if config.USE_CLI else 'API'} "
        f"({'Opus via CLI' if config.USE_CLI else config.MODEL})\n",
        "\n| Slice | Photos | Result | Time |\n",
        "|-------|--------|--------|------|\n",
    ]

    for r in results:
        if r["succeeded"] == 0 and r["failed"] == 0:
            continue
        status = f"{r['succeeded']}/{r['photos_found']}"
        if r["budget_exhausted"]:
            status += " (partial)"
        elapsed_str = f"{r['elapsed']:.0f}s"
        lines.append(f"| `{r['slice_path']}` | {r['photos_found']} | {status} | {elapsed_str} |\n")

    if slices_partial:
        lines.append(f"\n{slices_completed} slices completed, {slices_partial} partial (budget exhausted).\n")

    lines.append("\n---\n")

    # Insert after the header line (newest first)
    run_log = config.REPO_ROOT / "_dev" / "dev-log.md"
    if run_log.exists():
        content = run_log.read_text()
        # Find the end of the header section (after the first blank line following the header)
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


def main():
    parser = argparse.ArgumentParser(description="Batch photo pipeline processor")
    parser.add_argument("--hours", type=float, default=1,
                        help="Time budget in hours (default: 1)")
    parser.add_argument("--push", action="store_true",
                        help="Push metadata to Immich after each slice")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview work list without processing")
    parser.add_argument("--resume", metavar="RUN_ID",
                        help="Resume an interrupted batch run")
    parser.add_argument("--slices", nargs="+", metavar="PATTERN",
                        help="Filter slices by glob pattern (e.g. '2009*' '*/Album')")
    args = parser.parse_args()

    budget_seconds = args.hours * 3600
    run_id = args.resume or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch_start = time.time()

    log.info("Living Archive — Batch Mode")
    log.info("  Run ID: %s", run_id)
    log.info("  Budget: %.1f hours (%.0fs)", args.hours, budget_seconds)
    log.info("  Push to Immich: %s", "yes" if args.push else "no")
    if args.resume:
        log.info("  Resuming from: %s", args.resume)
    log.info("")

    # Preflight
    log.info("Preflight...")
    if not ensure_nas_mounted():
        sys.exit(1)

    if args.push:
        if not check_immich():
            log.error("  Immich required for --push but not available.")
            sys.exit(1)

    # Discovery
    log.info("")
    log.info("Discovering unprocessed albums...")
    work_list = build_batch_work_list(config.MEDIA_ROOT)

    if args.slices:
        work_list = filter_work_list(work_list, args.slices)
        log.info("  Filtered by --slices %s: %d albums match", args.slices, len(work_list))

    if not work_list:
        log.info("  No unprocessed albums found. Nothing to do.")
        sys.exit(0)

    total_remaining = sum(w["remaining"] for w in work_list)
    est_time = total_remaining * EST_SECONDS_PER_PHOTO
    est_hours = est_time / 3600

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
        sys.exit(0)

    # Process slices
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

    # Summary
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

    # Write run metadata
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
            "succeeded": r["succeeded"],
            "failed": r["failed"],
            "elapsed": r["elapsed"],
            "budget_exhausted": r["budget_exhausted"],
        } for r in results],
    )

    # Append to run log
    if results:
        append_run_log(results, run_id, total_elapsed)
        log.info("Run log updated: _dev/run-log.md")

    if total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
