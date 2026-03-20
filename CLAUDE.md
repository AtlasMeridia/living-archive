# Living Archive

AI-assisted archival system. Four-machine architecture: data (NAS, read-only), AI (local Mac, regeneratable metadata), presentation (Immich v2.5.6 on VPS at `living-archive.kennyliu.io`).

## Key paths

- `src/` — Python pipeline code
- `_dev/dev-log.md` — Working record of pipeline runs, architecture decisions, and process observations
- `_dev/research/` — Design sessions and architecture decisions (date-first naming: `YYYY-MM-DD <topic>.md`)
- `content/drafts/` — Blog post drafts before publishing to Ghost
- `BACKLOG.md` — Task tracking (check before starting work)
- `docs/architecture.md` — Infrastructure documentation
- `project-brief.md` — Project vision and scope
- `agents.md` — AI agent roles, conventions, and content workflow

## Dev log

Update `_dev/dev-log.md` at the end of any session that produces significant work. This includes pipeline runs (with metrics), architecture changes, experiment progress, and process observations. The log serves as the connective tissue between machine logs, research docs, and the backlog — if someone asks "what happened last week," this is where the answer lives.

## Agent information

See `agents.md` for agent roles, conventions, and how content drafting works.
