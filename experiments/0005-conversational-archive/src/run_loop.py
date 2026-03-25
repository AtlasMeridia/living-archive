"""Phase 2: Karpathy Loop — autonomous iteration on pipeline.py.

Each iteration:
  1. Analyze current scores and identify worst failures
  2. Propose a change to pipeline.py
  3. Re-run the question bank
  4. Compare scores to previous iteration
  5. If improved: keep. If regressed: revert.

Usage:
    python run_loop.py                     # run one iteration
    python run_loop.py --iterations 5      # run 5 iterations
    python run_loop.py --report            # show iteration history
"""

import argparse
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs" / "p2-loop"
PIPELINE_PATH = Path(__file__).resolve().parent / "pipeline.py"
PIPELINE_BACKUP = RUNS_DIR / "pipeline_backups"


def load_latest_scores() -> dict:
    """Load the most recent scores file."""
    score_files = sorted(Path(__file__).resolve().parents[1].rglob("scores_*.json"))
    if not score_files:
        return {}
    return json.loads(score_files[-1].read_text())


def save_iteration(iteration: int, scores: dict, changes: str, reverted: bool):
    """Save iteration results."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    with open(RUNS_DIR / f"iteration_{iteration:03d}_{timestamp}.json", "w") as f:
        json.dump({
            "iteration": iteration,
            "timestamp": timestamp,
            "changes": changes,
            "reverted": reverted,
            "scores": scores,
        }, f, indent=2)


def backup_pipeline(iteration: int):
    """Backup pipeline.py before modification."""
    PIPELINE_BACKUP.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PIPELINE_PATH, PIPELINE_BACKUP / f"pipeline_iter{iteration:03d}.py")


def get_iteration_count() -> int:
    """Count existing iterations."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return len(list(RUNS_DIR.glob("iteration_*.json")))


def show_report():
    """Print iteration history."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(RUNS_DIR.glob("iteration_*.json"))
    if not files:
        print("No iterations yet.")
        return

    print(f"{'Iter':>4}  {'Overall':>7}  {'Easy':>7}  {'Med':>7}  {'Hard':>7}  {'Rev':>4}  Changes")
    print("-" * 80)

    for f in files:
        data = json.loads(f.read_text())
        summary = data.get("scores", {}).get("summary", {})
        by_tier = summary.get("by_tier", {})
        print(
            f"{data['iteration']:>4}  "
            f"{summary.get('overall_avg', 0):>7.3f}  "
            f"{by_tier.get('easy', 0):>7.3f}  "
            f"{by_tier.get('medium', 0):>7.3f}  "
            f"{by_tier.get('hard', 0):>7.3f}  "
            f"{'Y' if data.get('reverted') else 'N':>4}  "
            f"{data.get('changes', '')[:50]}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    if args.report:
        show_report()
    else:
        print(f"Loop runner ready. Use the agent to execute iterations.")
        print(f"Current iteration count: {get_iteration_count()}")
        print(f"Pipeline: {PIPELINE_PATH}")
