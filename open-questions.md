# Every Branch Archive — Open Questions

**Status:** Decisions needed before implementation begins
**Related:** See `implementation-plan.md` Section 8

---

## Immediate Decisions

These choices affect Phase 1 and should be resolved before starting.

### 1. Domain Name

**Question:** What domain should the archive use?

| Option | Pros | Cons |
|--------|------|------|
| `everybranch.family` | Memorable, matches project name | `.family` TLD less common |
| `[surname].family` | Family-specific | Less distinctive |
| `[surname]-archive.com` | Traditional TLD | Generic |

**Decision:** _______________

---

### 2. Privacy Default

**Question:** Should new content be private or public by default?

| Option | Behavior | Recommended For |
|--------|----------|-----------------|
| **Private by default** | Must explicitly mark content as public | Cautious approach, living family members |
| **Public by default** | Must explicitly mark content as private | Historical focus, deceased ancestors |

**Recommendation:** Private by default for photos of living people; public by default for historical content (pre-1950).

**Decision:** _______________

---

### 3. Photo Storage Organization

**Question:** How should photos be organized in R2 storage?

| Option | Structure | Pros | Cons |
|--------|-----------|------|------|
| **Hash-based** | `/a1/a1b2c3d4...jpg` | Automatic deduplication, verifiable | Not human-browsable |
| **Date-based** | `/1985/03/wedding.jpg` | Human-readable | Manual organization, duplicates possible |
| **Hybrid** | Hash storage + date-based aliases | Best of both | More complexity |

**Recommendation:** Hash-based (plan default). The database provides the human-readable layer.

**Decision:** _______________

---

### 4. Admin Interface Approach

**Question:** What interface for data entry (adding people, tagging photos)?

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **CLI tools** | Python scripts run from terminal | Fast to build, Claude Code friendly | No visual preview |
| **Local web app** | Browser-based, runs locally | Visual, easier photo tagging | More complex to build |
| **Hybrid** | CLI for data, web for viewing | Balanced | Two systems to maintain |

**Recommendation:** Start with CLI tools. Add web interface later if friction is too high.

**Decision:** _______________

---

## Deferred Decisions

These can wait until later phases.

### 5. Elder Interview Format (Phase 4)

**Question:** What format for recording elder interviews?

| Option | Considerations |
|--------|----------------|
| Audio only | Simpler, less intrusive, easier storage |
| Video | Captures expressions, harder to transcribe |
| Audio + notes | Balance of fidelity and usability |

**Decide by:** Before Taiwan trip

---

### 6. Red Book Processing (Phase 5)

**Question:** How to digitize the 2026 red book reprint?

| Option | Considerations |
|--------|----------------|
| OCR | Faster if text is clear; Traditional Chinese OCR quality varies |
| Manual transcription | Slower but accurate; good for handwritten sections |
| Hybrid | OCR first pass, manual correction |

**Decide by:** After receiving the book (April 2026)

---

### 7. Family Collaboration Workflow (Post-V1)

**Question:** If other family members want to contribute data, how?

| Option | Considerations |
|--------|----------------|
| Shared spreadsheet | Low friction, import periodically |
| GitHub access | Technical barrier, but full audit trail |
| Submission form | Web form that queues for review |

**Decide by:** After V1 launch, based on interest

---

## How to Record Decisions

Fill in the **Decision** fields above, then:

1. Update `implementation-plan.md` Section 8 to reflect choices
2. Commit this file with decisions recorded
3. Begin Phase 1 implementation

---

*Created: December 25, 2025*
