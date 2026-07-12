# Phase 2 Source Re-grounding Checkpoint

**Run date:** 2026-07-12

**Experiment code:** `1149074`

**Private receipt:** `verification_fa138529f7601ab6.json`

**Verdict:** The source-verification mechanism passed its first bounded live
run; Phase 2 remains in progress for content and photo-region adjudication.

## Safety and validation

- The active SMB session used the dedicated `living_archive_ro` identity.
- Server-side ACL audit confirmed read-only access to the MNEME share, denial
  on all other shares, and denial on non-SMB application surfaces.
- The verifier bound opened files to the verified SMB device and rechecked the
  session before writing its receipt.
- The Phase 1 dossier remained byte-identical and mode `0600`.
- The private output directory remained mode `0700`; the receipt is `0600`.
- Runtime contract and Draft 2020-12 schema validation both passed.
- The receipt contains no source paths, source extensions, excerpts, page text,
  crops, or subject labels.
- No model or external provider was called.
- No source, manifest, catalog, synthesis record, people registry, pipeline, or
  Immich state changed.

## Aggregate verification result

| Measure | Result |
|---|---:|
| Explicitly selected originals | 3 |
| Review-level originals | 2 |
| Explicitly approved high-sensitivity originals | 1 |
| Hash-verified originals | 3 |
| Failed verifications | 0 |
| Source mutations detected | 0 |
| PDF document identity anchors | 2 |
| PDF page anchors | 1 |
| Photo region anchors | 0 |
| Claim-ready assets | 0 |
| Accepted claims | 0 |

The low-risk document and photograph established file-level identity. The
smallest exact-text candidate established that an existing Phase 1 page locator
resolves to a real page in the hash-matched original. This does not independently
verify the page's interpreted content.

## Why Phase 2 remains open

- No photo region was fabricated from a machine proposal; a curator must select
  any useful region in the original image.
- The verified page anchor remains locator-only until its content is reviewed.
- No transition sequence, biographical claim, or family-facing hypothesis was
  generated.

The next useful action is to inspect the one anchored page and decide whether
it supports a narrowly worded proposed observation. If a photo is useful, the
curator can then select a source-pixel region without asserting identity.
