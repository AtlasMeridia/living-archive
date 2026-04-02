"""Run a controlled Living Archive evaluation with stamped metadata.

Current implemented integration:
- accuracy lane -> experiment 0005 baseline/watchdog execution

Example:
    python src/run_controlled_eval.py \
      --lane accuracy \
      --candidate experiments/0005-conversational-archive/src/prompts.py \
      --artifact-type prompts \
      --benchmark-set qa_watchdog_v1 \
      --split live_canary \
      --catalog-id cat_20260401T1800Z \
      --synthesis-id syn_20260401T1812Z \
      --preflight-status pass
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "runs"
BENCHMARKS_DIR = ROOT / "benchmarks"
REPO_ROOT = ROOT.parents[1]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def git_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def benchmark_path(lane: str, set_id: str) -> Path:
    return BENCHMARKS_DIR / lane / f"{set_id}.json"


def latest_json(directory: Path, prefix: str) -> Path | None:
    files = sorted(directory.glob(f"{prefix}_*.json"))
    return files[-1] if files else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", required=True, choices=["accuracy", "efficiency", "presentation"])
    parser.add_argument("--candidate", required=True, help="Path to mutable artifact under test")
    parser.add_argument("--artifact-type", default="unknown")
    parser.add_argument("--benchmark-set", required=True)
    parser.add_argument("--split", required=True, choices=["train", "holdout", "live_canary"])
    parser.add_argument("--catalog-id")
    parser.add_argument("--synthesis-id")
    parser.add_argument("--manifests-id")
    parser.add_argument("--preflight-status", default="unknown", choices=["pass", "fail", "unknown"])
    parser.add_argument("--preflight-notes", default="")
    parser.add_argument("--candidate-notes", default="")
    parser.add_argument("--execute", action="store_true", help="Execute the benchmark instead of stamping metadata only")
    return parser.parse_args()


def stamp_manifest(args: argparse.Namespace, run_id: str, benchmark: dict) -> dict:
    return {
        "run_id": run_id,
        "lane": args.lane,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(REPO_ROOT),
        "candidate": {
            "path": args.candidate,
            "artifact_type": args.artifact_type,
            "notes": args.candidate_notes,
        },
        "benchmarks": {
            "set_id": args.benchmark_set,
            "split": args.split,
        },
        "snapshots": {
            "catalog_id": args.catalog_id,
            "synthesis_id": args.synthesis_id,
            "manifests_id": args.manifests_id,
        },
        "preflight": {
            "status": args.preflight_status,
            "notes": args.preflight_notes,
        },
        "metrics": {
            "baseline": {
                "target_overall": benchmark.get("target_overall"),
            },
            "candidate": None,
            "holdout": None,
        },
        "verdict": {
            "status": "incomplete",
            "reason": "Benchmark not executed yet.",
        },
        "artifacts": {
            "scores_json": None,
            "preflight_json": "preflight.json",
            "diff_patch": None,
            "trace_dir": "traces",
            "results_json": None,
            "benchmark_json": str(benchmark_path(args.lane, args.benchmark_set).relative_to(ROOT)),
        },
    }


def execute_accuracy_0005(run_dir: Path, benchmark: dict) -> tuple[dict, dict]:
    raw_dir = run_dir / "raw"
    traces_dir = run_dir / "traces"
    raw_dir.mkdir(parents=True, exist_ok=True)
    traces_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(REPO_ROOT / "experiments/0005-conversational-archive/src/run_baseline.py"),
        "--output-dir",
        str(raw_dir),
    ]
    if benchmark.get("skip_coherence", False):
        cmd.append("--quick")
    if benchmark.get("tier"):
        cmd.extend(["--tier", benchmark["tier"]])
    if benchmark.get("question_ids"):
        cmd.extend(["--question-ids", ",".join(benchmark["question_ids"])])

    completed = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=int(benchmark.get("timeout_seconds", 3600)),
        check=False,
    )

    (traces_dir / "benchmark.stdout.log").write_text(completed.stdout)
    (traces_dir / "benchmark.stderr.log").write_text(completed.stderr)

    if completed.returncode != 0:
        raise RuntimeError(f"0005 baseline exited {completed.returncode}: {completed.stderr[-400:]}")

    scores_path = latest_json(raw_dir, "scores")
    results_path = latest_json(raw_dir, "results")
    if not scores_path or not results_path:
        raise RuntimeError("0005 baseline completed but no scores/results JSON was produced")

    return load_json(scores_path), load_json(results_path)


def verdict_for_accuracy(scores_payload: dict, results_payload: dict, benchmark: dict) -> tuple[str, str]:
    overall = float(scores_payload.get("summary", {}).get("overall_avg", 0))
    succeeded = int(results_payload.get("questions_succeeded", 0))
    attempted = int(results_payload.get("questions_attempted", 0))
    minimum = int(benchmark.get("min_questions_succeeded", attempted))
    target = benchmark.get("target_overall")

    if succeeded < minimum:
        return "revert", f"Only {succeeded}/{attempted} questions succeeded; minimum required is {minimum}."
    if target is None:
        return "human_review", f"Run completed at overall {overall:.3f}; no target threshold configured."
    if overall >= float(target):
        return "keep", f"Overall {overall:.3f} met/exceeded target {float(target):.3f}."
    return "human_review", f"Overall {overall:.3f} below target {float(target):.3f}. Review before promotion."


def main() -> None:
    args = parse_args()
    bench_path = benchmark_path(args.lane, args.benchmark_set)
    if not bench_path.exists():
        raise SystemExit(f"Benchmark not found: {bench_path}")

    benchmark = load_json(bench_path)
    run_id = f"{args.lane}_{utc_stamp()}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    manifest = stamp_manifest(args, run_id, benchmark)
    preflight = {
        "status": args.preflight_status,
        "notes": args.preflight_notes,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    scores_stub = {
        "baseline": manifest["metrics"]["baseline"],
        "candidate": None,
        "holdout": None,
        "status": "pending",
    }

    (run_dir / "run.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (run_dir / "preflight.json").write_text(json.dumps(preflight, indent=2) + "\n")
    (run_dir / "scores.json").write_text(json.dumps(scores_stub, indent=2) + "\n")
    (run_dir / "notes.md").write_text("# Notes\n\nControlled run created.\n")

    if not args.execute:
        print(run_dir)
        return

    if args.preflight_status != "pass":
        manifest["verdict"] = {
            "status": "incomplete",
            "reason": f"Preflight status is {args.preflight_status}; refusing to execute benchmark.",
        }
        (run_dir / "run.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(run_dir)
        return

    if args.lane == "accuracy" and benchmark.get("integration") == "0005-baseline":
        scores_payload, results_payload = execute_accuracy_0005(run_dir, benchmark)
        verdict_status, verdict_reason = verdict_for_accuracy(scores_payload, results_payload, benchmark)

        manifest["metrics"]["candidate"] = scores_payload.get("summary", {})
        manifest["verdict"] = {
            "status": verdict_status,
            "reason": verdict_reason,
        }
        manifest["artifacts"]["scores_json"] = "raw/" + latest_json(run_dir / "raw", "scores").name
        manifest["artifacts"]["results_json"] = "raw/" + latest_json(run_dir / "raw", "results").name

        control_scores = {
            "baseline": manifest["metrics"]["baseline"],
            "candidate": scores_payload.get("summary", {}),
            "holdout": None,
            "status": "completed",
        }
        (run_dir / "scores.json").write_text(json.dumps(control_scores, indent=2) + "\n")
        (run_dir / "run.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (run_dir / "notes.md").write_text(
            "# Notes\n\n"
            f"Executed benchmark `{args.benchmark_set}` against 0005 baseline runner.\n"
            f"Verdict: {verdict_status} — {verdict_reason}\n"
        )
    else:
        raise SystemExit(f"Execution not implemented for lane={args.lane} benchmark={args.benchmark_set}")

    print(run_dir)


if __name__ == "__main__":
    main()
