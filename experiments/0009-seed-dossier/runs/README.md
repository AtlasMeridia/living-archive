# Run Artifacts

Generated family-specific dossiers do not belong in Git. The generator writes
only to this experiment's ignored, permission-restricted `runs/private/`
directory.

This directory may contain aggregate, redacted phase reports only. Reports must
not include source filenames, excerpts, addresses, identifiers, or other private
family material.

Phase 2 receipts are append-only overlays on the immutable Phase 1 dossier.
They retain hashes and privacy-safe locator references but never source paths,
excerpts, page text, crops, subject labels, or accepted claims.
