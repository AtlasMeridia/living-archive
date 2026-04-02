# Experiment 0007: Control Plane

## Question

Can Living Archive gain a trustworthy control plane for autonomous improvement loops — one that stamps exact data/code snapshots, enforces freshness gates, records keep/revert decisions, and prevents false conclusions from stale synthesis or degraded infrastructure?

## Why This Is an Experiment

Experiments 0005 and 0006 established the core pattern:
- narrow mutable artifact
- explicit metric
- bounded iteration

But they also exposed the next bottleneck: experimental trust.

The current system can produce a score, but a score is only meaningful if we know:
- which code/prompt version produced it
- which `catalog.db` / `synthesis.db` snapshot it used
- whether preflight was healthy
- whether the benchmark set was train, holdout, or live canary
- whether the result should be kept, reverted, or escalated for human review

Without that layer, the loop can misattribute infrastructure drift to model quality and optimize against stale data.

## Scope

This experiment does NOT optimize Living Archive directly.
It builds the orchestration/evaluation substrate that later loops rely on.

Initial target loops supported by this control plane:
1. **Accuracy loop** — conversational archive over `0005-conversational-archive`
2. **Efficiency loop** — bounded processing policy search
3. **Presentation watchdog** — regression gate for dashboard changes

## Core Hypothesis

A lightweight control plane will reduce optimization noise by separating:
- data plane work (batch, synthesis, QA, dashboard)
- control plane work (snapshotting, gating, benchmark selection, verdict logging)

Success means future loop results become comparable, replayable, and auditable.

## MVP Artifacts

```
experiments/0007-control-plane/
├── brief.md
├── manifest.json
├── manifest_schema.json
├── benchmarks/
│   └── README.md
├── runs/
│   └── README.md
└── src/
    └── run_controlled_eval.py
```

## Responsibilities of the Control Plane

1. **Snapshot identity**
   - Git commit under test
   - mutable artifact path
   - synthesis snapshot ID
   - catalog snapshot ID
   - benchmark set ID

2. **Freshness gates**
   - preflight passed
   - synthesis rebuilt for tested snapshot
   - benchmark set declared
   - lane-specific non-regression checks

3. **Run records**
   - run ID
   - lane
   - timestamps
   - baseline vs candidate metrics
   - keep/revert/human-review verdict
   - trace/log pointers

4. **Benchmark discipline**
   - train vs holdout vs live canary separation
   - hidden questions not shown to optimizer
   - fixed efficiency corpus for throughput tests

## Phases

### Phase 0 — Scaffold
Create directory structure, manifest schema, and a minimal run logger.
Gate: a controlled run directory can be created with stamped metadata.

### Phase 1 — Accuracy integration
Use the control plane to wrap `0005-conversational-archive` evaluations.
Gate: one accuracy run records snapshot IDs, preflight, scores, and verdict.

### Phase 2 — Efficiency integration
Add a representative batch benchmark corpus and efficiency metrics.
Gate: one throughput run is recorded without confusing infra degradation for model regressions.

### Phase 3 — Presentation gate
Add screenshot/human-review promotion checks for dashboard changes.
Gate: dashboard candidate can be marked pass/fail with explicit human-review status.

## Initial Metrics

This experiment's own success metrics are operational, not model-based:
- Controlled runs created: count
- Runs with complete metadata: %
- Runs rejected due to missing/failed gates: count
- Time to compare two candidate runs: operator minutes
- Reproducibility: can a later agent explain why a change was kept or reverted?

## Risks

- Overbuilding the control layer before it is exercised
- Encoding too much policy before the first real integration
- Treating the control plane as a product instead of a test harness

## First Practical Use

Wrap the existing 0005 accuracy watchdog and recover from 0.809 back toward >=0.830 with explicit snapshot discipline.
