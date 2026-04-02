# Benchmarks

This directory holds benchmark definitions used by the control plane.

Planned subdirectories:
- `accuracy/` — train, holdout, live canary QA sets for experiment 0005
- `efficiency/` — representative photo/document corpus plus expected runtime metadata
- `presentation/` — viewport definitions, screenshot tasks, and human-review checklist

Rules:
- Optimizers should not see hidden holdout/live-canary content.
- Benchmark IDs must be stable and referenced in each controlled run.
- Update benchmark versions when the underlying snapshot assumptions change.
