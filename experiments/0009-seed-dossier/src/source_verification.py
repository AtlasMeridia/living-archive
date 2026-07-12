"""Build append-only Phase 2 receipts without promoting historical claims."""

from __future__ import annotations

import json
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Iterable

from common import file_sha256, git_snapshot, stable_id, utc_now
from original_inspection import verify_candidate
from verification_io import (
    VerificationError,
    load_phase1_receipt,
    verify_smb_source_access,
)
from verification_validation import validate_source_verification


SCHEMA_VERSION = "source-verification-v0.1"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = EXPERIMENT_ROOT / "source-verification.schema.json"


def _package_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "unavailable"


def _producer() -> dict[str, Any]:
    return {
        "experiment_git": git_snapshot(REPOSITORY_ROOT),
        "contract_sha256": file_sha256(CONTRACT_PATH),
        "python_version": sys.version.split()[0],
        "pypdf_version": _package_version("pypdf"),
        "pillow_version": _package_version("Pillow"),
    }


def build_source_verification(
    dossier_path: Path,
    documents_root: Path,
    media_root: Path,
    selected_sha256s: Iterable[str],
    *,
    high_sensitivity_approvals: Iterable[str] = (),
    image_regions: dict[str, tuple[int, int, int, int]] | None = None,
    source_access: dict[str, Any],
    expected_source_devices: Iterable[int] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    dossier, dossier_sha256, dossier_bytes = load_phase1_receipt(dossier_path)
    selected = sorted(set(selected_sha256s))
    if not selected or any(not SHA256_PATTERN.fullmatch(value) for value in selected):
        raise VerificationError("selection_invalid")
    candidate_items = dossier["candidate_assets"]
    candidate_hashes = [item["asset_sha256"] for item in candidate_items]
    if len(candidate_hashes) != len(set(candidate_hashes)):
        raise VerificationError("phase1_duplicate_candidate_hash")
    candidates = {item["asset_sha256"]: item for item in candidate_items}
    missing = [value for value in selected if value not in candidates]
    if missing:
        raise VerificationError("selection_unknown_asset")
    if any(candidates[value]["media_type"] not in {"document", "photo"} for value in selected):
        raise VerificationError("selection_unsupported_media_type")
    approvals = set(high_sensitivity_approvals)
    unapproved = [
        value
        for value in selected
        if candidates[value]["sensitivity"]["level"] == "high" and value not in approvals
    ]
    if unapproved:
        raise VerificationError("high_sensitivity_approval_required")
    regions = image_regions or {}
    allowed_devices = set(expected_source_devices) if expected_source_devices is not None else None
    if any(value not in selected for value in regions):
        raise VerificationError("image_region_asset_not_selected")

    verifications = [
        verify_candidate(
            candidates[value],
            dossier["evidence_items"],
            documents_root,
            media_root,
            regions.get(value),
            allowed_devices,
        )
        for value in selected
    ]
    anchors = [anchor for item in verifications for anchor in item["anchors"]]
    high_assets = [item for item in verifications if item["sensitivity"] == "high"]
    summary = {
        "selected_assets": len(selected),
        "resolved_originals": sum(item["status"] == "verified" for item in verifications),
        "hash_verified_originals": sum(item["hash_verified"] for item in verifications),
        "pdf_document_anchors": sum(anchor["kind"] == "pdf_document" for anchor in anchors),
        "pdf_page_anchors": sum(anchor["kind"] == "pdf_page" for anchor in anchors),
        "image_region_anchors": sum(anchor["kind"] == "image_region" for anchor in anchors),
        "claim_ready_assets": 0,
        "accepted_claims": 0,
        "mutations_detected": sum(
            "source_changed_during_read" in item["warnings"] for item in verifications
        ),
        "failed_assets": sum(item["status"] == "failed" for item in verifications),
        "high_sensitivity_assets": len(high_assets),
    }
    producer = _producer()
    identity_payload = {
        "phase1_sha256": dossier_sha256,
        "selected": selected,
        "regions": {key: list(value) for key, value in sorted(regions.items())},
        "producer": producer,
        "source_access": source_access,
        "verifications": verifications,
    }
    verification_id = stable_id(
        "verification", json.dumps(identity_payload, sort_keys=True, separators=(",", ":"))
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "verification_id": verification_id,
        "generated_at": generated_at or utc_now(),
        "read_only": True,
        "human_verified": False,
        "visibility": "curator",
        "phase1_receipt": {
            "dossier_id": dossier["dossier_id"],
            "dossier_schema_version": dossier["schema_version"],
            "dossier_sha256": dossier_sha256,
            "dossier_byte_count": dossier_bytes,
        },
        "producer": producer,
        "source_access": source_access,
        "selection": {
            "requested_asset_sha256s": selected,
            "high_sensitivity_approvals": sorted(approvals & set(selected)),
        },
        "authority_rules": {
            "derived_layers": "locator_only",
            "hash_verification": "asset_identity_only",
            "pdf_page_anchor": "locator_only_until_content_review",
            "image_region_anchor": "locator_only_not_subject_identity",
            "accepted_claims": "none",
        },
        "summary": summary,
        "verifications": verifications,
        "accepted_claims": [],
        "warnings": [],
    }
    validate_source_verification(result)
    return result


__all__ = [
    "SCHEMA_VERSION",
    "SHA256_PATTERN",
    "VerificationError",
    "build_source_verification",
    "load_phase1_receipt",
    "verify_smb_source_access",
]
