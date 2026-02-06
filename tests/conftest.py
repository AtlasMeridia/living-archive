"""Shared fixtures for Living Archive tests."""

import pytest


@pytest.fixture
def sample_photo_json() -> dict:
    """A valid photo analysis JSON matching the prompt schema."""
    return {
        "date_estimate": "1978-06",
        "date_precision": "month",
        "date_confidence": 0.7,
        "date_reasoning": "Folder hint says 1978; clothing style consistent with late 1970s.",
        "description_en": "A family portrait taken outdoors. Three adults and two children standing in front of a house.",
        "description_zh": "一張在戶外拍攝的家庭合照。三位成人和兩位小孩站在房子前方。",
        "people_count": 5,
        "people_notes": "Two adults in their 30s-40s, one elderly person, two young children.",
        "location_estimate": "Taiwan",
        "location_confidence": 0.6,
        "tags": ["family", "portrait", "outdoor", "group"],
        "condition_notes": None,
        "ocr_text": None,
        "is_document": False,
    }


@pytest.fixture
def sample_document_json() -> dict:
    """A valid document analysis JSON matching the prompt schema."""
    return {
        "document_type": "legal/trust",
        "title": "Liu Family Living Trust Agreement",
        "date": "1995-03-15",
        "date_confidence": 0.95,
        "summary_en": "Living trust agreement establishing the Liu Family Trust. Names John and Mary Liu as co-trustees.",
        "summary_zh": "劉家生前信託協議，設立劉家信託。指定John和Mary Liu為共同受託人。",
        "key_people": ["John Liu", "Mary Liu"],
        "key_dates": ["1995-03-15"],
        "sensitivity": {
            "has_ssn": False,
            "has_financial": True,
            "has_medical": False,
        },
        "tags": ["legal", "trust", "estate-planning"],
        "language": "English",
        "quality": "good",
    }


@pytest.fixture
def sample_photo_manifest(sample_photo_json) -> dict:
    """A full photo manifest dict as stored on disk."""
    return {
        "source_file": "2009 Scanned Media/1978/photo001.tif",
        "source_sha256": "abcdef123456abcdef123456abcdef123456abcdef123456abcdef123456abcd",
        "analysis": sample_photo_json,
        "inference": {
            "model": "claude-sonnet-4-20250514",
            "prompt_version": "photo_analysis_v1",
            "timestamp": "2025-01-15T10:30:00+00:00",
            "input_tokens": 1500,
            "output_tokens": 350,
            "raw_response": None,
        },
    }
