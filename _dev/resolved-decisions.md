# Resolved Decisions

Archived from `docs/open-questions.md` (retired 2026-02-11). Kept for historical reference.

| # | Question | Answer | Date |
|---|----------|--------|------|
| 1 | Where does inference run? | MacBook Pro (M3 Pro) via Claude API; NAS mounted via AFP as read-only source | 2026-02-05 |
| 2 | Batch inference or interactive? | Slice-based batch processing (`SLICE_PATH`), with confidence routing for human review | 2026-02-05 |
| 4 | Review workflow for low-confidence dates? | Confidence-based Immich albums: ≥0.8 auto-apply, 0.5–0.8 "Needs Review", <0.5 "Low Confidence" | 2026-02-05 |
| 5 | What problem are we solving first? | All three simultaneously: correct Immich sorting, methodology documentation, reusable system | 2026-02-11 |
| — | Domain name | `archives.kennyliu.io` for Immich | 2026-01-25 |
| — | Photo storage | NAS external library in Immich | 2026-01-26 |
| — | Admin interface | Immich web UI | 2026-01-26 |
| — | Blog location | `kennyliu.io/notes` with `living-archive` tag | 2026-01-24 |
