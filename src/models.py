"""Pydantic models for photo and document manifest schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# --- Photo pipeline models ---


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


class InferenceMetadata(BaseModel):
    model: str = ""
    prompt_version: str = ""
    timestamp: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    raw_response: str | None = None


class PhotoManifest(BaseModel):
    source_file: str = ""
    source_sha256: str = ""
    analysis: PhotoAnalysis = PhotoAnalysis()
    inference: InferenceMetadata = InferenceMetadata()


# --- Document pipeline models ---


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


class DocumentExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text_file: str = ""


class DocumentInferenceMetadata(BaseModel):
    method: str = ""
    prompt_version: str = ""
    timestamp: str = ""


class DocumentManifest(BaseModel):
    source_file: str = ""
    source_sha256: str = ""
    file_size_bytes: int = 0
    page_count: int = 0
    extraction: DocumentExtraction = DocumentExtraction()
    analysis: DocumentAnalysis = DocumentAnalysis()
    inference: DocumentInferenceMetadata = DocumentInferenceMetadata()
