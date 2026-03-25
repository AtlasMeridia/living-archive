"""Conversational Archive Pipeline — the "one file" for the Karpathy Loop.

Three stages:
  1. PLAN   — classify the question, extract entities, decide retrieval strategy
  2. RETRIEVE — deterministic SQL queries (retrieval.py)
  3. COMPOSE — synthesize a sourced, bilingual answer from retrieved data

The autonomous loop modifies this file (prompts, retrieval logic, composition
strategy) to improve answer quality scores. The retrieval layer (retrieval.py)
and data sources are NOT modified.
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Add maxplan-inference to path
sys.path.insert(0, str(Path.home() / "Projects" / "tools" / "maxplan-inference"))
from maxplan import call as llm_call

from retrieval import (
    RetrievalResult,
    search_entities,
    get_person_profile,
    get_timeline_for_period,
    search_documents,
    get_assets_for_entity,
    get_archive_stats,
    get_location_entities,
)


# --- Result type ---


@dataclass
class PipelineResult:
    question: str
    answer: str
    sources: list[dict] = field(default_factory=list)
    plan: dict = field(default_factory=dict)
    retrieval_summary: dict = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0


# =========================================================================
# STAGE 1: PLAN — Classify question and extract entities
# =========================================================================

PLANNER_PROMPT_PREFIX = """You are a query planner for the Liu family archive. Given a user question,
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

Now answer for this question. Return ONLY the JSON object:
Q: "QUESTION_PLACEHOLDER"
A: """


def _format_planner_prompt(question: str) -> str:
    return PLANNER_PROMPT_PREFIX.replace("QUESTION_PLACEHOLDER", question)


def _strip_fences(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def plan(question: str) -> dict:
    """Classify the question and extract retrieval parameters."""
    result = llm_call(
        _format_planner_prompt(question),
        model="claude-sonnet-4-20250514",
        max_tokens=500,
    )
    try:
        return json.loads(_strip_fences(result.output))
    except (json.JSONDecodeError, TypeError):
        # Fallback: treat as general query
        return {
            "query_type": "general",
            "entities": [],
            "date_range": {},
            "search_terms": [question],
            "strategy": "General search",
        }


# =========================================================================
# STAGE 2: RETRIEVE — Execute retrieval based on plan
# =========================================================================


def retrieve(plan_result: dict) -> RetrievalResult:
    """Execute retrieval queries based on the plan."""
    qtype = plan_result.get("query_type", "general")
    entities = plan_result.get("entities", [])
    date_range = plan_result.get("date_range", {}) or {}
    search_terms = plan_result.get("search_terms", [])

    result = RetrievalResult(query_type=qtype)

    # Entity search
    for entity_name in entities:
        matches = search_entities(entity_name, limit=5)
        result.entities.extend(matches)

    # Person profiles — pull for ANY entity that matches a person, regardless
    # of query type. Also search documents by person name for cross-referencing.
    person_names_searched = set()
    for entity_name in entities:
        profile = get_person_profile(entity_name)
        if profile:
            result.person_profiles.append(profile)
            assets = get_assets_for_entity(profile.entity_id, limit=5)
            result.assets.extend(assets)
            result.timeline.extend(profile.timeline_events)
            person_names_searched.add(entity_name.lower())
    # Also check any entity matches that are persons
    for match in result.entities:
        if match.entity_type == "person" and match.entity_value.lower() not in person_names_searched:
            profile = get_person_profile(match.entity_value)
            if profile:
                result.person_profiles.append(profile)
                result.timeline.extend(profile.timeline_events)
                person_names_searched.add(match.entity_value.lower())

    # Always search documents for person names — death certs, medical records,
    # legal docs contain critical biographical facts not in synthesis
    for name in person_names_searched:
        # Extract surname for broader doc search
        parts = name.split()
        if parts:
            docs = search_documents(parts[-1], limit=3)  # surname search
            result.documents.extend(docs)

    # Date/timeline queries
    decade = date_range.get("decade", "")
    start = date_range.get("start", "")
    end = date_range.get("end", "")
    if decade or start or end:
        timeline = get_timeline_for_period(
            decade=decade or "", start=start or "", end=end or "", limit=20,
        )
        result.timeline.extend(timeline)

    # Document search
    for term in search_terms:
        docs = search_documents(term, limit=5)
        result.documents.extend(docs)

    # Stats queries — also trigger on keywords that imply counting
    stats_keywords = ["how many", "count", "total", "number of", "archive", "collection"]
    needs_stats = qtype == "stats" or any(
        kw in plan_result.get("strategy", "").lower()
        for kw in stats_keywords
    )
    if needs_stats:
        stats = get_archive_stats()
        result.raw_facts.append(f"Archive statistics: {json.dumps(stats)}")

    # Location queries
    if qtype == "location":
        locs = get_location_entities()
        result.entities.extend(locs)

    # General fallback: search entities + documents
    if qtype == "general" and not result.entities and not result.documents:
        for term in search_terms or entities:
            result.entities.extend(search_entities(term, limit=5))
            result.documents.extend(search_documents(term, limit=5))

    return result


# =========================================================================
# STAGE 3: COMPOSE — Generate sourced answer from retrieved data
# =========================================================================

COMPOSER_PROMPT_TEMPLATE = """You are composing an answer about a family archive for a family member.
You have retrieved the following data. Use ONLY this data to answer — do not invent facts.

QUESTION: <<QUESTION>>

RETRIEVED DATA:
<<CONTEXT>>

INSTRUCTIONS:
- Answer the question directly and conversationally
- Every factual claim must be traceable to the retrieved data
- Include both English and Chinese names where available
- Mention specific counts (photos, documents) when relevant
- If the data is incomplete, say what IS known and what gaps exist
- End with a "Sources" section listing the asset types used
- Keep the answer concise but complete — aim for 100-300 words
- Do NOT invent or assume facts not in the retrieved data

Write the answer now."""


def _format_composer_prompt(question: str, context: str) -> str:
    return COMPOSER_PROMPT_TEMPLATE.replace("<<QUESTION>>", question).replace("<<CONTEXT>>", context)


def _format_context(retrieval: RetrievalResult) -> str:
    """Format retrieval results into a context string for the composer."""
    parts = []

    # Person profiles
    for p in retrieval.person_profiles:
        section = f"PERSON: {p.name_en}"
        if p.name_zh:
            section += f" ({p.name_zh})"
        if p.birth_year:
            section += f", born {p.birth_year}"
        if p.relationship:
            section += f", relationship: {p.relationship}"
        section += f"\n  Photos linked: {p.photo_count}, Documents linked: {p.doc_count}"
        if p.timeline_events:
            section += f"\n  Timeline ({len(p.timeline_events)} events):"
            for e in p.timeline_events[:10]:
                section += f"\n    {e.date}: {e.label_en[:200]}"
        parts.append(section)

    # Documents
    if retrieval.documents:
        doc_section = "DOCUMENTS FOUND:"
        for d in retrieval.documents[:8]:
            doc_section += f"\n  [{d.sha256[:12]}] {d.source_file}"
            doc_section += f"\n    Date: {d.date}, Title: {d.title}"
            doc_section += f"\n    Summary: {d.summary_en[:300]}"
            if d.snippet:
                doc_section += f"\n    Excerpt: {d.snippet[:200]}"
        parts.append(doc_section)

    # Timeline events (not already in person profiles)
    standalone_timeline = [
        e for e in retrieval.timeline
        if not any(e in p.timeline_events for p in retrieval.person_profiles)
    ]
    if standalone_timeline:
        tl_section = "TIMELINE EVENTS:"
        for e in standalone_timeline[:10]:
            tl_section += f"\n  {e.date} ({e.decade}): {e.label_en[:200]}"
        parts.append(tl_section)

    # Assets
    if retrieval.assets:
        asset_section = "SAMPLE ASSETS:"
        for a in retrieval.assets[:5]:
            asset_section += f"\n  [{a.sha256[:12]}] {a.content_type}: {a.path}"
            if a.description_en:
                asset_section += f"\n    {a.description_en[:200]}"
        parts.append(asset_section)

    # Raw facts (stats etc.)
    for fact in retrieval.raw_facts:
        parts.append(f"FACT: {fact}")

    # Entities (if nothing else matched)
    if not parts and retrieval.entities:
        ent_section = "ENTITIES FOUND:"
        for e in retrieval.entities[:10]:
            ent_section += f"\n  {e.entity_type}: {e.entity_value} ({e.asset_count} linked assets)"
        parts.append(ent_section)

    return "\n\n".join(parts) if parts else "No relevant data found in the archive."


def compose(question: str, retrieval: RetrievalResult) -> PipelineResult:
    """Generate a sourced answer from retrieved data."""
    context = _format_context(retrieval)

    result = llm_call(
        _format_composer_prompt(question, context),
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
    )

    # Build source list
    sources = []
    for p in retrieval.person_profiles:
        sources.append({"type": "person_profile", "name": p.name_en, "assets": p.photo_count + p.doc_count})
    for d in retrieval.documents:
        sources.append({"type": "document", "file": d.source_file, "sha256": d.sha256[:12]})
    for a in retrieval.assets:
        sources.append({"type": a.content_type, "path": a.path, "sha256": a.sha256[:12]})

    return PipelineResult(
        question=question,
        answer=result.output,
        sources=sources,
        plan={"query_type": retrieval.query_type},
        retrieval_summary={
            "entities": len(retrieval.entities),
            "documents": len(retrieval.documents),
            "timeline_events": len(retrieval.timeline),
            "assets": len(retrieval.assets),
            "person_profiles": len(retrieval.person_profiles),
        },
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


# =========================================================================
# MAIN: Run the full pipeline
# =========================================================================


def ask(question: str) -> PipelineResult:
    """Full pipeline: plan → retrieve → compose."""
    plan_result = plan(question)
    retrieval = retrieve(plan_result)
    result = compose(question, retrieval)
    result.plan = plan_result
    return result


# CLI entry point
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py 'your question here'")
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    print(f"Question: {question}\n")

    result = ask(question)
    print(result.answer)
    print(f"\n--- Sources ({len(result.sources)}) ---")
    for s in result.sources[:10]:
        print(f"  {s['type']}: {s.get('file') or s.get('name') or s.get('path', '')}")
    print(f"\n--- Tokens: {result.input_tokens} in / {result.output_tokens} out ---")
