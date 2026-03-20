"""Local copies of analysis schemas for experiment isolation.

These mirror src/models.py but are self-contained — the experiment
must not import from src/.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PhotoAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date_estimate: str = ""
    date_precision: str = ""
    date_confidence: float = 0.0
    date_reasoning: str = ""
    description_en: str = ""
    description_zh: str = ""
    people_count: int | None = None
    people_notes: str = ""
    location_estimate: str = ""
    location_confidence: float = 0.0
    tags: list[str] = []
    condition_notes: str | None = None
    ocr_text: str | None = None
    is_document: bool = False


class Sensitivity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    has_ssn: bool = False
    has_financial: bool = False
    has_medical: bool = False


class DocumentAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    document_type: str = ""
    title: str = ""
    date: str = ""
    date_confidence: float = 0.0
    summary_en: str = ""
    summary_zh: str = ""
    key_people: list[str] = []
    key_dates: list[str] = []
    sensitivity: Sensitivity = Sensitivity()
    tags: list[str] = []
    language: str = ""
    quality: str = ""


def make_openai_strict(schema: dict) -> dict:
    """Recursively fix a Pydantic JSON Schema for OpenAI strict mode.

    Adds additionalProperties: false and explicit required arrays.
    Removes default values. Required for Codex CLI --output-schema.
    """
    if schema.get("type") == "object" and "properties" in schema:
        schema["additionalProperties"] = False
        schema["required"] = list(schema["properties"].keys())
        for prop in schema["properties"].values():
            prop.pop("default", None)
            make_openai_strict(prop)
    if "items" in schema:
        make_openai_strict(schema["items"])
    for defn in schema.get("$defs", {}).values():
        make_openai_strict(defn)
    return schema
