# Living Archive Architecture

Infrastructure documentation for the Living Archive project.

## Three-Machine Topology

| Machine | Hostname | Role | Access |
|---------|----------|------|--------|
| **NAS (DS923+)** | `mneme` | Storage + Immich runtime | SSH, Tailscale |
| **EllisAgent (M3 Pro)** | `ellis-mbp` | Execution, scripts, Claude Code | Local, Tailscale |
| **Atlas (M4 Max)** | `atlas` | Strategy, Claude Desktop | Local, Tailscale |

## Data Flow

```
[Scanned Photos]
    → NAS: /volume1/MNEME/05_PROJECTS/Living Archive Media/
    → Immich (read-only external library)
    → AI Layer: /volume1/MNEME/04_MEDIA/Photo/Family/_ai-layer/
    → Immich API (date metadata sync)
    → Family Access: archives.kennyliu.io (Cloudflare Tunnel)

[Methodology Content]
    → Obsidian: 10 AEON/RENDER/GHOST/drafts/
    → Ghost API: kennyliu.io/notes (tagged living-archive)
```

## Code vs Data Separation

| What | Where | Why |
|------|-------|-----|
| Source photos | NAS `/volume1/MNEME/05_PROJECTS/Living Archive Media/` | Canonical, never modified |
| AI manifests/outputs | NAS `_ai-layer/` | Regeneratable, lives with data |
| Inference scripts | Repo `src/ai_layer/` | Version controlled, testable |
| Methodology docs | Repo `docs/methodology/` | Public-facing content source |
| Working notes | Obsidian `10 AEON/MANIFOLD/Active/living-archive.md` | Transient state |

## Access Patterns

**Kenny (admin):**
- Tailscale → `http://mneme:2283` for Immich admin
- SSH → `mneme_admin@mneme.local` for NAS operations
- EllisAgent runs scripts that SSH to NAS

**Family (view/comment):**
- `https://archives.kennyliu.io` → Cloudflare Access (email OTP) → Immich

## Key Paths Reference

```
# NAS
/volume1/MNEME/05_PROJECTS/Living Archive Media/   # Source photos
/volume1/MNEME/04_MEDIA/Photo/Family/_ai-layer/    # AI inference layer
/volume1/docker/immich/                            # Immich installation

# EllisAgent
~/Projects/living-archive/                         # This repo
~/.config/living-archive/immich-api-key           # Credentials (not in repo)

# Obsidian (synced via Dropbox)
10 AEON/MANIFOLD/Active/living-archive.md         # Working thread
10 AEON/_CHANNEL/from-web/                        # Handoffs to Local Claude
```

## Architectural Principles

These are captured in AutoMem but documented here for reference:

1. **Data/AI layer separation**: Source photos at full fidelity (TIFF, PDF) are never modified. AI layer contains extracted text, structured metadata, cross-references — all regeneratable as better models emerge.

2. **Confidence-based automation**: AI dating uses thresholds:
   - ≥0.8: Auto-apply to Immich
   - 0.5-0.8: Flag for human review
   - <0.5: Mark as undated

3. **Hybrid access model**: Tailscale for admin (technical users), Cloudflare Tunnel + Access for family (email OTP, minimal friction).

4. **Quarterly reindex**: AI manifests are versioned per inference run. Plan to reindex as models improve.

---

*Last updated: 2026-01-26*
