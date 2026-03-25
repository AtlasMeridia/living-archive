# Experiment 0005: Conversational Archive

## Question

Can an autonomous loop build and refine a conversational interface that lets non-technical family members ask natural language questions about the archive — starting simple, surfacing complexity on demand, with verified answers sourced from actual assets?

## Why This Is an Experiment

The archive has 2,196 assets, 2,346 synthesis entities, 3,012 timeline events, and full-text search over 72 documents. The data is rich. But the only interfaces are an admin dashboard and raw API endpoints — both built for the operator, not the audience.

The product question: can we build a query layer that converts "tell me about grandpa" into a sourced, bilingual, confidence-rated answer without the user knowing anything about SHA-256 hashes, synthesis databases, or photo manifests?

The Karpathy Loop question: can an agent autonomously improve this query layer by generating questions, evaluating answers against ground truth, and refining the retrieval/prompting pipeline — all within fixed time boxes?

## Current Data Inventory

| Store | Contents | Size |
|-------|----------|------|
| `catalog.db` | Unified asset index (photos + docs) | 2,196 assets |
| `synthesis.db` → `entities` | People, dates, locations extracted from assets | 2,346 entities |
| `synthesis.db` → `entity_assets` | Entity-to-asset links with confidence + context | 5,735 links |
| `synthesis.db` → `timeline_events` | Chronological events with bilingual descriptions | 3,012 events |
| `documents_fts` | Full-text search over extracted document text | 72 docs |
| `data/photos/*/manifest.json` | Per-photo analysis (descriptions, dates, people, tags) | ~2,075 files |
| `data/people/registry.json` | People registry with Immich face cluster linkage | ~800 entries |
| `chronology.json` | Precomputed chronology with quality metrics | 1 file |

### Ground Truth (for verification)

| Fact | Source | Confidence |
|------|--------|------------|
| Feng Kuang Liu b. 1943-01-23, d. 2010-06-06 | Death certificate (doc) | High |
| Feng Kuang Liu occupation: engineer | Death certificate | High |
| Meichu Grace Liu (wife of Feng Kuang) | Multiple documents | High |
| Kenny Peng Liu, Karen Peling Liu (children) | Multiple documents | High |
| Liu Family Trust exists | 72 trust documents | High |
| Family locations: Taiwan, Los Altos CA, Peabody MA | Documents + photos | High |
| 10 resolved people in synthesis | People registry | Medium (name matching) |
| Photo date estimates | Vision analysis | Low-Medium (model-inferred) |

Ground truth is sparse but real. The loop expands verified territory outward.

## Architecture

```
USER QUESTION (natural language)
        │
        ▼
┌─────────────────┐
│  Query Planner   │  Classifies question type, extracts entities
│  (LLM prompt)    │  Decides which data sources to query
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Retrieval Layer │  Queries synthesis.db, catalog.db, FTS, manifests
│  (Python + SQL)  │  Aggregates, deduplicates, ranks by confidence
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Answer Composer │  Formats sourced answer with citations
│  (LLM prompt)   │  Bilingual, confidence-rated, progressive depth
└────────┬────────┘
         │
         ▼
ANSWER (text + sources + confidence)
```

Three LLM touchpoints: plan, compose, (later) verify. Retrieval is deterministic SQL — no LLM in the data path.

## Karpathy Loop Design

```
ONE FILE:     experiments/0005-conversational-archive/src/pipeline.py
              (query planner prompt + retrieval logic + answer composer prompt)

ONE METRIC:   Answer quality score (0-1)
              - factual_accuracy:  Does the answer match ground truth?
              - source_grounding:  Is every claim linked to a real asset?
              - completeness:      Does it use all relevant data available?
              - coherence:         Is the answer readable and well-structured?
              Weighted average. Evaluated by a separate LLM call against
              the ground truth table + source verification.

TIME BOX:     30-minute iterations
              Each iteration: generate 10 questions → retrieve → compose →
              score → analyze failures → modify pipeline.py → repeat
```

The agent modifies prompts and retrieval logic (SQL queries, ranking weights, source selection heuristics). It does NOT modify the underlying data or synthesis pipeline.

## Phases

### Phase 0: Scaffold (manual)
Set up experiment structure, build the query→retrieve→answer pipeline as a baseline.
- `src/pipeline.py` — orchestrator (planner + retrieval + composer)
- `src/retrieval.py` — SQL queries against synthesis.db, catalog.db, FTS
- `src/evaluate.py` — answer scoring against ground truth
- `src/questions.py` — test question bank (easy/medium/hard)
- Gate: Pipeline answers 3 known-answer questions with >0 scores.

### Phase 1: Baseline measurement
Run the full question bank through the pipeline. Establish baseline scores.
- 30 questions across 3 difficulty tiers:
  - Easy (10): "When was Feng Kuang Liu born?" — single fact, direct lookup
  - Medium (10): "What do we know about the Liu Family Trust?" — multi-source
  - Hard (10): "What was life like in the 1970s for this family?" — narrative synthesis
- Gate: Baseline scores recorded. Identify worst-performing question categories.

### Phase 2: Autonomous Loop
The Karpathy Loop runs. Agent modifies pipeline.py to improve scores.
- 30-minute time boxes, 5 iterations minimum
- Each iteration logs: questions asked, scores achieved, changes made
- Agent focuses on worst-performing category first
- Gate: >0.2 improvement in average score across any category.

### Phase 3: Interface
Build a minimal web UI that wraps the refined pipeline.
- Text input → answer with sources
- "Tell me more" drill-down
- Confidence indicators
- Bilingual toggle
- Gate: A non-technical person can ask 5 questions and get useful answers.

### Phase 4: Verification Sweep
Use the loop to systematically verify synthesis data.
- Generate questions whose answers are checkable against documents
- Identify entities where photo analysis contradicts document records
- Flag confidence scores that don't hold up
- Gate: Verification report with correction recommendations.

## What This Is NOT

- Not a chatbot. No conversation history, no persona. Questions in, sourced answers out.
- Not a search engine. It composes answers, not lists of results.
- Not a replacement for the dashboard. The dashboard is for operators. This is for family.
- Not modifying the data pipeline. The loop optimizes retrieval and composition, not analysis.

## Budget

- LLM: Max Plan tokens (zero marginal, via maxplan-inference)
- Time: Phase 0-1 in one session, Phase 2 as overnight loop, Phase 3-4 follow-up sessions
- Risk: Low — experiment is isolated, no pipeline modification

## Success Criteria

The experiment succeeds if:
1. A family member can type "tell me about grandpa" and get a factually correct,
   sourced answer that includes both photo and document evidence
2. The autonomous loop demonstrably improves answer quality (measured, not vibed)
3. The verification sweep identifies at least one correctable error in synthesis data
