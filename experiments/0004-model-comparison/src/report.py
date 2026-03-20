"""Generate final summary report for Phase 5.

Aggregates results from P3 (comparison) and P4 (synthesis diff) into
a single narrative report.

Usage:
    python -m experiments.0004-model-comparison.src.report
"""

from __future__ import annotations

import json
from pathlib import Path

from . import config


def _load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def generate_report():
    compare_dir = config.RUNS_DIR / "p3-compare"
    synth_dir = config.RUNS_DIR / "p4-synthesis"
    out_dir = config.RUNS_DIR / "p5-report"
    out_dir.mkdir(parents=True, exist_ok=True)

    agreement = _load_json(compare_dir / "field-agreement.json")
    divergence = _load_json(compare_dir / "divergence-catalog.json")
    entity_diff = _load_json(synth_dir / "entity-diff.json")

    # Load progress stats
    p1_progress = _load_json(config.RUNS_DIR / "p1-claude" / "progress.json")
    p2_progress = _load_json(config.RUNS_DIR / "p2-gpt" / "progress.json")

    lines = [
        "# Experiment 0004: Model Comparison Report\n",
        "## Claude Opus 4.6 vs GPT 5.4 — Full Corpus\n\n",
    ]

    # Methodology
    lines.append("## Methodology\n\n")
    lines.append("Both models analyzed the same corpus using identical prompts ")
    lines.append("and JSON schemas. Photos were passed as images; documents as ")
    lines.append("pre-extracted text. Both accessed via subscription CLI tools ")
    lines.append("at $0 cost.\n\n")

    if p1_progress and p2_progress:
        p1s = p1_progress.get("stats", {})
        p2s = p2_progress.get("stats", {})
        lines.append(f"- Claude: {p1s.get('total_completed', '?')}/"
                      f"{p1s.get('total_assets', '?')} assets, "
                      f"{p1s.get('total_errors', 0)} errors\n")
        lines.append(f"- GPT: {p2s.get('total_completed', '?')}/"
                      f"{p2s.get('total_assets', '?')} assets, "
                      f"{p2s.get('total_errors', 0)} errors\n\n")

    # Aggregate agreement
    if agreement:
        lines.append("## Aggregate Agreement\n\n")
        for content_type in ("photos", "documents"):
            data = agreement.get(content_type, {})
            if not data:
                continue
            lines.append(f"### {content_type.title()}\n\n")
            lines.append("| Metric | Value |\n|--------|-------|\n")
            for key, val in sorted(data.items()):
                rate = val.get("agreement_rate", val.get("mean", 0))
                n = val.get("count", 0)
                lines.append(f"| {key} | {rate:.1%} (n={n}) |\n")
            lines.append("\n")

    # Divergence highlights
    if divergence:
        lines.append("## Top Divergences\n\n")
        lines.append("Assets with highest disagreement between models:\n\n")
        lines.append("| # | SHA12 | Score | Key Differences |\n")
        lines.append("|---|-------|-------|-----------------|\n")
        for i, item in enumerate(divergence[:10]):
            metrics = item.get("metrics", {})
            diffs = [k for k, v in metrics.items()
                     if isinstance(v, bool) and not v]
            lines.append(
                f"| {i+1} | `{item['sha12']}` | "
                f"{item['divergence_score']:.2f} | "
                f"{', '.join(diffs[:3])} |\n"
            )
        lines.append("\n")

    # Synthesis cascade
    if entity_diff:
        lines.append("## Synthesis Cascade\n\n")
        lines.append("How model differences propagate into the entity graph:\n\n")

        counts = entity_diff.get("entity_counts", {})
        overlap = entity_diff.get("entity_overlap", {})

        lines.append("### Entity Counts\n\n")
        lines.append("| Type | Claude | GPT | Overlap | Jaccard |\n")
        lines.append("|------|--------|-----|---------|--------|\n")
        for etype in sorted(overlap):
            ov = overlap[etype]
            lines.append(
                f"| {etype} | {ov['claude_count']} | {ov['gpt_count']} | "
                f"{ov['overlap']} | {ov['jaccard']:.2f} |\n"
            )
        lines.append("\n")

        # Unique entities
        lines.append("### Sample Unique Entities\n\n")
        for etype in sorted(overlap):
            ov = overlap[etype]
            if ov["sample_claude_only"]:
                lines.append(f"**{etype} — Claude only:** "
                             f"{', '.join(ov['sample_claude_only'][:5])}\n\n")
            if ov["sample_gpt_only"]:
                lines.append(f"**{etype} — GPT only:** "
                             f"{', '.join(ov['sample_gpt_only'][:5])}\n\n")

        # Timeline
        tl = entity_diff.get("timeline", {})
        if tl:
            lines.append("### Timeline Events\n\n")
            for provider in ("claude", "gpt"):
                t = tl.get(provider, {})
                lines.append(f"- {provider.title()}: {t.get('total', 0)} events\n")
            lines.append("\n")

    lines.append("---\n\n")
    lines.append("*Generated by experiment 0004 report pipeline.*\n")

    report_path = out_dir / "summary.md"
    report_path.write_text("".join(lines))
    print(f"Report written to {report_path}")


def main():
    generate_report()


if __name__ == "__main__":
    main()
