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


def test_api_update_person_saves_and_returns(monkeypatch, tmp_path):
    from src.people import save_registry

    reg = _registry(
        Person(person_id="p1", immich_person_ids=["id-1"], notes="Auto-imported from Immich (50 assets)"),
    )
    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr("src.people.REGISTRY_PATH", reg_path)
    monkeypatch.setattr("src.people.PEOPLE_DIR", tmp_path)
    save_registry(reg)

    monkeypatch.setattr("src.dashboard_api._immich_quick_check", lambda timeout=1.5: False)

    result = dashboard_api.api_update_person("p1", {
        "name_en": "Alice Liu",
        "name_zh": "劉愛麗",
        "relationship": "grandmother",
        "birth_year": "1938",
    })
    assert result["ok"] is True
    assert set(result["changed"]) == {"name_en", "name_zh", "relationship", "birth_year"}
    assert result["person"]["name_en"] == "Alice Liu"
    assert result["person"]["birth_year"] == 1938
    assert result["pushed_to_immich"] is False


def test_api_update_person_not_found(monkeypatch, tmp_path):
    from src.people import save_registry

    reg = _registry()
    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr("src.people.REGISTRY_PATH", reg_path)
    monkeypatch.setattr("src.people.PEOPLE_DIR", tmp_path)
    save_registry(reg)

    result = dashboard_api.api_update_person("nonexistent", {"name_en": "Foo"})
    assert result["ok"] is False
