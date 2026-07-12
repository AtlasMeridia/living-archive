"""Format inspection and conservative evidence anchors for verified originals."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Iterable

from common import stable_id
from verification_io import VerificationError, hash_fd, open_matching_locator


def _pdf_inspection(descriptor: int) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise VerificationError("pypdf_unavailable") from error
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    with os.fdopen(os.dup(descriptor), "rb") as handle:
        try:
            page_count = len(PdfReader(handle, strict=False).pages)
        except Exception as error:
            raise VerificationError("pdf_unreadable") from error
    return {"kind": "pdf", "page_count": page_count}


def _image_inspection(descriptor: int) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError as error:
        raise VerificationError("pillow_unavailable") from error
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        with os.fdopen(os.dup(descriptor), "rb") as handle:
            with Image.open(handle) as image:
                image.verify()
        os.lseek(descriptor, 0, os.SEEK_SET)
        with os.fdopen(os.dup(descriptor), "rb") as handle:
            with Image.open(handle) as image:
                image_format = image.format or "UNKNOWN"
                width, height = image.size
                frame_count = int(getattr(image, "n_frames", 1))
                orientation = int(image.getexif().get(274, 1))
        os.lseek(descriptor, 0, os.SEEK_SET)
    except Exception as error:
        raise VerificationError("image_unreadable") from error
    if orientation in {5, 6, 7, 8}:
        oriented_width, oriented_height = height, width
    else:
        oriented_width, oriented_height = width, height
    return {
        "kind": "image",
        "detected_format": image_format,
        "frame_count": frame_count,
        "encoded_width_pixels": width,
        "encoded_height_pixels": height,
        "exif_orientation": orientation,
        "oriented_width_pixels": oriented_width,
        "oriented_height_pixels": oriented_height,
    }


def _document_anchors(
    asset_sha256: str,
    inspection: dict[str, Any],
    evidence_items: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = [
        {
            "anchor_id": stable_id("anchor", asset_sha256, "pdf_document"),
            "kind": "pdf_document",
            "source_sha256": asset_sha256,
            "claim_support": "asset_identity_only",
            "subject_identity_supported": False,
            "page_count": inspection["page_count"],
        }
    ]
    by_page: dict[int, list[str]] = {}
    for evidence in evidence_items:
        if evidence.get("asset_sha256") != asset_sha256:
            continue
        page = evidence.get("locator", {}).get("page")
        if isinstance(page, int):
            by_page.setdefault(page, []).append(evidence["evidence_id"])
    for page, evidence_ids in sorted(by_page.items()):
        if page < 1 or page > inspection["page_count"]:
            raise VerificationError("pdf_page_out_of_bounds")
        anchors.append(
            {
                "anchor_id": stable_id("anchor", asset_sha256, "pdf_page", page),
                "kind": "pdf_page",
                "source_sha256": asset_sha256,
                "page_number": page,
                "page_index": page - 1,
                "basis_evidence_ids": sorted(set(evidence_ids)),
                "content_reverified": False,
                "claim_support": "locator_only",
                "subject_identity_supported": False,
            }
        )
    return anchors


def _image_anchor(
    asset_sha256: str,
    inspection: dict[str, Any],
    region: tuple[int, int, int, int] | None,
) -> list[dict[str, Any]]:
    if region is None:
        return []
    if inspection["frame_count"] != 1:
        raise VerificationError("image_multiframe_unsupported")
    x, y, width, height = region
    image_width = inspection["oriented_width_pixels"]
    image_height = inspection["oriented_height_pixels"]
    if (
        min(x, y) < 0
        or width <= 0
        or height <= 0
        or x + width > image_width
        or y + height > image_height
    ):
        raise VerificationError("image_region_out_of_bounds")
    return [
        {
            "anchor_id": stable_id(
                "anchor", asset_sha256, "image_region", x, y, width, height
            ),
            "kind": "image_region",
            "source_sha256": asset_sha256,
            "claim_support": "locator_only",
            "subject_identity_supported": False,
            "curator_supplied": True,
            "frame_index": 0,
            "coordinate_space": "exif_oriented_source_pixel_xywh",
            "exif_orientation": inspection["exif_orientation"],
            "encoded_width_pixels": inspection["encoded_width_pixels"],
            "encoded_height_pixels": inspection["encoded_height_pixels"],
            "width_pixels": image_width,
            "height_pixels": image_height,
            "detected_format": inspection["detected_format"],
            "purpose": "curator_supplied_source_region",
            "pixel_region": {"x": x, "y": y, "width": width, "height": height},
        }
    ]


def _failed_record(candidate: dict[str, Any], code: str) -> dict[str, Any]:
    locators = candidate.get("source_files") or [""]
    locator_hash = hashlib.sha256(str(locators[0]).encode("utf-8")).hexdigest()
    root_role = "documents_root" if candidate.get("media_type") == "document" else "media_root"
    return {
        "asset_sha256": candidate["asset_sha256"],
        "media_type": candidate["media_type"],
        "sensitivity": candidate["sensitivity"]["level"],
        "source_locator_ref": {
            "root_role": root_role,
            "relative_path_sha256": locator_hash,
            "locator_source": "base_dossier.candidate_assets.source_files",
        },
        "status": "failed",
        "hash_verified": False,
        "unchanged_after_read": False,
        "anchors": [],
        "claim_ready": False,
        "human_verified": False,
        "visibility": "curator",
        "warnings": [code],
    }


def verify_candidate(
    candidate: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    documents_root: Path,
    media_root: Path,
    region: tuple[int, int, int, int] | None,
    allowed_devices: set[int] | None = None,
) -> dict[str, Any]:
    try:
        descriptor, locator, root_role = open_matching_locator(
            candidate, documents_root, media_root, allowed_devices
        )
    except VerificationError as error:
        return _failed_record(candidate, str(error))

    try:
        before = os.fstat(descriptor)
        observed_before = hash_fd(descriptor)
        if observed_before != candidate["asset_sha256"]:
            return _failed_record(candidate, "source_hash_mismatch")
        if candidate["media_type"] == "document":
            inspection = _pdf_inspection(descriptor)
            anchors = _document_anchors(
                candidate["asset_sha256"], inspection, evidence_items
            )
            warnings = (
                []
                if any(anchor["kind"] == "pdf_page" for anchor in anchors)
                else ["pdf_page_anchor_unavailable"]
            )
        elif candidate["media_type"] == "photo":
            inspection = _image_inspection(descriptor)
            anchors = _image_anchor(candidate["asset_sha256"], inspection, region)
            warnings = [] if anchors else ["image_region_not_supplied"]
        else:
            raise VerificationError("unsupported_media_type")
        observed_after = hash_fd(descriptor)
        after = os.fstat(descriptor)
        unchanged = (
            observed_before == observed_after
            and before.st_size == after.st_size
            and before.st_mtime_ns == after.st_mtime_ns
        )
        if not unchanged:
            return _failed_record(candidate, "source_changed_during_read")
        locator_hash = hashlib.sha256(locator.encode("utf-8")).hexdigest()
        return {
            "asset_sha256": candidate["asset_sha256"],
            "media_type": candidate["media_type"],
            "sensitivity": candidate["sensitivity"]["level"],
            "source_locator_ref": {
                "root_role": root_role,
                "relative_path_sha256": locator_hash,
                "locator_source": "base_dossier.candidate_assets.source_files",
            },
            "source_sha256": observed_after,
            "source_size_bytes": after.st_size,
            "status": "verified",
            "hash_verified": True,
            "unchanged_after_read": True,
            "anchors": anchors,
            "claim_ready": False,
            "human_verified": False,
            "visibility": "curator",
            "warnings": warnings,
        }
    except VerificationError as error:
        return _failed_record(candidate, str(error))
    finally:
        os.close(descriptor)
