# Experiment 0004: Model Comparison — Claude Opus 4.6 vs GPT 5.4

## Question

Do Claude and GPT see different things in archival photos and documents? How do manifest differences cascade into the synthesis entity graph? Is there information in the disagreement?

## Context

The living-archive corpus (2,019 photos + 121 documents) was analyzed by Claude Sonnet/Opus, producing manifests that feed the synthesis layer. There's no cross-vendor baseline. Experiment 0001 compared Opus vs Sonnet for 5 documents — same vendor, small scale, no photos.

This experiment reprocesses the full corpus through both Claude Opus 4.6 and GPT 5.4, using subscription CLI tools ($0 cost).

## Phases

| Phase | Description | Gate |
|-------|-------------|------|
| P0 | Setup & CLI validation | Both CLIs produce schema-valid output |
| P1 | Claude Opus 4.6 full corpus (~9 x 2hr chunks) | >= 95% success rate |
| P2 | GPT 5.4 full corpus (~9 x 2hr chunks) | >= 95% success rate |
| P3 | Field-level comparison | Informational |
| P4 | Synthesis rebuild & diff | Exploratory |
| P5 | Final report | - |

## Cost

$0 — both models accessed via subscription CLI tools (Claude Max plan, Codex CLI).

## Usage

```bash
# Run a 2-hour chunk of Claude analysis
python experiments/0004-model-comparison/run.py runner --provider claude --hours 2

# Run a 2-hour chunk of GPT analysis
python experiments/0004-model-comparison/run.py runner --provider gpt --hours 2

# Check progress
python experiments/0004-model-comparison/run.py runner --status

# Phase 3: compare manifests
python experiments/0004-model-comparison/run.py compare

# Phase 4: rebuild synthesis DBs and diff
python experiments/0004-model-comparison/run.py synthesis --provider claude
python experiments/0004-model-comparison/run.py synthesis --provider gpt
python experiments/0004-model-comparison/run.py diff

# Phase 5: generate report
python experiments/0004-model-comparison/run.py report
```

## What makes this an experiment

- No prior cross-vendor comparison at this scale
- Unknown whether model differences are noise or signal
- Synthesis cascade effects are unpredictable
- Negative result (models agree on everything) is still informative
