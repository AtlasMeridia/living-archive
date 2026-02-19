# Presentation Layer — Design Session

**Date:** 2026-02-18
**Status:** Decisions made, ready to execute

---

## Key Reframe

The presentation layer isn't about showing archive data yet. The data isn't processed enough, the methodology is still developing, and the AI analysis layer is still iterating. The interesting thing to present right now is **the process of building the system** — decisions, trade-offs, what AI gets right and wrong, how the layers work together.

The archive data becomes illustration material later, once the UI and analysis tools are mature enough to demonstrate a viable product.

## Audience Priority (current stage)

| Audience | Priority | Rationale |
|----------|----------|-----------|
| **Public (methodology)** | Now | The development process is the product. Documenting while building is more authentic than writing it up later. |
| **Admin (Kenny)** | Now | Working tools needed to iterate — and those tools become the illustrations for public content. |
| **Family** | Later | Immich is sufficient for now. Family access matters once the data is actually sorted. |

## Three Audiences — Full Analysis

### Public (methodology documentation)

**What it is:** A series of posts documenting the ongoing development of Living Archive — methodology, technical decisions, what's working, what isn't.

**Where it lives:** `kennyliu.io/living-archive`

**Infrastructure:** Headless Atlas (Next.js 16 + Ghost CMS + Vercel). The `/notes` section already works this way — Ghost posts fetched via Content API, rendered with ATLAS Meridia design system. `/living-archive` follows the same pattern: new route, posts tagged `living-archive` in Ghost, same design tokens.

**Content strategy:** Process-first. Not "here's the finished system" but "here's what we're figuring out." Screenshots and demos of working tools serve as illustrations as those tools mature. The development journey is the narrative.

**Agent workflow (progressive automation):**
1. **Early posts:** Co-write with an openclaw agent. Kenny and agent draft together, establishing voice, format, and what a good post looks like.
2. **Transition:** After a few iterations, the format gels. Agent begins drafting from `_dev/research/` documents, session transcripts, and code changes.
3. **Steady state:** Agent drafts posts from development activity, Kenny reviews and approves. Frees Kenny to focus on building.

**First post candidates:**
- Why this project exists (the "green box" reframe — organizing your digital life isn't about death, it's about knowing where things are)
- What the three-layer architecture looks like and why it matters
- What happens when you point Claude at a box of 1980s family photos
- The real cost of AI-assisted archival work (tokens, time, accuracy)

### Admin (Kenny — working tools)

**Current state:**
- Immich handles photo browsing
- Review dashboard (`review.html`) handles metadata QA before push
- `catalog.db` has structured data, queryable only via CLI
- FTS5 document index has no UI

**Gaps:**
- Document search — FTS5 index sits in SQLite with no web interface
- Cross-collection views — no way to see a person across photos, documents, and journal entries
- Archive health dashboard — no overview of processing status, confidence distribution, pending work
- Catalog query interface — no way to explore `catalog.db` except command line

**These gaps become content:** As admin tools get built, they demonstrate the methodology. A document search UI screenshot illustrates "here's how full-text search works across 72 family trust documents." A person-view demo shows cross-referencing in action.

**Open question:** Single local app vs. targeted tools. Deferred — build the most needed thing first (probably document search or catalog explorer), see if they converge.

### Family (browsing and contribution)

**Current state:** Immich works for photo browsing. Cloudflare Tunnel + Access planned but not built (`archives.kennyliu.io`).

**Deferred because:**
- Data isn't sorted enough to present well
- Learning to apply AI effectively is higher priority than sharing results
- Immich covers the basic "show family photos" need

**When it becomes priority:**
- After enough photo slices are processed with good metadata
- After document pipeline handles the full trust collection
- After elder knowledge capture (faces need names before family browsing is useful)

**Contribution side matters:** Family access is partly about giving (organized photos) and partly about getting (who is this person? what year? what's the story?). The contribution mechanism — how family members add knowledge — needs design attention when this becomes active.

**Bilingual consideration:** Metadata is already bilingual (English + Simplified Chinese). UI will likely need to be too.

## Implementation Path

### Phase 1: Content infrastructure (headless-atlas)

- Add `/app/living-archive/` routes to headless-atlas (index + detail pages)
- Filter Ghost posts by `living-archive` tag
- Add "Living Archive" to site navigation
- Update sitemap and RSS feed

### Phase 2: First posts (co-authored)

- Co-write 2-3 posts with openclaw agent to establish voice and format
- Source material: project-brief.md, this research doc, existing `_dev/research/` documents
- Include screenshots of existing tools (review dashboard, Immich albums, catalog CLI output)

### Phase 3: Automated drafting

- Agent drafts from new `_dev/research/` docs and session transcripts
- Kenny reviews, edits, publishes
- Cadence follows development activity (new post when something meaningful ships)

### Phase 4: Admin tools as content

- As document search UI, catalog explorer, etc. get built, they generate visual content
- Posts shift from "here's what we decided" toward "here's what it looks like in practice"

## Decisions Made

1. **Public presentation is methodology-first**, not data-first. The development process is the content.
2. **Series of posts at `kennyliu.io/living-archive`**, not a standalone site or separate domain.
3. **Uses existing headless-atlas infrastructure** (Next.js + Ghost + Vercel). No new stack.
4. **Agent-assisted authoring** with progressive automation: co-write early, agent drafts later.
5. **Family access deferred** until data is better sorted. Immich is sufficient for now.
6. **Admin tools built as needed** — they serve double duty as working infrastructure and illustration material.

## Relationship to Other Backlog Items

- Replaces backlog item: "UI development discussion" (Next — Focused Conversations)
- Informs: "First blog post" (Later — Public Presence & Content)
- Connects to: headless-atlas development, openclaw agent capabilities
- Deferred: Family access, privacy defaults, family uploads (stay in Later)
