# Agents

How AI agents interact with this project.

## Roles

**Development agent (Claude Code)** — builds pipelines, manages architecture, writes and maintains code. Works from `BACKLOG.md` and `_dev/research/` documents.

**Content agent (openclaw)** — drafts blog posts for `kennyliu.io/living-archive` based on research documents and development sessions. Co-writes with Kenny early on, then drafts more independently as the format solidifies. Publishes via Ghost CMS.

## Conventions

### Research documents

Location: `_dev/research/`

Naming: `YYYY-MM-DD <topic>.md` for dated sessions, `<topic>.md` for evolving documents. Date goes first so files sort chronologically.

Each document captures the thinking behind a decision or exploration — the "why" that doesn't belong in code comments or the backlog.

### Backlog

`BACKLOG.md` at project root. Agents should check this before starting work. Mark items in-progress while working, completed (with date) when done.

### Code

- Python source in `src/`, one module per concern
- Target 200-300 lines per file
- AI layer outputs on NAS at `_ai-layer/` paths, keyed by SHA-256
- Never modify source data (TIFFs, PDFs)

### Content drafting

Blog posts for the Living Archive series live at `kennyliu.io/living-archive`, published through Ghost CMS on the headless-atlas stack (Next.js + Vercel).

Workflow: `_dev/research/` (thinking) → `content/drafts/` (writing) → Ghost (publishing).

Drafts live in `content/drafts/` so they have direct access to the research docs, experiment results, and pipeline context that inform them. The headless-atlas repo handles rendering only.

Source material for posts:
- `_dev/research/` documents (design sessions, architecture decisions)
- Development session transcripts
- Screenshots of working tools (review dashboard, catalog output, Immich albums)
- `project-brief.md` for project framing

The content agent should:
- Write about process and methodology, not just results
- Include concrete details (costs, token counts, accuracy rates, screenshots)
- Avoid generic AI-writing patterns (see humanizer conventions)
- Draft for Kenny's review before publishing
