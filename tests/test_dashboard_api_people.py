"""Tests for dashboard people API fail-open behavior."""

from src import dashboard_api
from src.models import PeopleRegistry, Person


def _registry(*people: Person) -> PeopleRegistry:
    return PeopleRegistry(version=1, people=list(people))


def test_api_people_uses_registry_when_immich_offline(monkeypatch):
    monkeypatch.setattr("src.dashboard_api._immich_quick_check", lambda timeout=1.5: False)
    monkeypatch.setattr(
        "src.people.load_registry",
        lambda: _registry(
            Person(person_id="p1", name_en="Alice", immich_person_ids=["id-1"]),
            Person(person_id="p2", name_zh="王小明", immich_person_ids=[]),
            Person(person_id="p3"),
        ),
    )

    data = dashboard_api.api_people()
    assert data["immich_available"] is False
    assert data["registry_count"] == 3
    assert data["total_clusters"] == 3
    assert data["named"] == 2
    assert data["unnamed"] == 1
    assert len(data["people"]) == 3


def test_api_people_enriches_from_immich_list_people(monkeypatch):
    monkeypatch.setattr("src.dashboard_api._immich_quick_check", lambda timeout=1.5: True)
    monkeypatch.setattr(
        "src.people.load_registry",
        lambda: _registry(
            Person(person_id="p1", immich_person_ids=["id-1"]),
            Person(person_id="p2", immich_person_ids=["id-2"]),
        ),
    )

    class _FakeClient:
        def close(self):
            return None

    monkeypatch.setattr("src.immich._client", lambda: _FakeClient())
    monkeypatch.setattr(
        "src.immich.list_people",
        lambda client: [
            {"id": "id-1", "assetCount": 11},
            {"id": "id-2", "assets": 7},
            {"id": "id-3", "faceCount": 2},
        ],
    )

    data = dashboard_api.api_people()
    assert data["immich_available"] is True
    assert data["registry_count"] == 2
    assert data["total_clusters"] == 3
    assert data["named"] == 0
    assert data["unnamed"] == 3
    assert data["people"][0]["photo_count"] == 11
    assert data["people"][1]["photo_count"] == 7


def test_api_people_uses_registry_asset_hints_and_sorts_unknown_first(monkeypatch):
    monkeypatch.setattr("src.dashboard_api._immich_quick_check", lambda timeout=1.5: False)
    monkeypatch.setattr(
        "src.people.load_registry",
        lambda: _registry(
            Person(person_id="p1", name_en="Named", notes="Auto-imported from Immich (20 assets)"),
            Person(person_id="p2", notes="Auto-imported from Immich (200 assets)"),
            Person(person_id="p3", notes="Auto-imported from Immich (80 assets)"),
        ),
    )

    data = dashboard_api.api_people()
    assert data["people"][0]["person_id"] == "p2"
    assert data["people"][0]["photo_count"] == 200
    assert data["people"][0]["photo_count_is_estimate"] is True
    assert data["people"][1]["person_id"] == "p3"
    assert data["people"][2]["person_id"] == "p1"
