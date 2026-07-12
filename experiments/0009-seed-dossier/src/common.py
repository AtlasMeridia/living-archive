"""Shared primitives for the seed-dossier experiment."""

from __future__ import annotations

import hashlib
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA_VERSION = "seed-dossier-v0.1"
PAGE_HEADER = re.compile(r"(?m)^--- Page (\d+) ---\s*\n")
YEAR_PATTERN = re.compile(r"(?<!\d)((?:18|19|20)\d{2})(?!\d)")
HIGH_RISK_TYPE_PREFIXES = ("financial/", "legal/", "medical/")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "subject"


def file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint_files(paths: Iterable[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(set(paths)):
        try:
            relative = path.relative_to(root)
        except ValueError:
            relative = path
        digest.update(str(relative).encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update((file_sha256(path) or "missing").encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


class AliasMatcher:
    """Case-insensitive Latin and exact-script alias matcher."""

    def __init__(self, aliases: Iterable[str]):
        seen: set[str] = set()
        self.aliases: list[str] = []
        self.patterns: list[tuple[str, re.Pattern[str]]] = []
        for raw in aliases:
            alias = raw.strip()
            key = alias.casefold()
            if not alias or key in seen:
                continue
            seen.add(key)
            self.aliases.append(alias)
            escaped = re.escape(alias)
            escaped = re.sub(r"(?:\\[ _-])+", r"[\\s_-]+", escaped)
            if any(character.isascii() and character.isalnum() for character in alias):
                expression = rf"(?<!\w){escaped}(?!\w)"
                flags = re.IGNORECASE
            else:
                expression = escaped
                flags = 0
            self.patterns.append((alias, re.compile(expression, flags)))

    def aliases_in(self, text: object) -> list[str]:
        if not isinstance(text, str) or not text:
            return []
        return [alias for alias, pattern in self.patterns if pattern.search(text)]

    def occurrences(self, text: str) -> Iterator[tuple[tuple[str, ...], int, int]]:
        """Yield non-overlapping longest spans while retaining alias alternatives."""
        matches: list[tuple[int, int, str, int]] = []
        for alias_index, (alias, pattern) in enumerate(self.patterns):
            for match in pattern.finditer(text):
                matches.append((match.start(), match.end(), alias, alias_index))
        matches.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[3]))

        groups: list[list[tuple[int, int, str, int]]] = []
        for match in matches:
            if not groups or match[0] >= max(item[1] for item in groups[-1]):
                groups.append([match])
            else:
                groups[-1].append(match)
        for group in groups:
            chosen = min(
                group,
                key=lambda item: (-(item[1] - item[0]), item[3], item[0]),
            )
            aliases = [chosen[2]]
            aliases.extend(
                item[2]
                for item in sorted(group, key=lambda item: item[3])
                if item[2].casefold() != chosen[2].casefold()
            )
            yield tuple(aliases), chosen[0], chosen[1]


def iter_text_fields(value: Any, prefix: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield prefix or "$", value
    elif isinstance(value, dict):
        for key in sorted(value):
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            yield from iter_text_fields(value[key], next_prefix)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_text_fields(item, f"{prefix}[{index}]")


def split_pages(text: str) -> Iterator[tuple[int | None, str]]:
    headers = list(PAGE_HEADER.finditer(text))
    if not headers:
        yield None, text
        return
    for index, header in enumerate(headers):
        page_start = header.end()
        page_end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        yield int(header.group(1)), text[page_start:page_end]


def years_in(value: object) -> list[int]:
    if value is None:
        return []
    return [int(match.group(1)) for match in YEAR_PATTERN.finditer(str(value))]


def in_period(value: object, start_year: int, end_year: int) -> bool:
    return any(start_year <= year <= end_year for year in years_in(value))


def git_snapshot(project_root: Path) -> dict[str, Any]:
    def run(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(project_root), *args],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        return result.stdout.strip()

    commit = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    dirty_diff = run("diff", "--binary", "HEAD", "--")
    status_sha256 = (
        hashlib.sha256(status.encode("utf-8")).hexdigest() if status is not None else None
    )
    dirty_diff_sha256 = (
        hashlib.sha256(dirty_diff.encode("utf-8")).hexdigest()
        if dirty_diff is not None
        else None
    )
    return {
        "commit": commit,
        "dirty": bool(status) if status is not None else None,
        "status_sha256": status_sha256,
        "dirty_diff_sha256": dirty_diff_sha256,
    }


def sensitivity_from_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    document_type = str(analysis.get("document_type") or "unknown")
    raw_flags = analysis.get("sensitivity")
    flags = raw_flags if isinstance(raw_flags, dict) else {}
    true_flags = sorted(key for key, value in flags.items() if value is True)
    type_is_high = document_type.startswith(HIGH_RISK_TYPE_PREFIXES)
    level = "high" if type_is_high or true_flags else "review"
    reasons: list[str] = []
    if type_is_high:
        reasons.append("restricted_document_type")
    if true_flags:
        reasons.append("manifest_sensitivity_flag")
    if not reasons:
        reasons.append("unclassified_family_document")
    return {
        "level": level,
        "document_type": document_type,
        "flags": {key: bool(value) for key, value in sorted(flags.items())},
        "reasons": reasons,
    }


@dataclass(frozen=True)
class BuildOptions:
    subject_label: str
    aliases: tuple[str, ...]
    start_year: int
    end_year: int
    generated_at: str | None = None
