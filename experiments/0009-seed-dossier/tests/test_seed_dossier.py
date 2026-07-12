from __future__ import annotations

import hashlib
import json
import shutil
import stat
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import jsonschema


EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = EXPERIMENT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from common import BuildOptions  # noqa: E402
from discovery import DossierBuilder, build_seed_dossier  # noqa: E402
import seed_dossier as cli_module  # noqa: E402
from validation import ContractError, validate_dossier  # noqa: E402


SHA_LETTER = "a" * 64
SHA_LEGAL = "b" * 64
SHA_LOCATOR = "c" * 64
SHA_PHOTO = "d" * 64


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def write_document_run(
    root: Path,
    run_id: str,
    sha256: str,
    source_file: str,
    date: str,
    document_type: str,
    text: str,
    sensitivity: dict | None = None,
) -> None:
    run_root = root / "data" / "documents" / "runs" / run_id
    text_path = run_root / "extracted-text" / f"{sha256[:12]}.txt"
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text)
    write_json(
        run_root / "manifests" / f"{sha256[:12]}.json",
        {
            "source_file": source_file,
            "source_sha256": sha256,
            "file_size_bytes": 100,
            "page_count": 2,
            "extraction": {
                "chars_extracted": len(text),
                "text_file": f"extracted-text/{sha256[:12]}.txt",
            },
            "analysis": {
                "document_type": document_type,
                "title": "Synthetic fixture",
                "date": date,
                "date_confidence": 0.8,
                "summary_en": "Synthetic summary",
                "summary_zh": "合成摘要",
                "key_people": [],
                "key_dates": [date],
                "sensitivity": sensitivity
                or {"contains_ssn": False, "financial": False, "medical": False},
                "tags": [],
                "language": "en",
                "quality": "good",
            },
            "inference": {
                "method": "fixture",
                "provider": "fixture",
                "model": "fixture-v1",
                "prompt_version": "fixture-v1",
                "timestamp": "2026-07-11T00:00:00+00:00",
            },
        },
    )


def create_fixture_project(root: Path) -> Path:
    data_root = root / "data"
    data_root.mkdir(parents=True)

    catalog = sqlite3.connect(data_root / "catalog.db")
    catalog.execute(
        """
        CREATE TABLE assets (
            sha256 TEXT PRIMARY KEY,
            path TEXT,
            content_type TEXT,
            manifest_path TEXT,
            run_id TEXT,
            status TEXT,
            slice TEXT,
            file_size INTEGER,
            file_mtime REAL
        )
        """
    )
    catalog.executemany(
        "INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                SHA_LETTER,
                "Family/Letters/ordinary-letter.pdf",
                "document",
                None,
                None,
                "indexed",
                None,
                100,
                1.0,
            ),
            (
                SHA_LEGAL,
                "Family/Legal/Example_Alias_record.pdf",
                "document",
                None,
                None,
                "indexed",
                None,
                100,
                1.0,
            ),
            (
                SHA_LOCATOR,
                "Family/Unknown/locator.pdf",
                "document",
                None,
                None,
                "indexed",
                None,
                100,
                1.0,
            ),
            (
                SHA_PHOTO,
                "Family/Photos/photo.jpg",
                "photo",
                None,
                None,
                "indexed",
                None,
                100,
                1.0,
            ),
        ],
    )
    catalog.commit()
    catalog.close()

    synthesis = sqlite3.connect(data_root / "synthesis.db")
    synthesis.executescript(
        """
        CREATE TABLE entities (
            entity_id INTEGER PRIMARY KEY,
            entity_type TEXT,
            entity_value TEXT,
            normalized_value TEXT,
            name_en TEXT,
            name_zh TEXT
        );
        CREATE TABLE entity_assets (
            entity_id INTEGER,
            asset_sha256 TEXT,
            source TEXT,
            confidence REAL,
            PRIMARY KEY (entity_id, asset_sha256, source)
        );
        CREATE TABLE timeline_events (
            event_id INTEGER PRIMARY KEY,
            date_normalized TEXT,
            date_precision TEXT,
            event_type TEXT,
            asset_sha256 TEXT,
            source TEXT
        );
        """
    )
    synthesis.execute(
        "INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?)",
        (1, "person", "Example Person", "example person", None, None),
    )
    synthesis.executemany(
        "INSERT INTO entity_assets VALUES (?, ?, ?, ?)",
        [
            (1, SHA_LEGAL, "document", 0.8),
            (1, SHA_LOCATOR, "document", 0.6),
        ],
    )
    synthesis.execute(
        "INSERT INTO timeline_events VALUES (?, ?, ?, ?, ?, ?)",
        (1, "1975-01-01", "year", "date_mention", SHA_LOCATOR, "document"),
    )
    synthesis.commit()
    synthesis.close()

    letter_text = (
        "--- Page 1 ---\nUnrelated synthetic page.\n\n"
        "--- Page 2 ---\nExample Person appears in this synthetic fixture."
    )
    write_document_run(
        root,
        "run-a",
        SHA_LETTER,
        "Family/Letters/ordinary-letter.pdf",
        "1976-05-21",
        "personal/letter",
        letter_text,
    )
    write_document_run(
        root,
        "run-b",
        SHA_LETTER,
        "Family/Letters/ordinary-letter.pdf",
        "1977-05-21",
        "personal/letter",
        letter_text,
    )
    write_document_run(
        root,
        "run-c",
        SHA_LEGAL,
        "Family/Legal/Example_Alias_record.pdf",
        "1980-01-01",
        "legal/trust",
        "--- Page 1 ---\nExample Alias appears in a restricted synthetic record.",
    )

    write_json(
        data_root / "photos" / "runs" / "photo-run" / "manifests" / f"{SHA_PHOTO[:12]}.json",
        {
            "source_file": "Family/Photos/photo.jpg",
            "source_sha256": SHA_PHOTO,
            "analysis": {
                "date_estimate": "1979",
                "date_precision": "year",
                "date_confidence": 0.5,
                "description_en": "Synthetic family photo",
                "description_zh": "合成家庭照片",
                "people_count": 2,
                "people_notes": "Possibly Example Person",
                "location_estimate": "Unknown",
                "location_confidence": 0.1,
                "tags": [],
                "condition_notes": "Synthetic",
                "ocr_text": "",
                "is_document": False,
            },
            "inference": {
                "model": "fixture-v1",
                "prompt_version": "fixture-v1",
                "timestamp": "2026-07-11T00:00:00+00:00",
            },
        },
    )
    write_json(data_root / "people" / "registry.json", {"version": 2, "people": []})
    return root


def input_fingerprints(project_root: Path) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    for path in sorted((project_root / "data").rglob("*")):
        if path.is_file():
            fingerprints[str(path.relative_to(project_root))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return fingerprints


def options(**overrides) -> BuildOptions:
    values = {
        "subject_label": "Example Person",
        "aliases": ("Example Alias", "Person", "測試人物"),
        "start_year": 1970,
        "end_year": 1985,
        "generated_at": "2026-07-11T00:00:00+00:00",
    }
    values.update(overrides)
    return BuildOptions(**values)


def test_archive_first_dossier_unions_candidates_without_mutating_inputs(tmp_path: Path):
    project_root = create_fixture_project(tmp_path / "archive")
    before = input_fingerprints(project_root)

    dossier = build_seed_dossier(project_root, options())

    assert input_fingerprints(project_root) == before
    assert dossier["read_only"] is True
    assert dossier["human_verified"] is False
    assert dossier["visibility"] == "curator"
    assert dossier["claim_candidates"] == []
    assert dossier["summary"]["accepted_claims"] == 0
    assert dossier["summary"]["originals_verified"] == 0
    assert dossier["summary"]["candidate_assets"] == 4
    assert dossier["summary"]["candidate_assets_by_media_type"] == {
        "document": 3,
        "photo": 1,
    }

    candidates = {item["asset_sha256"]: item for item in dossier["candidate_assets"]}
    assert candidates[SHA_LETTER]["evidence_status"] == "exact_extracted_text_candidate"
    assert candidates[SHA_LEGAL]["sensitivity"]["level"] == "high"
    assert candidates[SHA_LOCATOR]["evidence_status"] == "locator_only"
    assert candidates[SHA_PHOTO]["evidence_status"] == "machine_proposal_only"

    assert len(dossier["evidence_items"]) == 2
    letter_evidence = next(
        item for item in dossier["evidence_items"] if item["asset_sha256"] == SHA_LETTER
    )
    assert letter_evidence["locator"]["page"] == 2
    assert letter_evidence["locator"]["char_start"] == 0
    assert letter_evidence["locator"]["char_end"] == len("Example Person")
    assert len(letter_evidence["extraction_refs"]) == 2
    assert "excerpt" not in letter_evidence

    assert len(dossier["contradictions"]) == 1
    assert dossier["contradictions"][0]["asset_sha256"] == SHA_LETTER
    assert dossier["summary"]["timeline_candidates_in_period"] == 0
    assert dossier["summary"]["unanchored_timeline_signals_in_period"] == 5
    assert dossier["timeline_candidates"] == []
    assert len(dossier["unanchored_timeline_signals"]) == 5
    triggers = {item["trigger"] for item in dossier["research_questions"]}
    assert triggers == {
        "weak_identity",
        "unverified_locator",
        "contradiction",
        "privacy_review",
        "missing_source_anchor",
    }


def test_dossier_never_contains_excerpts(tmp_path: Path):
    project_root = create_fixture_project(tmp_path / "archive")
    dossier = build_seed_dossier(project_root, options())

    def contains_excerpt_key(value) -> bool:
        if isinstance(value, dict):
            return "excerpt" in value or any(contains_excerpt_key(item) for item in value.values())
        if isinstance(value, list):
            return any(contains_excerpt_key(item) for item in value)
        return False

    assert not contains_excerpt_key(dossier)
    letter = next(
        item for item in dossier["evidence_items"] if item["asset_sha256"] == SHA_LETTER
    )
    assert letter["matched_alias"] == "Example Person"
    assert letter["matched_aliases"] == ["Example Person", "Person"]


def test_same_inputs_produce_same_canonical_dossier(tmp_path: Path):
    project_root = create_fixture_project(tmp_path / "archive")
    first = build_seed_dossier(project_root, options())
    second = build_seed_dossier(project_root, options())
    assert first == second


def test_cli_writes_only_requested_private_output(tmp_path: Path):
    project_root = create_fixture_project(tmp_path / "archive")
    before = input_fingerprints(project_root)
    output_root = tmp_path / "private-output"
    original_private_root = cli_module.PRIVATE_RUN_ROOT
    cli_module.PRIVATE_RUN_ROOT = output_root
    try:
        result = cli_module.main(
            [
                "--project-root",
                str(project_root),
                "--subject",
                "Example Person",
                "--alias",
                "Example Alias",
                "--start-year",
                "1970",
                "--end-year",
                "1985",
                "--output-name",
                "dossier.json",
            ]
        )
        output = output_root / "dossier.json"
        assert result == 0
        assert output.exists()
        assert json.loads(output.read_text())["visibility"] == "curator"
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
        assert stat.S_IMODE(output_root.stat().st_mode) == 0o700
        assert input_fingerprints(project_root) == before
        with pytest.raises(FileExistsError, match="already exists"):
            cli_module.main(
                [
                    "--project-root",
                    str(project_root),
                    "--subject",
                    "Example Person",
                    "--alias",
                    "Example Alias",
                    "--start-year",
                    "1970",
                    "--end-year",
                    "1985",
                    "--output-name",
                    "dossier.json",
                ]
            )
    finally:
        cli_module.PRIVATE_RUN_ROOT = original_private_root


def test_invalid_period_is_rejected(tmp_path: Path):
    project_root = create_fixture_project(tmp_path / "archive")
    with pytest.raises(ValueError, match="start_year"):
        build_seed_dossier(
            project_root,
            options(start_year=1985, end_year=1970),
        )


def test_evidence_locator_round_trips_to_raw_artifact_bytes(tmp_path: Path):
    project_root = create_fixture_project(tmp_path / "archive")
    dossier = build_seed_dossier(project_root, options())
    evidence = next(
        item for item in dossier["evidence_items"] if item["asset_sha256"] == SHA_LETTER
    )
    text_path = project_root / evidence["extraction_refs"][0]["text_file"]
    raw = text_path.read_bytes()
    locator = evidence["locator"]
    assert hashlib.sha256(raw).hexdigest() == locator["raw_artifact_sha256"]
    matched_bytes = raw[locator["artifact_byte_start"] : locator["artifact_byte_end"]]
    assert matched_bytes.decode("utf-8") == evidence["matched_alias"]
    decoded = raw.decode("utf-8")
    assert (
        decoded[locator["artifact_char_start"] : locator["artifact_char_end"]]
        == evidence["matched_alias"]
    )


def test_absolute_and_traversal_extraction_paths_never_become_evidence(tmp_path: Path):
    for variant in ("absolute", "traversal"):
        project_root = create_fixture_project(tmp_path / variant)
        outside = project_root / "data" / "documents" / "runs" / "outside.txt"
        outside.write_text("--- Page 1 ---\nExample Person must not be read.")
        for run_id in ("run-a", "run-b"):
            manifest_path = (
                project_root
                / "data"
                / "documents"
                / "runs"
                / run_id
                / "manifests"
                / f"{SHA_LETTER[:12]}.json"
            )
            manifest = json.loads(manifest_path.read_text())
            manifest["extraction"]["text_file"] = (
                str(outside.resolve()) if variant == "absolute" else "../outside.txt"
            )
            write_json(manifest_path, manifest)
        dossier = build_seed_dossier(project_root, options())
        assert all(
            item["asset_sha256"] != SHA_LETTER for item in dossier["evidence_items"]
        )
        expected_warning = (
            "extracted_text_path_absolute"
            if variant == "absolute"
            else "extracted_text_path_escape"
        )
        assert any(
            warning.startswith(expected_warning) for warning in dossier["warnings"]
        )


def test_symlink_escape_and_missing_page_headers_are_rejected(tmp_path: Path):
    symlink_root = create_fixture_project(tmp_path / "symlink")
    outside = symlink_root / "outside.txt"
    outside.write_text("--- Page 1 ---\nExample Person must not be read.")
    for run_id in ("run-a", "run-b"):
        text_path = (
            symlink_root
            / "data"
            / "documents"
            / "runs"
            / run_id
            / "extracted-text"
            / f"{SHA_LETTER[:12]}.txt"
        )
        text_path.unlink()
        text_path.symlink_to(outside)
    dossier = build_seed_dossier(symlink_root, options())
    assert all(item["asset_sha256"] != SHA_LETTER for item in dossier["evidence_items"])
    assert any(
        warning.startswith("extracted_text_path_escape") for warning in dossier["warnings"]
    )

    no_pages_root = create_fixture_project(tmp_path / "no-pages")
    for run_id in ("run-a", "run-b"):
        text_path = (
            no_pages_root
            / "data"
            / "documents"
            / "runs"
            / run_id
            / "extracted-text"
            / f"{SHA_LETTER[:12]}.txt"
        )
        text_path.write_text("Example Person without a page header")
    dossier = build_seed_dossier(no_pages_root, options())
    assert all(item["asset_sha256"] != SHA_LETTER for item in dossier["evidence_items"])
    assert any(
        warning.startswith("extracted_text_page_headers_missing")
        for warning in dossier["warnings"]
    )


def test_contract_validation_and_private_output_boundary_fail_closed(tmp_path: Path):
    project_root = create_fixture_project(tmp_path / "archive")
    dossier = build_seed_dossier(project_root, options())
    validate_dossier(dossier)
    dossier["visibility"] = "family"
    with pytest.raises(ContractError, match="visibility"):
        validate_dossier(dossier)

    with pytest.raises(ValueError, match="basename"):
        cli_module.private_output_path("../escape.json")
    with pytest.raises(FileNotFoundError):
        build_seed_dossier(tmp_path / "wrong-root", options())


def test_compatible_date_precision_is_not_a_contradiction(tmp_path: Path):
    project_root = create_fixture_project(tmp_path / "archive")
    manifest_path = (
        project_root
        / "data"
        / "documents"
        / "runs"
        / "run-b"
        / "manifests"
        / f"{SHA_LETTER[:12]}.json"
    )
    manifest = json.loads(manifest_path.read_text())
    manifest["analysis"]["date"] = "1976"
    write_json(manifest_path, manifest)
    dossier = build_seed_dossier(project_root, options())
    assert not any(
        item["asset_sha256"] == SHA_LETTER for item in dossier["contradictions"]
    )


def test_manifest_identity_mismatch_cannot_create_exact_evidence(tmp_path: Path):
    project_root = create_fixture_project(tmp_path / "archive")
    for run_id in ("run-a", "run-b"):
        manifests = project_root / "data" / "documents" / "runs" / run_id / "manifests"
        original = manifests / f"{SHA_LETTER[:12]}.json"
        original.rename(manifests / f"{'f' * 12}.json")
    dossier = build_seed_dossier(project_root, options())
    assert all(item["asset_sha256"] != SHA_LETTER for item in dossier["evidence_items"])
    assert any(
        warning.startswith("manifest_filename_sha_mismatch")
        for warning in dossier["warnings"]
    )


def test_input_change_during_build_aborts_without_a_dossier(tmp_path: Path):
    project_root = create_fixture_project(tmp_path / "archive")
    builder = DossierBuilder(project_root, options())
    before = builder._capture_input_state()
    after = {**before, "manifest_count": before["manifest_count"] + 1}
    with patch.object(builder, "_capture_input_state", side_effect=[before, after]):
        with pytest.raises(RuntimeError, match="changed"):
            builder.build()


def test_extracted_text_root_symlink_is_rejected(tmp_path: Path):
    project_root = create_fixture_project(tmp_path / "archive")
    outside = tmp_path / "outside-extractions"
    outside.mkdir()
    (outside / f"{SHA_LETTER[:12]}.txt").write_text(
        "--- Page 1 ---\nExample Person must not be read."
    )
    for run_id in ("run-a", "run-b"):
        extraction_root = (
            project_root / "data" / "documents" / "runs" / run_id / "extracted-text"
        )
        shutil.rmtree(extraction_root)
        extraction_root.symlink_to(outside, target_is_directory=True)
    dossier = build_seed_dossier(project_root, options())
    assert all(item["asset_sha256"] != SHA_LETTER for item in dossier["evidence_items"])
    assert any(
        warning.startswith("extracted_text_root_symlink")
        for warning in dossier["warnings"]
    )


def test_invalid_sha_filename_utf8_and_synthesis_schema_fail_closed(tmp_path: Path):
    invalid_sha_root = create_fixture_project(tmp_path / "invalid-sha")
    manifest_path = (
        invalid_sha_root
        / "data"
        / "documents"
        / "runs"
        / "run-a"
        / "manifests"
        / f"{SHA_LETTER[:12]}.json"
    )
    manifest = json.loads(manifest_path.read_text())
    manifest["source_sha256"] = SHA_LETTER.upper()
    write_json(manifest_path, manifest)
    dossier = build_seed_dossier(invalid_sha_root, options())
    assert any(warning.startswith("manifest_invalid_sha256") for warning in dossier["warnings"])

    filename_root = create_fixture_project(tmp_path / "filename-mismatch")
    for run_id in ("run-a", "run-b"):
        manifest_path = (
            filename_root
            / "data"
            / "documents"
            / "runs"
            / run_id
            / "manifests"
            / f"{SHA_LETTER[:12]}.json"
        )
        manifest = json.loads(manifest_path.read_text())
        wrong_name = f"{'e' * 12}.txt"
        wrong_path = manifest_path.parent.parent / "extracted-text" / wrong_name
        wrong_path.write_text("--- Page 1 ---\nExample Person must not be read.")
        manifest["extraction"]["text_file"] = f"extracted-text/{wrong_name}"
        write_json(manifest_path, manifest)
    dossier = build_seed_dossier(filename_root, options())
    assert all(item["asset_sha256"] != SHA_LETTER for item in dossier["evidence_items"])
    assert any(
        warning.startswith("extracted_text_filename_sha_mismatch")
        for warning in dossier["warnings"]
    )

    utf8_root = create_fixture_project(tmp_path / "invalid-utf8")
    for run_id in ("run-a", "run-b"):
        text_path = (
            utf8_root
            / "data"
            / "documents"
            / "runs"
            / run_id
            / "extracted-text"
            / f"{SHA_LETTER[:12]}.txt"
        )
        text_path.write_bytes(b"--- Page 1 ---\n\xff")
    dossier = build_seed_dossier(utf8_root, options())
    assert all(item["asset_sha256"] != SHA_LETTER for item in dossier["evidence_items"])
    assert any(
        warning.startswith("extracted_text_invalid_utf8") for warning in dossier["warnings"]
    )

    synthesis_root = create_fixture_project(tmp_path / "synthesis-drift")
    synthesis = sqlite3.connect(synthesis_root / "data" / "synthesis.db")
    synthesis.execute("UPDATE entities SET entity_type = 'place'")
    synthesis.execute("DROP TABLE timeline_events")
    synthesis.execute("CREATE TABLE timeline_events (event_id INTEGER PRIMARY KEY)")
    synthesis.commit()
    synthesis.close()
    dossier = build_seed_dossier(synthesis_root, options())
    assert all(
        reason["kind"] != "legacy_synthesis_link"
        for candidate in dossier["candidate_assets"]
        for reason in candidate["discovery_reasons"]
    )
    assert "legacy_timeline_columns_missing:asset_sha256,date_normalized" in dossier["warnings"]


def test_output_symlink_is_rejected_before_write(tmp_path: Path):
    private_root = tmp_path / "private"
    private_root.mkdir()
    target = private_root / "target.json"
    target.write_text("do not replace")
    link = private_root / "dossier.json"
    link.symlink_to(target)
    original_private_root = cli_module.PRIVATE_RUN_ROOT
    cli_module.PRIVATE_RUN_ROOT = private_root
    try:
        with pytest.raises(ValueError, match="symlink"):
            cli_module.private_output_path("dossier.json")
    finally:
        cli_module.PRIVATE_RUN_ROOT = original_private_root


def test_generated_dossier_matches_committed_json_schema(tmp_path: Path):
    project_root = create_fixture_project(tmp_path / "archive")
    dossier = build_seed_dossier(project_root, options())
    schema = json.loads((EXPERIMENT_ROOT / "seed-dossier.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(dossier), key=lambda error: list(error.path))
    assert not errors, "\n".join(error.message for error in errors)
