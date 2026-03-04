"""Tests for run_batch triage integration helpers."""

import json
from pathlib import Path

import pytest

import src.config as config
from src.run_batch import (
    filter_sources_by_triage,
    load_triage_for_slice,
    process_slice,
)


def test_load_triage_for_slice_prefers_exact_slice_match(tmp_path, monkeypatch):
    """Exact album match should beat generic album-name matches."""
    triage_dir = tmp_path / "triage"
    triage_dir.mkdir(parents=True)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    exact_path = triage_dir / "round_a_Red_Album_1_triage.json"
    exact_path.write_text(json.dumps({
        "album": "round-a/Red_Album_1",
        "keep": ["a.jpg"],
        "skip": ["b.jpg"],
    }))

    generic_path = triage_dir / "Red_Album_1_triage.json"
    generic_path.write_text(json.dumps({
        "album": "Red_Album_1",
        "keep": ["x.jpg"],
        "skip": [],
    }))

    triage, triage_file = load_triage_for_slice("round-a/Red_Album_1")

    assert triage is not None
    assert triage_file is not None
    assert triage_file.name == exact_path.name
    assert triage["album"] == "round-a/Red_Album_1"


def test_load_triage_for_slice_missing_returns_none(tmp_path, monkeypatch):
    """Missing triage directory or file should return (None, None)."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    triage, triage_file = load_triage_for_slice("missing/slice")
    assert triage is None
    assert triage_file is None


def test_filter_sources_by_triage_prefers_keep(tmp_path):
    """If keep is present, keep list should drive filtering."""
    sources = [tmp_path / "1.jpg", tmp_path / "2.jpg", tmp_path / "3.jpg"]
    triage_data = {"keep": ["1.jpg", "3.jpg"], "skip": ["1.jpg", "2.jpg", "3.jpg"]}

    filtered, skipped = filter_sources_by_triage(sources, triage_data)

    assert [p.name for p in filtered] == ["1.jpg", "3.jpg"]
    assert skipped == 1


def test_filter_sources_by_triage_uses_skip_when_keep_empty(tmp_path):
    """Skip list is used when keep is not provided."""
    sources = [tmp_path / "1.jpg", tmp_path / "2.jpg", tmp_path / "3.jpg"]
    triage_data = {"skip": ["2.jpg"]}

    filtered, skipped = filter_sources_by_triage(sources, triage_data)

    assert [p.name for p in filtered] == ["1.jpg", "3.jpg"]
    assert skipped == 1


def test_process_slice_require_triage_raises_when_missing(tmp_path, monkeypatch):
    """triage_mode=require should fail fast when no matching triage file exists."""
    album_dir = tmp_path / "album"
    album_dir.mkdir()

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "MEDIA_ROOT", tmp_path)
    monkeypatch.setattr(config, "AI_LAYER_DIR", tmp_path / "photos")
    monkeypatch.setattr(config, "WORKSPACE_DIR", tmp_path / "workspace")
    monkeypatch.setattr("src.run_batch.find_photos", lambda _: [album_dir / "a.jpg"])

    with pytest.raises(RuntimeError, match="Required triage file not found"):
        process_slice(
            slice_path="album",
            slice_dir=album_dir,
            run_id="20260304T000000Z",
            budget_remaining=3600,
            push=False,
            triage_mode="require",
        )
