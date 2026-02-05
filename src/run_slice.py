"""Main orchestrator: convert -> analyze -> manifest -> push to Immich."""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from . import config
from .analyze import analyze_photo
from .convert import convert_tiff_to_jpeg, find_tiffs, sha256_file
from .immich import (
    _client as immich_client,
    build_path_lookup,
    create_album,
    date_estimate_to_iso,
    search_assets_by_path,
    update_asset,
)
from .manifest import load_manifest, list_manifests, write_manifest, write_run_meta


def step_convert(tiffs: list[Path]) -> list[dict]:
    """Convert TIFFs to JPEGs and compute SHA-256 hashes.

    Returns list of dicts with keys: tiff_path, jpeg_path, sha256, rel_path
    """
    workspace = config.WORKSPACE_DIR
    workspace.mkdir(parents=True, exist_ok=True)

    results = []
    for tiff in tiffs:
        rel = tiff.relative_to(config.MEDIA_ROOT)
        jpeg_name = tiff.stem + ".jpg"
        jpeg_path = workspace / jpeg_name

        print(f"  Converting: {rel}")
        sha = sha256_file(tiff)
        convert_tiff_to_jpeg(tiff, jpeg_path)

        results.append({
            "tiff_path": tiff,
            "jpeg_path": jpeg_path,
            "sha256": sha,
            "rel_path": str(rel),
        })

    return results


def step_analyze(photos: list[dict], run_id: str) -> tuple[int, int, list[dict]]:
    """Analyze each photo with Claude and write manifests immediately.

    Returns (succeeded, failed, failures_list).
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    folder_hint = config.SLICE_PATH
    succeeded = 0
    failed = 0
    failures = []

    for i, photo in enumerate(photos):
        name = Path(photo["rel_path"]).name
        print(f"  [{i+1}/{len(photos)}] Analyzing: {name}")

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
            print(f"           -> {analysis.get('date_estimate', '?')} "
                  f"(confidence: {analysis.get('date_confidence', '?')})")

        except Exception as e:
            failed += 1
            failures.append({"file": photo["rel_path"], "error": str(e)})
            print(f"           -> FAILED: {e}")

        # Rate limiting
        if i < len(photos) - 1:
            time.sleep(0.5)

    return succeeded, failed, failures


def step_push_to_immich(run_id: str) -> dict:
    """Push manifest data to Immich: update dates/descriptions, create review albums."""
    manifests = list_manifests(run_id)
    if not manifests:
        print("  No manifests to push.")
        return {"matched": 0, "updated": 0, "skipped": 0}

    client = immich_client()

    # Search for assets in the slice folder
    # Immich paths look like: /external/photos/2009 Scanned Media/1978/...
    print(f"  Searching Immich for assets matching '{config.SLICE_PATH}'...")
    assets = search_assets_by_path(client, config.SLICE_PATH)
    print(f"  Found {len(assets)} assets in Immich.")

    path_lookup = build_path_lookup(assets)

    matched = 0
    updated = 0
    skipped = 0
    needs_review_ids = []
    low_confidence_ids = []

    for manifest_path in manifests:
        m = load_manifest(manifest_path)
        source_file = m["source_file"]
        analysis = m["analysis"]

        # Try to find matching Immich asset by filename
        asset_id = None
        source_name = Path(source_file).name
        for immich_path, aid in path_lookup.items():
            if immich_path.endswith(source_name):
                asset_id = aid
                break

        if not asset_id:
            print(f"    No Immich match for: {source_name}")
            skipped += 1
            continue

        matched += 1

        # Update date and description
        date_est = analysis.get("date_estimate")
        desc = analysis.get("description_en", "")
        desc_zh = analysis.get("description_zh", "")
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
            print(f"    Failed to update {source_name}: {e}")

        # Bucket by confidence for review albums
        confidence = analysis.get("date_confidence", 0)
        if confidence < config.CONFIDENCE_LOW:
            low_confidence_ids.append(asset_id)
        elif confidence < config.CONFIDENCE_HIGH:
            needs_review_ids.append(asset_id)

    # Create review albums
    if needs_review_ids:
        try:
            album = create_album(
                client,
                f"Needs Review (run {run_id[:13]})",
                description=f"Photos with date confidence {config.CONFIDENCE_LOW}-{config.CONFIDENCE_HIGH}",
                asset_ids=needs_review_ids,
            )
            print(f"  Created 'Needs Review' album with {len(needs_review_ids)} photos")
        except Exception as e:
            print(f"  Failed to create Needs Review album: {e}")

    if low_confidence_ids:
        try:
            album = create_album(
                client,
                f"Low Confidence (run {run_id[:13]})",
                description=f"Photos with date confidence below {config.CONFIDENCE_LOW}",
                asset_ids=low_confidence_ids,
            )
            print(f"  Created 'Low Confidence' album with {len(low_confidence_ids)} photos")
        except Exception as e:
            print(f"  Failed to create Low Confidence album: {e}")

    return {"matched": matched, "updated": updated, "skipped": skipped}


def verify_source_integrity(photos: list[dict]) -> bool:
    """Verify that source TIFFs were not modified during the run."""
    print("\nVerifying source file integrity...")
    all_ok = True
    for photo in photos:
        current_sha = sha256_file(photo["tiff_path"])
        if current_sha != photo["sha256"]:
            print(f"  INTEGRITY FAILURE: {photo['rel_path']}")
            all_ok = False
    if all_ok:
        print("  All source files unchanged.")
    return all_ok


def main():
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    start_time = time.time()

    print(f"Living Archive — Slice Run {run_id}")
    print(f"  Source: {config.SLICE_DIR}")
    print(f"  AI Layer: {config.AI_LAYER_DIR}")
    print(f"  Model: {config.MODEL}")
    print()

    # Validate paths
    if not config.SLICE_DIR.exists():
        print(f"ERROR: Source directory not found: {config.SLICE_DIR}")
        print("Is the NAS mounted? Try: Cmd+K in Finder, smb://mneme.local/MNEME")
        sys.exit(1)

    # Step 1: Find and convert
    print("Step 1: Converting TIFFs to JPEG...")
    tiffs = find_tiffs(config.SLICE_DIR)
    print(f"  Found {len(tiffs)} TIFF files.")
    if not tiffs:
        print("  No TIFFs found. Exiting.")
        sys.exit(0)
    photos = step_convert(tiffs)
    print()

    # Step 2 & 3: Analyze and write manifests
    print("Step 2: Analyzing with Claude API...")
    succeeded, failed, failures = step_analyze(photos, run_id)
    print()

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
    print("Step 3: Pushing metadata to Immich...")
    try:
        push_result = step_push_to_immich(run_id)
    except Exception as e:
        print(f"  Immich push failed: {e}")
        print("  (Manifests were still saved — you can re-push later)")
        push_result = {"matched": 0, "updated": 0, "skipped": 0}
    print()

    # Verify source integrity
    verify_source_integrity(photos)

    # Summary
    elapsed = time.time() - start_time
    print(f"\n{'='*50}")
    print(f"Run complete: {run_id}")
    print(f"  Elapsed: {elapsed:.1f}s")
    print(f"  Photos: {len(photos)} found, {succeeded} analyzed, {failed} failed")
    print(f"  Immich: {push_result['matched']} matched, "
          f"{push_result['updated']} updated, {push_result['skipped']} skipped")
    manifests_dir = config.AI_LAYER_DIR / "runs" / run_id / "manifests"
    print(f"  Manifests: {manifests_dir}")
    print(f"{'='*50}")

    if failed > 0:
        print(f"\nFailed files:")
        for f in failures:
            print(f"  - {f['file']}: {f['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
