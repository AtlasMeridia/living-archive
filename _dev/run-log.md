# Run Log

Operational record of pipeline runs — what happened, what worked, what didn't. Each entry is a dated section with the run ID, result, and lessons learned.

## 2026-02-25 — Albumpage retry (Digital Revolution Scans)

- **Run:** `20260225T092056Z` — 33 FastFoto scan JPEGs from `1st Round/Jpeg/Albumpage`
- **Result:** 31/33 succeeded, 2 timed out (Photo_028, Photo_036 — hit 120s CLI timeout)
- **Elapsed:** 2,317s (~39 min)
- **Fix applied this session:** Stripped `CLAUDECODE` env var from photo pipeline subprocess (`analyze.py`), matching existing pattern in `doc_analyze.py`. Committed as `147e5de`.
- **Previous attempt:** `20260225T074733Z` — 33/33 failed, nested Claude CLI session guard blocked every invocation
- **Immich:** Skipped (no API key in session env), manifests saved on NAS for later push
- **Next:** Retry 2 timed-out photos or move to next album

## 2026-02-19 — Liu Family Trust documents (full corpus)

- **Run:** `20260220T042253Z` — 116 documents, Opus 4.6
- **Result:** 116/116 succeeded, 0 failures
- **Elapsed:** ~43 min across 16 batches of ~20
- **Tokens:** 258k output tokens
- **Notes:** Large docs (up to 420 pages) chunked automatically without issues. Catalog reached 187 assets (121 doc + 66 photo).

## 2026-02-06 — 1980-1982 photos

- **Run:** 36 TIFFs from `2009 Scanned Media/1980-1982/`
- **Result:** 36/36 succeeded
- **Elapsed:** 369.8s

## 2026-02-05 — 1978 photos (first end-to-end run)

- **Run:** 26 TIFFs from `2009 Scanned Media/1978/`
- **Result:** 26/26 succeeded
- **Notes:** First successful end-to-end pipeline test. Established confidence-based Immich album routing.
