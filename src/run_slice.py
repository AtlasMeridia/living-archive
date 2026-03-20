"""Main orchestrator: convert -> analyze -> manifest -> push to Immich."""

import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .analyze import analyze_photo
from .convert import find_photos, needs_conversion, prepare_for_analysis, sha256_file
from .immich import (
    _client as immich_client,
    build_path_lookup,
    create_album,
    date_estimate_to_iso,
    search_assets_by_path,
    update_asset,
)
from .manifest import load_manifest, list_manifests, write_manifest, write_run_meta
from .preflight import run_preflight
from .review import load_review

log = config.setup_logging()


def step_prepare(sources: list[Path]) -> list[dict]:
    """Prepare photos for analysis: convert/resize as needed, compute SHA-256.

    Returns list of dicts with keys: source_path, jpeg_path, sha256, rel_path
    """
    workspace = config.WORKSPACE_DIR
    workspace.mkdir(parents=True, exist_ok=True)

    results = []
    for src in sources:
        rel = src.relative_to(config.MEDIA_ROOT)
        jpeg_name = src.stem + ".jpg"
        jpeg_path = workspace / jpeg_name

        sha = sha256_file(src)

        if needs_conversion(src):
            log.info("  Converting: %s", rel)
            prepare_for_analysis(src, jpeg_path)
        else:
            log.info("  Copying (already JPEG): %s", rel)
            jpeg_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, jpeg_path)

        results.append({
            "source_path": src,
            "jpeg_path": jpeg_path,
            "sha256": sha,
            "rel_path": str(rel),
        })

    return results


def step_analyze(
    photos: list[dict], run_id: str, folder_hint: str | None = None,
) -> tuple[int, int, list[dict]]:
    """Analyze each photo with Claude and write manifests immediately.

    Returns (succeeded, failed, failures_list).
    """
    # Only create API client when using API mode
    client = None
    if not config.USE_CLI:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    folder_hint = folder_hint or config.SLICE_PATH
    succeeded = 0
    failed = 0
    failures = []

    for i, photo in enumerate(photos):
        name = Path(photo["rel_path"]).name
        log.info("  [%d/%d] Analyzing: %s", i + 1, len(photos), name)

        try:
            analysis, inference_meta = analyze_photo(
                photo["jpeg_path"], folder_hint, client=client
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
            failures.append({"file": photo["rel_path"], "error": str(e)})
            log.error("           -> FAILED: %s", e)

        # Rate limiting: only needed for API mode (CLI has natural spacing)
        if not config.USE_CLI and i < len(photos) - 1:
            time.sleep(0.5)

    return succeeded, failed, failures


def step_push_to_immich(run_id: str, slice_path: str | None = None) -> dict:
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
    needs_review_ids = []
    low_confidence_ids = []

    reviewed_skipped = 0

    for manifest_path in manifests:
        m = load_manifest(manifest_path)
        source_file = m.source_file
        analysis = m.analysis
        sha = m.source_sha256[:12]

        # Check for human review overlay — human edits are sacred
        review = load_review(run_id, sha)
        if review and review.status == "skipped":
            skipped += 1
            continue
        if review and review.status in ("corrected", "approved"):
            reviewed_skipped += 1
            continue

        # Try to find matching Immich asset by filename
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

        # Update date and description
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

        # Bucket by confidence for review albums
        confidence = analysis.date_confidence
        if confidence < config.CONFIDENCE_LOW:
            low_confidence_ids.append(asset_id)
        elif confidence < config.CONFIDENCE_HIGH:
            needs_review_ids.append(asset_id)

    # Create review albums
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

    if reviewed_skipped:
        log.info("  Skipped %d human-reviewed assets (not overwritten)", reviewed_skipped)

    return {"matched": matched, "updated": updated, "skipped": skipped, "reviewed_skipped": reviewed_skipped}


def verify_source_integrity(photos: list[dict]) -> bool:
    """Verify that source files were not modified during the run."""
    log.info("")
    log.info("Verifying source file integrity...")
    all_ok = True
    for photo in photos:
        current_sha = sha256_file(photo["source_path"])
        if current_sha != photo["sha256"]:
            log.error("  INTEGRITY FAILURE: %s", photo["rel_path"])
            all_ok = False
    if all_ok:
        log.info("  All source files unchanged.")
    return all_ok


def main():
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    start_time = time.time()

    log.info("Living Archive — Slice Run %s", run_id)
    log.info("  Source: %s", config.SLICE_DIR)
    log.info("  AI Layer: %s", config.AI_LAYER_DIR)
    if config.USE_CLI:
        log.info("  Mode: CLI (%s via %s)", config.CLI_MODEL, config.CLAUDE_CLI.name)
    else:
        log.info("  Mode: API (%s)", config.MODEL)
    log.info("")

    # Preflight: NAS mount (auto-mount if needed), Immich health, config
    if not run_preflight(require_immich=False):
        sys.exit(1)

    # Step 1: Find and prepare
    log.info("Step 1: Preparing photos for analysis...")
    sources = find_photos(config.SLICE_DIR)
    log.info("  Found %d photo files.", len(sources))
    if not sources:
        log.info("  No photos found. Exiting.")
        sys.exit(0)
    photos = step_prepare(sources)
    log.info("")

    # Step 2 & 3: Analyze and write manifests
    mode_label = "CLI" if config.USE_CLI else "API"
    log.info("Step 2: Analyzing with Claude %s...", mode_label)
    succeeded, failed, failures = step_analyze(photos, run_id)
    log.info("")

    # Write run metadata
    elapsed = time.time() - start_time
    write_run_meta(
        run_id=run_id,
        total=len(photos),
        succeeded=succeeded,
        failed=failed,
        failures=failures,
        elapsed_seconds=elapsed,
    )

    # Step 4: Push to Immich
    immich_errors = config.validate_immich_config()
    if immich_errors:
        for err in immich_errors:
            log.warning("IMMICH: %s", err)
        log.info("  Skipping Immich push (not configured). Manifests were saved.")
        push_result = {"matched": 0, "updated": 0, "skipped": 0}
    else:
        log.info("Step 3: Pushing metadata to Immich...")
        try:
            push_result = step_push_to_immich(run_id)
        except Exception as e:
            log.error("  Immich push failed: %s", e)
            log.info("  (Manifests were still saved — you can re-push later)")
            push_result = {"matched": 0, "updated": 0, "skipped": 0}
    log.info("")

    # Verify source integrity
    verify_source_integrity(photos)

    # Summary
    elapsed = time.time() - start_time
    log.info("")
    log.info("=" * 50)
    log.info("Run complete: %s", run_id)
    log.info("  Elapsed: %.1fs", elapsed)
    log.info("  Photos: %d found, %d analyzed, %d failed", len(photos), succeeded, failed)
    log.info("  Immich: %d matched, %d updated, %d skipped",
             push_result["matched"], push_result["updated"], push_result["skipped"])
    manifests_dir = config.AI_LAYER_DIR / "runs" / run_id / "manifests"
    log.info("  Manifests: %s", manifests_dir)
    log.info("=" * 50)

    if failed > 0:
        log.error("")
        log.error("Failed files:")
        for f in failures:
            log.error("  - %s: %s", f["file"], f["error"])
        sys.exit(1)


if __name__ == "__main__":
    main()
