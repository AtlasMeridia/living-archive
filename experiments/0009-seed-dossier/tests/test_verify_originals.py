from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest
from PIL import Image
from pypdf import PdfWriter


EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = EXPERIMENT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from common import BuildOptions  # noqa: E402
from discovery import build_seed_dossier  # noqa: E402
from original_inspection import _image_anchor  # noqa: E402
from source_verification import (  # noqa: E402
    VerificationError,
    build_source_verification,
    verify_smb_source_access,
)
from validation import ContractError  # noqa: E402
from verification_validation import validate_source_verification  # noqa: E402


SOURCE_ACCESS = {
    "protocol": "smb",
    "user": "living_archive_ro",
    "host": "mneme.local",
    "share": "MNEME",
    "identity_verified": True,
    "server_acl_verification": "external_prerequisite",
}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_verification_fixture(tmp_path: Path, *, high_document: bool = False) -> dict:
    project_root = tmp_path / "project"
    data_root = project_root / "data"
    documents_root = tmp_path / "sources" / "Documents"
    media_root = tmp_path / "sources" / "Media"
    documents_root.mkdir(parents=True)
    media_root.mkdir(parents=True)

    pdf_path = documents_root / "fixture-document.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    with pdf_path.open("wb") as handle:
        writer.write(handle)
    document_sha = sha256(pdf_path)

    photo_path = media_root / "fixture-photo.png"
    Image.new("RGB", (100, 80), color=(20, 40, 60)).save(photo_path)
    photo_sha = sha256(photo_path)

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
                document_sha,
                pdf_path.name,
                "document",
                None,
                None,
                "indexed",
                None,
                pdf_path.stat().st_size,
                1.0,
            ),
            (
                photo_sha,
                photo_path.name,
                "photo",
                None,
                None,
                "indexed",
                None,
                photo_path.stat().st_size,
                1.0,
            ),
        ],
    )
    catalog.commit()
    catalog.close()

    document_run = data_root / "documents" / "runs" / "doc-run"
    text = "--- Page 1 ---\nUnrelated.\n--- Page 2 ---\nExample Person appears."
    text_path = document_run / "extracted-text" / f"{document_sha[:12]}.txt"
    text_path.parent.mkdir(parents=True)
    text_path.write_text(text)
    write_json(
        document_run / "manifests" / f"{document_sha[:12]}.json",
        {
            "source_file": pdf_path.name,
            "source_sha256": document_sha,
            "file_size_bytes": pdf_path.stat().st_size,
            "page_count": 2,
            "extraction": {
                "chars_extracted": len(text),
                "text_file": f"extracted-text/{document_sha[:12]}.txt",
            },
            "analysis": {
                "document_type": "legal/test" if high_document else "personal/letter",
                "title": "Synthetic fixture",
                "date": "1976-01-01",
                "date_confidence": 0.8,
                "summary_en": "Synthetic summary",
                "summary_zh": "合成摘要",
                "key_people": [],
                "key_dates": ["1976-01-01"],
                "sensitivity": {
                    "contains_ssn": False,
                    "financial": False,
                    "medical": False,
                },
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

    write_json(
        data_root / "photos" / "runs" / "photo-run" / "manifests" / f"{photo_sha[:12]}.json",
        {
            "source_file": photo_path.name,
            "source_sha256": photo_sha,
            "analysis": {
                "date_estimate": "1979",
                "date_precision": "year",
                "date_confidence": 0.5,
                "description_en": "Synthetic photo",
                "description_zh": "合成照片",
                "people_count": 1,
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

    options = BuildOptions(
        subject_label="Example Person",
        aliases=("Example Person",),
        start_year=1970,
        end_year=1985,
        generated_at="2026-07-11T00:00:00+00:00",
    )
    dossier = build_seed_dossier(project_root, options)
    dossier_path = tmp_path / "dossier.json"
    dossier_path.write_text(json.dumps(dossier, indent=2, sort_keys=True))
    os.chmod(dossier_path, 0o600)
    os.chmod(pdf_path, 0o444)
    os.chmod(photo_path, 0o444)
    return {
        "dossier_path": dossier_path,
        "documents_root": documents_root,
        "media_root": media_root,
        "document_sha": document_sha,
        "photo_sha": photo_sha,
        "pdf_path": pdf_path,
        "photo_path": photo_path,
    }


def build_receipt(fixture: dict, **overrides) -> dict:
    values = {
        "dossier_path": fixture["dossier_path"],
        "documents_root": fixture["documents_root"],
        "media_root": fixture["media_root"],
        "selected_sha256s": [fixture["document_sha"], fixture["photo_sha"]],
        "image_regions": {fixture["photo_sha"]: (10, 10, 20, 20)},
        "source_access": SOURCE_ACCESS,
        "generated_at": "2026-07-12T00:00:00+00:00",
    }
    values.update(overrides)
    return build_source_verification(**values)


def test_exact_originals_create_identity_page_and_curator_region_anchors(tmp_path: Path):
    fixture = create_verification_fixture(tmp_path)
    before = {
        path: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
        for path in (fixture["dossier_path"], fixture["pdf_path"], fixture["photo_path"])
    }

    receipt = build_receipt(fixture)

    validate_source_verification(receipt)
    assert receipt["summary"] == {
        "selected_assets": 2,
        "resolved_originals": 2,
        "hash_verified_originals": 2,
        "pdf_document_anchors": 1,
        "pdf_page_anchors": 1,
        "image_region_anchors": 1,
        "claim_ready_assets": 0,
        "accepted_claims": 0,
        "mutations_detected": 0,
        "failed_assets": 0,
        "high_sensitivity_assets": 0,
    }
    document = next(item for item in receipt["verifications"] if item["media_type"] == "document")
    page_anchor = next(anchor for anchor in document["anchors"] if anchor["kind"] == "pdf_page")
    assert page_anchor["page_number"] == 2
    assert page_anchor["content_reverified"] is False
    photo = next(item for item in receipt["verifications"] if item["media_type"] == "photo")
    assert photo["anchors"][0]["subject_identity_supported"] is False
    assert photo["anchors"][0]["pixel_region"] == {
        "x": 10,
        "y": 10,
        "width": 20,
        "height": 20,
    }
    assert receipt["accepted_claims"] == []
    for path, (content, mode) in before.items():
        assert path.read_bytes() == content
        assert stat.S_IMODE(path.stat().st_mode) == mode


def test_high_sensitivity_requires_exact_selected_approval(tmp_path: Path):
    fixture = create_verification_fixture(tmp_path, high_document=True)

    with pytest.raises(VerificationError, match="high_sensitivity_approval_required"):
        build_receipt(fixture)

    receipt = build_receipt(
        fixture,
        high_sensitivity_approvals=[fixture["document_sha"]],
    )
    assert receipt["summary"]["high_sensitivity_assets"] == 1


def test_hash_mismatch_and_out_of_bounds_region_fail_without_anchors(tmp_path: Path):
    fixture = create_verification_fixture(tmp_path)
    os.chmod(fixture["pdf_path"], 0o644)
    fixture["pdf_path"].write_bytes(fixture["pdf_path"].read_bytes() + b"changed")
    os.chmod(fixture["pdf_path"], 0o444)

    receipt = build_receipt(
        fixture,
        image_regions={fixture["photo_sha"]: (90, 70, 20, 20)},
    )

    assert receipt["summary"]["failed_assets"] == 2
    assert all(item["anchors"] == [] for item in receipt["verifications"])
    assert receipt["accepted_claims"] == []


def test_traversal_and_symlink_locators_fail_closed(tmp_path: Path):
    fixture = create_verification_fixture(tmp_path)
    dossier = json.loads(fixture["dossier_path"].read_text())
    document = next(item for item in dossier["candidate_assets"] if item["media_type"] == "document")
    document["source_files"] = ["../outside.pdf"]
    fixture["dossier_path"].write_text(json.dumps(dossier, indent=2, sort_keys=True))
    receipt = build_receipt(fixture)
    failed_document = next(item for item in receipt["verifications"] if item["media_type"] == "document")
    assert failed_document["status"] == "failed"
    assert failed_document["anchors"] == []

    fixture = create_verification_fixture(tmp_path / "symlink")
    real = fixture["photo_path"]
    link = real.with_name("linked-photo.png")
    link.symlink_to(real)
    dossier = json.loads(fixture["dossier_path"].read_text())
    photo = next(item for item in dossier["candidate_assets"] if item["media_type"] == "photo")
    photo["source_files"] = [link.name]
    fixture["dossier_path"].write_text(json.dumps(dossier, indent=2, sort_keys=True))
    receipt = build_receipt(fixture)
    failed_photo = next(item for item in receipt["verifications"] if item["media_type"] == "photo")
    assert failed_photo["status"] == "failed"
    assert failed_photo["anchors"] == []


def test_identity_is_stable_and_receipt_contains_no_paths_or_excerpts(tmp_path: Path):
    fixture = create_verification_fixture(tmp_path)
    first = build_receipt(fixture, generated_at="2026-07-12T00:00:00+00:00")
    second = build_receipt(fixture, generated_at="2026-07-13T00:00:00+00:00")

    assert first["verification_id"] == second["verification_id"]
    serialized = json.dumps(first, sort_keys=True)
    assert "fixture-document.pdf" not in serialized
    assert "fixture-photo.png" not in serialized
    assert "Example Person" not in serialized
    assert "excerpt" not in serialized
    assert "page_text" not in serialized


def test_duplicate_phase1_hashes_are_rejected_before_sensitivity_selection(tmp_path: Path):
    fixture = create_verification_fixture(tmp_path)
    dossier = json.loads(fixture["dossier_path"].read_text())
    duplicate = json.loads(json.dumps(dossier["candidate_assets"][0]))
    duplicate["sensitivity"]["level"] = "review"
    dossier["candidate_assets"].append(duplicate)
    summary = dossier["summary"]
    summary["candidate_assets"] += 1
    summary["candidate_assets_by_media_type"][duplicate["media_type"]] += 1
    summary["evidence_status_counts"][duplicate["evidence_status"]] += 1
    summary["sensitivity_counts"][duplicate["sensitivity"]["level"]] += 1
    fixture["dossier_path"].write_text(json.dumps(dossier, indent=2, sort_keys=True))

    with pytest.raises(VerificationError, match="phase1_duplicate_candidate_hash"):
        build_receipt(fixture)


def test_failed_and_recovered_attempts_have_distinct_receipt_ids(tmp_path: Path):
    fixture = create_verification_fixture(tmp_path)
    original = fixture["pdf_path"].read_bytes()
    os.chmod(fixture["pdf_path"], 0o644)
    fixture["pdf_path"].write_bytes(original + b"changed")
    failed = build_receipt(fixture)

    fixture["pdf_path"].write_bytes(original)
    os.chmod(fixture["pdf_path"], 0o444)
    recovered = build_receipt(fixture)

    assert failed["summary"]["failed_assets"] == 1
    assert recovered["summary"]["failed_assets"] == 0
    assert failed["verification_id"] != recovered["verification_id"]


def test_generated_receipt_matches_committed_json_schema(tmp_path: Path):
    fixture = create_verification_fixture(tmp_path)
    receipt = build_receipt(fixture)
    schema = json.loads((EXPERIMENT_ROOT / "source-verification.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(receipt), key=lambda error: list(error.path))
    assert not errors, "\n".join(error.message for error in errors)


def test_multiframe_image_region_is_rejected_without_explicit_frame_semantics():
    inspection = {
        "frame_count": 2,
        "oriented_width_pixels": 100,
        "oriented_height_pixels": 80,
        "encoded_width_pixels": 100,
        "encoded_height_pixels": 80,
        "exif_orientation": 1,
        "detected_format": "TIFF",
    }
    with pytest.raises(VerificationError, match="image_multiframe_unsupported"):
        _image_anchor("a" * 64, inspection, (0, 0, 10, 10))


def test_failed_integrity_flags_are_rejected_by_runtime_and_schema(tmp_path: Path):
    fixture = create_verification_fixture(tmp_path)
    os.chmod(fixture["pdf_path"], 0o644)
    fixture["pdf_path"].write_bytes(fixture["pdf_path"].read_bytes() + b"changed")
    receipt = build_receipt(fixture)
    contradictory = deepcopy(receipt)
    failed = next(item for item in contradictory["verifications"] if item["status"] == "failed")
    failed["hash_verified"] = True
    failed["unchanged_after_read"] = True

    with pytest.raises(ContractError, match="contradictory integrity flags"):
        validate_source_verification(contradictory)
    schema = json.loads((EXPERIMENT_ROOT / "source-verification.schema.json").read_text())
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(contradictory))


def test_phase1_receipt_symlink_is_not_followed(tmp_path: Path):
    fixture = create_verification_fixture(tmp_path)
    link = tmp_path / "linked-dossier.json"
    link.symlink_to(fixture["dossier_path"])
    with pytest.raises(VerificationError, match="phase1_receipt_unreadable"):
        build_source_verification(
            link,
            fixture["documents_root"],
            fixture["media_root"],
            [fixture["document_sha"]],
            source_access=SOURCE_ACCESS,
        )


def test_live_smb_identity_must_match_expected_session(tmp_path: Path, monkeypatch):
    volume = tmp_path / "Volumes" / "MNEME-1"
    documents = volume / "Documents"
    media = volume / "Media"
    documents.mkdir(parents=True)
    media.mkdir()
    mount_line = (
        f"//living_archive_ro@mneme.local/MNEME on {volume} "
        "(smbfs, nodev, nosuid)\n"
    )
    monkeypatch.setattr(
        "verification_io.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=mount_line),
    )
    access, devices = verify_smb_source_access((documents, media))
    assert access["identity_verified"] is True
    assert devices == frozenset({documents.stat().st_dev})

    wrong_mount = mount_line.replace("living_archive_ro", "mneme_admin")
    monkeypatch.setattr(
        "verification_io.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=wrong_mount),
    )
    with pytest.raises(VerificationError, match="smb_identity_mismatch"):
        verify_smb_source_access((documents, media))
