"""Read-only readers for Living Archive's existing derived layers."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from common import (
    AliasMatcher,
    BuildOptions,
    PAGE_HEADER,
    iter_text_fields,
    sensitivity_from_analysis,
    stable_id,
    table_columns,
    table_exists,
)


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SourceReader:
    """Discover candidates while retaining the authority of every input."""

    def __init__(self, project_root: Path, options: BuildOptions):
        self.project_root = project_root.resolve()
        self.data_root = self.project_root / "data"
        self.matcher = AliasMatcher((options.subject_label, *options.aliases))
        self.options = options
        self.catalog_path = self.data_root / "catalog.db"
        self.synthesis_path = self.data_root / "synthesis.db"
        self.registry_path = self.data_root / "people" / "registry.json"

        self.catalog_by_sha: dict[str, dict[str, Any]] = {}
        self.manifests_by_sha: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.candidates: dict[str, dict[str, Any]] = {}
        self.evidence_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
        self.timeline_candidates: list[dict[str, Any]] = []
        self.subject_candidates: list[dict[str, Any]] = []
        self.manifest_paths: list[Path] = []
        self.matched_text_paths: list[Path] = []
        self.document_run_ids: set[str] = set()
        self.photo_run_ids: set[str] = set()
        self.warnings: list[str] = []

    @staticmethod
    def _valid_sha256(value: object) -> str | None:
        """Return a strict lowercase SHA-256 value, or None when invalid."""
        if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
            return None
        return value

    @staticmethod
    def _manifest_filename_matches(path: Path, sha256: str) -> bool:
        """Accept the current 12-character stem or a future full-hash stem."""
        return path.stem in {sha256[:12], sha256}

    def _candidate(self, sha256: str, media_type: str | None = None) -> dict[str, Any]:
        candidate = self.candidates.setdefault(
            sha256,
            {
                "asset_sha256": sha256,
                "media_type": media_type or "unknown",
                "source_files": set(),
                "discovery_reasons": [],
                "_reason_keys": set(),
            },
        )
        if candidate["media_type"] == "unknown" and media_type:
            candidate["media_type"] = media_type
        return candidate

    def _add_reason(
        self,
        sha256: str,
        media_type: str | None,
        kind: str,
        **details: Any,
    ) -> None:
        candidate = self._candidate(sha256, media_type)
        payload = {
            "kind": kind,
            **{key: value for key, value in details.items() if value is not None},
        }
        key = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        reason = {
            "reason_id": stable_id("reason", sha256, key),
            **payload,
        }
        if key not in candidate["_reason_keys"]:
            candidate["_reason_keys"].add(key)
            candidate["discovery_reasons"].append(reason)

    def _read_catalog(self) -> None:
        if not self.catalog_path.exists():
            self.warnings.append("catalog_missing")
            return
        connection = sqlite3.connect(f"file:{self.catalog_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            if not table_exists(connection, "assets"):
                self.warnings.append("catalog_assets_table_missing")
                return
            available = table_columns(connection, "assets")
            if "sha256" not in available:
                self.warnings.append("catalog_assets_sha256_column_missing")
                return
            desired = [
                "sha256",
                "path",
                "content_type",
                "manifest_path",
                "run_id",
                "status",
                "slice",
                "file_size",
                "file_mtime",
            ]
            selected = [column for column in desired if column in available]
            for row in connection.execute(f"SELECT {', '.join(selected)} FROM assets"):
                payload = dict(row)
                sha256 = self._valid_sha256(payload.get("sha256"))
                if sha256 is None:
                    self.warnings.append("catalog_asset_invalid_sha256")
                    continue
                self.catalog_by_sha[sha256] = payload
                path = str(payload.get("path") or "")
                for alias in self.matcher.aliases_in(path):
                    self._add_reason(
                        sha256,
                        payload.get("content_type"),
                        "catalog_path_match",
                        alias=alias,
                        authority="locator_only",
                    )
        finally:
            connection.close()

    def _read_synthesis_candidates(self) -> None:
        if not self.synthesis_path.exists():
            self.warnings.append("legacy_synthesis_missing")
            return
        connection = sqlite3.connect(f"file:{self.synthesis_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            if not table_exists(connection, "entities") or not table_exists(
                connection, "entity_assets"
            ):
                self.warnings.append("legacy_synthesis_tables_missing")
                return
            entity_columns = table_columns(connection, "entities")
            required_entity_columns = {"entity_id", "entity_type"}
            missing_entity_columns = sorted(required_entity_columns - entity_columns)
            if missing_entity_columns:
                self.warnings.append(
                    "legacy_synthesis_entities_columns_missing:"
                    + ",".join(missing_entity_columns)
                )
                return
            name_columns = [
                column
                for column in ("entity_value", "normalized_value", "name_en", "name_zh")
                if column in entity_columns
            ]
            if not name_columns:
                self.warnings.append("legacy_synthesis_entity_name_columns_missing")
                return

            asset_columns = table_columns(connection, "entity_assets")
            required_asset_columns = {"entity_id", "asset_sha256"}
            missing_asset_columns = sorted(required_asset_columns - asset_columns)
            if missing_asset_columns:
                self.warnings.append(
                    "legacy_synthesis_entity_assets_columns_missing:"
                    + ",".join(missing_asset_columns)
                )
                return

            matched_entities: dict[Any, set[str]] = {}
            selected = ["entity_id"] + name_columns
            entity_query = (
                f"SELECT {', '.join(selected)} FROM entities "
                "WHERE LOWER(CAST(entity_type AS TEXT)) = 'person'"
            )
            for row in connection.execute(entity_query):
                aliases: set[str] = set()
                for column in name_columns:
                    aliases.update(self.matcher.aliases_in(row[column]))
                if aliases:
                    matched_entities[row["entity_id"]] = aliases
            if not matched_entities:
                return

            placeholders = ",".join("?" for _ in matched_entities)
            selected_asset_columns = ["entity_id", "asset_sha256"]
            selected_asset_columns.extend(
                column
                for column in ("source", "confidence")
                if column in asset_columns
            )
            query = (
                f"SELECT {', '.join(selected_asset_columns)} "
                f"FROM entity_assets WHERE entity_id IN ({placeholders})"
            )
            for row in connection.execute(query, tuple(matched_entities)):
                payload = dict(row)
                sha256 = self._valid_sha256(payload.get("asset_sha256"))
                if sha256 is None:
                    self.warnings.append("legacy_synthesis_asset_invalid_sha256")
                    continue
                source = payload.get("source")
                media_type = source if source in {"photo", "document"} else None
                self._add_reason(
                    sha256,
                    media_type,
                    "legacy_synthesis_link",
                    entity_id=payload["entity_id"],
                    aliases=sorted(matched_entities[payload["entity_id"]]),
                    source=source,
                    original_confidence=payload.get("confidence"),
                    authority="locator_only",
                )
        finally:
            connection.close()

    def _manifest_record(
        self, path: Path, payload: dict[str, Any], media_type: str
    ) -> dict[str, Any]:
        analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
        inference = payload.get("inference") if isinstance(payload.get("inference"), dict) else {}
        run_id = path.parent.parent.name
        if media_type == "document":
            date_value = analysis.get("date")
            document_type = analysis.get("document_type")
            sensitivity = sensitivity_from_analysis(analysis)
            self.document_run_ids.add(run_id)
        else:
            date_value = analysis.get("date_estimate")
            document_type = None
            sensitivity = {"level": "review", "reasons": ["family_photo"]}
            self.photo_run_ids.add(run_id)
        return {
            "manifest_path": str(path.relative_to(self.project_root)),
            "run_id": run_id,
            "media_type": media_type,
            "source_file": payload.get("source_file"),
            "date_proposal": date_value,
            "date_confidence": analysis.get("date_confidence"),
            "date_precision": analysis.get("date_precision"),
            "document_type": document_type,
            "people_count": analysis.get("people_count") if media_type == "photo" else None,
            "sensitivity": sensitivity,
            "inference": {
                key: inference.get(key)
                for key in ("method", "provider", "model", "prompt_version", "timestamp")
                if inference.get(key) is not None
            },
            "status": "machine_proposal",
        }

    def _add_manifest_alias_reasons(
        self,
        sha256: str,
        media_type: str,
        payload: dict[str, Any],
        manifest_path: Path,
        *,
        trusted_identity: bool,
    ) -> None:
        """Add manifest matches without upgrading identity-mismatched inputs."""
        relative_manifest = str(manifest_path.relative_to(self.project_root))
        authority = "machine_proposal" if trusted_identity else "locator_only"
        path_kind = (
            "manifest_source_path_match"
            if trusted_identity
            else "untrusted_manifest_source_path_match"
        )
        analysis_kind = (
            "manifest_analysis_match"
            if trusted_identity
            else "untrusted_manifest_analysis_match"
        )

        source_file = str(payload.get("source_file") or "")
        for alias in self.matcher.aliases_in(source_file):
            self._add_reason(
                sha256,
                media_type,
                path_kind,
                alias=alias,
                manifest_path=relative_manifest,
                authority=authority,
            )

        analysis = payload.get("analysis")
        if isinstance(analysis, dict):
            for field, text in iter_text_fields(analysis):
                for alias in self.matcher.aliases_in(text):
                    self._add_reason(
                        sha256,
                        media_type,
                        analysis_kind,
                        alias=alias,
                        field=field,
                        manifest_path=relative_manifest,
                        authority=authority,
                    )

    def _scan_manifests(self) -> None:
        groups = (
            ("document", self.data_root / "documents" / "runs"),
            ("photo", self.data_root / "photos" / "runs"),
        )
        for media_type, runs_root in groups:
            paths = sorted(runs_root.glob("*/manifests/*.json")) if runs_root.exists() else []
            for path in paths:
                self.manifest_paths.append(path)
                try:
                    payload = json.loads(path.read_text())
                except (OSError, json.JSONDecodeError):
                    self.warnings.append(
                        f"manifest_unreadable:{path.relative_to(self.project_root)}"
                    )
                    continue
                sha256 = self._valid_sha256(payload.get("source_sha256"))
                if sha256 is None:
                    self.warnings.append(
                        f"manifest_invalid_sha256:{path.relative_to(self.project_root)}"
                    )
                    continue

                manifest_identity_valid = self._manifest_filename_matches(path, sha256)
                if not manifest_identity_valid:
                    self.warnings.append(
                        f"manifest_filename_sha_mismatch:{path.relative_to(self.project_root)}"
                    )

                    # Preserve matching text as a locator only. Do not retain this
                    # manifest as an observation version or follow its extraction
                    # pointer because its asset identity is not trustworthy.
                    self._add_manifest_alias_reasons(
                        sha256,
                        media_type,
                        payload,
                        path,
                        trusted_identity=False,
                    )
                    continue

                record = self._manifest_record(path, payload, media_type)
                if media_type == "document" and not self._scan_extracted_text(
                    path, payload, record
                ):
                    self._add_manifest_alias_reasons(
                        sha256,
                        media_type,
                        payload,
                        path,
                        trusted_identity=False,
                    )
                    continue

                self.manifests_by_sha[sha256].append(record)
                self._add_manifest_alias_reasons(
                    sha256,
                    media_type,
                    payload,
                    path,
                    trusted_identity=True,
                )

    def _scan_extracted_text(
        self,
        manifest_path: Path,
        manifest: dict[str, Any],
        manifest_record: dict[str, Any],
    ) -> bool:
        extraction = manifest.get("extraction")
        if not isinstance(extraction, dict):
            self.warnings.append(
                f"extracted_text_metadata_missing:{manifest_path.relative_to(self.project_root)}"
            )
            return False
        relative_text_path = extraction.get("text_file")
        if not isinstance(relative_text_path, str) or not relative_text_path:
            self.warnings.append(
                f"extracted_text_path_missing:{manifest_path.relative_to(self.project_root)}"
            )
            return False

        sha256 = self._valid_sha256(manifest.get("source_sha256"))
        if sha256 is None:
            self.warnings.append(
                f"extracted_text_manifest_sha_invalid:{manifest_path.relative_to(self.project_root)}"
            )
            return False

        relative_path = Path(relative_text_path)
        if relative_path.is_absolute():
            self.warnings.append(
                f"extracted_text_path_absolute:{manifest_path.relative_to(self.project_root)}"
            )
            return False

        run_root = manifest_path.parent.parent
        expected_root = run_root / "extracted-text"
        if expected_root.is_symlink():
            self.warnings.append(
                f"extracted_text_root_symlink:{manifest_path.relative_to(self.project_root)}"
            )
            return False
        lexical_text_path = run_root / relative_path
        try:
            run_root_resolved = run_root.resolve(strict=True)
            expected_root_resolved = expected_root.resolve(strict=True)
            text_path = lexical_text_path.resolve(strict=True)
        except OSError:
            self.warnings.append(
                f"extracted_text_missing:{manifest_path.relative_to(self.project_root)}"
            )
            return False

        if not expected_root_resolved.is_relative_to(run_root_resolved):
            self.warnings.append(
                f"extracted_text_root_escape:{manifest_path.relative_to(self.project_root)}"
            )
            return False

        if not text_path.is_relative_to(expected_root_resolved):
            self.warnings.append(
                f"extracted_text_path_escape:{manifest_path.relative_to(self.project_root)}"
            )
            return False

        expected_names = {f"{sha256[:12]}.txt", f"{sha256}.txt"}
        if relative_path.name not in expected_names or text_path.name not in expected_names:
            self.warnings.append(
                f"extracted_text_filename_sha_mismatch:{manifest_path.relative_to(self.project_root)}"
            )
            return False
        logical_text_path = expected_root / text_path.relative_to(expected_root_resolved)

        try:
            raw_text = text_path.read_bytes()
        except OSError:
            self.warnings.append(
                f"extracted_text_unreadable:{manifest_path.relative_to(self.project_root)}"
            )
            return False
        raw_text_hash = hashlib.sha256(raw_text).hexdigest()
        try:
            full_text = raw_text.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            self.warnings.append(
                f"extracted_text_invalid_utf8:{manifest_path.relative_to(self.project_root)}"
            )
            return False

        headers = list(PAGE_HEADER.finditer(full_text))
        if not headers:
            self.warnings.append(
                f"extracted_text_page_headers_missing:{manifest_path.relative_to(self.project_root)}"
            )
            return False

        sensitivity = manifest_record["sensitivity"]
        matched_file = False
        for page_index, header in enumerate(headers):
            page_number = int(header.group(1))
            page_start = header.end()
            page_end = (
                headers[page_index + 1].start()
                if page_index + 1 < len(headers)
                else len(full_text)
            )
            page_text = full_text[page_start:page_end]
            for matched_aliases, start, end in self.matcher.occurrences(page_text):
                alias = matched_aliases[0]
                matched_file = True
                self._add_reason(
                    sha256,
                    "document",
                    "extracted_text_match",
                    alias=alias,
                    aliases=list(matched_aliases),
                    page=page_number,
                    authority="exact_extracted_text",
                )
                artifact_char_start = page_start + start
                artifact_char_end = page_start + end
                artifact_byte_start = len(
                    full_text[:artifact_char_start].encode("utf-8")
                )
                artifact_byte_end = len(full_text[:artifact_char_end].encode("utf-8"))
                key = (
                    sha256,
                    raw_text_hash,
                    page_number,
                    start,
                    end,
                    tuple(item.casefold() for item in matched_aliases),
                )
                extraction_ref = {
                    "run_id": manifest_record["run_id"],
                    "text_file": str(logical_text_path.relative_to(self.project_root)),
                    "manifest_path": manifest_record["manifest_path"],
                }
                evidence = self.evidence_by_key.get(key)
                if evidence is None:
                    evidence = {
                        "evidence_id": stable_id(
                            "evidence",
                            sha256,
                            raw_text_hash,
                            page_number,
                            start,
                            end,
                            *(item.casefold() for item in matched_aliases),
                        ),
                        "asset_sha256": sha256,
                        "media_type": "document",
                        "source_role": "extracted_text_candidate",
                        "locator": {
                            "page": page_number,
                            "char_start": start,
                            "char_end": end,
                            "coordinate_space": "utf8_codepoints_within_page_body",
                            "page_body_char_start_in_artifact": page_start,
                            "artifact_char_start": artifact_char_start,
                            "artifact_char_end": artifact_char_end,
                            "artifact_byte_start": artifact_byte_start,
                            "artifact_byte_end": artifact_byte_end,
                            "extraction_sha256": raw_text_hash,
                            "raw_artifact_sha256": raw_text_hash,
                        },
                        "matched_alias": alias,
                        "matched_aliases": list(matched_aliases),
                        "extraction_refs": [],
                        "sensitivity": sensitivity,
                        "visibility": "curator",
                        "human_verified": False,
                    }
                    self.evidence_by_key[key] = evidence
                elif sensitivity["level"] == "high":
                    evidence["sensitivity"] = sensitivity
                if extraction_ref not in evidence["extraction_refs"]:
                    evidence["extraction_refs"].append(extraction_ref)
        if matched_file:
            self.matched_text_paths.append(text_path)
        return True

    def _read_people_registry(self) -> None:
        if not self.registry_path.exists():
            self.warnings.append("people_registry_missing")
            return
        try:
            payload = json.loads(self.registry_path.read_text())
        except (OSError, json.JSONDecodeError):
            self.warnings.append("people_registry_unreadable")
            return
        people = payload.get("people") if isinstance(payload, dict) else None
        if not isinstance(people, list):
            return
        for person in people:
            if not isinstance(person, dict):
                continue
            matches: set[str] = set()
            for field in ("name_en", "name_zh", "notes"):
                matches.update(self.matcher.aliases_in(person.get(field)))
            if not matches:
                continue
            self.subject_candidates.append(
                {
                    "person_id": person.get("person_id"),
                    "name_en": person.get("name_en"),
                    "name_zh": person.get("name_zh"),
                    "matched_aliases": sorted(matches),
                    "immich_person_ids": sorted(person.get("immich_person_ids") or []),
                    "source_role": "machine_derived_locator",
                    "human_verified": False,
                    "visibility": "curator",
                }
            )
