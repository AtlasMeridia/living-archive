# Phase 1 Private Pilot Summary

**Run date:** 2026-07-11

**Experiment code:** `674db49`

**Derived-data project revision:** `dc9698a` with pre-existing local changes

**Verdict:** Phase 1 discovery gate passed; source re-grounding remains blocked

## Safety and validation

- Experiment tests on ATLASM: 16 passed, including Draft 2020-12 validation.
- Existing production tests: 59 passed.
- Runtime contract and committed JSON Schema both validated the private dossier.
- Derived input fingerprints matched before, during, and after generation.
- Output directory mode: `0700`; output file mode: `0600`.
- No source excerpts were stored.
- No model or external provider was called.
- No source, manifest, catalog, synthesis, people-registry, pipeline, or Immich
  state changed.
- The authoritative main worktree retained its exact pre-run status.

## Aggregate discovery result

| Measure | Result |
|---|---:|
| Candidate assets | 67 |
| Candidate documents | 64 |
| Candidate photos | 3 |
| Assets with byte-addressable extracted-text mentions | 47 |
| Exact extracted-text mention records | 445 |
| Locator-only assets | 6 |
| Machine-proposal-only assets | 14 |
| High-sensitivity assets | 63 |
| Review-required assets without a high flag | 4 |
| Grounded timeline candidates | 0 |
| Unanchored in-period date signals | 148 |
| Accepted claims | 0 |
| Verified originals | 0 |
| Named people-registry matches | 0 |
| Generated research questions | 4 |

The generated questions cover missing source anchors, privacy review,
locator-only candidates, and weak photo identity.

## Fail-closed findings

The reader skipped or downgraded historical artifacts that could not meet the
new identity and locator contract:

- 72 extracted-text artifacts lacked page headers.
- 5 manifests contained invalid SHA-256 identity values.
- 1 catalog row contained an invalid SHA-256 value.
- 1 legacy synthesis link contained an invalid SHA-256 value.

These are coverage gaps, not accepted evidence. The packet retains warnings but
does not promote affected material into exact evidence or subject history.

## Interpretation

The archive can bootstrap a substantial research packet without asking the
curator to re-enter basic biography. The previous interview-first approach is
therefore rejected for routine facts.

The packet is not family-ready. Most candidate material is sensitive, photo
recall remains limited to manifest mentions, no people-registry identity is
available, and all dates remain unanchored signals rather than claims about the
subject.

## Next gate

Phase 2 must re-ground a deliberately selected low-risk subset in original PDFs
and photographs, add page or image-region evidence for actual propositions,
and produce the first claim-backed transition sequence. It remains blocked
until original storage is available and the known credential-logging exposure
has been remediated.
