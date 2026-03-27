"""Test question bank with ground truth for evaluation.

Three tiers:
  Easy   — single fact, direct lookup
  Medium — multi-source aggregation
  Hard   — narrative synthesis across photos and documents
"""

from dataclasses import dataclass, field


@dataclass
class TestQuestion:
    id: str
    tier: str  # easy, medium, hard
    question: str
    # Ground truth facts that a correct answer MUST contain
    required_facts: list[str]
    # Facts that SHOULD appear if the data supports them
    bonus_facts: list[str] = field(default_factory=list)
    # Expected data sources (for grounding check)
    expected_sources: list[str] = field(default_factory=list)


# --- Easy: Single fact, direct lookup ---

EASY_QUESTIONS = [
    TestQuestion(
        id="e01",
        tier="easy",
        question="When was Feng Kuang Liu born?",
        required_facts=["January 23, 1943"],
        expected_sources=["death certificate", "medical records"],
    ),
    TestQuestion(
        id="e02",
        tier="easy",
        question="When did Feng Kuang Liu die?",
        required_facts=["June 6, 2010"],
        bonus_facts=["age 67", "Lahey Clinic", "Peabody"],
        expected_sources=["death certificate"],
    ),
    TestQuestion(
        id="e03",
        tier="easy",
        question="What was Feng Kuang Liu's occupation?",
        required_facts=["engineer"],
        expected_sources=["death certificate"],
    ),
    TestQuestion(
        id="e04",
        tier="easy",
        question="Who are the children of Feng Kuang Liu?",
        required_facts=["Kenny Peng Liu", "Karen Peling Liu"],
        expected_sources=["trust documents", "court filings"],
    ),
    TestQuestion(
        id="e05",
        tier="easy",
        question="How many photos are in the archive?",
        required_facts=["2075"],
        bonus_facts=["2196 total assets", "121 documents"],
        expected_sources=["catalog"],
    ),
    TestQuestion(
        id="e06",
        tier="easy",
        question="How many documents are in the archive?",
        required_facts=["121"],
        expected_sources=["catalog"],
    ),
    TestQuestion(
        id="e07",
        tier="easy",
        question="Who is Meichu Grace Liu?",
        required_facts=["Meichu Grace Liu"],
        bonus_facts=["wife", "Feng Kuang", "Liu family"],
        expected_sources=["documents", "synthesis"],
    ),
    TestQuestion(
        id="e08",
        tier="easy",
        question="What is the Liu Family Trust?",
        required_facts=["trust"],
        bonus_facts=["Karen Peling Liu", "Kenny Peng Liu", "successor trustee"],
        expected_sources=["trust documents"],
    ),
    TestQuestion(
        id="e09",
        tier="easy",
        question="Where did the Liu family live?",
        required_facts=["California"],
        bonus_facts=["Los Altos", "Taiwan", "United States"],
        expected_sources=["documents", "photos"],
    ),
    TestQuestion(
        id="e10",
        tier="easy",
        question="Who filed the probate petition for the Liu Family Trust?",
        required_facts=["Karen Peling Liu", "Kenny Peng Liu"],
        bonus_facts=["Santa Clara County", "2011"],
        expected_sources=["court filings"],
    ),
]


# --- Medium: Multi-source aggregation ---

MEDIUM_QUESTIONS = [
    TestQuestion(
        id="m01",
        tier="medium",
        question="Tell me about Feng Kuang Liu.",
        required_facts=["born 1943", "engineer", "died 2010"],
        bonus_facts=["Taiwan", "Los Altos", "Meichu", "Kenny", "Karen", "photos"],
        expected_sources=["death certificate", "medical records", "photos", "trust documents"],
    ),
    TestQuestion(
        id="m02",
        tier="medium",
        question="What happened in 2010 for the Liu family?",
        required_facts=["Feng Kuang Liu died", "June 2010"],
        bonus_facts=["successor trustee", "trust administration", "probate"],
        expected_sources=["death certificate", "trust documents"],
    ),
    TestQuestion(
        id="m03",
        tier="medium",
        question="What legal documents are in the archive?",
        required_facts=["trust", "court", "probate"],
        bonus_facts=["death certificate", "medical records", "wire transfer"],
        expected_sources=["documents"],
    ),
    TestQuestion(
        id="m04",
        tier="medium",
        question="What do the medical records tell us about Feng Kuang Liu?",
        required_facts=["medical"],
        bonus_facts=["Palo Alto", "Camino", "2001", "2010"],
        expected_sources=["medical records"],
    ),
    TestQuestion(
        id="m05",
        tier="medium",
        question="What decades are represented in the photo collection?",
        required_facts=["1970s"],
        bonus_facts=["1940s", "1980s", "1990s", "2000s"],
        expected_sources=["photos", "timeline"],
    ),
    TestQuestion(
        id="m06",
        tier="medium",
        question="Who appears most often in the archive?",
        required_facts=["Feng Kuang Liu"],
        bonus_facts=["Meichu Grace Liu", "Kenny Peng Liu", "Karen Peling Liu", "90"],
        expected_sources=["synthesis"],
    ),
    TestQuestion(
        id="m07",
        tier="medium",
        question="What locations are associated with the Liu family?",
        required_facts=["Taiwan"],
        bonus_facts=["United States", "Hong Kong", "California", "Los Altos"],
        expected_sources=["synthesis", "documents"],
    ),
    TestQuestion(
        id="m08",
        tier="medium",
        question="What can you tell me about the family's connection to Taiwan?",
        required_facts=["Taiwan"],
        bonus_facts=["born", "Feng Kuang", "photos"],
        expected_sources=["documents", "photos", "synthesis"],
    ),
    TestQuestion(
        id="m09",
        tier="medium",
        question="How was the Liu family trust administered after Feng Kuang's death?",
        required_facts=["successor trustee", "Karen", "Kenny"],
        bonus_facts=["Santa Clara County", "probate", "Heggstad"],
        expected_sources=["trust documents", "court filings"],
    ),
    TestQuestion(
        id="m10",
        tier="medium",
        question="What types of photos are in the archive?",
        required_facts=["family"],
        bonus_facts=["scanned", "albums", "wedding", "FastFoto", "digital"],
        expected_sources=["photos", "catalog"],
    ),
]


# --- Hard: Narrative synthesis ---

HARD_QUESTIONS = [
    TestQuestion(
        id="h01",
        tier="hard",
        question="Tell me everything you know about Feng Kuang Liu.",
        required_facts=["Feng Kuang Liu", "born", "died"],
        bonus_facts=["1943", "2010", "engineer", "Taiwan", "photos", "documents"],
        expected_sources=["synthesis", "documents", "photos"],
    ),
    TestQuestion(
        id="h02",
        tier="hard",
        question="What was life like for the Liu family in the 1970s?",
        required_facts=["1970s", "photo"],
        bonus_facts=["Las Vegas", "wedding", "family"],
        expected_sources=["photos", "timeline"],
    ),
    TestQuestion(
        id="h03",
        tier="hard",
        question="What is the story of this family?",
        required_facts=["Liu", "Taiwan", "California"],
        bonus_facts=["Feng Kuang", "Meichu", "trust", "photos", "decades"],
        expected_sources=["synthesis", "documents", "photos", "timeline"],
    ),
    TestQuestion(
        id="h04",
        tier="hard",
        question="What do we know about the family's financial and legal history?",
        required_facts=["trust", "Liu Family Trust"],
        bonus_facts=["probate", "wire transfer", "real estate", "insurance"],
        expected_sources=["documents"],
    ),
    TestQuestion(
        id="h05",
        tier="hard",
        question="How has the archive been built? What are its strengths and gaps?",
        required_facts=["photos", "documents"],
        bonus_facts=["2075", "121", "scanned", "synthesis", "unresolved"],
        expected_sources=["catalog", "synthesis"],
    ),
    TestQuestion(
        id="h06",
        tier="hard",
        question="What health issues did Feng Kuang Liu face?",
        required_facts=["medical"],
        bonus_facts=["diabetes", "Palo Alto", "2001", "2010", "Lahey Clinic"],
        expected_sources=["medical records", "death certificate"],
    ),
    TestQuestion(
        id="h07",
        tier="hard",
        question="What can you tell me about the women in this family?",
        required_facts=["Meichu Grace Liu"],
        bonus_facts=["Karen Peling Liu", "trustee", "photos"],
        expected_sources=["documents", "photos", "synthesis"],
    ),
    TestQuestion(
        id="h08",
        tier="hard",
        question="If I wanted to learn about my family history, where should I start in this archive?",
        required_facts=["photos", "documents"],
        bonus_facts=["timeline", "decades", "people", "trust"],
        expected_sources=["catalog", "synthesis", "timeline"],
    ),
    TestQuestion(
        id="h09",
        tier="hard",
        question="What patterns do you notice across the photos from different decades?",
        required_facts=["decades"],
        bonus_facts=["1940s", "1970s", "1980s", "2000s", "scanned"],
        expected_sources=["timeline", "photos"],
    ),
    TestQuestion(
        id="h10",
        tier="hard",
        question="Summarize everything the archive knows about 1943.",
        required_facts=["1943", "Feng Kuang Liu", "born"],
        bonus_facts=["January 23", "Taiwan"],
        expected_sources=["documents", "timeline", "synthesis"],
    ),
]


ALL_QUESTIONS = EASY_QUESTIONS + MEDIUM_QUESTIONS + HARD_QUESTIONS


def get_questions(tier: str = None) -> list[TestQuestion]:
    """Get test questions, optionally filtered by tier."""
    if tier is None:
        return ALL_QUESTIONS
    return [q for q in ALL_QUESTIONS if q.tier == tier]
