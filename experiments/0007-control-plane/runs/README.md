# Runs

Each controlled evaluation creates one run directory here:

`runs/<run_id>/`

Expected files:
- `run.json` — stamped manifest for the candidate under test
- `preflight.json` — gate status and environment notes
- `scores.json` — baseline/candidate/holdout metrics
- `notes.md` — optional operator notes
- `diff.patch` — optional candidate diff
- `traces/` — optional raw execution logs

A run is not considered valid unless `run.json` includes:
- lane
- benchmark set
- snapshot IDs
- preflight status
- verdict
