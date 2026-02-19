# Council: Face Recognition & Collaborative Family Tagging

**Date**: 2026-02-06
**Models**: Claude Opus, Gemini, GPT-4.1, Grok 4

## Problem

Face recognition and collaborative family tagging for the Living Archive photo pipeline. Key questions: (1) What face recognition software fits this stack? (2) How should a people/identity layer work? (3) How to enable family member contributions? (4) Use Immich's built-in face recognition or build independent?

---

## CLAUDE OPUS (Anthropic)

**Initial Reaction:** Use Immich's built-in face recognition — don't build a parallel system. The real engineering challenge here isn't face detection, it's capturing elder knowledge before it's lost. The architecture question is really about building a collaborative annotation layer that's durable (outlives any single presentation tool) while being easy enough for 70-80 year olds to use.

**Strengths:**
- Three-layer architecture already separates concerns well — adding a people/identity layer is a natural extension of the AI layer
- Immich's built-in face recognition handles the hard ML part and is actively maintained by a large open-source community
- The existing review dashboard pattern maps directly to face tagging workflows
- Self-hosted stack means face embeddings and identity data never leave the family's control
- Claude Vision already notes `people_count` and `people_notes` in manifests — natural extension

**Risks & Weaknesses:**
- **Immich coupling risk**: If you store all identity data only in Immich's database, migrating away means losing person associations
- **Elder UX gap**: The review dashboard is a developer tool. Elders need "tap a face, type a name" with no other complexity
- **Scanned photo quality**: Face recognition on 1970s scanned prints will have significantly lower accuracy
- **Scale mismatch**: ~200 photos is too small for face clustering to work well
- **Identity merging complexity**: Same person at age 5 and age 50 won't cluster together — hard UX problem
- **Data loss urgency**: Elders are the most time-constrained resource

**Suggested Approach:**
1. Use Immich's face recognition as-is for detection and initial clustering
2. Add a `people` section to AI layer manifests with identity assertions independent of Immich
3. Create a people registry — simple JSON or SQLite in the AI layer mapping `person_id` to `{name_en, name_zh, relationship, birth_year, notes}`
4. Sync bidirectionally with Immich — AI layer registry is source of truth
5. Build an elder-friendly tagging interface — mobile-first, large tap targets, one face crop at a time, audio notes option
6. Prioritize elder sessions — treat this as oral history capture, not software testing
7. Add face data to Claude Vision prompts once people registry exists

**Key Insight:** The real constraint isn't technical — it's temporal. The people who can identify faces in 50-year-old photos are in their 70s and 80s. Every month of architecture deliberation is a month of knowledge that might be lost. Optimize for time-to-elder-input, not technical elegance. You can always re-architect later — you cannot recover the knowledge of someone who's passed.

---

## GEMINI (Google)

**Initial Reaction:** The core architectural challenge is the tension between the elegant, one-way, regenerative pipeline and the new requirement for a messy, two-way, collaborative feedback loop. The project's strength — its pristine data flow — is now its primary obstacle. The solution lies not in choosing a face-recognition tool, but in designing a workflow for human knowledge to flow back upstream without corrupting the source of truth.

**Strengths:**
- Clear layering: Data-AI-Presentation architecture is clean, modular, and easy to understand
- Data sovereignty: Self-hosted foundation respects privacy and control
- Regeneratable AI layer: Treating manifests as disposable, regeneratable sidecar files is brilliant
- Pragmatic tooling: Immich offers rich UX out of the box; Python scripting core is simple and maintainable

**Risks & Weaknesses:**
- **The Write-Back Problem**: No mechanism for writing family data back into a persistent store. If Immich rebuilds, all tagging work is lost
- **UX for Elders**: A separate dashboard is a non-starter. The only viable UI for elders is the main photo viewing app (Immich)
- **Data Siloing**: Immich face recognition without sync creates a data silo
- **Pipeline Brittleness**: Multiple family members of varying skill will introduce inconsistencies

**Suggested Approach:**
1. Embrace Immich as the UI — abandon separate review tools for family members
2. Run Immich's face recognition — let it handle detection, embedding, and clustering
3. Create an "Identity Sync" service — a regularly-run Python script that pulls recognized faces and labels from Immich API and exports to durable format
4. Establish an independent Identity Layer — SQLite or JSON directory. Fourth layer: canonical source of truth for who is in photos
5. Modify pipeline to be identity-aware — cross-reference against people.db, pre-apply known names
6. Proceed with Cloudflare Tunnel + Access for secure remote access

**Key Insight:** Reframe the system's "source of truth." For face identification, the family's input becomes the new source of truth, and Immich is merely the UI to capture it. The architectural flow should be a cycle, not a line: AI pipeline provides the initial low-confidence draft, family corrects through Immich, sync script extracts human-validated truth into the permanent Identity Layer, which then informs future pipeline runs.

---

## GPT-4.1 (OpenAI)

**Initial Reaction:** The pipeline is impressively forward-thinking, striking a balance between privacy and AI-enhanced usability. The biggest challenge is practical, not technical: integrating collaborative tagging from technophobic elders without sacrificing data integrity or fragmenting the data layer.

**Strengths:**
- Data sovereignty: No reliance on third-party cloud services
- Layered architecture: Decoupled data, AI, and presentation layers
- Human-in-the-loop review: Dashboard safeguards against AI annotation mistakes
- Localized and bilingual: Dual-language support is thoughtful for cross-generational access
- Leverages Immich: Capable, open-source presentation/backend

**Risks & Weaknesses:**
- Single point of edit: One-admin bottleneck impedes scaling collaborative input
- Face/identity data fragmentation: Risk of mismatch between Immich face clusters and external AI manifests
- Elders' user experience: Elders may struggle with any but the most dead-simple UI
- Tightly coupled to Immich: Building logic around Immich APIs limits flexibility
- Photo quality issues: Scanned/degraded photos lower recognition accuracy

**Suggested Approach:**
1. Leverage Immich's built-in face recognition first
2. Synchronize person/identity data across layers — periodic extract from Immich back to AI layer manifests
3. Crowdsource tagging via Immich UI — onboard family as Immich users with tagging access
4. Review corrections and feed back — use dashboard to periodically review and accept family changes
5. Keep an exportable identity/people table — versioned, human-editable (YAML or SQLite)
6. If hitting Immich's limits, consider standalone recognition (InsightFace or DeepFace) later

**Key Insight:** The "ground truth" for family identities will always live in the heads of the oldest family members — not in any software. The project's north star should be making it effortless for them to "imprint" that knowledge. Build a feedback loop: treat Immich as the collaborative interface, make your AI layer "learn" from corrections.

---

## GROK 4 (xAI)

**Initial Reaction:** This is a smart, privacy-first evolution of a personal archive into a living family resource. The biggest opportunity is harnessing Immich's built-in face recognition to avoid reinventing the wheel, while the real challenge lies in making collaborative tagging accessible to non-tech-savvy elders. Feasible and elegant if we prioritize simplicity over custom layers.

**Strengths:**
- Strong self-hosting and data sovereignty foundation — no vendor lock-in
- Modular three-layer architecture allows targeted enhancements without disrupting the flow
- Immich's native face clustering provides out-of-the-box collaborative potential
- Multilingual manifests add cultural relevance for a Taiwanese-American family

**Risks & Weaknesses:**
- Degraded scan quality from 1970s photos could tank face recognition accuracy
- Elders may struggle even with simplified Immich interface
- Over-reliance on Immich ties identity layer too tightly — if Immich breaks, tagging crumbles
- No clear data isolation for face embeddings risks privacy leaks with remote access
- Collaborative edits could introduce inconsistencies without versioning

**Suggested Approach:**
1. Leverage Immich's built-in face recognition as core — enable immediately, let it auto-cluster after JPEG push
2. Store face data in Immich with NAS backups — enhance AI manifests with exported face metadata, mirror embeddings as encrypted files
3. Build family collaboration via Immich sharing + lightweight "elder mode" dashboard — one-tap naming, voice-assisted via browser, shared family device
4. Pilot with 20-30 old photos — measure accuracy against elder knowledge, plan annual exports to avoid lock-in

**Key Insight:** In a Taiwanese-American family archive, face recognition isn't just technical — it's a bridge to oral history. By embedding collaborative tagging as a ritual — perhaps via scheduled virtual "tagging nights" through Cloudflare-secured Immich — you transform the pipeline from passive storage to an interactive cultural artifact.

---

## SYNTHESIS

### Consensus
- **Use Immich's built-in face recognition.** Unanimous: don't add InsightFace/DeepFace/CompreFace at this scale.
- **Identity data must be backed up outside Immich.** All four models say coupling identity data exclusively to Immich is unacceptable.
- **Elder UX is the hardest problem.** The real bottleneck is frictionless input for 70-80 year olds with irreplaceable knowledge.
- **Cloudflare Tunnel + Access is the right access model** for remote family access.
- **Scanned photo quality will degrade recognition accuracy** — plan for more human correction.

### Divergence
- **Separate elder UI vs. Immich-only** — Gemini/GPT say use Immich as the elder interface; Claude/Grok argue for a purpose-built simple tool.
- **Source of truth directionality** — Claude says AI layer registry is canonical (Immich syncs from it); Gemini says family input in Immich is canonical (sync extracts from Immich).
- **Fourth layer vs. extended third** — Gemini proposes a distinct "Identity Layer"; others extend the existing AI layer.

### Blind Spots
- **Immich's face recognition API surface** — no model verified what Immich actually exposes (face crops, bounding boxes, person assignments via API).
- **Conflict resolution** — when two family members disagree about who's in a photo.
- **Age-spanning identity** — same person at age 5 vs. age 50 won't auto-cluster.
- **Audio/voice input** — critical for elders who speak Mandarin/Taiwanese but can't type.

### Recommended Path Forward
1. **Enable Immich's built-in face recognition now.** Zero additional software. Evaluate quality on existing ~200 photos.
2. **Investigate Immich's face/person API.** Verify: can you pull face crops, person assignments, bounding boxes? This determines feasibility.
3. **Create a people registry in the AI layer** — `_ai-layer/people/` with JSON registry. Durable, Immich-independent identity store.
4. **Build the sync loop** — script that pulls Immich face assignments into people registry and pushes confirmed identities back.
5. **Prioritize elder knowledge capture** — get faces in front of elders within weeks. Low-tech fallback: print face crops, sit with elders, write names on paper, digitize later.
6. **Defer custom elder UI decision** until after investigating Immich's face tagging UX on mobile.
