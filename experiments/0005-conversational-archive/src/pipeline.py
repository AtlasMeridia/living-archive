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
from prompts import PLANNER_PROMPT, COMPOSER_PROMPT


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

def _format_planner_prompt(question: str) -> str:
    return PLANNER_PROMPT.replace("QUESTION_PLACEHOLDER", question)


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
    # Combine strategy + search terms + original question for keyword matching
    _searchable = " ".join([
        plan_result.get("strategy", ""),
        " ".join(search_terms),
        " ".join(entities),
    ]).lower()

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

    # For "decades" or "time period" questions — provide decade coverage summary
    decade_keywords = ["decade", "decades", "period", "era", "years", "century"]
    if any(kw in _searchable for kw in decade_keywords) or qtype == "date":
        from retrieval import _connect, SYNTHESIS_DB
        conn = _connect(SYNTHESIS_DB)
        if conn:
            rows = conn.execute("""
                SELECT era_decade, COUNT(*) as cnt
                FROM timeline_events
                WHERE era_decade IS NOT NULL AND era_decade != ''
                GROUP BY era_decade
                ORDER BY era_decade
            """).fetchall()
            if rows:
                coverage = "; ".join(f"{r['era_decade']}: {r['cnt']} events" for r in rows)
                result.raw_facts.append(f"Decade coverage in timeline: {coverage}")

    # Document search
    for term in search_terms:
        docs = search_documents(term, limit=5)
        result.documents.extend(docs)

    # Stats queries — also trigger on keywords that imply counting
    stats_keywords = ["how many", "count", "total", "number of", "archive", "collection"]
    needs_stats = qtype == "stats" or any(kw in _searchable for kw in stats_keywords)
    if needs_stats:
        stats = get_archive_stats()
        # Format stats as readable text, not raw JSON
        by_type = stats.get("by_type", {})
        entities_map = stats.get("entities", {})
        result.raw_facts.append(
            f"The archive contains {stats.get('total_assets', 0)} total assets: "
            f"{by_type.get('photo', 0)} photos and {by_type.get('document', 0)} documents. "
            f"Synthesis has extracted {entities_map.get('person', 0)} people, "
            f"{entities_map.get('date', 0)} dates, and {entities_map.get('location', 0)} locations. "
            f"There are {stats.get('timeline_events', 0)} timeline events."
        )

    # For "who appears most" type queries — inject top entity ranking
    ranking_keywords = ["most", "frequently", "appears", "common", "often"]
    if any(kw in _searchable for kw in ranking_keywords):
        top_people = search_entities("", entity_type="person", limit=10)
        if top_people:
            ranking = "; ".join(f"{p.entity_value} ({p.asset_count} assets)" for p in top_people[:10])
            result.raw_facts.append(f"Top people by asset count: {ranking}")

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

def _format_composer_prompt(question: str, context: str) -> str:
    return COMPOSER_PROMPT.replace("<<QUESTION>>", question).replace("<<CONTEXT>>", context)


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

    # Entities — always include when present (locations, dates, people not in profiles)
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
