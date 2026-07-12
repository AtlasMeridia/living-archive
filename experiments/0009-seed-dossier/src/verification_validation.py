"""Runtime invariants for append-only source-verification receipts."""

from __future__ import annotations

import re
from typing import Any

from validation import ContractError


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ID_PATTERN = re.compile(r"^(?:verification|anchor)_[0-9a-f]{16}$")
WARNING_PATTERN = re.compile(r"^[a-z0-9_]+$")


def _exact_keys(value: dict[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ContractError(
            f"{path} keys differ: missing={sorted(expected - actual)} "
            f"extra={sorted(actual - expected)}"
        )


def _sha256(value: object, path: str, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise ContractError(f"{path} must be a lowercase SHA-256")


def _nonnegative_integer(value: object, path: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ContractError(f"{path} must be a non-negative integer")


def _warnings(value: object, path: str) -> None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not WARNING_PATTERN.fullmatch(item) for item in value
    ):
        raise ContractError(f"{path} must contain warning codes only")


def _forbid_private_payload_keys(value: Any, path: str = "$") -> None:
    forbidden = {"excerpt", "page_text", "crop", "source_path", "relative_path"}
    if isinstance(value, dict):
        overlap = forbidden & set(value)
        if overlap:
            raise ContractError(f"{path} contains forbidden payload keys: {sorted(overlap)}")
        for key, item in value.items():
            _forbid_private_payload_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _forbid_private_payload_keys(item, f"{path}[{index}]")


def _validate_anchor(anchor: dict[str, Any], asset_sha256: str, path: str) -> None:
    kind = anchor.get("kind")
    if kind == "pdf_document":
        _exact_keys(
            anchor,
            {
                "anchor_id",
                "kind",
                "source_sha256",
                "claim_support",
                "subject_identity_supported",
                "page_count",
            },
            path,
        )
        if anchor["claim_support"] != "asset_identity_only":
            raise ContractError(f"{path} cannot support a historical claim")
        if anchor["subject_identity_supported"] is not False:
            raise ContractError(f"{path} cannot assert subject identity")
        if not isinstance(anchor["page_count"], int) or anchor["page_count"] < 1:
            raise ContractError(f"{path}.page_count must be positive")
    elif kind == "pdf_page":
        _exact_keys(
            anchor,
            {
                "anchor_id",
                "kind",
                "source_sha256",
                "page_number",
                "page_index",
                "basis_evidence_ids",
                "content_reverified",
                "claim_support",
                "subject_identity_supported",
            },
            path,
        )
        if anchor["claim_support"] != "locator_only" or anchor["content_reverified"] is not False:
            raise ContractError(f"{path} cannot promote page content")
        if anchor["subject_identity_supported"] is not False:
            raise ContractError(f"{path} cannot assert subject identity")
        if not isinstance(anchor["page_number"], int) or anchor["page_number"] < 1:
            raise ContractError(f"{path}.page_number must be positive")
        if anchor["page_index"] != anchor["page_number"] - 1:
            raise ContractError(f"{path}.page_index does not match page_number")
        if not isinstance(anchor["basis_evidence_ids"], list) or not anchor[
            "basis_evidence_ids"
        ]:
            raise ContractError(f"{path}.basis_evidence_ids must not be empty")
    elif kind == "image_region":
        _exact_keys(
            anchor,
            {
                "anchor_id",
                "kind",
                "source_sha256",
                "claim_support",
                "subject_identity_supported",
                "curator_supplied",
                "frame_index",
                "coordinate_space",
                "exif_orientation",
                "encoded_width_pixels",
                "encoded_height_pixels",
                "width_pixels",
                "height_pixels",
                "detected_format",
                "purpose",
                "pixel_region",
            },
            path,
        )
        if anchor["curator_supplied"] is not True:
            raise ContractError(f"{path} region must be curator supplied")
        if anchor["frame_index"] != 0:
            raise ContractError(f"{path}.frame_index is invalid")
        if anchor["coordinate_space"] != "exif_oriented_source_pixel_xywh":
            raise ContractError(f"{path}.coordinate_space is invalid")
        if anchor["exif_orientation"] not in range(1, 9):
            raise ContractError(f"{path}.exif_orientation is invalid")
        if anchor["subject_identity_supported"] is not False:
            raise ContractError(f"{path} cannot assert subject identity")
        if anchor["claim_support"] != "locator_only":
            raise ContractError(f"{path} cannot support a historical claim")
        if anchor["purpose"] != "curator_supplied_source_region":
            raise ContractError(f"{path}.purpose is invalid")
        for key in (
            "encoded_width_pixels",
            "encoded_height_pixels",
            "width_pixels",
            "height_pixels",
        ):
            if not isinstance(anchor[key], int) or anchor[key] < 1:
                raise ContractError(f"{path}.{key} must be positive")
        expected_dimensions = (
            (anchor["encoded_height_pixels"], anchor["encoded_width_pixels"])
            if anchor["exif_orientation"] in {5, 6, 7, 8}
            else (anchor["encoded_width_pixels"], anchor["encoded_height_pixels"])
        )
        if (anchor["width_pixels"], anchor["height_pixels"]) != expected_dimensions:
            raise ContractError(f"{path} oriented dimensions do not match EXIF orientation")
        region = anchor["pixel_region"]
        _exact_keys(region, {"x", "y", "width", "height"}, f"{path}.pixel_region")
        for key in ("x", "y", "width", "height"):
            _nonnegative_integer(region[key], f"{path}.pixel_region.{key}")
        if region["width"] < 1 or region["height"] < 1:
            raise ContractError(f"{path} region must have positive dimensions")
        if region["x"] + region["width"] > anchor["width_pixels"]:
            raise ContractError(f"{path} region exceeds image width")
        if region["y"] + region["height"] > anchor["height_pixels"]:
            raise ContractError(f"{path} region exceeds image height")
    else:
        raise ContractError(f"{path}.kind is invalid")
    if not isinstance(anchor.get("anchor_id"), str) or not ID_PATTERN.fullmatch(
        anchor["anchor_id"]
    ):
        raise ContractError(f"{path}.anchor_id is invalid")
    if anchor.get("source_sha256") != asset_sha256:
        raise ContractError(f"{path}.source_sha256 differs from its asset")


def _validate_verification(item: dict[str, Any], path: str) -> None:
    base_keys = {
        "asset_sha256",
        "media_type",
        "sensitivity",
        "source_locator_ref",
        "status",
        "hash_verified",
        "unchanged_after_read",
        "anchors",
        "claim_ready",
        "human_verified",
        "visibility",
        "warnings",
    }
    expected = base_keys | (
        {"source_sha256", "source_size_bytes"}
        if item.get("status") == "verified"
        else set()
    )
    _exact_keys(item, expected, path)
    _sha256(item["asset_sha256"], f"{path}.asset_sha256")
    if item["media_type"] not in {"document", "photo"}:
        raise ContractError(f"{path}.media_type is invalid")
    if item["sensitivity"] not in {"high", "review"}:
        raise ContractError(f"{path}.sensitivity is invalid")
    _exact_keys(
        item["source_locator_ref"],
        {"root_role", "relative_path_sha256", "locator_source"},
        f"{path}.source_locator_ref",
    )
    expected_role = "documents_root" if item["media_type"] == "document" else "media_root"
    if item["source_locator_ref"]["root_role"] != expected_role:
        raise ContractError(f"{path}.source_locator_ref.root_role is invalid")
    if item["source_locator_ref"]["locator_source"] != (
        "base_dossier.candidate_assets.source_files"
    ):
        raise ContractError(f"{path}.source_locator_ref.locator_source is invalid")
    _sha256(
        item["source_locator_ref"]["relative_path_sha256"],
        f"{path}.source_locator_ref.relative_path_sha256",
    )
    if item["status"] == "verified":
        _sha256(item["source_sha256"], f"{path}.source_sha256")
        _nonnegative_integer(item["source_size_bytes"], f"{path}.source_size_bytes")
        if item["source_sha256"] != item["asset_sha256"]:
            raise ContractError(f"{path} verified source hash differs from asset")
        if item["hash_verified"] is not True or item["unchanged_after_read"] is not True:
            raise ContractError(f"{path} verified source lacks integrity proof")
        if item["media_type"] == "document" and not any(
            anchor["kind"] == "pdf_document" for anchor in item["anchors"]
        ):
            raise ContractError(f"{path} verified document lacks identity anchor")
    elif item["status"] == "failed":
        if item["hash_verified"] is not False or item["unchanged_after_read"] is not False:
            raise ContractError(f"{path} failed verification has contradictory integrity flags")
        if item["anchors"]:
            raise ContractError(f"{path} failed verification cannot have anchors")
    else:
        raise ContractError(f"{path}.status is invalid")
    if item["claim_ready"] is not False or item["human_verified"] is not False:
        raise ContractError(f"{path} cannot be claim-ready or human-verified")
    if item["visibility"] != "curator":
        raise ContractError(f"{path}.visibility must be curator")
    _warnings(item["warnings"], f"{path}.warnings")
    for index, anchor in enumerate(item["anchors"]):
        _validate_anchor(anchor, item["asset_sha256"], f"{path}.anchors[{index}]")


def validate_source_verification(payload: dict[str, Any]) -> None:
    """Validate Phase 2 authority, privacy, and referential invariants."""
    _exact_keys(
        payload,
        {
            "schema_version",
            "verification_id",
            "generated_at",
            "read_only",
            "human_verified",
            "visibility",
            "phase1_receipt",
            "producer",
            "source_access",
            "selection",
            "authority_rules",
            "summary",
            "verifications",
            "accepted_claims",
            "warnings",
        },
        "$",
    )
    if payload["schema_version"] != "source-verification-v0.1":
        raise ContractError("$.schema_version is invalid")
    if not isinstance(payload["verification_id"], str) or not ID_PATTERN.fullmatch(
        payload["verification_id"]
    ):
        raise ContractError("$.verification_id is invalid")
    if payload["read_only"] is not True or payload["human_verified"] is not False:
        raise ContractError("receipt authority flags are invalid")
    if payload["visibility"] != "curator" or payload["accepted_claims"] != []:
        raise ContractError("receipt cannot publish or accept claims")
    _exact_keys(
        payload["phase1_receipt"],
        {"dossier_id", "dossier_schema_version", "dossier_sha256", "dossier_byte_count"},
        "$.phase1_receipt",
    )
    _sha256(payload["phase1_receipt"]["dossier_sha256"], "$.phase1_receipt.dossier_sha256")
    _nonnegative_integer(
        payload["phase1_receipt"]["dossier_byte_count"],
        "$.phase1_receipt.dossier_byte_count",
    )
    _exact_keys(
        payload["producer"],
        {
            "experiment_git",
            "contract_sha256",
            "python_version",
            "pypdf_version",
            "pillow_version",
        },
        "$.producer",
    )
    _sha256(payload["producer"]["contract_sha256"], "$.producer.contract_sha256")
    git = payload["producer"]["experiment_git"]
    _exact_keys(
        git,
        {"commit", "dirty", "status_sha256", "dirty_diff_sha256"},
        "$.producer.experiment_git",
    )
    if git["commit"] is not None and not isinstance(git["commit"], str):
        raise ContractError("$.producer.experiment_git.commit is invalid")
    if git["dirty"] is not None and not isinstance(git["dirty"], bool):
        raise ContractError("$.producer.experiment_git.dirty is invalid")
    _sha256(git["status_sha256"], "$.producer.experiment_git.status_sha256", nullable=True)
    _sha256(
        git["dirty_diff_sha256"],
        "$.producer.experiment_git.dirty_diff_sha256",
        nullable=True,
    )
    for key in ("python_version", "pypdf_version", "pillow_version"):
        if not isinstance(payload["producer"][key], str) or not payload["producer"][key]:
            raise ContractError(f"$.producer.{key} must be non-empty")
    expected_access = {
        "protocol": "smb",
        "identity_verified": True,
        "server_acl_verification": "external_prerequisite",
    }
    _exact_keys(
        payload["source_access"],
        {"protocol", "user", "host", "share", "identity_verified", "server_acl_verification"},
        "$.source_access",
    )
    if any(payload["source_access"].get(key) != value for key, value in expected_access.items()):
        raise ContractError("$.source_access is not a verified SMB prerequisite")
    if payload["source_access"] != {
        "protocol": "smb",
        "user": "living_archive_ro",
        "host": "mneme.local",
        "share": "MNEME",
        "identity_verified": True,
        "server_acl_verification": "external_prerequisite",
    }:
        raise ContractError("$.source_access differs from the pinned read-only session")
    _exact_keys(
        payload["selection"],
        {"requested_asset_sha256s", "high_sensitivity_approvals"},
        "$.selection",
    )
    requested = payload["selection"]["requested_asset_sha256s"]
    approvals = payload["selection"]["high_sensitivity_approvals"]
    if not isinstance(requested, list) or requested != sorted(set(requested)) or not requested:
        raise ContractError("$.selection.requested_asset_sha256s must be unique and sorted")
    for index, value in enumerate(requested):
        _sha256(value, f"$.selection.requested_asset_sha256s[{index}]")
    if not isinstance(approvals, list) or approvals != sorted(set(approvals)):
        raise ContractError("$.selection.high_sensitivity_approvals must be unique and sorted")
    if any(value not in requested for value in approvals):
        raise ContractError("high-sensitivity approvals must be selected assets")
    expected_rules = {
        "derived_layers": "locator_only",
        "hash_verification": "asset_identity_only",
        "pdf_page_anchor": "locator_only_until_content_review",
        "image_region_anchor": "locator_only_not_subject_identity",
        "accepted_claims": "none",
    }
    if payload["authority_rules"] != expected_rules:
        raise ContractError("$.authority_rules differs from the fixed authority boundary")
    if not isinstance(payload["verifications"], list):
        raise ContractError("$.verifications must be an array")
    for index, item in enumerate(payload["verifications"]):
        _validate_verification(item, f"$.verifications[{index}]")
    assets = [item["asset_sha256"] for item in payload["verifications"]]
    if assets != requested:
        raise ContractError("verification assets differ from the explicit selection")
    high_assets = {item["asset_sha256"] for item in payload["verifications"] if item["sensitivity"] == "high"}
    if not high_assets.issubset(set(approvals)):
        raise ContractError("high-sensitivity verification lacks explicit approval")
    anchors = [anchor for item in payload["verifications"] for anchor in item["anchors"]]
    expected_summary = {
        "selected_assets": len(payload["verifications"]),
        "resolved_originals": sum(item["status"] == "verified" for item in payload["verifications"]),
        "hash_verified_originals": sum(item["hash_verified"] for item in payload["verifications"]),
        "pdf_document_anchors": sum(anchor["kind"] == "pdf_document" for anchor in anchors),
        "pdf_page_anchors": sum(anchor["kind"] == "pdf_page" for anchor in anchors),
        "image_region_anchors": sum(anchor["kind"] == "image_region" for anchor in anchors),
        "claim_ready_assets": 0,
        "accepted_claims": 0,
        "mutations_detected": sum(
            "source_changed_during_read" in item["warnings"] for item in payload["verifications"]
        ),
        "failed_assets": sum(item["status"] == "failed" for item in payload["verifications"]),
        "high_sensitivity_assets": len(high_assets),
    }
    if payload["summary"] != expected_summary:
        raise ContractError("$.summary does not match verification records")
    _warnings(payload["warnings"], "$.warnings")
    _forbid_private_payload_keys(payload)
