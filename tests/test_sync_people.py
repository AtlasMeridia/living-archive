"""Tests for people sync queue prioritization helpers."""

from src.models import PeopleRegistry, Person
from src.sync_people import _apply_csv_row, _asset_hint_from_notes, _parse_birth_year, _queue_rows


def test_asset_hint_from_notes():
    assert _asset_hint_from_notes("Auto-imported from Immich (2485 assets)") == 2485
    assert _asset_hint_from_notes("No asset count in this note") == 0


def test_queue_rows_unknown_first_by_asset_hint():
    registry = PeopleRegistry(
        version=1,
        people=[
            Person(
                person_id="named",
                name_en="Alice",
                notes="Auto-imported from Immich (20 assets)",
                immich_person_ids=["immich-named"],
            ),
            Person(
                person_id="unknown-big",
                notes="Auto-imported from Immich (200 assets)",
                immich_person_ids=["immich-big"],
            ),
            Person(
                person_id="unknown-small",
                notes="Auto-imported from Immich (80 assets)",
            ),
        ],
    )

    rows = _queue_rows(registry, include_named=False)
    assert [r["person_id"] for r in rows] == ["unknown-big", "unknown-small"]
    assert rows[0]["immich_person_id"] == "immich-big"
    assert rows[0]["asset_count_hint"] == 200


def test_queue_rows_include_named_flag():
    registry = PeopleRegistry(
        version=1,
        people=[
            Person(person_id="named", name_zh="王小明", notes="Auto-imported from Immich (20 assets)"),
            Person(person_id="unknown", notes="Auto-imported from Immich (50 assets)"),
        ],
    )

    rows = _queue_rows(registry, include_named=True)
    assert [r["person_id"] for r in rows] == ["unknown", "named"]


def test_parse_birth_year():
    assert _parse_birth_year("1942") == 1942
    assert _parse_birth_year("") is None
    assert _parse_birth_year("unknown") is None


def test_apply_csv_row_updates_non_empty_fields():
    person = Person(
        person_id="p1",
        name_en="",
        name_zh="",
        relationship="",
        notes="Auto-imported from Immich (50 assets)",
        birth_year=None,
    )
    row = {
        "name_en": "Feng Kuang Liu",
        "name_zh": "劉逢光",
        "relationship": "grandfather",
        "birth_year": "1930",
        "notes": "Confirmed by elder session",
    }

    changed = _apply_csv_row(person, row)
    assert changed == ["name_en", "name_zh", "relationship", "notes", "birth_year"]
    assert person.name_en == "Feng Kuang Liu"
    assert person.name_zh == "劉逢光"
    assert person.relationship == "grandfather"
    assert person.birth_year == 1930
    assert person.notes == "Confirmed by elder session"


def test_apply_csv_row_ignores_empty_values():
    person = Person(person_id="p2", name_en="Existing Name")
    row = {"name_en": "", "name_zh": "", "relationship": "", "birth_year": ""}
    changed = _apply_csv_row(person, row)
    assert changed == []
    assert person.name_en == "Existing Name"
