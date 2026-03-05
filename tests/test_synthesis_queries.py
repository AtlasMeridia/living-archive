"""Unit tests for shared synthesis query helpers."""

import json
import sqlite3

from src import synthesis_queries


def _seed_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE entities (
            entity_id INTEGER PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_value TEXT NOT NULL,
            normalized_value TEXT NOT NULL,
            name_zh TEXT,
            metadata TEXT
        );
        CREATE TABLE entity_assets (
            entity_id INTEGER NOT NULL,
            asset_sha256 TEXT NOT NULL,
            source TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            context TEXT
        );
        CREATE TABLE timeline_events (
            event_id INTEGER PRIMARY KEY,
            date_normalized TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        INSERT INTO entities (entity_id, entity_type, entity_value, normalized_value, name_zh, metadata)
        VALUES (1, 'person', 'Feng Kuang Liu', 'feng kuang liu', '劉逢光', ?)
        """,
        (json.dumps({"family_role": "grandfather"}),),
    )
    conn.execute(
        """
        INSERT INTO entities (entity_id, entity_type, entity_value, normalized_value)
        VALUES (2, 'date', '1978', '1978')
        """
    )
    conn.execute(
        """
        INSERT INTO entities (entity_id, entity_type, entity_value, normalized_value)
        VALUES (3, 'location', 'Taiwan', 'taiwan')
        """
    )
    conn.execute(
        """
        INSERT INTO entities (entity_id, entity_type, entity_value, normalized_value)
        VALUES (4, 'person', 'Unknown Cousin', 'unknown cousin')
        """
    )
    conn.execute(
        """
        INSERT INTO entity_assets (entity_id, asset_sha256, source, confidence, context)
        VALUES (1, 'aaa111', 'document', 1.0, 'will')
        """
    )
    conn.execute(
        """
        INSERT INTO entity_assets (entity_id, asset_sha256, source, confidence, context)
        VALUES (2, 'bbb222', 'vision', 0.7, NULL)
        """
    )
    conn.execute(
        """
        INSERT INTO entity_assets (entity_id, asset_sha256, source, confidence, context)
        VALUES (3, 'ccc333', 'vision', 0.6, 'Taipei, Taiwan')
        """
    )
    conn.execute(
        """
        INSERT INTO entity_assets (entity_id, asset_sha256, source, confidence, context)
        VALUES (4, 'ddd444', 'document', 0.9, 'letter')
        """
    )
    conn.execute(
        """
        INSERT INTO timeline_events (event_id, date_normalized)
        VALUES (1, '1978')
        """
    )
    conn.commit()
    return conn


def test_query_person_entity():
    conn = _seed_conn()
    person = synthesis_queries.query_person_entity(conn, "Feng")
    assert person is not None
    assert person["entity_value"] == "Feng Kuang Liu"
    assert person["name_zh"] == "劉逢光"
    assert person["family_role"] == "grandfather"
    assert len(person["links"]) == 1
    assert person["links"][0]["asset_sha256"] == "aaa111"
    conn.close()


def test_query_date_entities():
    conn = _seed_conn()
    result = synthesis_queries.query_date_entities(conn, "1978")
    assert result is not None
    assert result["dates_matched"] == ["1978"]
    assert len(result["links"]) == 1
    assert result["links"][0]["asset_sha256"] == "bbb222"
    conn.close()


def test_query_location_entity():
    conn = _seed_conn()
    result = synthesis_queries.query_location_entity(conn, "tai")
    assert result is not None
    assert result["location"] == "Taiwan"
    assert len(result["links"]) == 1
    assert result["links"][0]["context"] == "Taipei, Taiwan"
    conn.close()


def test_query_overview_and_chronology(monkeypatch, tmp_path):
    conn = _seed_conn()
    overview = synthesis_queries.query_overview(conn)
    assert overview["total_entities"] == 4
    assert overview["entity_asset_links"] == 4
    assert overview["timeline_events"] == 1
    assert overview["resolved_people"] == 1
    assert overview["unresolved_people"] == 1
    assert overview["top_unresolved"][0]["entity_value"] == "Unknown Cousin"
    conn.close()

    monkeypatch.setattr(synthesis_queries.config, "DATA_DIR", tmp_path)
    assert synthesis_queries.chronology_metadata()["exists"] is False

    payload = {
        "generated_at": "2026-03-04T00:00:00Z",
        "decade_count": 1,
        "total_events": 2,
        "decades": [],
    }
    (tmp_path / "chronology.json").write_text(json.dumps(payload))
    meta = synthesis_queries.chronology_metadata()
    assert meta["exists"] is True
    assert meta["meta"]["decade_count"] == 1
    assert meta["meta"]["quality"] == {}
    full = synthesis_queries.chronology_payload()
    assert full["available"] is True
    assert full["total_events"] == 2


def test_query_unresolved_people():
    conn = _seed_conn()
    rows = synthesis_queries.query_unresolved_people(conn)
    assert len(rows) == 1
    assert rows[0]["entity_value"] == "Unknown Cousin"
    assert rows[0]["asset_count"] == 1
    conn.close()
