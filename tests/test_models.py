"""Tests for Pydantic models: validation, defaults, serialization."""

import json

import pytest
from pydantic import ValidationError

from src.models import (
    DocumentAnalysis,
    DocumentManifest,
    InferenceMetadata,
    PhotoAnalysis,
    PhotoManifest,
    Sensitivity,
)


class TestPhotoAnalysis:
    def test_valid_data(self, sample_photo_json):
        pa = PhotoAnalysis.model_validate(sample_photo_json)
        assert pa.date_estimate == "1978-06"
        assert pa.date_confidence == 0.7
        assert pa.people_count == 5
        assert "family" in pa.tags

    def test_missing_optional_fields(self):
        """Fields should have defaults — minimal data should validate."""
        pa = PhotoAnalysis.model_validate({})
        assert pa.date_estimate == ""
        assert pa.date_confidence == 0.0
        assert pa.tags == []
        assert pa.people_count is None

    def test_extra_fields_ignored(self):
        """extra='ignore' should silently drop unknown fields."""
        pa = PhotoAnalysis.model_validate({
            "date_estimate": "1980",
            "unknown_field": "should be ignored",
            "another_extra": 42,
        })
        assert pa.date_estimate == "1980"
        assert not hasattr(pa, "unknown_field")

    def test_round_trip_serialization(self, sample_photo_json):
        pa = PhotoAnalysis.model_validate(sample_photo_json)
        dumped = pa.model_dump()
        pa2 = PhotoAnalysis.model_validate(dumped)
        assert pa == pa2

    def test_json_round_trip(self, sample_photo_json):
        """Validate from JSON string and back."""
        json_str = json.dumps(sample_photo_json)
        pa = PhotoAnalysis.model_validate_json(json_str)
        assert pa.date_estimate == "1978-06"
        json_out = pa.model_dump_json()
        pa2 = PhotoAnalysis.model_validate_json(json_out)
        assert pa == pa2


class TestInferenceMetadata:
    def test_valid_data(self):
        meta = InferenceMetadata(
            model="claude-sonnet-4-20250514",
            prompt_version="photo_analysis_v1",
            input_tokens=1500,
            output_tokens=350,
            raw_response='{"date_estimate": "1978"}',
        )
        assert meta.model == "claude-sonnet-4-20250514"
        assert meta.raw_response is not None

    def test_defaults(self):
        meta = InferenceMetadata()
        assert meta.model == ""
        assert meta.raw_response is None
        assert meta.input_tokens == 0


class TestPhotoManifest:
    def test_from_disk_format(self, sample_photo_manifest):
        m = PhotoManifest.model_validate(sample_photo_manifest)
        assert m.source_file == "2009 Scanned Media/1978/photo001.tif"
        assert m.analysis.date_estimate == "1978-06"
        assert m.inference.model == "claude-sonnet-4-20250514"

    def test_empty_manifest(self):
        m = PhotoManifest()
        assert m.source_file == ""
        assert m.analysis.date_estimate == ""

    def test_old_manifest_without_raw_response(self, sample_photo_manifest):
        """Old manifests won't have raw_response — should still load."""
        del sample_photo_manifest["inference"]["raw_response"]
        m = PhotoManifest.model_validate(sample_photo_manifest)
        assert m.inference.raw_response is None


class TestDocumentModels:
    def test_sensitivity(self):
        s = Sensitivity(has_ssn=True, has_financial=True)
        assert s.has_ssn is True
        assert s.has_medical is False

    def test_document_analysis(self, sample_document_json):
        da = DocumentAnalysis.model_validate(sample_document_json)
        assert da.document_type == "legal/trust"
        assert da.sensitivity.has_financial is True
        assert "John Liu" in da.key_people

    def test_document_analysis_extra_ignored(self):
        da = DocumentAnalysis.model_validate({
            "document_type": "legal/trust",
            "new_future_field": "should not break",
        })
        assert da.document_type == "legal/trust"

    def test_document_manifest_defaults(self):
        dm = DocumentManifest()
        assert dm.source_file == ""
        assert dm.page_count == 0
        assert dm.analysis.document_type == ""
