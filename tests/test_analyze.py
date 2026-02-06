"""Tests for analyze.py: JSON fence stripping."""

import json

import pytest

from src.analyze import strip_json_fences


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
