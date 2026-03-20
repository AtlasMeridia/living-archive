"""Diff two synthesis databases for Phase 4.

Compares entity counts, overlap, unique-to-each, and timeline divergence
between Claude and GPT synthesis databases.

Usage:
    python -m experiments.0004-model-comparison.src.synthesis_diff
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import config


def _query_entities(db_path: Path) -> dict[str, set[str]]:
    """Get all entities grouped by type as sets of normalized_value."""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT entity_type, normalized_value FROM entities"
    ).fetchall()
    conn.close()
    result: dict[str, set[str]] = {}
    for etype, nval in rows:
        result.setdefault(etype, set()).add(nval)
    return result


def _query_entity_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type"
    ).fetchall()
    conn.close()
    return dict(rows)


def _query_timeline_stats(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    total = conn.execute("SELECT COUNT(*) FROM timeline_events").fetchone()[0]
    by_type = dict(conn.execute(
        "SELECT event_type, COUNT(*) FROM timeline_events GROUP BY event_type"
    ).fetchall())
    by_decade = dict(conn.execute(
        "SELECT era_decade, COUNT(*) FROM timeline_events "
        "WHERE era_decade IS NOT NULL GROUP BY era_decade ORDER BY era_decade"
    ).fetchall())
    conn.close()
    return {"total": total, "by_type": by_type, "by_decade": by_decade}


def _query_asset_coverage(db_path: Path) -> int:
    """Count distinct assets referenced in entity_assets."""
    conn = sqlite3.connect(str(db_path))
    count = conn.execute(
        "SELECT COUNT(DISTINCT asset_sha256) FROM entity_assets"
    ).fetchone()[0]
    conn.close()
    return count


def run_diff():
    out_dir = config.RUNS_DIR / "p4-synthesis"
    claude_db = out_dir / "claude-synthesis.db"
    gpt_db = out_dir / "gpt-synthesis.db"
    prod_db = config.DATA_DIR / "synthesis.db"

    for db, label in [(claude_db, "Claude"), (gpt_db, "GPT")]:
        if not db.exists():
            print(f"{label} synthesis DB not found at {db}")
            print("Run synthesis_rebuild first for both providers.")
            return

    claude_entities = _query_entities(claude_db)
    gpt_entities = _query_entities(gpt_db)
    claude_counts = _query_entity_counts(claude_db)
    gpt_counts = _query_entity_counts(gpt_db)

    all_types = sorted(set(claude_counts) | set(gpt_counts))

    diff_result = {
        "entity_counts": {
            "claude": claude_counts,
            "gpt": gpt_counts,
        },
        "entity_overlap": {},
        "timeline": {
            "claude": _query_timeline_stats(claude_db),
            "gpt": _query_timeline_stats(gpt_db),
        },
        "asset_coverage": {
            "claude": _query_asset_coverage(claude_db),
            "gpt": _query_asset_coverage(gpt_db),
        },
    }

    # Compare against production if available
    if prod_db.exists():
        diff_result["entity_counts"]["production"] = _query_entity_counts(prod_db)
        diff_result["timeline"]["production"] = _query_timeline_stats(prod_db)
        diff_result["asset_coverage"]["production"] = _query_asset_coverage(prod_db)

    for etype in all_types:
        ce = claude_entities.get(etype, set())
        ge = gpt_entities.get(etype, set())
        overlap = ce & ge
        claude_only = ce - ge
        gpt_only = ge - ce

        diff_result["entity_overlap"][etype] = {
            "claude_count": len(ce),
            "gpt_count": len(ge),
            "overlap": len(overlap),
            "claude_only": len(claude_only),
            "gpt_only": len(gpt_only),
            "jaccard": len(overlap) / len(ce | ge) if (ce | ge) else 0,
            "sample_claude_only": sorted(claude_only)[:10],
            "sample_gpt_only": sorted(gpt_only)[:10],
        }

    (out_dir / "entity-diff.json").write_text(
        json.dumps(diff_result, indent=2, ensure_ascii=False) + "\n"
    )

    # Markdown report
    lines = ["# Synthesis Comparison\n\n"]

    lines.append("## Entity Counts\n\n")
    lines.append("| Type | Claude | GPT |")
    if prod_db.exists():
        lines.append(" Production |")
    lines.append("\n|------|--------|-----|")
    if prod_db.exists():
        lines.append("------------|")
    lines.append("\n")
    for etype in all_types:
        cc = claude_counts.get(etype, 0)
        gc = gpt_counts.get(etype, 0)
        line = f"| {etype} | {cc} | {gc} |"
        if prod_db.exists():
            pc = diff_result["entity_counts"]["production"].get(etype, 0)
            line += f" {pc} |"
        lines.append(line + "\n")

    lines.append("\n## Entity Overlap\n\n")
    lines.append("| Type | Overlap | Claude-only | GPT-only | Jaccard |\n")
    lines.append("|------|---------|-------------|----------|--------|\n")
    for etype in all_types:
        ov = diff_result["entity_overlap"][etype]
        lines.append(
            f"| {etype} | {ov['overlap']} | {ov['claude_only']} | "
            f"{ov['gpt_only']} | {ov['jaccard']:.2f} |\n"
        )

    lines.append("\n## Timeline\n\n")
    ct = diff_result["timeline"]["claude"]
    gt = diff_result["timeline"]["gpt"]
    lines.append(f"- Claude: {ct['total']} events\n")
    lines.append(f"- GPT: {gt['total']} events\n")
    if prod_db.exists():
        pt = diff_result["timeline"]["production"]
        lines.append(f"- Production: {pt['total']} events\n")

    lines.append("\n## Asset Coverage\n\n")
    ac = diff_result["asset_coverage"]
    lines.append(f"- Claude: {ac['claude']} unique assets\n")
    lines.append(f"- GPT: {ac['gpt']} unique assets\n")
    if "production" in ac:
        lines.append(f"- Production: {ac['production']} unique assets\n")

    (out_dir / "synthesis-comparison.md").write_text("".join(lines))
    print(f"Synthesis diff complete. Results in {out_dir}")


def main():
    run_diff()


if __name__ == "__main__":
    main()
