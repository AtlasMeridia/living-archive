"""Read/write manifest JSON files to the AI layer."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import config


def run_dir(run_id: str) -> Path:
    """Return the directory for a given run."""
    return config.AI_LAYER_DIR / "runs" / run_id / "manifests"


def write_manifest(
    run_id: str,
    source_file_rel: str,
    source_sha256: str,
    analysis: dict,
    inference: dict,
) -> Path:
    """Write a single photo manifest JSON.

    Returns the path to the written file.
    """
    manifest = {
        "source_file": source_file_rel,
        "source_sha256": source_sha256,
        "analysis": analysis,
        "inference": {
            **inference,
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


def load_manifest(path: Path) -> dict:
    """Load a manifest JSON file."""
    return json.loads(path.read_text())


def list_manifests(run_id: str) -> list[Path]:
    """List all manifest files for a run."""
    d = run_dir(run_id)
    if not d.exists():
        return []
    return sorted(d.glob("*.json"))
