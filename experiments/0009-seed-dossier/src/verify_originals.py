#!/usr/bin/env python3
"""Write a private Phase 2 receipt for selected original source files."""

from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path

import seed_dossier
from source_verification import (
    SHA256_PATTERN,
    VerificationError,
    build_source_verification,
    load_phase1_receipt,
    verify_smb_source_access,
)


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        description=(
            "Verify explicitly selected Phase 1 locators against read-only "
            "originals without promoting historical claims."
        )
    )
    argument_parser.add_argument("--dossier", required=True, type=Path)
    argument_parser.add_argument("--documents-root", required=True, type=Path)
    argument_parser.add_argument("--media-root", required=True, type=Path)
    argument_parser.add_argument(
        "--asset-sha256",
        action="append",
        required=True,
        help="Exact Phase 1 candidate hash; repeat for a bounded allowlist",
    )
    argument_parser.add_argument(
        "--allow-high-sensitivity",
        action="append",
        default=[],
        metavar="SHA256",
        help="Explicitly approve one selected high-sensitivity candidate",
    )
    argument_parser.add_argument(
        "--image-region",
        action="append",
        default=[],
        metavar="SHA256:X:Y:WIDTH:HEIGHT",
        help="Curator-supplied pixel region; no region is inferred automatically",
    )
    argument_parser.add_argument(
        "--output-name",
        help="Optional JSON basename inside the private run directory",
    )
    return argument_parser


def _private_dossier_path(path: Path) -> Path:
    private_root = seed_dossier.PRIVATE_RUN_ROOT
    if private_root.is_symlink():
        raise VerificationError("private_run_root_symlink")
    try:
        resolved_root = private_root.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        resolved_path.relative_to(resolved_root)
    except (OSError, ValueError) as error:
        raise VerificationError("phase1_receipt_outside_private_root") from error
    if path.is_symlink() or not resolved_path.is_file():
        raise VerificationError("phase1_receipt_invalid_file")
    if stat.S_IMODE(resolved_path.stat().st_mode) & 0o077:
        raise VerificationError("phase1_receipt_permissions_too_broad")
    return resolved_path


def _parse_regions(values: list[str]) -> dict[str, tuple[int, int, int, int]]:
    regions: dict[str, tuple[int, int, int, int]] = {}
    for value in values:
        parts = value.split(":")
        if len(parts) != 5 or not SHA256_PATTERN.fullmatch(parts[0]):
            raise VerificationError("image_region_invalid")
        try:
            region = tuple(int(part) for part in parts[1:])
        except ValueError as error:
            raise VerificationError("image_region_invalid") from error
        if parts[0] in regions:
            raise VerificationError("image_region_duplicate")
        regions[parts[0]] = region  # type: ignore[assignment]
    return regions


def main(argv: list[str] | None = None) -> int:
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    try:
        dossier_path = _private_dossier_path(args.dossier)
        regions = _parse_regions(args.image_region)
        source_access, source_devices = verify_smb_source_access(
            (args.documents_root, args.media_root)
        )
        receipt = build_source_verification(
            dossier_path,
            args.documents_root,
            args.media_root,
            args.asset_sha256,
            high_sensitivity_approvals=args.allow_high_sensitivity,
            image_regions=regions,
            source_access=source_access,
            expected_source_devices=source_devices,
        )
        _, final_dossier_sha256, final_dossier_size = load_phase1_receipt(dossier_path)
        phase1 = receipt["phase1_receipt"]
        if (
            final_dossier_sha256 != phase1["dossier_sha256"]
            or final_dossier_size != phase1["dossier_byte_count"]
        ):
            raise VerificationError("phase1_receipt_changed_during_verification")
        final_access, final_devices = verify_smb_source_access(
            (args.documents_root, args.media_root)
        )
        if final_access != source_access or final_devices != source_devices:
            raise VerificationError("smb_session_changed_during_verification")
        output_name = args.output_name or f"{receipt['verification_id']}.json"
        output = seed_dossier.private_output_path(output_name)
        seed_dossier.atomic_write_json(output, receipt, replace_existing=False)
    except (VerificationError, FileExistsError, ValueError) as error:
        argument_parser.error(str(error))

    safe_summary = {
        "verification_id": receipt["verification_id"],
        "output": str(output),
        **receipt["summary"],
        "visibility": receipt["visibility"],
        "human_verified": receipt["human_verified"],
    }
    print(json.dumps(safe_summary, indent=2, sort_keys=True))
    return 2 if receipt["summary"]["failed_assets"] else 0


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(main())
