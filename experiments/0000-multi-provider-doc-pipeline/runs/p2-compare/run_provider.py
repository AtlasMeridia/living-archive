#!/usr/bin/env python3
"""Run a single provider against the locked test set.

Usage:
    python runs/p2-compare/run_provider.py claude
    python runs/p2-compare/run_provider.py codex
    python runs/p2-compare/run_provider.py ollama
"""

import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from src.doc_analyze import analyze_document
from src.models import DocumentAnalysis

COMPARE_DIR = Path(__file__).resolve().parent
CACHE_DIR = COMPARE_DIR / "extracted"

PROVIDER_MAP = {
    "claude": "claude-cli",
    "codex": "codex",
    "ollama": "ollama",
}


def run_provider(provider_key: str) -> None:
    provider_name = PROVIDER_MAP[provider_key]
    out_dir = COMPARE_DIR / provider_key
    out_dir.mkdir(exist_ok=True)

    cached_files = sorted(CACHE_DIR.glob("*.json"))
    print(f"Provider: {provider_name}")
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

        # Use first chunk (all our test docs are single-chunk)
        text = cache["chunks"][0]["text"]

        print(f"  [{i:2d}/{len(cached_files)}] {sha_short} {pages:3d}pp  ", end="", flush=True)

        doc_start = time.monotonic()
        try:
            analysis, inference = analyze_document(
                text=text,
                source_file=src,
                page_count=pages,
                provider_name=provider_name,
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

            print(f"{analysis.document_type:30s}  {elapsed:5.1f}s")

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
            print(f"ERROR: {exc}"[:80])

    total_elapsed = time.monotonic() - total_start

    # Write results
    output = {
        "provider": provider_name,
        "total_documents": len(cached_files),
        "succeeded": sum(1 for r in results if r["status"] == "ok"),
        "failed": sum(1 for r in results if r["status"] == "error"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "total_elapsed_seconds": round(total_elapsed, 1),
        "results": results,
    }
    (out_dir / "results.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    )

    print()
    print(f"Done: {output['succeeded']} ok, {output['failed']} errors, {output['skipped']} skipped")
    print(f"Total time: {total_elapsed:.1f}s ({total_elapsed/len(cached_files):.1f}s avg)")
    print(f"Saved to: {out_dir / 'results.json'}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in PROVIDER_MAP:
        print(f"Usage: {sys.argv[0]} <{'|'.join(PROVIDER_MAP)}>")
        sys.exit(1)
    run_provider(sys.argv[1])
