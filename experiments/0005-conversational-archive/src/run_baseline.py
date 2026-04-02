"""Phase 1: Run baseline questions through the pipeline and score them.

Usage:
    python run_baseline.py                           # all questions
    python run_baseline.py --tier easy              # one tier only
    python run_baseline.py --question-ids e01,m02   # explicit subset
    python run_baseline.py --quick                  # skip coherence LLM scoring
    python run_baseline.py --output-dir /tmp/run    # custom artifact destination
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from pipeline import ask
from questions import get_questions
from evaluate import evaluate_answer, print_scores

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"


def _summary(scores: list) -> dict:
    if not scores:
        return {
            "overall_avg": 0,
            "by_tier": {},
            "by_dimension": {
                "factual_accuracy": 0,
                "source_grounding": 0,
                "completeness": 0,
                "coherence": 0,
            },
        }

    tiers = sorted(set(s.tier for s in scores))
    return {
        "overall_avg": round(sum(s.overall for s in scores) / len(scores), 3),
        "by_tier": {
            tier_name: round(
                sum(s.overall for s in scores if s.tier == tier_name)
                / max(1, len([s for s in scores if s.tier == tier_name])),
                3,
            )
            for tier_name in tiers
        },
        "by_dimension": {
            "factual_accuracy": round(sum(s.factual_accuracy for s in scores) / len(scores), 3),
            "source_grounding": round(sum(s.source_grounding for s in scores) / len(scores), 3),
            "completeness": round(sum(s.completeness for s in scores) / len(scores), 3),
            "coherence": round(sum(s.coherence for s in scores) / len(scores), 3),
        },
    }


def run_baseline(
    tier: str = None,
    skip_coherence: bool = False,
    question_ids: list[str] | None = None,
    output_dir: str | None = None,
):
    questions = get_questions(tier=tier, question_ids=question_ids)
    selector = []
    if tier:
        selector.append(f"tier={tier}")
    if question_ids:
        selector.append(f"ids={','.join(question_ids)}")

    print(
        f"Phase 1 Baseline: {len(questions)} questions"
        + (f" ({'; '.join(selector)})" if selector else "")
        + (" [coherence skipped]" if skip_coherence else "")
    )
    print("=" * 60)

    results = []
    scores = []
    total_input = 0
    total_output = 0
    start = time.time()

    for i, q in enumerate(questions):
        print(f"\n[{i+1}/{len(questions)}] {q.id} ({q.tier}): {q.question}")
        try:
            result = ask(q.question)
            print(f"  Answer: {result.answer[:150]}...")
            print(f"  Tokens: {result.input_tokens} in / {result.output_tokens} out, {len(result.sources)} sources")

            score = evaluate_answer(q, result.answer, result.sources, skip_coherence=skip_coherence)
            print(
                f"  Score: {score.overall:.3f} "
                f"(fact={score.factual_accuracy:.2f} src={score.source_grounding:.2f} "
                f"comp={score.completeness:.2f} coh={score.coherence:.2f})"
            )

            if score.details.get("factual", {}).get("missing"):
                print(f"  Missing: {score.details['factual']['missing']}")

            results.append({
                "question_id": q.id,
                "tier": q.tier,
                "question": q.question,
                "answer": result.answer,
                "sources": result.sources,
                "plan": result.plan,
                "retrieval_summary": result.retrieval_summary,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            })
            scores.append(score)
            total_input += result.input_tokens
            total_output += result.output_tokens

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "question_id": q.id,
                "tier": q.tier,
                "question": q.question,
                "error": str(e),
            })

    elapsed = time.time() - start

    print("\n" + "=" * 60)
    if scores:
        print_scores(scores)

    per_question = elapsed / len(questions) if questions else 0
    print(f"\nElapsed: {elapsed:.0f}s ({per_question:.1f}s/question)")
    print(f"Tokens: {total_input} input + {total_output} output = {total_input + total_output} total")

    run_dir = Path(output_dir) if output_dir else (RUNS_DIR / "p1-baseline")
    run_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results_payload = {
        "timestamp": timestamp,
        "tier_filter": tier,
        "question_ids": question_ids,
        "skip_coherence": skip_coherence,
        "elapsed_seconds": round(elapsed, 1),
        "seconds_per_question": round(per_question, 2),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "questions_attempted": len(questions),
        "questions_succeeded": len(scores),
        "results": results,
    }
    scores_payload = {
        "timestamp": timestamp,
        "scores": [
            {
                "question_id": s.question_id,
                "tier": s.tier,
                "factual_accuracy": s.factual_accuracy,
                "source_grounding": s.source_grounding,
                "completeness": s.completeness,
                "coherence": s.coherence,
                "overall": s.overall,
                "details": s.details,
            }
            for s in scores
        ],
        "summary": _summary(scores),
    }

    (run_dir / f"results_{timestamp}.json").write_text(json.dumps(results_payload, indent=2) + "\n")
    (run_dir / f"scores_{timestamp}.json").write_text(json.dumps(scores_payload, indent=2) + "\n")

    print(f"\nResults saved to {run_dir}/")
    return scores_payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Phase 1 baseline evaluation")
    parser.add_argument("--tier", choices=["easy", "medium", "hard"], help="Run only one tier")
    parser.add_argument("--question-ids", help="Comma-separated explicit question IDs")
    parser.add_argument("--quick", action="store_true", help="Skip coherence LLM scoring")
    parser.add_argument("--output-dir", help="Custom output directory for results artifacts")
    args = parser.parse_args()

    question_ids = [q.strip() for q in args.question_ids.split(",")] if args.question_ids else None
    run_baseline(
        tier=args.tier,
        skip_coherence=args.quick,
        question_ids=question_ids,
        output_dir=args.output_dir,
    )
