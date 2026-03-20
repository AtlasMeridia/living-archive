#!/usr/bin/env python3
"""Wrapper script for running experiment 0004 commands.

Usage:
    python experiments/0004-model-comparison/run.py runner --provider claude --hours 2
    python experiments/0004-model-comparison/run.py runner --status
    python experiments/0004-model-comparison/run.py compare
    python experiments/0004-model-comparison/run.py synthesis --provider claude
    python experiments/0004-model-comparison/run.py synthesis --provider gpt
    python experiments/0004-model-comparison/run.py diff
    python experiments/0004-model-comparison/run.py report
"""

import importlib
import sys
from pathlib import Path

# Ensure repo root is on sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

COMMANDS = {
    "runner": "experiments.0004-model-comparison.src.runner",
    "compare": "experiments.0004-model-comparison.src.compare",
    "synthesis": "experiments.0004-model-comparison.src.synthesis_rebuild",
    "diff": "experiments.0004-model-comparison.src.synthesis_diff",
    "report": "experiments.0004-model-comparison.src.report",
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: {sys.argv[0]} <command> [args...]")
        print(f"Commands: {', '.join(COMMANDS)}")
        sys.exit(1)

    command = sys.argv[1]
    sys.argv = [sys.argv[0]] + sys.argv[2:]  # strip command from argv

    mod = importlib.import_module(COMMANDS[command])
    mod.main()


if __name__ == "__main__":
    main()
