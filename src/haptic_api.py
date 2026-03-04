"""Haptic browser API — faceted grid view of all analyzed photos.

Loads all photo manifests across runs, returns structured data for the
haptic browser. Applies LA's confidence tiers: high (>=0.8), medium
(0.5-0.8), low (<0.5). Deduplicates by SHA-256 so re-analyzed photos
don't appear twice.

Adapted from the haptic workbench pattern in naked-robot.
"""

import json
import logging
from pathlib import Path

from . import config

log = logging.getLogger("living_archive")


def api_haptic_photos() -> dict:
    """Return all analyzed photos with metadata for the haptic browser.

    Reads manifests from data/photos/runs/*/manifests/*.json — local, no NAS.
    Photo images are served separately via /api/haptic/photo?path=...
    """
    runs_dir = config.AI_LAYER_DIR / "runs"
    if not runs_dir.exists():
        return {"photos": [], "stats": {"total": 0, "confidence": {}, "nas_available": False}}

    seen: set[str] = set()
    photos = []

    # Newest runs first so latest analysis wins on dedup
    manifest_files = sorted(runs_dir.glob("*/manifests/*.json"), reverse=True)
    for mf in manifest_files:
        try:
            data = json.loads(mf.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        sha = data.get("source_sha256", "")
        if not sha or sha in seen:
            continue
        seen.add(sha)

        analysis = data.get("analysis", {})
        dc = float(analysis.get("date_confidence") or 0)

        if dc >= config.CONFIDENCE_HIGH:
            confidence = "high"
        elif dc >= config.CONFIDENCE_LOW:
            confidence = "medium"
        else:
            confidence = "low"

        date_est = str(analysis.get("date_estimate") or "")
        era = ""
        if len(date_est) >= 4:
            try:
                era = date_est[:3] + "0s"
            except (ValueError, IndexError):
                pass

        # Run ID is the parent of 'manifests'
        run_id = mf.parent.parent.name

        photos.append({
            "sha256": sha,
            "sha_short": sha[:12],
            "source_file": data.get("source_file", ""),
            "date_estimate": date_est,
            "date_precision": str(analysis.get("date_precision") or ""),
            "date_confidence": dc,
            "confidence": confidence,
            "era": era,
            "people_count": int(analysis.get("people_count") or 0),
            "description_en": str(analysis.get("description_en") or ""),
            "description_zh": str(analysis.get("description_zh") or ""),
            "people_notes": str(analysis.get("people_notes") or ""),
            "location_estimate": str(analysis.get("location_estimate") or ""),
            "tags": list(analysis.get("tags") or []),
            "run_id": run_id,
        })

    conf_counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for p in photos:
        conf_counts[p["confidence"]] += 1

    return {
        "photos": photos,
        "stats": {
            "total": len(photos),
            "confidence": conf_counts,
            "nas_available": config.MEDIA_ROOT.exists(),
        },
    }


def serve_photo(source_file: str) -> tuple[bytes, str] | None:
    """Serve a photo from NAS by its source_file relative path.

    Returns (image_bytes, content_type) or None if not available.
    """
    if not source_file or not config.MEDIA_ROOT.exists():
        return None

    photo_path = config.MEDIA_ROOT / source_file
    if not photo_path.exists():
        return None

    suffix = photo_path.suffix.lower()
    content_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".png": "image/png",
    }
    content_type = content_type_map.get(suffix, "application/octet-stream")

    try:
        return photo_path.read_bytes(), content_type
    except OSError:
        return None
