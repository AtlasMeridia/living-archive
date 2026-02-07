"""Tests for analyze.py: JSON fence stripping and CLI dispatch."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.analyze import strip_json_fences, _analyze_via_cli, _build_cli_prompt


class TestStripJsonFences:
    def test_clean_json(self):
        """Plain JSON should pass through unchanged."""
        raw = '{"date_estimate": "1978-06"}'
        assert strip_json_fences(raw) == raw

    def test_markdown_fenced_json(self):
        """```json ... ``` fences should be stripped."""
        raw = '```json\n{"date_estimate": "1978-06"}\n```'
        result = strip_json_fences(raw)
        parsed = json.loads(result)
        assert parsed["date_estimate"] == "1978-06"

    def test_markdown_fenced_no_language(self):
        """``` ... ``` fences without language tag should be stripped."""
        raw = '```\n{"key": "value"}\n```'
        result = strip_json_fences(raw)
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    def test_multiline_fenced_json(self):
        """Multi-line fenced JSON should be fully extracted."""
        raw = '```json\n{\n  "a": 1,\n  "b": 2\n}\n```'
        result = strip_json_fences(raw)
        parsed = json.loads(result)
        assert parsed == {"a": 1, "b": 2}

    def test_whitespace_around_json(self):
        """Leading/trailing whitespace should be trimmed."""
        raw = '  \n  {"key": "value"}  \n  '
        result = strip_json_fences(raw)
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    def test_malformed_json_raises(self):
        """Malformed JSON should raise when parsed."""
        raw = '```json\n{not valid json}\n```'
        result = strip_json_fences(raw)
        with pytest.raises(json.JSONDecodeError):
            json.loads(result)


class TestBuildCliPrompt:
    def test_includes_image_path(self, tmp_path):
        """CLI prompt should include the resolved image path."""
        jpeg = tmp_path / "test.jpg"
        jpeg.write_bytes(b"fake")
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Analyze this photo from {folder_hint}.")

        with patch("src.analyze.config") as mock_config:
            mock_config.PROMPT_FILE = prompt_file
            result = _build_cli_prompt(jpeg, "1978")

        assert str(jpeg.resolve()) in result
        assert "1978" in result


class TestAnalyzeViaCli:
    """Tests for CLI-based photo analysis with mocked subprocess."""

    FAKE_ENVELOPE = {
        "structured_output": {
            "date_estimate": "1978-06",
            "date_precision": "month",
            "date_confidence": 0.85,
            "date_reasoning": "Clothing style suggests late 1970s",
            "description_en": "Family photo in garden",
            "description_zh": "",
            "people_count": 3,
            "people_notes": "",
            "location_estimate": "",
            "location_confidence": 0.0,
            "tags": ["family", "outdoor"],
        },
        "usage": {"input_tokens": 1500, "output_tokens": 200},
        "model": "claude-sonnet-4-5-20250929",
    }

    @patch("src.analyze.subprocess.run")
    @patch("src.analyze.config")
    def test_success(self, mock_config, mock_run, tmp_path):
        """Successful CLI call returns PhotoAnalysis and InferenceMetadata."""
        jpeg = tmp_path / "test.jpg"
        jpeg.write_bytes(b"fake jpeg data")

        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Analyze from {folder_hint}.")
        mock_config.PROMPT_FILE = prompt_file
        mock_config.CLAUDE_CLI = Path("/usr/local/bin/claude")
        mock_config.CLI_MODEL = "sonnet"
        mock_config.PROMPT_VERSION = "photo_analysis_v1"

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(self.FAKE_ENVELOPE),
            stderr="",
        )

        analysis, meta = _analyze_via_cli(jpeg, "1978")

        assert analysis.date_estimate == "1978-06"
        assert analysis.date_confidence == 0.85
        assert analysis.tags == ["family", "outdoor"]
        assert meta.input_tokens == 1500
        assert meta.output_tokens == 200
        assert meta.model == "claude-sonnet-4-5-20250929"

        # Verify subprocess was called with expected args
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "--output-format" in cmd
        assert "--json-schema" in cmd
        assert "--no-session-persistence" in cmd

    @patch("src.analyze.subprocess.run")
    @patch("src.analyze.config")
    def test_nonzero_exit_raises(self, mock_config, mock_run, tmp_path):
        """Non-zero exit code should raise RuntimeError."""
        jpeg = tmp_path / "test.jpg"
        jpeg.write_bytes(b"fake")

        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Analyze from {folder_hint}.")
        mock_config.PROMPT_FILE = prompt_file
        mock_config.CLAUDE_CLI = Path("/usr/local/bin/claude")
        mock_config.CLI_MODEL = "sonnet"

        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error: something went wrong",
        )

        with pytest.raises(RuntimeError, match="exited with code 1"):
            _analyze_via_cli(jpeg, "1978")

    @patch("src.analyze.subprocess.run")
    @patch("src.analyze.config")
    def test_timeout_raises(self, mock_config, mock_run, tmp_path):
        """Subprocess timeout should propagate."""
        jpeg = tmp_path / "test.jpg"
        jpeg.write_bytes(b"fake")

        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Analyze from {folder_hint}.")
        mock_config.PROMPT_FILE = prompt_file
        mock_config.CLAUDE_CLI = Path("/usr/local/bin/claude")
        mock_config.CLI_MODEL = "sonnet"

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)

        with pytest.raises(subprocess.TimeoutExpired):
            _analyze_via_cli(jpeg, "1978")

    @patch("src.analyze.subprocess.run")
    @patch("src.analyze.config")
    def test_invalid_json_raises(self, mock_config, mock_run, tmp_path):
        """Invalid JSON stdout should raise JSONDecodeError."""
        jpeg = tmp_path / "test.jpg"
        jpeg.write_bytes(b"fake")

        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Analyze from {folder_hint}.")
        mock_config.PROMPT_FILE = prompt_file
        mock_config.CLAUDE_CLI = Path("/usr/local/bin/claude")
        mock_config.CLI_MODEL = "sonnet"

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="not valid json",
            stderr="",
        )

        with pytest.raises(json.JSONDecodeError):
            _analyze_via_cli(jpeg, "1978")
