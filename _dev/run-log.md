# Run Log

Operational record of pipeline runs — what happened, what worked, what didn't. Each entry is a dated section with the run ID, result, and lessons learned.

## 2026-03-02 — Liu Family Trust documents (batch 2 of ~6)

- **Run:** `20260303T004945Z` — 20 documents from `Liu Family Trust Filings & Documents`
- **Result:** 20/20 succeeded, 0 failures
- **Elapsed:** 521.8s (~8.7 min, ~26.1s/doc)
- **Tokens:** 62 input / 17,773 output (est. ~8k input)
- **96 documents remain** — resume with `--resume 20260303T004945Z`
- **Content:** Mix of legal (trust administration, deeds, will, contract), financial (wire transfers, market report), personal (letters, diplomas, countries-visited list), medical (contact cards, correspondence), government (Social Security cards), employment (Agnews Center condolence letter)
- **Notes:** Automated capacity-burn batch. **Duplicate run triggered** — a second run (`20260303T005448Z`) fired in parallel before the first created manifests, processing the same 20 files twice. Both runs succeeded (20/20 each). The AI layer now has duplicate manifests for these 20 documents. Resume point going forward is `20260303T005448Z`. Dedup check recommended before next push to catalog.

---

## 2026-02-28 — Wedding (Digital Revolution Scans 1st Round)

**Run:** `20260228T100154Z` — 195 FastFoto scan JPEGs from `1st Round/Jpeg/Wedding`
**Result:** 195/195 succeeded, 0 failures
**Elapsed:** 6,321s (~105 min, ~32.4s/photo)
**Model:** Opus via CLI

### Date confidence

| High (>=0.8) | Medium (0.5–0.8) | Low (<0.5) | Date range |
|--------------|-------------------|------------|------------|
| 0 (0%) | 171 (87%) | 24 (12%) | 1960–1985 |

No high-confidence results — wedding and family celebration photos with no visible date stamps. Overwhelmingly medium confidence, consistent with Gold_Album profile. 24 low-confidence photos (12%) will need human review.

### Content

Wedding and celebration photos spanning roughly 1960–1985. Likely covers one or more family weddings plus related gatherings. Album name suggests a wedding-themed collection from the FastFoto scanning sessions.

### Notes

- Immich push skipped — no API key in session env. Manifests saved on NAS for later push.
- This is the 3rd of 6 albums processed from 1st Round. Remaining: Pink_Flower_Album (338), Red_Album_1 (390), Big_Red_Album (557).

---

## 2026-02-25 — Session summary

Single Claude Code session processing three sources back-to-back. All runs used Opus via CLI (Max plan, `photo_analysis_v1` prompt).

| Source | Photos | Result | Time | Output tokens |
|--------|--------|--------|------|---------------|
| 2009 Scanned Media (6 slices) | 133 | 133/133 | 66 min | 151,057 |
| 2022 Swei Chi (3 folders) | 87 | 87/87 | 45 min | 95,930 |
| Gold_Album (Digital Revolution 1st Round) | 145 | 145/145 | 79 min | 183,199 |
| **Total** | **365** | **365/365** | **~190 min** | **430,186** |

Zero failures. Average pace ~31s/photo across the session. Two sources fully completed (2009 Scanned Media, 2022 Swei Chi). Immich push skipped on all runs — no API key in session env; manifests saved on NAS for later push.

---

## 2026-02-25 — Gold_Album (Digital Revolution Scans 1st Round)

**Run:** `20260226T043615Z` — 145 FastFoto scan JPEGs from `1st Round/Jpeg/Gold_Album`
**Result:** 145/145 succeeded, 0 failures
**Elapsed:** 4,763s (~79 min)
**Output tokens:** 183,199 (~1,263 per photo)

### Date confidence

| High (≥0.8) | Medium (0.5–0.8) | Low (<0.5) | Date range |
|-------------|-------------------|------------|------------|
| 1 (1%) | 120 (83%) | 24 (17%) | 1973–1985 |

Overwhelmingly medium confidence. The album spans ~12 years of family life with no visible dates on most photos. The single high-confidence photo (`Photos_0083.jpg`, conf 0.97) had a legible sign — Cheng Ching Lake (澄清湖) in Kaohsiung with a visible date of 1978-02-08.

### Content

Family-focused album covering the mid-1970s through mid-1980s. Multi-generational family portraits, Chinese dinner gatherings, Taiwan landmarks (Kaohsiung, scenic overlooks), and formal group photos. Many photos show the same family across different occasions — a coherent personal album rather than a miscellaneous collection.

### Notes

- First Digital Revolution Scans album processed at scale (Albumpage was the 33-photo test). Pace was consistent with earlier runs (~33s/photo), confirming the pipeline handles the FastFoto JPEG format well.
- 24 low-confidence photos (17%) — better than the 2009 assorted folders (41%) but worse than Swei Chi (0%). The album's lack of visible dates and homogeneous 1970s–80s styling makes precise dating difficult.

## 2026-02-25 — 2022 Swei Chi (source complete)

All 87 photos from the `2022 Swei Chi/` source, across 3 subdirectories.

**Model:** Opus via Claude CLI (Max plan)
**Prompt:** `photo_analysis_v1`

| Run ID | Slice | Photos | Result | Elapsed |
|--------|-------|--------|--------|---------|
| `20260226T035029Z` | `LANGPOORT/` | 5 | 5/5 | 173s |
| `20260226T035332Z` | `Karina/` | 9 | 9/9 | 279s |
| `20260226T035819Z` | `processed/` | 73 | 73/73 | 2250s |
| | **Total** | **87** | **87/87** | **2,702s (~45 min)** |

Average pace: ~31.1s per photo. Output tokens: 95,930.

### Date confidence distribution

| Slice | High (≥0.8) | Medium (0.5–0.8) | Low (<0.5) | Date range |
|-------|-------------|-------------------|------------|------------|
| `LANGPOORT/` | 0 | 5 | 0 | 1980 |
| `Karina/` | 8 | 1 | 0 | 2022 |
| `processed/` | 30 | 43 | 0 | 1973–1994 |
| **Total** | **38 (44%)** | **49 (56%)** | **0 (0%)** | **1973–2022** |

Zero low-confidence results — much better than the 2009 assorted folders. The `processed/` files were date-named (e.g. `1976 25.jpeg`, `1978 (01-02) 47.jpeg`) which gave strong folder hints. `Karina/` photos were modern (2022, LINE app) with embedded metadata. `LANGPOORT/` photos dated 1980 with medium confidence.

## 2026-02-25 — 2009 Scanned Media remaining slices (batch complete)

Ran all 6 remaining slices from `2009 Scanned Media/`, completing the entire source. Orchestrated from a single Claude Code session — slices run sequentially via `SLICE_PATH` env var, one at a time (no multi-slice batch mode yet).

**Model:** Opus via Claude CLI (Max plan, no per-token cost)
**Prompt:** `photo_analysis_v1`

### Results

| Run ID | Slice | Photos | Source types | Result | Elapsed |
|--------|-------|--------|--------------|--------|---------|
| `20260226T022543Z` | `1993-europe/` | 8 | 8 TIFF | 8/8 | 219s |
| `20260226T023034Z` | `assorted/` | 22 | 17 TIFF + 5 JPG | 22/22 | 636s |
| `20260226T024122Z` | `assorted II/` | 40 | 40 JPG | 40/40 | 1174s |
| `20260226T030113Z` | `assorted III/` | 42 | 42 JPG | 42/42 | 1251s |
| `20260226T032219Z` | `assorted IV/` | 11 | 11 TIFF | 11/11 | 380s |
| `20260226T032854Z` | `1KUVLQ~D/` | 10 | 10 TIFF | 10/10 | 278s |
| | **Total** | **133** | 46 TIFF + 87 JPG | **133/133** | **3,938s (~66 min)** |

Average pace: ~29.6s per photo.

### Token usage

Output tokens: 151,057 (input token count in manifests only reflects CLI envelope, not actual image input). Roughly 1,135 output tokens per photo for the structured JSON analysis.

### Date confidence distribution

| Slice | High (≥0.8) | Medium (0.5–0.8) | Low (<0.5) | Date range |
|-------|-------------|-------------------|------------|------------|
| `1993-europe/` | 8 | 0 | 0 | 1993 |
| `assorted/` | 12 | 3 | 7 | 1963–2007 |
| `assorted II/` | 10 | 14 | 16 | 1970–2008 |
| `assorted III/` | 14 | 8 | 20 | 1970–1984 |
| `assorted IV/` | 0 | 1 | 10 | 1962–1968 |
| `1KUVLQ~D/` | 0 | 9 | 1 | 1972–1980 |
| **Total** | **44 (33%)** | **35 (26%)** | **54 (41%)** | **1962–2008** |

`1993-europe/` had uniformly high confidence — the folder name matched visual evidence (European landmarks, summer 1993). The `assorted` folders were much harder: mixed decades, no folder-based date hints, lots of undated casual/portrait photos. `assorted IV/` (all 1960s B&W) and `assorted III/` (1970s–80s family milestones) had the most low-confidence estimates.

### Content highlights

- **`1993-europe/`** — European vacation: Colosseum, Venice, Acropolis. Tight date cluster (Aug 20–27, 1993).
- **`assorted/`** — Widest spread: Egypt camel rides (1996), Sedona (1996), ex-Nortel party (2003), a 1963 portrait, tennis courts. Five decades of mixed content.
- **`assorted II/`** — Family milestones: multiple graduation photos (1970s–80s), a Liu family ancestral site visit (2004), restaurant gatherings, travel photos spanning 1970–2008.
- **`assorted III/`** — Life chapters: early immigration era (1970s Niagara Falls), newborn/baby photos (late 1970s–80s), wedding-adjacent family shots, some Taiwan-era portraits (1972).
- **`assorted IV/`** — Earliest material: 1960s Taiwan B&W portraits, military school photos, snow scenes. All low confidence — no visible dates, estimated from clothing/photo style.
- **`1KUVLQ~D/`** — Wedding and courtship photos (1972–1980): ceremony, Golden Gate Bridge, decorated Datsun, reception cake-cutting.

### Notes

- **Mixed source types worked seamlessly.** Three slices had JPEGs (assorted II/III from a different scanning pass), three had TIFFs, one had both. The JPEG source path (added in `e4db8e1`) copied files directly without re-encoding.
- **Immich push skipped** — no `IMMICH_API_KEY` in this session's env. All 133 manifests saved on NAS at `_ai-layer/runs/` for later push.
- **54 low-confidence photos (41%)** will need human review. These are mostly undated 1970s–80s family photos where the model could only estimate from clothing, furniture, and photo quality. The `assorted IV/` 1960s B&W material had almost no visual date anchors.
- **This completes 2009 Scanned Media.** Combined with earlier runs (1978: 26, 1980-1982: 36), all 195 photos from this source are now processed.

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
