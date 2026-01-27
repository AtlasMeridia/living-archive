# Open Questions

Consolidated list of decisions needed for the Living Archive project. Updated 2026-01-26.

For historical context on earlier open questions, see `docs/liu-family-archive/open-questions.md`.

---

## Infrastructure

### 1. Where does inference actually run?

Options:
- EllisAgent scripts that SSH to NAS to read photos
- Scripts running directly on NAS
- Interactive Claude Desktop sessions (exploration-first)
- Some combination

Considerations: NAS has limited compute. EllisAgent has Claude Code. Photos are large (TIFFs).

### 2. Is batch inference the right model?

The spec assumes: scan all 5,257 photos → generate manifest → sync to Immich.

Alternative: Start with interactive exploration to build intuition, let family comments inform dating, then systematize.

---

## Workflow

### 3. How do family comments feed back into dating?

Immich supports comments on photos. How do family members' contributions (identifications, date corrections, context) flow back into the AI layer?

Options:
- Manual review of comments → update manifest
- Structured feedback form outside Immich
- Immich comments as ground truth, AI layer learns from them

### 4. What's the review workflow for low-confidence dates?

For photos where AI confidence is 0.5-0.8:
- Immich album called "Needs Review"?
- Export to spreadsheet for batch decisions?
- Flag in manifest, surface in custom UI?

---

## Prioritization

### 5. What problem are we solving first?

Options:
- **Correct sorting in Immich** — Immediate value, photos appear in timeline correctly
- **Methodology documentation** — Public content for kennyliu.io, "how to do a family archive"
- **Reusable system** — Engineering a tool others could use

These aren't mutually exclusive but they sequence differently.

---

## Access

### 6. Family user accounts: individual or shared?

Immich supports multiple users. Options:
- Individual accounts per family member (tracks who commented what)
- Single shared "Liu Family" account (simpler)
- Admin (Kenny) + one shared family account

### 7. Photo contribution workflow for family uploads?

If family members have photos to add:
- Upload directly to Immich shared album?
- Separate upload folder on NAS, reviewed before import?
- Email/messaging to Kenny for manual ingest?

---

## Content (Carried Forward)

### 8. Privacy default for published content

What's the default visibility for people in photos?
- Opt-in (explicit consent required)
- Opt-out (published unless requested otherwise)
- Deceased vs living distinction?

Needs adaptation to Immich model (Cloudflare Access controls who sees anything).

### 9. Elder interview format

For capturing oral history (especially before Taiwan trip):
- Audio only (lower friction)
- Video (richer but more setup)
- Hybrid (audio default, video for key sessions)

### 10. Red book (族譜) processing

The traditional genealogy book requires OCR of traditional Chinese:
- Professional OCR service
- dots.ocr or similar tool
- Manual transcription

Defer decision until Phase 5 (April 2026+), but worth noting.

---

## Answered Questions (Reference)

These were open but have been resolved:

| Question | Answer | Date |
|----------|--------|------|
| Domain name | `archives.kennyliu.io` for Immich | 2026-01-25 |
| Photo storage | NAS external library in Immich | 2026-01-26 |
| Admin interface | Immich web UI | 2026-01-26 |
| Blog location | `kennyliu.io/notes` with `living-archive` tag | 2026-01-24 |

---

*Last updated: 2026-01-26*
