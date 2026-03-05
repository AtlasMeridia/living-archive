"""Unit tests for synthesis helpers in src.synthesis."""

import json
import sqlite3

from src import synthesis


def test_normalize_date_and_precision():
    assert synthesis.normalize_date("1978-03-15") == ("1978-03-15", "day")
    assert synthesis.normalize_date("1978-03") == ("1978-03", "month")
    assert synthesis.normalize_date("1978") == ("1978", "year")
    assert synthesis.normalize_date("1970s") == ("1970", "decade")


def test_date_to_decade():
    assert synthesis.date_to_decade("1978-03-15") == "1970s"
    assert synthesis.date_to_decade("2001") == "2000s"
    assert synthesis.date_to_decade("unknown") is None


def test_extract_countries():
    assert synthesis.extract_countries("Taipei, Taiwan") == ["Taiwan"]
    assert synthesis.extract_countries("Rome, Italy") == ["Italy"]
    # Multiple countries in one free-text location should all be captured.
    assert synthesis.extract_countries(
        "Mediterranean cruise from Italy to Spain"
    ) == ["Italy", "Spain"]


def test_normalize_person_name_strips_titles_and_annotations():
    assert synthesis.normalize_person_name("Dr. Feng-Kuang Liu (patient)") == "feng kuang liu"
    assert synthesis.normalize_person_name("M. Grace Liu (劉彭美珠)") == "m grace liu"


def test_label_group_key_compacts_numeric_variants():
    a = synthesis._label_group_key(
        "Wire transfer on 2026-02-10 amount $2500", "", "document"
    )
    b = synthesis._label_group_key(
        "Wire transfer on 2026-02-12 amount $3000", "", "document"
    )
    assert a == b


def test_build_chronology_data_includes_quality_outliers():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE timeline_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_normalized TEXT NOT NULL,
            date_precision TEXT NOT NULL,
            era_decade TEXT,
            label_en TEXT,
            label_zh TEXT,
            event_type TEXT NOT NULL,
            asset_sha256 TEXT,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE entities (
            entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_value TEXT NOT NULL,
            normalized_value TEXT NOT NULL,
            name_en TEXT,
            name_zh TEXT,
            person_id TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE entity_assets (
            entity_id INTEGER NOT NULL,
            asset_sha256 TEXT NOT NULL,
            source TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            context TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    conn.execute(
        """
        INSERT INTO timeline_events
        (date_normalized, date_precision, era_decade, label_en, label_zh, event_type, asset_sha256, source)
        VALUES
        ('1978-03-01', 'day', '1970s', 'Family gathering', '', 'photo', 'sha1', 'vision'),
        ('1978-03-01', 'day', '1970s', 'Family gathering', '', 'photo', 'sha2', 'vision'),
        ('2042-01-01', 'day', '2040s', 'Future typo date', '', 'document', 'sha3', 'document')
        """
    )
    conn.commit()

    chronology = synthesis.build_chronology_data(conn)
    conn.close()
    assert chronology["quality"]["raw_timeline_rows"] == 3
    assert chronology["quality"]["compacted_rows"] == 1
    assert chronology["quality"]["outlier_event_count"] >= 1


def test_reconcile_cluster_variant_updates_lookup(tmp_path):
    cluster_file = tmp_path / "clusters.json"
    cluster_file.write_text(
        json.dumps(
            {
                "generated": "2026-03-03",
                "source": "test",
                "cluster_count": 1,
                "variant_count": 1,
                "clusters": [
                    {
                        "canonical": "Feng Kuang Liu",
                        "canonical_zh": "劉逢光",
                        "variants": ["Feng Kuang Liu"],
                        "confidence": 0.95,
                    }
                ],
                "lookup": {
                    "Feng Kuang Liu": {
                        "canonical": "Feng Kuang Liu",
                        "canonical_zh": "劉逢光",
                    }
                },
            },
            ensure_ascii=False,
        )
    )

    result = synthesis.reconcile_cluster_variant(
        "Feng K. Liu (new variant)", "Feng Kuang Liu", path=cluster_file
    )
    assert result["changed"] is True
    updated = json.loads(cluster_file.read_text())
    assert "Feng K. Liu (new variant)" in updated["clusters"][0]["variants"]
    assert updated["lookup"]["Feng K. Liu (new variant)"]["canonical"] == "Feng Kuang Liu"
