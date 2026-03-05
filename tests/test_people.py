"""Unit tests for people registry path resolution."""

import json

from src import people
from src.models import PeopleRegistry


def test_load_registry_prefers_canonical_path(tmp_path, monkeypatch):
    canonical = tmp_path / "data" / "people" / "registry.json"
    legacy = tmp_path / "data" / "photos" / "people" / "registry.json"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    legacy.parent.mkdir(parents=True, exist_ok=True)

    canonical.write_text(json.dumps({"version": 1, "people": [{"person_id": "canonical"}]}))
    legacy.write_text(json.dumps({"version": 1, "people": [{"person_id": "legacy"}]}))

    monkeypatch.setattr(people, "REGISTRY_PATH", canonical)
    monkeypatch.setattr(people, "LEGACY_REGISTRY_PATH", legacy)

    registry = people.load_registry()
    assert len(registry.people) == 1
    assert registry.people[0].person_id == "canonical"


def test_load_registry_falls_back_to_legacy_path(tmp_path, monkeypatch):
    canonical = tmp_path / "data" / "people" / "registry.json"
    legacy = tmp_path / "data" / "photos" / "people" / "registry.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"version": 1, "people": [{"person_id": "legacy"}]}))

    monkeypatch.setattr(people, "REGISTRY_PATH", canonical)
    monkeypatch.setattr(people, "LEGACY_REGISTRY_PATH", legacy)

    registry = people.load_registry()
    assert len(registry.people) == 1
    assert registry.people[0].person_id == "legacy"


def test_save_registry_writes_canonical_path(tmp_path, monkeypatch):
    canonical_dir = tmp_path / "data" / "people"
    canonical = canonical_dir / "registry.json"

    monkeypatch.setattr(people, "PEOPLE_DIR", canonical_dir)
    monkeypatch.setattr(people, "REGISTRY_PATH", canonical)

    registry = PeopleRegistry(version=1, people=[])
    out_path = people.save_registry(registry)
    assert out_path == canonical
    assert canonical.exists()
