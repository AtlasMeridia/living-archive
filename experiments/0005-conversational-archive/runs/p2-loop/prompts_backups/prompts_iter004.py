"""Prompt templates for the conversational archive pipeline.

This is the MUTABLE FILE for the Karpathy Loop (Phase 2+).
The autonomous loop modifies prompts here to improve answer quality.
Pipeline logic (pipeline.py) and retrieval (retrieval.py) are NOT modified.

Version history is tracked via pipeline_backups/ (now prompts_backups/).
"""

# =========================================================================
# PLANNER PROMPT
# =========================================================================

PLANNER_PROMPT = """You are a query planner for the Liu family archive. Given a user question,
extract structured retrieval parameters. The archive contains photos, legal documents,
medical records, death certificates, and trust filings for the Liu family.

Key people: Feng Kuang Liu (patriarch), Meichu Grace Liu (wife), Kenny Peng Liu (son),
Karen Peling Liu (daughter). The family lived in Los Altos Hills, California.
Feng Kuang Liu was born January 23, 1943 in Taiwan and died June 6, 2010.

Return a JSON object with these fields:
- query_type: "person", "date", "location", "topic", "stats", or "general"
- entities: list of person names or entity values to look up
- date_range: object with optional "start", "end", "decade" fields
- search_terms: list of 1-3 word keywords for document text search (NOT full sentences)
- strategy: one sentence describing what to retrieve

EXAMPLES:

Q: "When did Feng Kuang Liu die?"
A: {"query_type": "person", "entities": ["Feng Kuang Liu"], "date_range": {}, "search_terms": ["death", "died"], "strategy": "Look up Feng Kuang Liu person profile and search death-related documents"}

Q: "How many photos are in the archive?"
A: {"query_type": "stats", "entities": [], "date_range": {}, "search_terms": [], "strategy": "Get archive statistics including photo and document counts"}

Q: "What happened in the 1970s?"
A: {"query_type": "date", "entities": [], "date_range": {"decade": "1970s"}, "search_terms": [], "strategy": "Get timeline events from the 1970s decade"}

Q: "Tell me about grandpa."
A: {"query_type": "person", "entities": ["Feng Kuang Liu"], "date_range": {}, "search_terms": ["Liu"], "strategy": "Get full person profile for Feng Kuang Liu with timeline and documents"}

Q: "What legal documents are in the archive?"
A: {"query_type": "topic", "entities": [], "date_range": {}, "search_terms": ["trust", "court", "probate", "legal"], "strategy": "Search documents for legal and trust-related content"}

Q: "Who appears most often in the archive?"
A: {"query_type": "stats", "entities": ["Feng Kuang Liu", "Meichu Grace Liu"], "date_range": {}, "search_terms": [], "strategy": "Get entity rankings by asset count and person profiles for top people"}

Now answer for this question. Return ONLY the JSON object:
Q: "QUESTION_PLACEHOLDER"
A: """


# =========================================================================
# COMPOSER PROMPT
# =========================================================================

COMPOSER_PROMPT = """You are composing an answer about a family archive for a family member.
You have retrieved the following data. Use ONLY this data to answer — do not invent facts.

QUESTION: <<QUESTION>>

RETRIEVED DATA:
<<CONTEXT>>

INSTRUCTIONS:
- Answer the question directly and conversationally
- Every factual claim must be traceable to the retrieved data
- When the retrieved data contains EXACT NUMBERS (photo counts, document counts, entity counts), you MUST use those exact numbers. Do not round, estimate, or paraphrase numerical data.
- Include both English and Chinese names where available
- If the data is incomplete, say what IS known and what gaps exist
- End with a "Sources" section listing the asset types used
- Keep the answer concise but complete — aim for 100-300 words
- Do NOT invent or assume facts not in the retrieved data
- When listing "top people" or rankings, use the exact order and counts from the FACT section

Write the answer now."""


# =========================================================================
# COHERENCE JUDGE PROMPT (used by evaluator, not pipeline)
# =========================================================================

COHERENCE_JUDGE_PROMPT = """Rate the coherence of this answer on a scale of 0.0 to 1.0.

Criteria:
- Is it well-structured and readable?
- Does it flow naturally?
- Is it an appropriate length (not too short, not rambling)?
- Does it directly address the question asked?

Question: {question}
Answer: {answer}

Return ONLY a JSON object: {{"score": 0.X, "reason": "brief explanation"}}"""
