# Experiments

Guidelines for running experiments in this project.

## Structure

```
experiments/
├── EXPERIMENTS.md              # this file
├── 0000-experiment-name/
│   ├── brief.md                # question, branches, phases, gates, budget
│   ├── manifest.json           # metadata, tags, status
│   ├── src/                    # all experiment code lives here
│   │   └── ...
│   └── runs/                   # phase outputs, metrics, reports
│       ├── p0-setup/
│       ├── p1-.../
│       └── ...
```

## Principles

**Self-contained.** Each experiment is a standalone directory. Its code, data, and outputs all live inside `experiments/NNNN-name/`. Delete the directory and nothing else breaks.

**Isolated from `src/`.** Experiment code does not live in the project's `src/` tree. It reads project data (manifests, databases) but does not modify shared code or schemas. The main pipeline should not know the experiment exists.

**Disposable.** Experiments can be abandoned, restarted, or deleted without risk. Generated databases and artifacts are rebuilt from inputs, not migrated.

**Promotion is explicit.** If an experiment succeeds and its code should become infrastructure, it graduates to `src/` as a deliberate decision — new commit, backlog item, documentation update. This never happens automatically or by default.

## Conventions

- **Naming:** `NNNN-short-description` (zero-padded, sequential)
- **Brief:** Every experiment has a `brief.md` that states the question, what makes it an experiment (not just a feature), evaluation criteria, and phase gates
- **No pipeline imports:** Experiment code must not import from `src/`. Manifests and data files are the contract boundary
- **Branches over assumptions:** When multiple approaches could work, test them empirically rather than picking one upfront
- **Negative results are valid:** Document what didn't work and why. An experiment that disproves an approach is successful
- **Phase gates:** Each phase has a pass/fail gate. If a gate fails, the experiment pauses for redesign rather than pushing forward
- **Metrics in `runs/`:** Every phase produces its outputs in `runs/pN-name/`. This is the evidence trail

## Lifecycle

```
design → brief.md → implement (in experiment/src/) → run phases → evaluate
    → if successful: promote to src/ (explicit commit)
    → if not: document findings, close experiment
```
