"""Answer evaluation — scores pipeline answers against ground truth.

Scoring dimensions (each 0.0-1.0):
  factual_accuracy  — required facts present in the answer
  source_grounding  — answer cites actual archive sources
  completeness      — bonus facts present (normalized)
  coherence         — LLM-judged readability and structure

Overall score = weighted average.
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from questions import TestQuestion, get_questions

# Add maxplan for coherence scoring
sys.path.insert(0, str(Path.home() / "Projects" / "tools" / "maxplan-inference"))
from maxplan import call as llm_call


@dataclass
class Score:
    question_id: str
    tier: str
    factual_accuracy: float = 0.0
    source_grounding: float = 0.0
    completeness: float = 0.0
    coherence: float = 0.0
    overall: float = 0.0
    details: dict = field(default_factory=dict)


# --- Scoring weights ---

WEIGHTS = {
    "factual_accuracy": 0.40,
    "source_grounding": 0.20,
    "completeness": 0.20,
    "coherence": 0.20,
}


def score_factual_accuracy(answer: str, question: TestQuestion) -> tuple[float, dict]:
    """Check what fraction of required facts appear in the answer."""
    answer_lower = answer.lower()
    found = []
    missing = []

    for fact in question.required_facts:
        if fact.lower() in answer_lower:
            found.append(fact)
        else:
            missing.append(fact)

    accuracy = len(found) / len(question.required_facts) if question.required_facts else 1.0
    return accuracy, {"found": found, "missing": missing}


def score_source_grounding(answer: str, sources: list[dict]) -> tuple[float, dict]:
    """Check if the answer mentions sources or asset references."""
    # Look for source-like patterns in the answer
    indicators = [
        "source", "document", "photo", "certificate", "record",
        "filing", "trust", "archive", "catalog",
    ]
    answer_lower = answer.lower()
    mentioned = [ind for ind in indicators if ind in answer_lower]

    # Check if actual sources were provided
    has_sources = len(sources) > 0

    # Score: some credit for mentioning sources, full credit for actual references
    if has_sources and mentioned:
        score = min(1.0, len(mentioned) / 3)
    elif has_sources:
        score = 0.3  # sources exist but answer doesn't reference them
    elif mentioned:
        score = 0.2  # mentions sources but none actually provided
    else:
        score = 0.0

    return score, {"mentioned": mentioned, "source_count": len(sources)}


def score_completeness(answer: str, question: TestQuestion) -> tuple[float, dict]:
    """Check how many bonus facts appear in the answer."""
    if not question.bonus_facts:
        return 1.0, {"bonus_found": [], "bonus_missing": []}

    answer_lower = answer.lower()
    found = [f for f in question.bonus_facts if f.lower() in answer_lower]
    missing = [f for f in question.bonus_facts if f.lower() not in answer_lower]

    score = len(found) / len(question.bonus_facts)
    return score, {"bonus_found": found, "bonus_missing": missing}


COHERENCE_PROMPT = """Rate the coherence of this answer on a scale of 0.0 to 1.0.

Criteria:
- Is it well-structured and readable?
- Does it flow naturally?
- Is it an appropriate length (not too short, not rambling)?
- Does it directly address the question asked?

Question: {question}
Answer: {answer}

Return ONLY a JSON object: {{"score": 0.X, "reason": "brief explanation"}}"""


def score_coherence(question: str, answer: str) -> tuple[float, dict]:
    """LLM-judged coherence score."""
    try:
        result = llm_call(
            COHERENCE_PROMPT.format(question=question, answer=answer),
            model="claude-sonnet-4-20250514",
            max_tokens=100,
        )
        parsed = json.loads(result.output)
        return float(parsed.get("score", 0.5)), {"reason": parsed.get("reason", "")}
    except Exception as e:
        return 0.5, {"error": str(e)}


def evaluate_answer(
    question: TestQuestion,
    answer: str,
    sources: list[dict],
    skip_coherence: bool = False,
) -> Score:
    """Full evaluation of a pipeline answer."""
    fa_score, fa_details = score_factual_accuracy(answer, question)
    sg_score, sg_details = score_source_grounding(answer, sources)
    co_score, co_details = score_completeness(answer, question)

    if skip_coherence:
        ch_score, ch_details = 0.5, {"skipped": True}
    else:
        ch_score, ch_details = score_coherence(question.question, answer)

    overall = (
        WEIGHTS["factual_accuracy"] * fa_score
        + WEIGHTS["source_grounding"] * sg_score
        + WEIGHTS["completeness"] * co_score
        + WEIGHTS["coherence"] * ch_score
    )

    return Score(
        question_id=question.id,
        tier=question.tier,
        factual_accuracy=round(fa_score, 3),
        source_grounding=round(sg_score, 3),
        completeness=round(co_score, 3),
        coherence=round(ch_score, 3),
        overall=round(overall, 3),
        details={
            "factual": fa_details,
            "grounding": sg_details,
            "completeness": co_details,
            "coherence": ch_details,
        },
    )


def evaluate_batch(
    results: list[tuple],  # (TestQuestion, answer_str, sources_list)
    skip_coherence: bool = False,
) -> list[Score]:
    """Evaluate a batch of pipeline results."""
    return [
        evaluate_answer(q, answer, sources, skip_coherence=skip_coherence)
        for q, answer, sources in results
    ]


def print_scores(scores: list[Score]):
    """Pretty-print evaluation results."""
    print(f"\n{'ID':<6} {'Tier':<8} {'Fact':>6} {'Src':>6} {'Comp':>6} {'Coh':>6} {'TOTAL':>7}")
    print("-" * 50)
    for s in scores:
        print(
            f"{s.question_id:<6} {s.tier:<8} "
            f"{s.factual_accuracy:>6.3f} {s.source_grounding:>6.3f} "
            f"{s.completeness:>6.3f} {s.coherence:>6.3f} "
            f"{s.overall:>7.3f}"
        )

    # Averages by tier
    tiers = sorted(set(s.tier for s in scores))
    print("-" * 50)
    for tier in tiers:
        tier_scores = [s for s in scores if s.tier == tier]
        avg = sum(s.overall for s in tier_scores) / len(tier_scores)
        print(f"{'AVG':<6} {tier:<8} {'':>6} {'':>6} {'':>6} {'':>6} {avg:>7.3f}")

    total_avg = sum(s.overall for s in scores) / len(scores)
    print(f"{'AVG':<6} {'ALL':<8} {'':>6} {'':>6} {'':>6} {'':>6} {total_avg:>7.3f}")
