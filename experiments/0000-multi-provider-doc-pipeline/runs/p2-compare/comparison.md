# Provider Comparison Report

**Date**: 2026-02-18
**Test set**: 18 documents, 151 pages

## Summary Table

| Metric | Claude CLI | Codex CLI | Ollama (qwen3:32b) |
|--------|-----------|-----------|-------------------|
| doc_type Match | 78% (14/18) | 78% (14/18) | 28% (5/18) |
| Sensitivity Recall | 100% | 100% | 86% |
| Sensitivity FN | 0 | 0 | 3 |
| Sensitivity Precision | 98% | 90% | 93% |
| Date Exact | 11/18 | 14/18 | 7/18 |
| People F1 (avg) | 36% | 46% | 10% |
| Tags F1 (avg) | 35% | 14% | 14% |
| Avg Time/Doc | 19.7s | 37.7s | 111.8s |
| P95 Time/Doc | 25.0s | 61.3s | 206.3s |
| Total Time | 354.2s | 678.3s | 2013.0s |

## Quality Gates

- **claude**: doc_type >= 80%: FAIL (78%), sensitivity FN = 0: PASS (0FN) -> **FAIL**
- **codex**: doc_type >= 80%: FAIL (78%), sensitivity FN = 0: PASS (0FN) -> **FAIL**
- **ollama**: doc_type >= 80%: FAIL (28%), sensitivity FN = 0: FAIL (3FN) -> **FAIL**

## Document Type Mismatches

### claude
- `0d2eaf1ef095`: ground truth `personal/invitation` vs predicted `personal/certificate`
- `8ad09e2eca3f`: ground truth `employment/records` vs predicted `employment/correspondence`
- `e28810d04c65`: ground truth `legal/litigation` vs predicted `legal/contract`
- `077159dc446d`: ground truth `financial/insurance` vs predicted `financial/statement`

### codex
- `0d2eaf1ef095`: ground truth `personal/invitation` vs predicted `personal/letter`
- `8ad09e2eca3f`: ground truth `employment/records` vs predicted `employment/correspondence`
- `e28810d04c65`: ground truth `legal/litigation` vs predicted `financial/statement`
- `077159dc446d`: ground truth `financial/insurance` vs predicted `financial/statement`

### ollama
- `191e25b99dbb`: ground truth `personal/certificate` vs predicted `death_certificate`
- `ac9080ef8a79`: ground truth `personal/letter` vs predicted `personal/memorial`
- `0d2eaf1ef095`: ground truth `personal/invitation` vs predicted `personal/memorial`
- `8ad09e2eca3f`: ground truth `employment/records` vs predicted `email_transcript`
- `e28810d04c65`: ground truth `legal/litigation` vs predicted `Real Estate Transaction & Financial Records`
- `33c13901edc9`: ground truth `financial/statement` vs predicted `Mixed Financial and Healthcare Documents`
- `40b0a7f5a982`: ground truth `government/immigration` vs predicted `Immigration and Financial Documents`
- `9bebd08ebcdd`: ground truth `legal/contract` vs predicted `California Real Estate Purchase Agreement Addendum`
- `7bd2ccac29b5`: ground truth `financial/tax-return` vs predicted `Security Transaction Report & Tax Instructions`
- `2f0b8ac56576`: ground truth `legal/trust` vs predicted `信托法律纠纷`
- `f3ed4d4da292`: ground truth `medical/correspondence` vs predicted `Privacy Statement and Conditions of Admission`
- `077159dc446d`: ground truth `financial/insurance` vs predicted `Product Comparison`
- `09192c83a93f`: ground truth `legal/deed` vs predicted `Title Insurance Policy`


## Sensitivity False Negatives

### claude: None

### codex: None

### ollama
- `9bebd08ebcdd` (Weston Dr Sales Contract): missed `has_financial`
- `7bd2ccac29b5` (Liu Estate K-1 USO Fund LP): missed `has_ssn`
- `09192c83a93f` (Weston Dr Deed transfer to Trust): missed `has_financial`

## Analysis

### Ground Truth Issues

Three of the four mismatches shared by Claude and Codex involve debatable ground truth labels:

1. **`personal/invitation`** (wedding invitation): This category is NOT in the prompt's controlled vocabulary. The prompt defines `personal/letter`, `personal/certificate`, `personal/memorial`. Both providers reasonably chose the closest available category. If we accept any `personal/*` subcategory as a match, both providers hit 83%.

2. **`employment/records` vs `employment/correspondence`**: The retirement email notifications are both records and correspondence. This is a borderline case.

3. **`financial/insurance` vs `financial/statement`**: The Marquis Diamond docs include GIA reports, appraisals, AND insurance records. `financial/statement` is defensible.

4. **`legal/litigation`**: This is a legitimate miss — both providers classified the mobile home park court case differently.

### Adjusted Scores (accepting borderline matches)

If we treat (1) as a ground truth issue and (2) as a borderline match:
- **Claude**: 16/18 (89%) — PASS
- **Codex**: 16/18 (89%) — PASS
- **Ollama**: still 7/18 at best — FAIL

### Ollama Failure Pattern

Ollama (qwen3:32b) fundamentally fails to follow the controlled vocabulary:
- Uses free-form descriptions instead of category/subcategory format
- Outputs in Simplified Chinese instead of English for some types
- Misses sensitivity flags on financial documents
- 5.7x slower than Claude, 3x slower than Codex

### Provider Verdict

| Provider | Classification | Safety | Speed | Verdict |
|----------|---------------|--------|-------|---------|
| Claude CLI | 78% strict / 89% adjusted | 0 FN, 100% recall | 19.7s avg | **conditionally-viable** |
| Codex CLI | 78% strict / 89% adjusted | 0 FN, 100% recall | 37.7s avg | **conditionally-viable** |
| Ollama | 28% | 3 FN, 86% recall | 111.8s avg | **not-viable** |

### Recommendations

1. **Use Claude CLI as primary provider** — fastest, zero safety misses, best tag overlap
2. **Codex CLI is a viable backup** — better date matching and people extraction, but 2x slower
3. **Drop Ollama** — cannot reliably follow the controlled vocabulary or detect sensitive content
4. **Update the category vocabulary** — add `personal/invitation`, `legal/litigation` to the prompt to reduce ambiguity

