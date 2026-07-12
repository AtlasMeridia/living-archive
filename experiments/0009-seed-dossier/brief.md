# Experiment 0009: Archive-First Seed Dossier

## Question

Can Living Archive assemble a useful, evidence-addressable research packet for
one person and period from its existing derived data before asking a family
member to re-enter basic biographical information?

The first locked pilot is supplied privately at runtime:

- **Subject:** one private deceased adult
- **Period:** one bounded 10-15 year interval
- **Research question:** What is the best-supported sequence of places,
  households, and major family, work, and migration transitions for the pilot
  person during the selected interval?

## Why This Is an Experiment

The current catalog, run manifests, extracted text, people registry, and legacy
synthesis database can locate relevant material, but none of them is historical
truth. The unknown is whether those imperfect layers provide enough recall to
bootstrap a grounded investigation without turning the researcher into a data
entry interface.

This experiment tests an archive-first sequence:

```text
derived locators -> candidate evidence -> exact source locators
                 -> provisional research view -> high-value questions
```

It does not build the family workbench, publish a biography, call a model, or
change the ingestion pipeline.

## Architecture Constraints

1. All code remains under `experiments/0009-seed-dossier/`.
2. No imports from the production `src/` package.
3. Source files, manifests, catalogs, synthesis databases, people registries,
   and Immich are read-only inputs.
4. Catalog and legacy synthesis records are locators only. They have zero
   independent evidentiary weight.
5. A run-manifest statement remains a machine proposal unless it resolves to an
   exact page, passage, or image region in original evidence.
6. Outputs stay in the experiment's ignored `runs/private/` directory.
7. Every output is marked `visibility: curator`, `read_only: true`, and
   `human_verified: false`.
8. Phase 1 never stores source excerpts. The dossier records restricted
   locators and sensitivity metadata instead.
9. No original file is required for the discovery phase. Verification against
   originals is a later gate and must fail visibly when storage is unavailable.

## Inputs

- `data/catalog.db`
- `data/synthesis.db`, when present
- `data/documents/runs/*/manifests/*.json`
- `data/documents/runs/*/extracted-text/*.txt`
- `data/photos/runs/*/manifests/*.json`
- `data/people/registry.json`, when present

## Invocation

Supply the private subject label and reviewed name forms at runtime; do not add
them to tracked experiment files:

```text
python experiments/0009-seed-dossier/src/seed_dossier.py \
  --project-root /path/to/living-archive \
  --subject "PRIVATE SUBJECT" \
  --alias "PRIVATE ALIAS" \
  --start-year YYYY \
  --end-year YYYY
```

The command refuses a missing project root, writes only beneath
`runs/private/`, and does not replace an existing dossier unless explicitly
requested.

## Output Contract

The private `SeedDossier` contains:

- snapshot fingerprints and the repository revision;
- the operator-supplied subject label, aliases, and bounded period;
- candidate assets with every discovery reason retained;
- exact extracted-text name mentions with page and character offsets;
- machine date proposals and legacy timeline signals, clearly labeled;
- sensitivity and coverage summaries;
- contradictions and unresolved questions;
- no accepted biographical claims.

The JSON Schema at `seed-dossier.schema.json` defines the stable top-level
contract for this experiment. Nested candidate payloads may expand during the
experiment but cannot weaken the authority or visibility rules above.

## Phases

### Phase 0 - Synthetic contract

Build the standalone generator and test it with synthetic catalog, synthesis,
manifest, and extracted-text fixtures.

**Gate:** Tests prove candidate union, deduplication, page/offset locators,
confidence labeling, sensitivity defaults, contradiction retention, and no
input mutation.

### Phase 1 - Private pilot discovery packet

Run the generator against the current derived data using the known English,
romanized, and Traditional Chinese name forms.

**Gate:** The generator produces a private dossier with reproducible snapshot
identity, at least one byte-faithful extracted-text locator, no source excerpts, and a
summary that can be inspected without exposing private filenames or text.

### Phase 2 - Source re-grounding

After MNEME access and the security prerequisite are restored, verify selected
candidate documents and photos against originals and add durable page/region
anchors.

**Gate:** Every displayed material claim resolves to original evidence. Legacy
synthesis supports no claim.

### Phase 3 - Human-value evaluation

Present the evidence-backed packet and its generated research queue to the
curator.

**Gate:** Routine facts already recoverable from the archive generate no human
questions. Human prompts are limited to contradictions, uncertain identities,
or memories with high information value.

## Success Criteria

| Area | Gate |
|---|---|
| Safety | Zero writes to sources, manifests, catalogs, synthesis, or Immich |
| Provenance | Every candidate retains all discovery reasons and snapshot IDs |
| Evidence | Every text observation has a resolvable page and character range |
| Authority | No locator-only record is emitted as an accepted claim |
| Privacy | All output is curator-only; Phase 1 stores no source excerpts |
| Reproducibility | Same inputs and options produce identical canonical content apart from generation time |
| Human burden | No basic biographical interview is required to create the initial packet |

## Non-Goals

- Training or fine-tuning a model
- Naming face clusters automatically
- Publishing family-facing hypotheses
- Replacing Immich
- Migrating manifests or the catalog
- Repairing the NAS mount or rotating credentials
- Treating the first dossier as a biography

## Rollback

Delete the generated dossier or the entire experiment directory. No production
consumer points at this output and no source or durable human record changes.
