# Experiment 0001 — Opus 4.6 vs Sonnet 4.6: Comparison

**Date**: 2026-02-19
**Status**: Complete

## Overview

| Metric | Sonnet 4.6 | Opus 4.6 |
|--------|-----------|----------|
| Documents processed | 5/5 | 5/5 |
| Total time | 153.0s | 114.7s |
| Avg time/doc | 30.6s | 22.9s |
| Total output tokens | 7,721 | 5,415 |
| Avg output tokens/doc | 1,544 | 1,083 |
| Errors | 0 | 0 |

Notable: Opus was **25% faster** and used **30% fewer output tokens** than Sonnet. Input tokens reported as 3 per document for both (CLI envelope under-reports input tokens on Max plan).

---

## Document-by-Document Comparison

### 1. Countries Visited (personal artifact, 1pp, 387 chars)

| Field | Sonnet | Opus |
|-------|--------|------|
| document_type | personal/letter | personal/letter |
| title | "Countries Visited — Personal Travel List" | "Handwritten List of Countries Visited" |
| date | 1990 (conf 0.2) | 2000 (conf 0.1) |
| quality | poor | fair |
| output_tokens | 1,386 | 1,345 |
| elapsed | 28.5s | 26.8s |

**Summary comparison**: Both enumerate countries by continent. Opus lists more specific destinations (adds Laos, Singapore, Hong Kong, Nepal, Turkey, Holland, Belgium, Switzerland, Hungary, Slovakia, Finland, South Africa, Chile, Grand Cayman, Bahamas, Puerto Rico, Hawaii, Alaska). Sonnet includes Scandinavia as a group; Opus breaks it into individual countries. Opus provides an approximate count ("45–50 destinations").

**Sensitivity**: Both correct (all false).

**Tags**: Sonnet adds "handwritten"; Opus uses "international" instead.

**Assessment**: Opus extracts more detail from the same text — more individual countries named, higher specificity. Opus rates quality as "fair" vs Sonnet's "poor", suggesting it has a different threshold or more confidence in the content.

---

### 2. Will of Feng Kuang Liu (legal/sensitive, 4pp, 4372 chars)

| Field | Sonnet | Opus |
|-------|--------|------|
| document_type | legal/will | legal/will |
| title | "Last Will and Testament of Feng Kuang Liu" | "Last Will and Testament of Feng Kuang Liu" |
| date | 2007-05-10 (conf 0.95) | 2007-05-10 (conf 0.92) |
| key_people | 4 (exact match) | 4 (exact match) |
| key_dates | 2 (exact match) | 2 (exact match) |
| quality | fair | good |
| output_tokens | 1,246 | 950 |
| elapsed | 24.9s | 21.0s |

**Summary comparison**: Both capture the core facts: pour-over will, "A" Trust, executor chain. Sonnet notes "unmarried with two adult children" and that the testator was "a resident of Santa Clara County." Opus is more concise but still covers the essential details. Both mention the fiancée, daughter, and son as executor chain.

**Chinese summary**: Sonnet transliterates names differently (劉鳳光 vs 劉豐光; 劉佩玲 vs 劉沛伶; 蔡美良 vs 蔡美良). Both are plausible romanization-to-Chinese mappings.

**Sensitivity**: Both correct (all false — the will itself isn't sensitive in the SSN/financial/medical sense).

**Tags**: Sonnet adds "property"; Opus does not. Both have "legal", "will", "estate-planning", "trust".

**Assessment**: Near-identical quality. Opus is more concise (24% fewer tokens) and rates quality higher ("good" vs "fair").

---

### 3. Quitclaim Deed (legal, 2pp, 294 chars)

| Field | Sonnet | Opus |
|-------|--------|------|
| document_type | legal/deed | legal/deed |
| title | "Quitclaim Deed — Santa Clara County" | "Quitclaim Deed — Santa Clara County Property" |
| date | 2010-04-14 (conf 0.85) | 2010-04-14 (conf 0.7) |
| key_dates | 2 (exact match) | 2 (exact match) |
| quality | poor | poor |
| output_tokens | 1,198 | 1,016 |
| elapsed | 29.6s | 22.8s |
| has_financial | false | **true** |

**Summary comparison**: Both correctly identify that only the mailing envelope was extracted, not the deed contents. Sonnet mentions "ZIP code 94022 (Los Altos area)" — a specific detail. Opus mentions "70 West Hedding Street" (the county government center address) — a different specific detail.

**Sensitivity divergence**: Opus flags `has_financial: true` on a property deed. Sonnet does not. A quitclaim deed is a property transfer instrument, so Opus's flag is arguably more conservative and correct.

**Tags**: Sonnet is more specific: adds "quitclaim", "real-estate", "california", "santa-clara-county". Opus is more general: "legal", "property", "deed", "estate-planning".

**Assessment**: Sonnet extracts more detailed metadata (ZIP, more tags). Opus is more conservative on sensitivity (flags financial for a property deed). Both correctly note the extraction limitation.

---

### 4. Investment Record (financial, 2pp, 2684 chars)

| Field | Sonnet | Opus |
|-------|--------|------|
| document_type | financial/statement | financial/statement |
| title | Similar (both mention 1970–1979) | Similar (both mention 1970–1979) |
| date | 1970-08-29 (conf 0.85) | 1970-08-29 (conf 0.7) |
| key_dates count | 15 | 20 |
| quality | poor | poor |
| output_tokens | 2,614 | 1,134 |
| elapsed | 44.0s | 22.6s |
| has_financial | true | true |

**Summary comparison**: Both identify the stock ledger and list company names. Opus adds "Columbia Gas" and "Gulf Research & Chemical" — companies Sonnet missed. Opus also provides transaction value ranges ("roughly $200 to $5,000 per trade") which Sonnet does not. Sonnet provides more explanation of the extraction quality issue.

**Key dates**: Opus extracts 20 dates vs Sonnet's 15. Opus captures more transaction dates from the ledger. Some date formats differ (Sonnet: "1973-03-00"; Opus: "1973-01-01") — both are approximations from degraded text.

**Tags**: Sonnet adds "tax"; Opus does not. Otherwise similar.

**Token efficiency**: Opus used **57% fewer output tokens** (1,134 vs 2,614) for comparable or better content — the largest efficiency gap in the test set.

**Assessment**: Opus wins on completeness (more companies, more dates, value ranges) while using far fewer tokens. Sonnet is more verbose without adding proportional value.

---

### 5. HR Letter / Meichu Liu (employment/medical, 1pp, 1739 chars)

| Field | Sonnet | Opus |
|-------|--------|------|
| document_type | employment/correspondence | employment/correspondence |
| title | Both descriptive, Opus is longer | Both descriptive, Opus is longer |
| date | 2004-06-16 (conf 0.99) | 2004-06-16 (conf 0.95) |
| key_people | 5 | 4 |
| quality | fair | fair |
| output_tokens | 1,277 | 970 |
| elapsed | 25.9s | 21.5s |
| has_financial | true | true |

**Key people divergence**: Sonnet includes "Arnold Schwarzenegger" (who appears on the letter as the sitting Governor of California — his name is on the letterhead). Opus does not include him. This is a judgment call: Schwarzenegger is on the letterhead but is not a party to the correspondence.

**Summary comparison**: Both capture the essential content. Opus adds the detail that "death benefits and retirement contribution refunds will be handled separately by other agencies" — a fact Sonnet does not mention. Sonnet notes the letter "expressing condolences" — both capture this.

**Chinese summary**: Opus provides a more detailed Chinese summary, mentioning that Meichu "was beloved by colleagues" (深受同事愛戴).

**Tags**: Sonnet adds "personal", "estate-planning". Opus adds "financial", "california", "state-government".

**Assessment**: Close to parity. Opus makes a better judgment call on Schwarzenegger (letterhead governor shouldn't be a key_people entry). Opus captures an additional procedural detail about separate benefit processing.

---

## Aggregate Analysis

### Quality

| Dimension | Sonnet edge | Opus edge | Tie |
|-----------|-------------|-----------|-----|
| document_type | — | — | 5/5 identical |
| date accuracy | — | — | 5/5 identical dates |
| date_confidence | Higher (avg 0.77) | Lower (avg 0.67) | — |
| key_people | +1 (Schwarzenegger) | Better judgment | Depends on standard |
| key_dates | — | +5 more dates | — |
| summary detail | — | More specific facts | — |
| sensitivity | — | +1 flag (deed) | 4/5 |
| quality self-rating | — | Rates higher | Subjective |
| tag specificity | More tags | — | — |

### Efficiency

| Metric | Sonnet | Opus | Opus advantage |
|--------|--------|------|----------------|
| Total time | 153.0s | 114.7s | **25% faster** |
| Total output tokens | 7,721 | 5,415 | **30% fewer** |
| Avg tokens/doc | 1,544 | 1,083 | — |
| Largest gap | 2,614 (investment) | 1,134 (investment) | 57% fewer |

### Token Cost (Max Plan)

Both models are covered by the Max plan subscription ($200/month). At this usage level, the per-token cost is effectively zero. On the API:
- Sonnet: $3/M input, $15/M output
- Opus: $15/M input, $75/M output

For the 5-doc test (assuming ~2,000 input tokens per doc which the CLI underreports):
- Sonnet API cost: ~$0.03 input + ~$0.12 output = **~$0.15**
- Opus API cost: ~$0.15 input + ~$0.41 output = **~$0.56**

At scale (116 remaining docs), estimated API-equivalent costs:
- Sonnet: ~$3.50
- Opus: ~$13.00

---

## Verdict

**Opus 4.6 is the better model for this task**, with caveats:

1. **Quality**: Opus extracts more detail (more dates, more countries, transaction values) while being more concise. It makes better judgment calls (Schwarzenegger exclusion, property deed sensitivity flag). Document type classification is identical.

2. **Efficiency**: Opus is faster (25%) and more token-efficient (30% fewer output tokens). This is the opposite of the typical expectation that larger models are slower and more verbose.

3. **Cost**: On Max plan, both are free. On API pricing, Opus would cost ~4x more — but the absolute cost is still low ($13 vs $3.50 for all 116 docs).

4. **Recommendation**: Use **Opus for the remaining 116 documents**. The quality advantage is real (better extraction from degraded text, better judgment on edge cases), the speed is better, and the cost is covered by the subscription.

5. **Caveat**: This is a 5-document sample. The differences are consistent but small. For budget-constrained API usage, Sonnet is perfectly adequate — the quality gap is not large enough to justify 4x API cost.
