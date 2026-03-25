"""Conversational query API — natural language questions about the archive.

Wraps the experiment 0005 pipeline (plan → retrieve → compose) for
production use in the dashboard. Uses maxplan-inference for LLM calls.

Usage:
    from src.ask import ask, AskResult

    result = ask("Tell me about grandpa")
    print(result.answer)
    print(result.sources)
"""

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import config
from .catalog import get_catalog_db, init_catalog, get_stats
from .synthesis_queries import (
    open_synthesis_db,
    query_overview,
    query_person_entity,
    query_date_entities,
    query_location_entity,
)

log = logging.getLogger("living_archive")


# ---------------------------------------------------------------------------
# Lazy import — only load maxplan when ask() is actually called
# ---------------------------------------------------------------------------

_maxplan = None

def _get_maxplan():
    global _maxplan
    if _maxplan is None:
        from . import maxplan as _mp
        _maxplan = _mp
    return _maxplan


# ---------------------------------------------------------------------------
# Import retrieval from experiment (until promoted)
# ---------------------------------------------------------------------------

_EXPERIMENT_SRC = Path(__file__).resolve().parent.parent / "experiments" / "0005-conversational-archive" / "src"
if str(_EXPERIMENT_SRC) not in sys.path:
    sys.path.insert(0, str(_EXPERIMENT_SRC))

from retrieval import (
    search_entities,
    get_person_profile,
    get_timeline_for_period,
    search_documents,
    get_assets_for_entity,
    get_archive_stats,
    get_location_entities,
    RetrievalResult,
    _connect,
    SYNTHESIS_DB,
)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class AskResult:
    question: str
    answer: str
    sources: list[dict] = field(default_factory=list)
    plan: dict = field(default_factory=dict)
    retrieval_summary: dict = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    error: str = ""


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

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

Now answer for this question. Return ONLY the JSON object:
Q: "QUESTION"
A: """


COMPOSER_PROMPT = """You are composing an answer about a family archive for a family member.
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


def _plan(question: str) -> dict:
    """Classify the question and extract retrieval parameters."""
    maxplan = _get_maxplan()
    prompt = PLANNER_PROMPT.replace("QUESTION", question)
    result = maxplan.call(prompt, model=config.OAUTH_MODEL, max_tokens=500)
    try:
        return json.loads(_strip_fences(result.output))
    except (json.JSONDecodeError, TypeError):
        return {
            "query_type": "general",
            "entities": [],
            "date_range": {},
            "search_terms": [question],
            "strategy": "General search",
        }


def _retrieve(plan_result: dict) -> RetrievalResult:
    """Execute retrieval queries based on the plan."""
    qtype = plan_result.get("query_type", "general")
    entities = plan_result.get("entities", [])
    date_range = plan_result.get("date_range", {}) or {}
    search_terms = plan_result.get("search_terms", [])

    result = RetrievalResult(query_type=qtype)
    _searchable = " ".join([
        plan_result.get("strategy", ""),
        " ".join(search_terms),
        " ".join(entities),
    ]).lower()

    # Entity search
    for entity_name in entities:
        matches = search_entities(entity_name, limit=5)
        result.entities.extend(matches)

    # Person profiles — always pull for any matching person entity
    person_names_searched = set()
    for entity_name in entities:
        profile = get_person_profile(entity_name)
        if profile:
            result.person_profiles.append(profile)
            assets = get_assets_for_entity(profile.entity_id, limit=5)
            result.assets.extend(assets)
            result.timeline.extend(profile.timeline_events)
            person_names_searched.add(entity_name.lower())
    for match in result.entities:
        if match.entity_type == "person" and match.entity_value.lower() not in person_names_searched:
            profile = get_person_profile(match.entity_value)
            if profile:
                result.person_profiles.append(profile)
                result.timeline.extend(profile.timeline_events)
                person_names_searched.add(match.entity_value.lower())

    # Always search docs for person names
    for name in person_names_searched:
        parts = name.split()
        if parts:
            docs = search_documents(parts[-1], limit=3)
            result.documents.extend(docs)

    # Timeline
    decade = date_range.get("decade", "")
    start = date_range.get("start", "")
    end = date_range.get("end", "")
    if decade or start or end:
        timeline = get_timeline_for_period(
            decade=decade or "", start=start or "", end=end or "", limit=20,
        )
        result.timeline.extend(timeline)

    # Decade coverage
    decade_keywords = ["decade", "decades", "period", "era", "years", "century"]
    if any(kw in _searchable for kw in decade_keywords) or qtype == "date":
        conn = _connect(SYNTHESIS_DB)
        if conn:
            rows = conn.execute("""
                SELECT era_decade, COUNT(*) as cnt
                FROM timeline_events
                WHERE era_decade IS NOT NULL AND era_decade != ''
                GROUP BY era_decade ORDER BY era_decade
            """).fetchall()
            if rows:
                coverage = "; ".join(f"{r['era_decade']}: {r['cnt']} events" for r in rows)
                result.raw_facts.append(f"Decade coverage in timeline: {coverage}")

    # Stats
    stats_keywords = ["how many", "count", "total", "number of", "archive", "collection"]
    if qtype == "stats" or any(kw in _searchable for kw in stats_keywords):
        stats = get_archive_stats()
        by_type = stats.get("by_type", {})
        entities_map = stats.get("entities", {})
        result.raw_facts.append(
            f"The archive contains {stats.get('total_assets', 0)} total assets: "
            f"{by_type.get('photo', 0)} photos and {by_type.get('document', 0)} documents. "
            f"Synthesis has extracted {entities_map.get('person', 0)} people, "
            f"{entities_map.get('date', 0)} dates, and {entities_map.get('location', 0)} locations. "
            f"There are {stats.get('timeline_events', 0)} timeline events."
        )

    # Entity ranking
    ranking_keywords = ["most", "frequently", "appears", "common", "often"]
    if any(kw in _searchable for kw in ranking_keywords):
        top_people = search_entities("", entity_type="person", limit=10)
        if top_people:
            ranking = "; ".join(f"{p.entity_value} ({p.asset_count} assets)" for p in top_people[:10])
            result.raw_facts.append(f"Top people by asset count: {ranking}")

    # Location entities
    if qtype == "location":
        locs = get_location_entities()
        result.entities.extend(locs)

    # Document search
    for term in search_terms:
        docs = search_documents(term, limit=5)
        result.documents.extend(docs)

    # General fallback
    if qtype == "general" and not result.entities and not result.documents:
        for term in search_terms or entities:
            result.entities.extend(search_entities(term, limit=5))
            result.documents.extend(search_documents(term, limit=5))

    return result


def _format_context(retrieval: RetrievalResult) -> str:
    """Format retrieval results into context for the composer."""
    parts = []

    for p in retrieval.person_profiles:
        section = f"PERSON: {p.name_en}"
        if p.name_zh:
            section += f" ({p.name_zh})"
        if p.birth_year:
            section += f", born {p.birth_year}"
        section += f"\n  Photos linked: {p.photo_count}, Documents linked: {p.doc_count}"
        if p.timeline_events:
            section += f"\n  Timeline ({len(p.timeline_events)} events):"
            for e in p.timeline_events[:10]:
                section += f"\n    {e.date}: {e.label_en[:200]}"
        parts.append(section)

    if retrieval.documents:
        doc_section = "DOCUMENTS FOUND:"
        for d in retrieval.documents[:8]:
            doc_section += f"\n  [{d.sha256[:12]}] {d.source_file}"
            doc_section += f"\n    Date: {d.date}, Title: {d.title}"
            doc_section += f"\n    Summary: {d.summary_en[:300]}"
        parts.append(doc_section)

    standalone_timeline = [
        e for e in retrieval.timeline
        if not any(e in p.timeline_events for p in retrieval.person_profiles)
    ]
    if standalone_timeline:
        tl_section = "TIMELINE EVENTS:"
        for e in standalone_timeline[:10]:
            tl_section += f"\n  {e.date} ({e.decade}): {e.label_en[:200]}"
        parts.append(tl_section)

    if retrieval.assets:
        asset_section = "SAMPLE ASSETS:"
        for a in retrieval.assets[:5]:
            asset_section += f"\n  [{a.sha256[:12]}] {a.content_type}: {a.path}"
            if a.description_en:
                asset_section += f"\n    {a.description_en[:200]}"
        parts.append(asset_section)

    for fact in retrieval.raw_facts:
        parts.append(f"FACT: {fact}")

    non_profile_entities = [
        e for e in retrieval.entities
        if e.entity_type != "person" or not any(
            p.name_en.lower() == e.entity_value.lower()
            for p in retrieval.person_profiles
        )
    ]
    if non_profile_entities:
        ent_section = "ENTITIES IN ARCHIVE:"
        for e in non_profile_entities[:15]:
            ent_section += f"\n  {e.entity_type}: {e.entity_value} ({e.asset_count} linked assets)"
        parts.append(ent_section)

    return "\n\n".join(parts) if parts else "No relevant data found in the archive."


def _compose(question: str, retrieval: RetrievalResult) -> AskResult:
    """Generate a sourced answer from retrieved data."""
    maxplan = _get_maxplan()
    context = _format_context(retrieval)

    prompt = COMPOSER_PROMPT.replace("<<QUESTION>>", question).replace("<<CONTEXT>>", context)
    result = maxplan.call(prompt, model=config.OAUTH_MODEL, max_tokens=1500)

    sources = []
    for p in retrieval.person_profiles:
        sources.append({"type": "person_profile", "name": p.name_en, "assets": p.photo_count + p.doc_count})
    for d in retrieval.documents:
        sources.append({"type": "document", "file": d.source_file, "sha256": d.sha256[:12]})
    for a in retrieval.assets:
        sources.append({"type": a.content_type, "path": a.path, "sha256": a.sha256[:12]})

    return AskResult(
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ask(question: str) -> AskResult:
    """Full pipeline: plan → retrieve → compose.

    This is the main entry point for the dashboard's /api/ask endpoint.
    """
    if not question or not question.strip():
        return AskResult(question="", answer="", error="No question provided")

    try:
        plan_result = _plan(question)
        retrieval = _retrieve(plan_result)
        result = _compose(question, retrieval)
        result.plan = plan_result
        return result
    except Exception as e:
        log.exception("ask() failed for question: %s", question)
        return AskResult(
            question=question,
            answer="",
            error=f"Failed to process question: {str(e)}",
        )
