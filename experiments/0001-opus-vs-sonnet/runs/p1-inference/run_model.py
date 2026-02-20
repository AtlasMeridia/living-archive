#!/usr/bin/env python3
"""Phase 1: Run a model against the locked test set.

Usage:
    python runs/p1-inference/run_model.py sonnet
    python runs/p1-inference/run_model.py opus
"""

import json
import os
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from src.doc_analyze import analyze_document
from src import config

INFERENCE_DIR = Path(__file__).resolve().parent
CACHE_DIR = INFERENCE_DIR.parent / "p0-setup" / "extracted"

MODEL_MAP = {
    "sonnet": "sonnet",
    "opus": "opus",
}


def run_model(model_key: str) -> None:
    model_alias = MODEL_MAP[model_key]
    out_dir = INFERENCE_DIR / model_key
    out_dir.mkdir(exist_ok=True)

    # Override the model at config level
    original_model = config.DOC_CLI_MODEL
    config.DOC_CLI_MODEL = model_alias

    cached_files = sorted(CACHE_DIR.glob("*.json"))
    print(f"Model: {model_alias}")
    print(f"Documents: {len(cached_files)}")
    print(f"Output: {out_dir}")
    print()

    results = []
    total_start = time.monotonic()

    for i, cf in enumerate(cached_files, 1):
        cache = json.loads(cf.read_text())
        sha_short = cache["source_sha256"][:12]
        src = cache["source_file"]
        pages = cache["page_count"]

        if cache["is_empty"]:
            print(f"  [{i:2d}/{len(cached_files)}] {sha_short} SKIP (empty)")
            results.append({
                "source_sha256": cache["source_sha256"],
                "source_file": src,
                "status": "skipped",
                "reason": "empty_text",
            })
            continue

        text = cache["full_text"]
        print(f"  [{i:2d}/{len(cached_files)}] {sha_short} {pages:3d}pp  ", end="", flush=True)

        doc_start = time.monotonic()
        try:
            analysis, inference = analyze_document(
                text=text,
                source_file=src,
                page_count=pages,
                provider_name="claude-cli",
            )
            elapsed = time.monotonic() - doc_start

            result = {
                "source_sha256": cache["source_sha256"],
                "source_file": src,
                "status": "ok",
                "elapsed_seconds": round(elapsed, 1),
                "analysis": analysis.model_dump(),
                "inference": inference.model_dump(),
            }
            results.append(result)

            print(f"{analysis.document_type:30s}  {elapsed:5.1f}s  "
                  f"in={inference.input_tokens} out={inference.output_tokens}")

        except Exception as exc:
            elapsed = time.monotonic() - doc_start
            result = {
                "source_sha256": cache["source_sha256"],
                "source_file": src,
                "status": "error",
                "elapsed_seconds": round(elapsed, 1),
                "error": f"{type(exc).__name__}: {exc}",
            }
            results.append(result)
            print(f"ERROR: {str(exc)[:80]}")

    total_elapsed = time.monotonic() - total_start

    # Restore config
    config.DOC_CLI_MODEL = original_model

    # Aggregate usage
    ok_results = [r for r in results if r["status"] == "ok"]
    total_input = sum(r["inference"]["input_tokens"] for r in ok_results)
    total_output = sum(r["inference"]["output_tokens"] for r in ok_results)

    output = {
        "model": model_alias,
        "provider": "claude-cli",
        "total_documents": len(cached_files),
        "succeeded": len(ok_results),
        "failed": sum(1 for r in results if r["status"] == "error"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "total_elapsed_seconds": round(total_elapsed, 1),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "results": results,
    }
    results_path = out_dir / "results.json"
    results_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")

    print()
    print(f"Done: {output['succeeded']} ok, {output['failed']} errors, {output['skipped']} skipped")
    print(f"Total time: {total_elapsed:.1f}s ({total_elapsed/len(cached_files):.1f}s avg)")
    print(f"Tokens: {total_input} input, {total_output} output")
    print(f"Saved to: {results_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in MODEL_MAP:
        print(f"Usage: {sys.argv[0]} <{'|'.join(MODEL_MAP)}>")
        sys.exit(1)
    run_model(sys.argv[1])
