"""Tests for manifest.py: write + load round-trip, atomic writes."""

import json

from src.manifest import load_manifest, write_manifest
from src.models import InferenceMetadata, PhotoAnalysis, PhotoManifest

# Patch the AI_LAYER_DIR to use tmp_path for tests
import src.config as config


class TestManifestRoundTrip:
    def test_write_and_load(self, tmp_path, monkeypatch):
        """Write a manifest and load it back — fields should survive round-trip."""
        monkeypatch.setattr(config, "AI_LAYER_DIR", tmp_path)

        analysis = PhotoAnalysis(
            date_estimate="1978-06",
            date_precision="month",
            date_confidence=0.7,
            description_en="A family photo.",
            tags=["family", "outdoor"],
        )
        inference = InferenceMetadata(
            model="claude-sonnet-4-20250514",
            prompt_version="photo_analysis_v1",
            input_tokens=1500,
            output_tokens=350,
            raw_response='{"date_estimate": "1978-06"}',
        )

        path = write_manifest(
            run_id="20250115T103000Z",
            source_file_rel="2009 Scanned Media/1978/photo001.tif",
            source_sha256="abcdef123456" + "0" * 52,
            analysis=analysis,
            inference=inference,
        )

        assert path.exists()
        assert path.name == "abcdef123456.json"

        loaded = load_manifest(path)
        assert isinstance(loaded, PhotoManifest)
        assert loaded.source_file == "2009 Scanned Media/1978/photo001.tif"
        assert loaded.analysis.date_estimate == "1978-06"
        assert loaded.analysis.date_confidence == 0.7
        assert loaded.inference.model == "claude-sonnet-4-20250514"
        assert loaded.inference.raw_response == '{"date_estimate": "1978-06"}'

    def test_write_creates_directory(self, tmp_path, monkeypatch):
        """write_manifest should create the run directory if it doesn't exist."""
        monkeypatch.setattr(config, "AI_LAYER_DIR", tmp_path)

        analysis = PhotoAnalysis(date_estimate="1980")
        inference = InferenceMetadata(model="test")

        path = write_manifest(
            run_id="20250115T120000Z",
            source_file_rel="test.tif",
            source_sha256="a" * 64,
            analysis=analysis,
            inference=inference,
        )

        assert path.exists()
        assert "20250115T120000Z" in str(path)

    def test_atomic_write_no_temp_files(self, tmp_path, monkeypatch):
        """After a successful write, no .tmp files should remain."""
        monkeypatch.setattr(config, "AI_LAYER_DIR", tmp_path)

        analysis = PhotoAnalysis()
        inference = InferenceMetadata()

        write_manifest(
            run_id="20250115T130000Z",
            source_file_rel="test.tif",
            source_sha256="b" * 64,
            analysis=analysis,
            inference=inference,
        )

        run_dir = tmp_path / "runs" / "20250115T130000Z" / "manifests"
        tmp_files = list(run_dir.glob("*.tmp"))
        assert tmp_files == []

    def test_manifest_has_timestamp(self, tmp_path, monkeypatch):
        """Written manifest should have an inference timestamp."""
        monkeypatch.setattr(config, "AI_LAYER_DIR", tmp_path)

        path = write_manifest(
            run_id="20250115T140000Z",
            source_file_rel="test.tif",
            source_sha256="c" * 64,
            analysis=PhotoAnalysis(),
            inference=InferenceMetadata(),
        )

        data = json.loads(path.read_text())
        assert "timestamp" in data["inference"]
        assert data["inference"]["timestamp"]  # not empty
