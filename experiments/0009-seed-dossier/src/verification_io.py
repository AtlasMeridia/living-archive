"""Read-only file and SMB identity primitives for source verification."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote

from validation import validate_dossier


EXPECTED_SMB_USER = "living_archive_ro"
EXPECTED_SMB_HOST = "mneme.local"
EXPECTED_SMB_SHARE = "MNEME"


class VerificationError(ValueError):
    """Raised when an input cannot satisfy the fail-closed contract."""


def hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def hash_fd(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest()


def load_phase1_receipt(path: Path) -> tuple[dict[str, Any], str, int]:
    """Load and validate exact Phase 1 bytes without following a final symlink."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise VerificationError("phase1_receipt_unreadable") from error
    try:
        receipt_stat = os.fstat(descriptor)
        if not stat.S_ISREG(receipt_stat.st_mode):
            raise VerificationError("phase1_receipt_not_regular_file")
        if stat.S_IMODE(receipt_stat.st_mode) & 0o077:
            raise VerificationError("phase1_receipt_permissions_too_broad")
        with os.fdopen(os.dup(descriptor), "rb") as handle:
            raw = handle.read()
    finally:
        os.close(descriptor)
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError("phase1_receipt_invalid_json") from error
    validate_dossier(payload)
    return payload, hash_bytes(raw), len(raw)


def _relative_locator(value: object) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise VerificationError("source_locator_invalid")
    parts = value.split("/")
    if value.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise VerificationError("source_locator_invalid")
    return tuple(parts)


def _open_source_beneath(root: Path, locator: object) -> tuple[int, str]:
    """Open a regular source file read-only beneath a non-symlinked root."""
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        current_descriptor = os.open(root, directory_flags)
    except OSError as error:
        raise VerificationError("source_root_unavailable") from error
    parts = _relative_locator(locator)
    try:
        for part in parts[:-1]:
            try:
                next_descriptor = os.open(part, directory_flags, dir_fd=current_descriptor)
            except OSError as error:
                raise VerificationError("source_locator_unresolved") from error
            os.close(current_descriptor)
            current_descriptor = next_descriptor
        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(parts[-1], file_flags, dir_fd=current_descriptor)
        except OSError as error:
            raise VerificationError("source_unreadable") from error
    finally:
        os.close(current_descriptor)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise VerificationError("source_not_regular_file")
    return descriptor, str(locator)


def _candidate_root(media_type: str, documents_root: Path, media_root: Path) -> tuple[str, Path]:
    if media_type == "document":
        return "documents_root", documents_root
    if media_type == "photo":
        return "media_root", media_root
    raise VerificationError("unsupported_media_type")


def open_matching_locator(
    candidate: dict[str, Any],
    documents_root: Path,
    media_root: Path,
    allowed_devices: set[int] | None = None,
) -> tuple[int, str, str]:
    """Return the one candidate locator whose original bytes match its asset hash."""
    root_role, root = _candidate_root(candidate["media_type"], documents_root, media_root)
    matching: list[tuple[int, str]] = []
    seen_files: set[tuple[int, int]] = set()
    for locator in candidate.get("source_files", []):
        try:
            descriptor, raw_locator = _open_source_beneath(root, locator)
        except VerificationError:
            continue
        observed = hash_fd(descriptor)
        if observed != candidate["asset_sha256"]:
            os.close(descriptor)
            continue
        source_stat = os.fstat(descriptor)
        if allowed_devices is not None and source_stat.st_dev not in allowed_devices:
            os.close(descriptor)
            continue
        file_key = (source_stat.st_dev, source_stat.st_ino)
        if file_key in seen_files:
            os.close(descriptor)
            continue
        seen_files.add(file_key)
        matching.append((descriptor, raw_locator))
    if not matching:
        raise VerificationError("source_hash_match_not_found")
    if len(matching) > 1:
        for descriptor, _ in matching:
            os.close(descriptor)
        raise VerificationError("source_locator_ambiguous")
    descriptor, locator = matching[0]
    return descriptor, locator, root_role


def verify_smb_source_access(
    roots: Iterable[Path],
) -> tuple[dict[str, Any], frozenset[int]]:
    """Confirm that every source root is on the expected live SMB session."""
    try:
        result = subprocess.run(
            ["/sbin/mount"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise VerificationError("smb_identity_unavailable") from error
    pattern = re.compile(r"^//(?P<user>[^@/]+)@(?P<host>[^/]+)/(?P<share>.+)$")
    parsed_mounts: list[tuple[Path, dict[str, str]]] = []
    for line in result.stdout.splitlines():
        source, separator, remainder = line.partition(" on ")
        if not separator:
            continue
        target, options_separator, options = remainder.partition(" (")
        match = pattern.fullmatch(source)
        if not options_separator or match is None:
            continue
        if options.rstrip(")").split(",", 1)[0] != "smbfs":
            continue
        parsed_mounts.append(
            (
                Path(target),
                {key: unquote(value) for key, value in match.groupdict().items()},
            )
        )
    expected = {
        "user": EXPECTED_SMB_USER,
        "host": EXPECTED_SMB_HOST.casefold().rstrip("."),
        "share": EXPECTED_SMB_SHARE,
    }
    devices: set[int] = set()
    for root in roots:
        try:
            resolved = root.resolve(strict=True)
        except OSError as error:
            raise VerificationError("source_root_unavailable") from error
        matches = []
        for target, identity in parsed_mounts:
            try:
                resolved.relative_to(target)
            except ValueError:
                continue
            matches.append((len(target.parts), identity))
        if not matches:
            raise VerificationError("source_root_not_smb")
        identity = max(matches, key=lambda item: item[0])[1]
        normalized = {**identity, "host": identity["host"].casefold().rstrip(".")}
        if normalized != expected:
            raise VerificationError("smb_identity_mismatch")
        devices.add(resolved.stat().st_dev)
    return (
        {
            "protocol": "smb",
            "user": EXPECTED_SMB_USER,
            "host": EXPECTED_SMB_HOST,
            "share": EXPECTED_SMB_SHARE,
            "identity_verified": True,
            "server_acl_verification": "external_prerequisite",
        },
        frozenset(devices),
    )
