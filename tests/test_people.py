"""Unit tests for people registry save/load."""

from src import people
from src.models import PeopleRegistry


def test_save_registry_writes_canonical_path(tmp_path, monkeypatch):
    canonical_dir = tmp_path / "data" / "people"
    canonical = canonical_dir / "registry.json"

    monkeypatch.setattr(people, "PEOPLE_DIR", canonical_dir)
    monkeypatch.setattr(people, "REGISTRY_PATH", canonical)

    registry = PeopleRegistry(version=1, people=[])
    out_path = people.save_registry(registry)
    assert out_path == canonical
    assert canonical.exists()


def test_load_registry_returns_empty_when_missing(tmp_path, monkeypatch):
    missing = tmp_path / "nope" / "registry.json"
    monkeypatch.setattr(people, "REGISTRY_PATH", missing)

    registry = people.load_registry()
    assert len(registry.people) == 0
