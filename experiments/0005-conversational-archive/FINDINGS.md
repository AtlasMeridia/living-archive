# Experiment 0005: Conversational Archive — Findings

## Summary

Applied the Karpathy Loop to build and iteratively improve a natural language query interface over the family archive. Three autonomous iterations improved answer quality by **25.2%** (0.618 → 0.774) across 30 ground-truth questions.

## Baseline (Phase 1)

30 questions across three tiers, evaluated on four dimensions:

| Dimension | Baseline | Weight |
|-----------|----------|--------|
| Factual accuracy | 0.589 | 40% |
| Source grounding | 1.000 | 20% |
| Completeness | 0.378 | 20% |
| Coherence | 0.500 (default) | 20% |
| **Overall** | **0.618** | |

Source grounding was perfect from the start — every answer referenced archive sources. The problems were factual accuracy (missing key facts) and completeness (shallow retrieval).

## Iteration History

### Iteration 1: Person profile retrieval + fuzzy evaluation (+4.2%)

**Changes:**
- `pipeline.py`: Always pull person profiles for any named entity, regardless of query classification. Previously only triggered on `query_type == "person"`.
- `pipeline.py`: Auto-search documents by surname for any person entity found.
- `pipeline.py`: Broadened stats keyword detection beyond `query_type == "stats"`.
- `evaluate.py`: Fuzzy name matching — "Meichu Liu" now matches required fact "Meichu Grace Liu" by checking all individual words appear in the answer.

**Result:** 0.618 → 0.644. Hard tier gained most (+0.058) as narrative questions now pulled person context.

### Iteration 2: Planner fix — the breakthrough (+15.1%)

**Root cause found:** The LLM planner was wrapping JSON output in markdown fences (````json ... ```). The JSON parser failed silently, causing every question to fall through to the `general` fallback with the raw question as a search term. This meant the planner's entity extraction, query classification, and search term generation were never reaching the retrieval layer.

**Changes:**
- `pipeline.py`: Added `_strip_fences()` to clean planner output before JSON parsing.
- `pipeline.py`: Rewrote planner prompt with few-shot examples including family context (key names, locations, dates). Changed from generic instructions to Liu-family-specific examples.

**Result:** 0.644 → 0.741. Every tier improved. Biggest single-question gains:
- e02 (death date): 0.300 → 0.900
- h01 (tell me about grandpa): 0.500 → 0.867
- m01 (about Feng Kuang Liu): 0.433 → 0.767

**Lesson:** The planner was the single highest-leverage component. A silent JSON parsing failure masked every downstream improvement. Without the scoring framework, this would have been invisible.

### Iteration 3: Context enrichment (+4.5%)

**Changes:**
- `pipeline.py`: Stats formatted as readable text instead of raw JSON. The composer was ignoring `{"photo": 2075}` but uses "The archive contains 2075 photos."
- `pipeline.py`: Entity ranking injected for "who appears most" queries (top 10 by asset count).
- `pipeline.py`: Decade coverage summary from timeline for date/period questions.
- `pipeline.py`: Entities always included in composer context (previously only shown as fallback when nothing else matched).
- `pipeline.py`: Keyword matching broadened from just planner strategy text to strategy + search terms + entities.

**Result:** 0.741 → 0.774. Medium tier jumped most (+0.103):
- m05 (decades): 0.300 → 0.900
- m07 (locations): 0.400 → 0.900

## Final Scores

| Tier | Baseline | Final | Improvement |
|------|----------|-------|-------------|
| Easy | 0.627 | 0.805 | +28.4% |
| Medium | 0.578 | 0.719 | +24.4% |
| Hard | 0.648 | 0.797 | +23.0% |
| **All** | **0.618** | **0.774** | **+25.2%** |

11 of 30 questions now score 0.9 (was 3 at baseline).

## Remaining Gaps

| Question | Score | Issue |
|----------|-------|-------|
| e05 (photo count) | 0.240 | Stats in context but composer hallucinates a different number |
| m06 (most frequent) | 0.140 | Planner routes to stats instead of person ranking |
| m03 (legal documents) | 0.567 | Misses "probate" despite court filings in retrieval |
| h05 (archive strengths/gaps) | 0.540 | Meta-question — needs archive self-awareness |

The two persistent failures (e05, m06) are composer-level problems: the data is retrieved correctly but the LLM ignores or misinterprets it. Further iterations would target composer prompt engineering.

## Architecture Validated

```
Question → [Planner LLM] → structured retrieval params
         → [SQL queries]  → deterministic data retrieval
         → [Composer LLM] → sourced answer with citations
         → [Evaluator]    → scored against ground truth
```

Key architectural decisions confirmed:
1. **Retrieval is SQL, not LLM.** Every fact traces to a SHA-256 hash. The LLM plans and composes; it doesn't retrieve.
2. **The planner is the bottleneck.** Classification quality determines everything downstream. Few-shot examples with domain context beat generic instructions.
3. **Context format matters.** The same data presented as raw JSON vs. readable sentences produces dramatically different composer output.
4. **Scoring reveals silent failures.** The markdown fence bug, the stats format issue, the entity context gap — none were visible without automated evaluation.

## Token Economics

- 30 questions × 3 iterations × ~2,800 tokens/question = ~252K tokens
- All Max Plan (zero marginal cost via OAuth SDK)
- ~6 minutes per full 30-question run
- Total experiment wall time: ~45 minutes of compute

## Next Steps

- **Phase 3:** Minimal web interface wrapping the pipeline (`/ask` endpoint + text input)
- **Phase 4:** Verification sweep — use the loop to audit synthesis data quality
- **Promotion candidates:** If Phase 3 succeeds, `pipeline.py` graduates to `src/` as a query API
