# Branch C Reproducibility

Branch C now supports two explicit execution modes via
`python -m experiments.0002-synthesis-layer.src.branch_c`:

- `--mode inline` (default): uses curated local clusters from
  `branch-c-inline-clusters.json` (matches the original experiment run path:
  interactive Claude session + human review).
- `--mode anthropic`: generates clusters directly via the Anthropic API.

## Rebuild from inline curated clusters

```bash
python -m experiments.0002-synthesis-layer.src.branch_c \
  --mode inline \
  --inline-clusters experiments/0002-synthesis-layer/runs/p1-person-branches/branch-c-inline-clusters.json \
  --output experiments/0002-synthesis-layer/runs/p1-person-branches/branch-c-clusters.json
```

## Generate fresh clusters via API

```bash
python -m experiments.0002-synthesis-layer.src.branch_c \
  --mode anthropic \
  --model claude-sonnet-4-20250514 \
  --output experiments/0002-synthesis-layer/runs/p1-person-branches/branch-c-clusters.api.json
```

The API result should be reviewed by a human before replacing the curated
inline clusters.
