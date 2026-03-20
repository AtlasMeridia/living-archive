"""Field-level comparison engine for Phase 3.

Compares Claude vs GPT manifests across all assets and generates
agreement metrics and divergence catalogs.

Usage:
    python -m experiments.0004-model-comparison.src.compare
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from . import config


def _load_manifests(phase_dir: Path) -> dict[str, dict]:
    """Load all manifests from a phase directory, keyed by sha12."""
    result = {}
    for subdir in ("photos", "documents"):
        d = phase_dir / subdir
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json")):
            data = json.loads(f.read_text())
            sha12 = f.stem
            data["_content_type"] = subdir.rstrip("s")
            result[sha12] = data
    return result


# --- Comparison metrics ---


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def rouge1(text_a: str, text_b: str) -> float:
    """Unigram overlap (ROUGE-1 F1)."""
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    overlap = len(tokens_a & tokens_b)
    precision = overlap / len(tokens_a) if tokens_a else 0
    recall = overlap / len(tokens_b) if tokens_b else 0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _extract_year(date_str: str) -> int | None:
    m = re.match(r"(\d{4})", date_str or "")
    return int(m.group(1)) if m else None


def _extract_decade(date_str: str) -> str | None:
    y = _extract_year(date_str)
    return f"{y // 10 * 10}s" if y else None


def _extract_country(location: str) -> str | None:
    """Extract first country-level token from a location string."""
    location = location.strip().lower()
    for country in ("taiwan", "united states", "usa", "japan", "china",
                     "hong kong", "canada", "egypt", "greece", "italy"):
        if country in location:
            return country
    parts = [p.strip() for p in location.split(",")]
    return parts[-1] if parts else None


# --- Photo comparison ---


def compare_photo(claude: dict, gpt: dict) -> dict:
    ca = claude.get("analysis", {})
    ga = gpt.get("analysis", {})
    metrics = {}

    # Date
    cd, gd = ca.get("date_estimate", ""), ga.get("date_estimate", "")
    metrics["date_exact"] = cd == gd and bool(cd)
    metrics["date_year"] = _extract_year(cd) == _extract_year(gd) and bool(cd)
    metrics["date_decade"] = _extract_decade(cd) == _extract_decade(gd) and bool(cd)
    metrics["date_confidence_delta"] = abs(
        ca.get("date_confidence", 0) - ga.get("date_confidence", 0)
    )

    # Description
    metrics["description_en_rouge1"] = rouge1(
        ca.get("description_en", ""), ga.get("description_en", ""),
    )
    en_a = len(ca.get("description_en", "").split())
    en_b = len(ga.get("description_en", "").split())
    metrics["description_en_length_ratio"] = (
        min(en_a, en_b) / max(en_a, en_b) if max(en_a, en_b) > 0 else 1.0
    )
    zh_a = len(ca.get("description_zh", ""))
    zh_b = len(ga.get("description_zh", ""))
    metrics["description_zh_length_ratio"] = (
        min(zh_a, zh_b) / max(zh_a, zh_b) if max(zh_a, zh_b) > 0 else 1.0
    )

    # People count
    cp = ca.get("people_count")
    gp = ga.get("people_count")
    metrics["people_exact"] = cp == gp
    metrics["people_within_1"] = (
        abs((cp or 0) - (gp or 0)) <= 1 if cp is not None and gp is not None
        else cp == gp
    )

    # Location
    cc = _extract_country(ca.get("location_estimate", ""))
    gc = _extract_country(ga.get("location_estimate", ""))
    metrics["location_country_match"] = cc == gc and cc is not None

    # Tags
    ct = set(t.lower() for t in ca.get("tags", []))
    gt = set(t.lower() for t in ga.get("tags", []))
    metrics["tags_jaccard"] = jaccard(ct, gt)

    return metrics


# --- Document comparison ---


def compare_document(claude: dict, gpt: dict) -> dict:
    ca = claude.get("analysis", {})
    ga = gpt.get("analysis", {})
    metrics = {}

    # Document type
    cd_type = ca.get("document_type", "").lower()
    gd_type = ga.get("document_type", "").lower()
    metrics["doctype_exact"] = cd_type == gd_type and bool(cd_type)
    metrics["doctype_category"] = (
        cd_type.split("/")[0] == gd_type.split("/")[0]
        if "/" in cd_type and "/" in gd_type else cd_type == gd_type
    ) and bool(cd_type)

    # Date
    cd, gd = ca.get("date", ""), ga.get("date", "")
    metrics["date_exact"] = cd == gd and bool(cd)
    metrics["date_year"] = _extract_year(cd) == _extract_year(gd) and bool(cd)

    # Key people
    cp = set(p.lower().strip() for p in ca.get("key_people", []))
    gp = set(p.lower().strip() for p in ga.get("key_people", []))
    metrics["people_jaccard"] = jaccard(cp, gp)

    # Key dates
    ckd = set(ca.get("key_dates", []))
    gkd = set(ga.get("key_dates", []))
    metrics["dates_jaccard"] = jaccard(ckd, gkd)

    # Sensitivity flags
    cs = ca.get("sensitivity", {})
    gs = ga.get("sensitivity", {})
    for flag in ("has_ssn", "has_financial", "has_medical"):
        metrics[f"sensitivity_{flag}"] = cs.get(flag) == gs.get(flag)

    # Tags
    ct = set(t.lower() for t in ca.get("tags", []))
    gt = set(t.lower() for t in ga.get("tags", []))
    metrics["tags_jaccard"] = jaccard(ct, gt)

    return metrics


# --- Aggregate ---


def run_comparison():
    claude_dir = config.RUNS_DIR / "p1-claude"
    gpt_dir = config.RUNS_DIR / "p2-gpt"
    out_dir = config.RUNS_DIR / "p3-compare"
    out_dir.mkdir(parents=True, exist_ok=True)

    claude_manifests = _load_manifests(claude_dir)
    gpt_manifests = _load_manifests(gpt_dir)

    common = set(claude_manifests) & set(gpt_manifests)
    print(f"Comparing {len(common)} assets "
          f"(Claude: {len(claude_manifests)}, GPT: {len(gpt_manifests)})")

    photo_metrics: list[dict] = []
    doc_metrics: list[dict] = []
    all_scores: list[tuple[str, float, dict]] = []

    for sha12 in sorted(common):
        cm = claude_manifests[sha12]
        gm = gpt_manifests[sha12]
        ct = cm["_content_type"]

        if ct == "photo":
            m = compare_photo(cm, gm)
            m["sha12"] = sha12
            photo_metrics.append(m)
            score = sum(1 for v in m.values()
                        if isinstance(v, bool) and not v) / max(
                            sum(1 for v in m.values() if isinstance(v, bool)), 1)
            all_scores.append((sha12, score, m))
        else:
            m = compare_document(cm, gm)
            m["sha12"] = sha12
            doc_metrics.append(m)
            score = sum(1 for v in m.values()
                        if isinstance(v, bool) and not v) / max(
                            sum(1 for v in m.values() if isinstance(v, bool)), 1)
            all_scores.append((sha12, score, m))

    # Aggregate field agreement
    agreement = _aggregate_agreement(photo_metrics, doc_metrics)
    (out_dir / "field-agreement.json").write_text(
        json.dumps(agreement, indent=2) + "\n"
    )

    # Divergence catalog (top 10% most-disagreed)
    all_scores.sort(key=lambda x: x[1], reverse=True)
    top_n = max(1, len(all_scores) // 10)
    divergent = [{"sha12": s, "divergence_score": sc, "metrics": m}
                 for s, sc, m in all_scores[:top_n]]
    (out_dir / "divergence-catalog.json").write_text(
        json.dumps(divergent, indent=2) + "\n"
    )

    # Sample diffs (top 20)
    _generate_sample_diffs(
        all_scores[:20], claude_manifests, gpt_manifests, out_dir / "sample-diffs",
    )

    # Markdown reports
    _write_type_report("photos", photo_metrics, agreement, out_dir / "photo-comparison.md")
    _write_type_report("documents", doc_metrics, agreement, out_dir / "doc-comparison.md")

    print(f"Comparison complete. Results in {out_dir}")


def _aggregate_agreement(photos: list[dict], docs: list[dict]) -> dict:
    """Compute mean/count for each metric across all assets."""
    result = {"photos": {}, "documents": {}}
    for label, items in [("photos", photos), ("documents", docs)]:
        if not items:
            continue
        keys = [k for k in items[0] if k != "sha12"]
        for key in keys:
            vals = [m[key] for m in items if key in m]
            if not vals:
                continue
            if isinstance(vals[0], bool):
                result[label][key] = {
                    "agreement_rate": sum(vals) / len(vals),
                    "count": len(vals),
                }
            elif isinstance(vals[0], (int, float)):
                result[label][key] = {
                    "mean": sum(vals) / len(vals),
                    "count": len(vals),
                }
    return result


def _generate_sample_diffs(top_scores, claude, gpt, diff_dir: Path):
    diff_dir.mkdir(parents=True, exist_ok=True)
    for i, (sha12, score, _metrics) in enumerate(top_scores):
        cm = claude.get(sha12, {})
        gm = gpt.get(sha12, {})
        lines = [
            f"# Diff: {sha12} (divergence: {score:.2f})\n",
            f"Content type: {cm.get('_content_type', '?')}\n",
            f"Source: {cm.get('source_file', '?')}\n\n",
            "## Claude\n```json\n",
            json.dumps(cm.get("analysis", {}), indent=2, ensure_ascii=False),
            "\n```\n\n## GPT\n```json\n",
            json.dumps(gm.get("analysis", {}), indent=2, ensure_ascii=False),
            "\n```\n",
        ]
        (diff_dir / f"{i+1:02d}-{sha12}.md").write_text("".join(lines))


def _write_type_report(label: str, metrics: list[dict], agreement: dict, path: Path):
    data = agreement.get(label, {})
    lines = [f"# {label.title()} Comparison Results\n\n"]
    lines.append(f"**{len(metrics)} {label} compared**\n\n")
    lines.append("| Metric | Agreement Rate |\n|--------|---------------|\n")
    for key, val in sorted(data.items()):
        rate = val.get("agreement_rate", val.get("mean", 0))
        lines.append(f"| {key} | {rate:.1%} |\n")
    path.write_text("".join(lines))


def main():
    run_comparison()


if __name__ == "__main__":
    main()
