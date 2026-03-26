"""Run targeted evaluation on specific weak questions."""

from pipeline import ask
from questions import get_questions
from evaluate import evaluate_answer

targets = ['m01', 'm03', 'm10', 'h08', 'e05', 'e06', 'm06']
questions = {q.id: q for q in get_questions()}

for qid in targets:
    q = questions[qid]
    result = ask(q.question)
    score = evaluate_answer(q, result.answer, result.sources, skip_coherence=True)
    print(f'{qid}: {score.overall:.3f} (fact={score.factual_accuracy:.2f} src={score.source_grounding:.2f} comp={score.completeness:.2f})')
    if score.details.get('factual', {}).get('missing'):
        print(f'  Missing: {score.details["factual"]["missing"]}')
    print()
