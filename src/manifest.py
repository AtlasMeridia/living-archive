"""Read/write manifest JSON files to the AI layer."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .models import InferenceMetadata, PhotoAnalysis, PhotoManifest
from .util import atomic_write_text

log = logging.getLogger("living_archive")


def run_dir(run_id: str) -> Path:
    """Return the directory for a given run."""
    return config.AI_LAYER_DIR / "runs" / run_id / "manifests"


def write_manifest(
    run_id: str,
    source_file_rel: str,
    source_sha256: str,
    analysis: PhotoAnalysis,
    inference: InferenceMetadata,
) -> Path:
    """Write a single photo manifest JSON.

    Returns the path to the written file.
    """
    manifest = {
        "source_file": source_file_rel,
        "source_sha256": source_sha256,
        "analysis": analysis.model_dump(),
        "inference": {
            **inference.model_dump(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

    out_path = run_dir(run_id) / f"{source_sha256[:12]}.json"
    atomic_write_text(out_path, json.dumps(manifest, indent=2, ensure_ascii=False))

    # Update catalog (non-fatal — catalog is optional)
    try:
        from .catalog import record_indexed_asset
        record_indexed_asset(
            sha256=source_sha256,
            path=source_file_rel,
            content_type="photo",
            manifest_path=str(out_path.relative_to(config.AI_LAYER_DIR)),
            run_id=run_id,
        )
    except Exception:
        log.warning("Catalog update failed for %s (non-fatal)", out_path.name, exc_info=True)

    return out_path


def write_run_meta(
    run_id: str,
    total: int,
    succeeded: int,
    failed: int,
    failures: list[dict],
    elapsed_seconds: float,
    *,
    slice_path: str | None = None,
    batch_slices: list[dict] | None = None,
) -> Path:
    """Write run-level metadata."""
    meta = {
        "run_id": run_id,
        "slice_path": slice_path or config.SLICE_PATH,
        "started": run_id,
        "completed": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 1),
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "failures": failures,
        "model": config.OAUTH_MODEL,
        "inference_mode": "oauth",
        "prompt_version": config.PROMPT_VERSION,
    }
    if batch_slices:
        meta["batch_mode"] = True
        meta["slices"] = batch_slices

    out_path = config.AI_LAYER_DIR / "runs" / run_id / "run_meta.json"
    return atomic_write_text(out_path, json.dumps(meta, indent=2, ensure_ascii=False))


def load_manifest(path: Path) -> PhotoManifest:
    """Load a manifest JSON file as a PhotoManifest model."""
    return PhotoManifest.model_validate(json.loads(path.read_text()))


def list_manifests(run_id: str) -> list[Path]:
    """List all manifest files for a run."""
    d = run_dir(run_id)
    if not d.exists():
        return []
    return sorted(d.glob("*.json"))
