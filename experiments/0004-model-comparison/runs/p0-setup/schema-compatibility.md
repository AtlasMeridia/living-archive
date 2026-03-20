# Schema Compatibility Report

## Photo Analysis (14 fields)

Both Claude and GPT return all 14 fields with valid types.

| Field | Claude | GPT | Notes |
|-------|--------|-----|-------|
| date_estimate | "1978-12" | "1991" | Different estimates — expected |
| date_precision | "month" | "year" | Claude more precise |
| date_confidence | 0.6 | 0.45 | Both within range |
| date_reasoning | string | string | OK |
| description_en | string | string | OK |
| description_zh | string | string | OK |
| people_count | 4 | 4 | Agree |
| people_notes | string | string | OK |
| location_estimate | string | string | OK |
| location_confidence | float | float | OK |
| tags | list[str] | list[str] | OK |
| condition_notes | str/null | str/null | OK |
| ocr_text | str/null | str/null | OK |
| is_document | bool | bool | OK |

## Document Analysis (12 fields)

Both return all 12 fields. Sensitivity is a nested object with 3 bool fields.

| Field | Claude | GPT | Notes |
|-------|--------|-----|-------|
| document_type | "personal/certificate" | "personal/certificate" | Agree |
| title | string | string | OK |
| date | string | string | OK |
| date_confidence | float | float | OK |
| summary_en | string | string | OK |
| summary_zh | string | string | OK |
| key_people | list[str] | list[str] | OK |
| key_dates | list[str] | list[str] | OK |
| sensitivity | {3 bools} | {3 bools} | OK |
| tags | list[str] | list[str] | OK |
| language | string | string | OK |
| quality | string | string | OK |

## Token Usage

| Test | Claude tokens | GPT tokens |
|------|-------------|-----------|
| Photo | 5 + 1,342 | 18,012 + 483 |
| Document | 3 + 671 | 17,838 + 642 |

GPT reports much higher input tokens (image encoding); Claude CLI reports minimal input tokens (likely not counting image).

## Verdict

**PASS** — Both CLIs produce schema-valid JSON for both content types. Ready for full-corpus processing.
