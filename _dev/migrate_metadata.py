"""One-time migration: push manifest metadata to new VPS Immich instance.

The standard pipeline matches assets by originalPath, but CLI-uploaded photos
have UUID-based paths. This script matches by originalFileName instead.

Usage: python -m _dev.migrate_metadata
"""

import json
import logging
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

from src import config
from src.immich import _client as immich_client, date_estimate_to_iso, update_asset, create_album
from src.manifest import load_manifest

log = logging.getLogger("migrate_metadata")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def fetch_all_assets(client: httpx.Client) -> list[dict]:
    """Fetch all assets from Immich, paginating through results."""
    assets = []
    page = 1
    while True:
        resp = client.post(
            "/search/metadata",
            json={"page": page, "size": 250},
        )
        resp.raise_for_status()
        items = resp.json().get("assets", {}).get("items", [])
        if not items:
            break
        assets.extend(items)
        page += 1
    return assets


def build_filename_lookup(assets: list[dict]) -> dict[str, str]:
    """Map originalFileName -> asset ID."""
    lookup = {}
    for asset in assets:
        fname = asset.get("originalFileName", "")
        if fname:
            lookup[fname] = asset["id"]
    return lookup


def collect_all_manifests() -> list[Path]:
    """Collect manifests from all runs."""
    runs_dir = config.AI_LAYER_DIR / "runs"
    if not runs_dir.exists():
        return []
    manifests = []
    for run_dir in sorted(runs_dir.iterdir()):
        manifest_dir = run_dir / "manifests"
        if manifest_dir.exists():
            manifests.extend(sorted(manifest_dir.glob("*.json")))
    return manifests


def main():
    client = immich_client()

    log.info("Fetching all assets from %s...", config.IMMICH_URL)
    assets = fetch_all_assets(client)
    log.info("Found %d assets in Immich.", len(assets))

    filename_lookup = build_filename_lookup(assets)
    log.info("Built filename lookup with %d entries.", len(filename_lookup))

    manifests = collect_all_manifests()
    log.info("Found %d manifests across all runs.\n", len(manifests))

    matched = 0
    updated = 0
    skipped = 0
    failed = 0
    seen_filenames = set()
    needs_review_ids = []
    low_confidence_ids = []

    for manifest_path in manifests:
        m = load_manifest(manifest_path)
        source_name = Path(m.source_file).stem  # e.g., Photos_0164
        # Try both .jpg and original extension
        candidates = [
            source_name + ".jpg",
            source_name + ".jpeg",
            Path(m.source_file).name,
        ]

        asset_id = None
        matched_name = None
        for name in candidates:
            if name in filename_lookup:
                asset_id = filename_lookup[name]
                matched_name = name
                break

        if not asset_id:
            skipped += 1
            continue

        if matched_name in seen_filenames:
            continue  # skip duplicate manifests for same photo
        seen_filenames.add(matched_name)

        matched += 1
        analysis = m.analysis

        desc = analysis.description_en or ""
        if analysis.description_zh:
            desc = f"{desc}\n\n{analysis.description_zh}" if desc else analysis.description_zh

        date_est = analysis.date_estimate

        try:
            update_asset(
                client,
                asset_id,
                date_time_original=date_estimate_to_iso(date_est) if date_est else None,
                description=desc if desc else None,
            )
            updated += 1
            if updated % 50 == 0:
                log.info("  Updated %d assets...", updated)
        except Exception as e:
            log.error("  Failed to update %s: %s", matched_name, e)
            failed += 1

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
                "Needs Review (migration)",
                description=f"Photos with date confidence {config.CONFIDENCE_LOW}-{config.CONFIDENCE_HIGH}",
                asset_ids=needs_review_ids,
            )
            log.info("Created 'Needs Review' album with %d photos", len(needs_review_ids))
        except Exception as e:
            log.error("Failed to create Needs Review album: %s", e)

    if low_confidence_ids:
        try:
            create_album(
                client,
                "Low Confidence (migration)",
                description=f"Photos with date confidence < {config.CONFIDENCE_LOW}",
                asset_ids=low_confidence_ids,
            )
            log.info("Created 'Low Confidence' album with %d photos", len(low_confidence_ids))
        except Exception as e:
            log.error("Failed to create Low Confidence album: %s", e)

    log.info("\n--- Migration complete ---")
    log.info("Manifests scanned: %d", len(manifests))
    log.info("Assets matched:    %d", matched)
    log.info("Assets updated:    %d", updated)
    log.info("No match (skipped):%d", skipped)
    log.info("Failed:            %d", failed)
    log.info("Needs Review:      %d", len(needs_review_ids))
    log.info("Low Confidence:    %d", len(low_confidence_ids))


if __name__ == "__main__":
    main()
