"""Read/write document manifest JSON files to the AI layer."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .util import atomic_write_text

log = logging.getLogger("living_archive")


def run_dir(run_id: str) -> Path:
    """Return the manifests directory for a given run."""
    return config.DOC_AI_LAYER_DIR / "runs" / run_id / "manifests"


def text_dir(run_id: str) -> Path:
    """Return the extracted-text directory for a given run."""
    return config.DOC_AI_LAYER_DIR / "runs" / run_id / "extracted-text"


def write_manifest(
    run_id: str,
    source_file_rel: str,
    source_sha256: str,
    file_size_bytes: int,
    page_count: int,
    extraction: dict,
    analysis: dict,
    inference: dict | None = None,
) -> Path:
    """Write a single document manifest JSON.

    Returns the path to the written file.
    If inference is provided, it's used as-is. Otherwise a default is generated.
    """
    default_inference = {
        "method": "auto",
        "prompt_version": config.DOC_PROMPT_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    manifest = {
        "source_file": source_file_rel,
        "source_sha256": source_sha256,
        "file_size_bytes": file_size_bytes,
        "page_count": page_count,
        "extraction": {
            **extraction,
            "text_file": f"extracted-text/{source_sha256[:12]}.txt",
        },
        "analysis": analysis,
        "inference": inference if inference is not None else default_inference,
    }

    out_path = run_dir(run_id) / f"{source_sha256[:12]}.json"
    atomic_write_text(out_path, json.dumps(manifest, indent=2, ensure_ascii=False))

    # Update catalog (non-fatal — catalog is optional)
    try:
        from .catalog import record_indexed_asset
        record_indexed_asset(
            sha256=source_sha256,
            path=source_file_rel,
            content_type="document",
            manifest_path=str(out_path.relative_to(config.DOC_AI_LAYER_DIR)),
            run_id=run_id,
            file_size=file_size_bytes,
        )
    except Exception:
        log.warning("Catalog update failed for %s (non-fatal)", out_path.name, exc_info=True)

    return out_path


def write_extracted_text(run_id: str, sha256: str, text: str) -> Path:
    """Write extracted text to a plain text file.

    Returns the path to the written file.
    """
    return atomic_write_text(text_dir(run_id) / f"{sha256[:12]}.txt", text)


def write_run_meta(
    run_id: str,
    total: int,
    succeeded: int,
    failed: int,
    skipped: int,
    failures: list[dict],
    elapsed_seconds: float,
    method: str = "auto",
    provider: str = "",
    usage: dict | None = None,
    batch_size: int = 0,
) -> Path:
    """Write run-level metadata."""
    meta = {
        "run_id": run_id,
        "pipeline": "document",
        "doc_slice_path": config.DOC_SLICE_PATH,
        "started": run_id,
        "completed": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 1),
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "failures": failures,
        "method": method,
        "provider": provider or method,
        "prompt_version": config.DOC_PROMPT_VERSION,
    }
    if batch_size > 0:
        meta["batch_size"] = batch_size
    if usage:
        meta["usage"] = usage

    out_path = config.DOC_AI_LAYER_DIR / "runs" / run_id / "run_meta.json"
    return atomic_write_text(out_path, json.dumps(meta, indent=2, ensure_ascii=False))


def load_manifest(path: Path) -> dict:
    """Load a manifest JSON file."""
    return json.loads(path.read_text())


def list_manifests(run_id: str) -> list[Path]:
    """List all manifest files for a run."""
    d = run_dir(run_id)
    if not d.exists():
        return []
    return sorted(d.glob("*.json"))


def get_processed_hashes(run_id: str) -> set[str]:
    """Return set of SHA-256 hashes already processed in a run."""
    hashes = set()
    for manifest_path in list_manifests(run_id):
        data = load_manifest(manifest_path)
        hashes.add(data["source_sha256"])
    return hashes
