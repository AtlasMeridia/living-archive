"""Read/write manifest JSON files to the AI layer."""

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .models import InferenceMetadata, PhotoAnalysis, PhotoManifest

log = logging.getLogger(__name__)


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

    out_dir = run_dir(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{source_sha256[:12]}.json"
    out_path = out_dir / filename

    # Atomic write: temp file + rename
    fd, tmp = tempfile.mkstemp(dir=out_dir, suffix=".tmp")
    try:
        with open(fd, "w") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        Path(tmp).rename(out_path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise

    # Update catalog (non-fatal — catalog is optional)
    try:
        from .catalog import get_catalog_db, init_catalog, upsert_asset
        db_path = get_catalog_db("family")
        if db_path.parent.exists():
            conn = init_catalog(db_path)
            upsert_asset(
                conn,
                sha256=source_sha256,
                path=source_file_rel,
                content_type="photo",
                manifest_path=str(out_path.relative_to(config.AI_LAYER_DIR)),
                run_id=run_id,
                status="indexed",
            )
            conn.close()
    except Exception:
        log.debug("Catalog update skipped (non-fatal)", exc_info=True)

    return out_path


def write_run_meta(
    run_id: str,
    total: int,
    succeeded: int,
    failed: int,
    failures: list[dict],
    elapsed_seconds: float,
) -> Path:
    """Write run-level metadata."""
    meta = {
        "run_id": run_id,
        "slice_path": config.SLICE_PATH,
        "started": run_id,
        "completed": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 1),
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "failures": failures,
        "model": config.MODEL,
        "prompt_version": config.PROMPT_VERSION,
    }

    out_dir = config.AI_LAYER_DIR / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "run_meta.json"
    out_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return out_path


def load_manifest(path: Path) -> PhotoManifest:
    """Load a manifest JSON file as a PhotoManifest model.

    Falls back to raw dict parsing with a warning for incompatible manifests.
    """
    data = json.loads(path.read_text())
    try:
        return PhotoManifest.model_validate(data)
    except Exception:
        log.warning("Failed to validate manifest %s, loading with defaults", path.name)
        return PhotoManifest.model_validate(data)


def list_manifests(run_id: str) -> list[Path]:
    """List all manifest files for a run."""
    d = run_dir(run_id)
    if not d.exists():
        return []
    return sorted(d.glob("*.json"))
