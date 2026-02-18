#!/usr/bin/env python3
"""Score provider results against ground truth and generate comparison report.

Usage:
    python runs/p2-compare/score_results.py
"""

import json
import statistics
from pathlib import Path

COMPARE_DIR = Path(__file__).resolve().parent
GT_FILE = COMPARE_DIR.parent / "p0-recon" / "ground-truth.json"
PROVIDERS = ["claude", "codex", "ollama"]


def load_ground_truth() -> dict[str, dict]:
    """Load ground truth keyed by SHA-256."""
    gt = json.loads(GT_FILE.read_text())
    return {label["source_sha256"]: label for label in gt["labels"]}


def load_provider_results(provider: str) -> dict[str, dict]:
    """Load provider results keyed by SHA-256."""
    results_file = COMPARE_DIR / provider / "results.json"
    if not results_file.exists():
        return {}
    data = json.loads(results_file.read_text())
    return {
        r["source_sha256"]: r
        for r in data["results"]
        if r["status"] == "ok"
    }


def normalize_doc_type(dt: str) -> str:
    """Normalize document type for comparison."""
    return dt.strip().lower().rstrip("/")


def score_doc_type(gt_type: str, pred_type: str) -> bool:
    """Exact match on document_type (primary quality metric)."""
    return normalize_doc_type(gt_type) == normalize_doc_type(pred_type)


def score_date(gt_date: str, pred_date: str) -> str:
    """Score date match: exact, partial (year matches), or miss."""
    if not gt_date or not pred_date:
        return "skip"
    if gt_date == pred_date:
        return "exact"
    # Partial: year matches
    gt_year = gt_date[:4]
    pred_year = pred_date[:4]
    if gt_year == pred_year:
        return "partial"
    return "miss"


def score_sensitivity(
    gt_sens: dict, pred_sens: dict
) -> dict:
    """Score sensitivity flags: precision, recall, false negatives."""
    flags = ["has_ssn", "has_financial", "has_medical"]
    tp = fp = fn = tn = 0
    fn_details = []

    for flag in flags:
        gt_val = gt_sens.get(flag, False)
        pred_val = pred_sens.get(flag, False)
        if gt_val and pred_val:
            tp += 1
        elif not gt_val and pred_val:
            fp += 1
        elif gt_val and not pred_val:
            fn += 1
            fn_details.append(flag)
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0

    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "fn_details": fn_details,
    }


def _normalize_item(item) -> str:
    """Normalize a list item to a lowercase string for comparison."""
    if isinstance(item, dict):
        # key_dates may be {date, event} dicts — extract the date
        return str(item.get("date", item.get("name", str(item)))).lower().strip()
    return str(item).lower().strip()


def score_set_overlap(gt_list: list, pred_list: list) -> dict:
    """Score set overlap for key_people, key_dates, tags."""
    gt_set = {_normalize_item(s) for s in gt_list}
    pred_set = {_normalize_item(s) for s in pred_list}
    if not gt_set and not pred_set:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    intersection = gt_set & pred_set
    precision = len(intersection) / len(pred_set) if pred_set else 1.0
    recall = len(intersection) / len(gt_set) if gt_set else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "gt_count": len(gt_set),
        "pred_count": len(pred_set),
        "overlap": len(intersection),
    }


def score_provider(provider: str, gt: dict[str, dict]) -> dict:
    """Score all results for a single provider."""
    results = load_provider_results(provider)
    if not results:
        return {"error": f"No results for {provider}"}

    # Load timing from results file
    results_file = COMPARE_DIR / provider / "results.json"
    results_data = json.loads(results_file.read_text())

    doc_scores = []
    total_fn = 0
    fn_details_all = []
    timings = []

    for sha, gt_label in gt.items():
        pred = results.get(sha)
        if not pred:
            doc_scores.append({"sha": sha[:12], "status": "missing"})
            continue

        analysis = pred["analysis"]
        elapsed = pred.get("elapsed_seconds", 0)
        timings.append(elapsed)

        dt_match = score_doc_type(gt_label["document_type"], analysis["document_type"])
        date_score = score_date(gt_label.get("date", ""), analysis.get("date", ""))
        sens_score = score_sensitivity(gt_label["sensitivity"], analysis.get("sensitivity", {}))
        people_score = score_set_overlap(gt_label.get("key_people", []), analysis.get("key_people", []))
        dates_score = score_set_overlap(gt_label.get("key_dates", []), analysis.get("key_dates", []))
        tags_score = score_set_overlap(gt_label.get("tags", []), analysis.get("tags", []))

        total_fn += sens_score["fn"]
        if sens_score["fn_details"]:
            fn_details_all.append({
                "sha": sha[:12],
                "source_file": gt_label.get("source_file", pred.get("source_file", "")),
                "missed_flags": sens_score["fn_details"],
            })

        doc_scores.append({
            "sha": sha[:12],
            "pages": gt_label.get("page_count", pred.get("page_count", 0)),
            "status": "scored",
            "doc_type_match": dt_match,
            "gt_type": gt_label["document_type"],
            "pred_type": analysis["document_type"],
            "date_score": date_score,
            "sensitivity": sens_score,
            "people_overlap": people_score,
            "dates_overlap": dates_score,
            "tags_overlap": tags_score,
            "elapsed_seconds": elapsed,
        })

    scored = [d for d in doc_scores if d["status"] == "scored"]
    dt_matches = sum(1 for d in scored if d["doc_type_match"])
    dt_total = len(scored)

    date_exact = sum(1 for d in scored if d["date_score"] == "exact")
    date_partial = sum(1 for d in scored if d["date_score"] == "partial")

    avg_sens_precision = statistics.mean(d["sensitivity"]["precision"] for d in scored) if scored else 0
    avg_sens_recall = statistics.mean(d["sensitivity"]["recall"] for d in scored) if scored else 0

    avg_people_f1 = statistics.mean(d["people_overlap"]["f1"] for d in scored) if scored else 0
    avg_tags_f1 = statistics.mean(d["tags_overlap"]["f1"] for d in scored) if scored else 0

    avg_time = statistics.mean(timings) if timings else 0
    p95_time = sorted(timings)[int(len(timings) * 0.95)] if timings else 0

    return {
        "provider": provider,
        "documents_scored": dt_total,
        "documents_missing": sum(1 for d in doc_scores if d["status"] == "missing"),
        "doc_type_exact_match": round(dt_matches / dt_total, 3) if dt_total else 0,
        "doc_type_matches": dt_matches,
        "doc_type_total": dt_total,
        "date_exact": date_exact,
        "date_partial": date_partial,
        "date_total": dt_total,
        "sensitivity_precision_avg": round(avg_sens_precision, 3),
        "sensitivity_recall_avg": round(avg_sens_recall, 3),
        "sensitivity_total_fn": total_fn,
        "sensitivity_fn_details": fn_details_all,
        "people_f1_avg": round(avg_people_f1, 3),
        "tags_f1_avg": round(avg_tags_f1, 3),
        "avg_time_seconds": round(avg_time, 1),
        "p95_time_seconds": round(p95_time, 1),
        "total_time_seconds": results_data.get("total_elapsed_seconds", 0),
        "per_doc_scores": doc_scores,
    }


def generate_report(scores: dict[str, dict]) -> str:
    """Generate markdown comparison report."""
    lines = [
        "# Provider Comparison Report",
        "",
        f"**Date**: 2026-02-18",
        f"**Test set**: 18 documents, 151 pages",
        "",
        "## Summary Table",
        "",
        "| Metric | Claude CLI | Codex CLI | Ollama (qwen3:32b) |",
        "|--------|-----------|-----------|-------------------|",
    ]

    def _val(provider, key, fmt="{}"):
        s = scores.get(provider, {})
        v = s.get(key, "N/A")
        return fmt.format(v) if v != "N/A" else "N/A"

    lines.append(f"| doc_type Match | {_val('claude', 'doc_type_exact_match', '{:.0%}')} ({_val('claude', 'doc_type_matches')}/{_val('claude', 'doc_type_total')}) | {_val('codex', 'doc_type_exact_match', '{:.0%}')} ({_val('codex', 'doc_type_matches')}/{_val('codex', 'doc_type_total')}) | {_val('ollama', 'doc_type_exact_match', '{:.0%}')} ({_val('ollama', 'doc_type_matches')}/{_val('ollama', 'doc_type_total')}) |")
    lines.append(f"| Sensitivity Recall | {_val('claude', 'sensitivity_recall_avg', '{:.0%}')} | {_val('codex', 'sensitivity_recall_avg', '{:.0%}')} | {_val('ollama', 'sensitivity_recall_avg', '{:.0%}')} |")
    lines.append(f"| Sensitivity FN | {_val('claude', 'sensitivity_total_fn')} | {_val('codex', 'sensitivity_total_fn')} | {_val('ollama', 'sensitivity_total_fn')} |")
    lines.append(f"| Sensitivity Precision | {_val('claude', 'sensitivity_precision_avg', '{:.0%}')} | {_val('codex', 'sensitivity_precision_avg', '{:.0%}')} | {_val('ollama', 'sensitivity_precision_avg', '{:.0%}')} |")
    lines.append(f"| Date Exact | {_val('claude', 'date_exact')}/{_val('claude', 'date_total')} | {_val('codex', 'date_exact')}/{_val('codex', 'date_total')} | {_val('ollama', 'date_exact')}/{_val('ollama', 'date_total')} |")
    lines.append(f"| People F1 (avg) | {_val('claude', 'people_f1_avg', '{:.0%}')} | {_val('codex', 'people_f1_avg', '{:.0%}')} | {_val('ollama', 'people_f1_avg', '{:.0%}')} |")
    lines.append(f"| Tags F1 (avg) | {_val('claude', 'tags_f1_avg', '{:.0%}')} | {_val('codex', 'tags_f1_avg', '{:.0%}')} | {_val('ollama', 'tags_f1_avg', '{:.0%}')} |")
    lines.append(f"| Avg Time/Doc | {_val('claude', 'avg_time_seconds')}s | {_val('codex', 'avg_time_seconds')}s | {_val('ollama', 'avg_time_seconds')}s |")
    lines.append(f"| P95 Time/Doc | {_val('claude', 'p95_time_seconds')}s | {_val('codex', 'p95_time_seconds')}s | {_val('ollama', 'p95_time_seconds')}s |")
    lines.append(f"| Total Time | {_val('claude', 'total_time_seconds')}s | {_val('codex', 'total_time_seconds')}s | {_val('ollama', 'total_time_seconds')}s |")

    # Quality gates
    lines.extend(["", "## Quality Gates", ""])
    for p in PROVIDERS:
        s = scores.get(p, {})
        dt_match = s.get("doc_type_exact_match", 0)
        total_fn = s.get("sensitivity_total_fn", -1)
        dt_pass = dt_match >= 0.80
        fn_pass = total_fn == 0
        verdict = "PASS" if (dt_pass and fn_pass) else "FAIL"
        lines.append(f"- **{p}**: doc_type >= 80%: {'PASS' if dt_pass else 'FAIL'} ({dt_match:.0%}), sensitivity FN = 0: {'PASS' if fn_pass else 'FAIL'} ({total_fn}FN) -> **{verdict}**")

    # doc_type mismatches
    lines.extend(["", "## Document Type Mismatches", ""])
    for p in PROVIDERS:
        s = scores.get(p, {})
        mismatches = [d for d in s.get("per_doc_scores", []) if d.get("status") == "scored" and not d.get("doc_type_match")]
        if mismatches:
            lines.append(f"### {p}")
            for m in mismatches:
                lines.append(f"- `{m['sha']}`: ground truth `{m['gt_type']}` vs predicted `{m['pred_type']}`")
            lines.append("")

    # Sensitivity false negatives
    lines.extend(["", "## Sensitivity False Negatives", ""])
    for p in PROVIDERS:
        s = scores.get(p, {})
        fns = s.get("sensitivity_fn_details", [])
        if fns:
            lines.append(f"### {p}")
            for fn in fns:
                lines.append(f"- `{fn['sha']}` ({fn.get('source_file', '')}): missed {fn['missed_flags']}")
            lines.append("")
        else:
            lines.append(f"### {p}: None")
            lines.append("")

    return "\n".join(lines)


def main():
    gt = load_ground_truth()
    print(f"Ground truth: {len(gt)} documents")

    all_scores = {}
    for provider in PROVIDERS:
        print(f"\nScoring {provider}...")
        s = score_provider(provider, gt)
        all_scores[provider] = s
        if "error" not in s:
            print(f"  doc_type match: {s['doc_type_exact_match']:.0%} ({s['doc_type_matches']}/{s['doc_type_total']})")
            print(f"  sensitivity FN: {s['sensitivity_total_fn']}")
            print(f"  avg time: {s['avg_time_seconds']}s")

    # Write scores
    (COMPARE_DIR / "scores.json").write_text(
        json.dumps(all_scores, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"\nScores written to: {COMPARE_DIR / 'scores.json'}")

    # Write safety metrics
    safety = {}
    for p in PROVIDERS:
        s = all_scores.get(p, {})
        safety[p] = {
            "sensitivity_precision_avg": s.get("sensitivity_precision_avg", 0),
            "sensitivity_recall_avg": s.get("sensitivity_recall_avg", 0),
            "sensitivity_total_fn": s.get("sensitivity_total_fn", -1),
            "sensitivity_fn_details": s.get("sensitivity_fn_details", []),
        }
    (COMPARE_DIR / "safety-metrics.json").write_text(
        json.dumps(safety, indent=2, ensure_ascii=False) + "\n"
    )

    # Write comparison report
    report = generate_report(all_scores)
    (COMPARE_DIR / "comparison.md").write_text(report + "\n")
    print(f"Report written to: {COMPARE_DIR / 'comparison.md'}")


if __name__ == "__main__":
    main()
