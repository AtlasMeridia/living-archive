"""Resumable batch runner for model comparison experiment.

Usage:
    python -m experiments.0004-model-comparison.src.runner --provider claude --hours 2
    python -m experiments.0004-model-comparison.src.runner --provider gpt --hours 2
    python -m experiments.0004-model-comparison.src.runner --status
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .convert import needs_conversion, prepare_for_analysis
from .providers import RateLimitError, get_provider

log = logging.getLogger("exp0004")

PROVIDER_PHASE = {"claude": "p1-claude", "gpt": "p2-gpt"}


def build_locked_inputs() -> list[dict]:
    """Build locked input list from catalog.db."""
    conn = sqlite3.connect(str(config.CATALOG_DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT sha256, path, content_type, slice FROM assets ORDER BY sha256"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def find_extracted_text(sha256: str) -> Path | None:
    """Find pre-extracted text file for a document."""
    sha12 = sha256[:12]
    for text_dir in sorted(config.DATA_DIR.glob(config.DOC_EXTRACTED_TEXT_GLOB)):
        candidate = text_dir / f"{sha12}.txt"
        if candidate.exists():
            return candidate
    return None


def load_progress(path: Path) -> dict:
    if path.exists():
        data = json.loads(path.read_text())
        data["completed"] = set(data.get("completed", []))
        return data
    return {"completed": set(), "errors": [], "stats": {}}


def save_progress(path: Path, progress: dict):
    data = {
        "completed": sorted(progress["completed"]),
        "errors": progress["errors"],
        "stats": progress["stats"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def write_manifest(path: Path, sha256: str, content_type: str,
                   source_file: str, analysis: dict, inference: dict):
    manifest = {
        "source_sha256": sha256,
        "source_file": source_file,
        "content_type": content_type,
        "analysis": analysis,
        "inference": inference,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def run_batch(provider_name: str, hours: float):
    """Run a time-budgeted batch of analyses."""
    provider = get_provider(provider_name)
    phase = PROVIDER_PHASE[provider_name]
    output_dir = config.RUNS_DIR / phase
    progress_path = output_dir / "progress.json"

    # Load or build locked inputs
    locked_path = config.RUNS_DIR / "p0-setup" / "locked-inputs.json"
    if locked_path.exists():
        inputs = json.loads(locked_path.read_text())
    else:
        print("Building locked inputs from catalog.db...")
        inputs = build_locked_inputs()
        locked_path.parent.mkdir(parents=True, exist_ok=True)
        locked_path.write_text(json.dumps(inputs, indent=2) + "\n")
        print(f"  Locked {len(inputs)} assets")

    progress = load_progress(progress_path)
    budget_seconds = hours * 3600
    t_start = time.monotonic()
    processed = 0
    errors_this_run = 0
    consecutive_empty = 0

    remaining = [a for a in inputs if a["sha256"] not in progress["completed"]]
    total = len(inputs)
    done = len(progress["completed"])
    print(f"\n{'='*60}")
    print(f"Provider: {provider_name} | Budget: {hours}h | "
          f"Done: {done}/{total} | Remaining: {len(remaining)}")
    print(f"{'='*60}\n")

    for asset in remaining:
        sha = asset["sha256"]
        sha12 = sha[:12]
        content_type = asset["content_type"]
        raw_path = Path(asset["path"])
        # Catalog stores relative paths — resolve against the correct root
        if raw_path.is_absolute():
            source_path = raw_path
        elif content_type == "photo":
            source_path = config.MEDIA_ROOT / raw_path
        else:
            source_path = config.FAMILY_ROOT / "Documents" / raw_path

        elapsed = time.monotonic() - t_start
        if elapsed + config.EST_SECONDS_PER_ASSET > budget_seconds:
            print(f"\nBudget exhausted ({elapsed:.0f}s / {budget_seconds:.0f}s). "
                  f"Run again to continue.")
            break

        try:
            if content_type == "photo":
                if not source_path.exists():
                    raise FileNotFoundError(f"Photo not found: {source_path}")

                # Convert if needed
                if needs_conversion(source_path):
                    tmp = tempfile.NamedTemporaryFile(
                        suffix=".jpg", prefix=f"exp0004-{sha12}-", delete=False,
                    )
                    tmp.close()
                    jpeg_path = Path(tmp.name)
                    prepare_for_analysis(source_path, jpeg_path)
                else:
                    jpeg_path = source_path

                folder_hint = asset.get("slice", source_path.parent.name)
                try:
                    analysis, meta = provider.analyze_photo(jpeg_path, folder_hint)
                finally:
                    if jpeg_path != source_path:
                        jpeg_path.unlink(missing_ok=True)

                out_path = output_dir / "photos" / f"{sha12}.json"

            elif content_type == "document":
                text_file = find_extracted_text(sha)
                if text_file is None:
                    raise FileNotFoundError(
                        f"No extracted text for {sha12} ({source_path.name})"
                    )
                text = text_file.read_text()
                page_count = max(1, text.count("\f") + 1)
                analysis, meta = provider.analyze_document(
                    text, source_path.name, page_count,
                )
                out_path = output_dir / "documents" / f"{sha12}.json"
            else:
                log.warning("Unknown content_type %s for %s", content_type, sha12)
                continue

            write_manifest(out_path, sha, content_type, str(source_path),
                           analysis, meta)
            progress["completed"].add(sha)
            processed += 1

        except RateLimitError as e:
            print(f"\nRate limited: {e}")
            print("Stopping early. Wait a few minutes and run again.")
            progress["errors"].append({
                "sha": sha, "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            break

        except Exception as e:
            err_msg = str(e)
            # Detect empty-response pattern (Codex rate limit without proper error)
            if "no last agent message" in err_msg or "wrote empty content" in err_msg:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    print(f"\n{consecutive_empty} consecutive empty responses — "
                          f"likely rate limited. Pausing 60s...")
                    time.sleep(60)
                if consecutive_empty >= 10:
                    print("Too many empty responses. Stopping early.")
                    progress["errors"].append({
                        "sha": sha, "error": err_msg,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    break
            else:
                consecutive_empty = 0

            errors_this_run += 1
            progress["errors"].append({
                "sha": sha, "error": err_msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            log.warning("Error on %s: %s", sha12, e)

        save_progress(progress_path, progress)

        # Progress log every 25 assets
        if processed > 0 and processed % 25 == 0:
            elapsed = time.monotonic() - t_start
            rate = processed / elapsed * 3600
            remaining_count = total - len(progress["completed"])
            budget_left = budget_seconds - elapsed
            print(f"  [{processed}] {len(progress['completed'])}/{total} done | "
                  f"{rate:.0f}/hr | ~{budget_left/60:.0f}min budget left | "
                  f"{remaining_count} remaining")

    # Final stats
    elapsed = time.monotonic() - t_start
    progress["stats"] = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "last_run_processed": processed,
        "last_run_errors": errors_this_run,
        "last_run_seconds": round(elapsed, 1),
        "total_completed": len(progress["completed"]),
        "total_errors": len(progress["errors"]),
        "total_assets": total,
    }
    save_progress(progress_path, progress)

    print(f"\nRun complete: {processed} processed, {errors_this_run} errors, "
          f"{elapsed:.0f}s elapsed")
    print(f"Total progress: {len(progress['completed'])}/{total} "
          f"({len(progress['completed'])/total*100:.1f}%)")


def clear_errors_for_retry(provider_name: str):
    """Remove errored SHAs from completed set so they get re-attempted."""
    phase = PROVIDER_PHASE[provider_name]
    progress_path = config.RUNS_DIR / phase / "progress.json"
    if not progress_path.exists():
        print("No progress file found.")
        return
    progress = load_progress(progress_path)
    errored_shas = {e["sha"] for e in progress["errors"]}
    # Remove errored SHAs from completed (they weren't actually completed)
    before = len(progress["completed"])
    progress["completed"] -= errored_shas
    removed = before - len(progress["completed"])
    old_errors = len(progress["errors"])
    progress["errors"] = []
    save_progress(progress_path, progress)
    print(f"Cleared {old_errors} errors, {removed} SHAs eligible for retry")


def show_status():
    """Show progress for all providers."""
    for name, phase in PROVIDER_PHASE.items():
        progress_path = config.RUNS_DIR / phase / "progress.json"
        if not progress_path.exists():
            print(f"{name}: not started")
            continue
        data = json.loads(progress_path.read_text())
        completed = len(data.get("completed", []))
        errors = len(data.get("errors", []))
        stats = data.get("stats", {})
        total = stats.get("total_assets", "?")
        print(f"{name}: {completed}/{total} completed, {errors} errors")
        if stats.get("last_run"):
            print(f"  Last run: {stats['last_run']} "
                  f"({stats.get('last_run_processed', 0)} processed in "
                  f"{stats.get('last_run_seconds', 0):.0f}s)")


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(
        description="Run model comparison batch analysis"
    )
    parser.add_argument("--provider", choices=["claude", "gpt"])
    parser.add_argument("--hours", type=float, default=2.0,
                        help="Wall-clock budget in hours (default: 2)")
    parser.add_argument("--status", action="store_true",
                        help="Show progress without running")
    parser.add_argument("--retry-errors", action="store_true",
                        help="Re-attempt previously errored assets")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if not args.provider:
        parser.error("--provider is required (unless using --status)")

    if args.retry_errors:
        clear_errors_for_retry(args.provider)

    run_batch(args.provider, args.hours)


if __name__ == "__main__":
    main()
