"""Experiment 0008: Grok photo-analysis pilot.

Runs N already-processed photos through the Grok Build CLI (SuperGrok Heavy
subscription, $0 marginal) and compares the results field-by-field against
the existing Claude manifests. Decides whether Grok is fit to be a photo
pipeline backend.

Usage:
    python experiments/0008-grok-photo-pilot/run.py select            # preview sample
    python experiments/0008-grok-photo-pilot/run.py analyze --limit 2 # smoke
    python experiments/0008-grok-photo-pilot/run.py analyze           # full 30
    python experiments/0008-grok-photo-pilot/run.py report
"""

import argparse
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src import config  # noqa: E402
from src.analyze import load_prompt  # noqa: E402
from src.convert import needs_conversion, prepare_for_analysis  # noqa: E402
from src.inference import grok_structured  # noqa: E402
from src.models import PhotoAnalysis  # noqa: E402

EXP_DIR = Path(__file__).resolve().parent
RUN_DIR = EXP_DIR / "runs" / "grok"
WORKSPACE = EXP_DIR / "workspace"
SAMPLE_SIZE = 30

log = config.setup_logging()


def select_sample(limit: int = SAMPLE_SIZE) -> list[dict]:
    """Evenly-strided sample of indexed photos that have Claude manifests."""
    conn = sqlite3.connect(config.FAMILY_CATALOG_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT path, sha256, manifest_path, slice FROM assets
        WHERE content_type='photo' AND status='indexed'
          AND manifest_path IS NOT NULL
        ORDER BY path
    """).fetchall()
    conn.close()
    if not rows:
        return []
    stride = max(1, len(rows) // limit)
    return [dict(rows[i]) for i in range(0, len(rows), stride)][:limit]


def claude_analysis(manifest_rel: str) -> dict | None:
    """Load the analysis block from an existing Claude manifest."""
    path = config.AI_LAYER_DIR / manifest_rel
    if not path.exists():
        return None
    return json.loads(path.read_text()).get("analysis")


def analyze(limit: int) -> int:
    sample = select_sample(limit)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    schema = PhotoAnalysis.model_json_schema()

    done = failed = 0
    for i, item in enumerate(sample, 1):
        out_path = RUN_DIR / f"{item['sha256'][:12]}.json"
        if out_path.exists():
            log.info("[%d/%d] already done: %s", i, len(sample), Path(item["path"]).name)
            done += 1
            continue

        src = config.MEDIA_ROOT / item["path"]
        if not src.exists():
            log.warning("[%d/%d] source missing: %s", i, len(sample), item["path"])
            failed += 1
            continue

        jpeg = WORKSPACE / f"{item['sha256'][:12]}.jpg"
        if needs_conversion(src):
            prepare_for_analysis(src, jpeg)
        else:
            shutil.copy2(src, jpeg)

        prompt = (
            f'First, read the image file "{jpeg.name}" in the current directory. '
            f"Then analyze it per the instructions below.\n\n"
            + load_prompt(folder_hint=item["slice"])
        )

        log.info("[%d/%d] grok: %s", i, len(sample), Path(item["path"]).name)
        start = time.monotonic()
        try:
            raw = grok_structured(prompt, schema, cwd=WORKSPACE)
            analysis = PhotoAnalysis.model_validate(raw)
        except Exception as e:
            log.error("  FAILED: %s: %s", type(e).__name__, e)
            failed += 1
            continue
        finally:
            jpeg.unlink(missing_ok=True)

        elapsed = time.monotonic() - start
        out_path.write_text(json.dumps({
            "source_file": item["path"],
            "source_sha256": item["sha256"],
            "slice": item["slice"],
            "claude_manifest": item["manifest_path"],
            "analysis": analysis.model_dump(),
            "elapsed_seconds": round(elapsed, 1),
        }, indent=2, ensure_ascii=False))
        done += 1
        log.info("  OK: %s (conf %.2f) in %.0fs",
                 analysis.date_estimate or "?", analysis.date_confidence, elapsed)

    log.info("Done: %d ok, %d failed", done, failed)
    return 1 if failed and not done else 0


def _year(estimate: str) -> int | None:
    try:
        return int(estimate[:4])
    except (ValueError, TypeError, IndexError):
        return None


def report() -> int:
    rows = []
    for f in sorted(RUN_DIR.glob("*.json")):
        g = json.loads(f.read_text())
        c = claude_analysis(g["claude_manifest"])
        if not c:
            continue
        ga, ca = g["analysis"], c
        gy, cy = _year(ga["date_estimate"]), _year(ca.get("date_estimate", ""))
        gt, ct = set(ga.get("tags", [])), set(ca.get("tags", []))
        rows.append({
            "file": Path(g["source_file"]).name,
            "slice": g["slice"],
            "claude_date": ca.get("date_estimate", ""), "grok_date": ga["date_estimate"],
            "year_delta": abs(gy - cy) if gy and cy else None,
            "claude_conf": ca.get("date_confidence", 0), "grok_conf": ga["date_confidence"],
            "tag_jaccard": round(len(gt & ct) / len(gt | ct), 2) if gt | ct else None,
            "grok_zh_ok": len(ga.get("description_zh", "")) > 10,
            "claude_loc": ca.get("location_estimate", ""), "grok_loc": ga["location_estimate"],
            "grok_secs": g["elapsed_seconds"],
        })

    if not rows:
        log.error("No comparable results in %s", RUN_DIR)
        return 1

    deltas = [r["year_delta"] for r in rows if r["year_delta"] is not None]
    jac = [r["tag_jaccard"] for r in rows if r["tag_jaccard"] is not None]
    lines = [
        "# Grok photo pilot — comparison vs existing Claude manifests\n",
        f"Photos compared: {len(rows)}\n",
        f"- Date agreement: {sum(1 for d in deltas if d == 0)}/{len(deltas)} same year, "
        f"{sum(1 for d in deltas if d <= 2)}/{len(deltas)} within 2 years, "
        f"mean |Δyear| {sum(deltas)/len(deltas):.1f}",
        f"- Mean date confidence: claude {sum(r['claude_conf'] for r in rows)/len(rows):.2f}, "
        f"grok {sum(r['grok_conf'] for r in rows)/len(rows):.2f}",
        f"- Mean tag jaccard: {sum(jac)/len(jac):.2f}" if jac else "- No tag data",
        f"- Grok zh description present: {sum(1 for r in rows if r['grok_zh_ok'])}/{len(rows)}",
        f"- Mean grok latency: {sum(r['grok_secs'] for r in rows)/len(rows):.0f}s/photo\n",
        "| Photo | Slice | Claude date | Grok date | Δyr | C conf | G conf | Tag jac | Grok s |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['file']} | {r['slice'][:30]} | {r['claude_date']} | {r['grok_date']} "
            f"| {r['year_delta'] if r['year_delta'] is not None else '-'} "
            f"| {r['claude_conf']:.2f} | {r['grok_conf']:.2f} "
            f"| {r['tag_jaccard'] if r['tag_jaccard'] is not None else '-'} | {r['grok_secs']:.0f} |"
        )

    out = EXP_DIR / "runs" / "report.md"
    out.write_text("\n".join(lines) + "\n")
    log.info("Report written: %s", out)
    for line in lines[1:8]:
        log.info("%s", line)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Grok photo-analysis pilot")
    parser.add_argument("command", choices=["select", "analyze", "report"])
    parser.add_argument("--limit", type=int, default=SAMPLE_SIZE)
    args = parser.parse_args()

    if args.command == "select":
        for item in select_sample(args.limit):
            log.info("  %s", item["path"])
        return 0
    if args.command == "analyze":
        return analyze(args.limit)
    return report()


if __name__ == "__main__":
    sys.exit(main())
