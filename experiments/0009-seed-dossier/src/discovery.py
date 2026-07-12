"""Compile read-only source discoveries into a private seed dossier."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from common import (
    SCHEMA_VERSION,
    BuildOptions,
    file_sha256,
    fingerprint_files,
    git_snapshot,
    in_period,
    stable_id,
    table_columns,
    table_exists,
    utc_now,
    years_in,
)
from source_reader import SourceReader


class DossierBuilder(SourceReader):
    """Compile candidate pointers without upgrading them into historical facts."""

    def __init__(self, project_root: Path, options: BuildOptions):
        super().__init__(project_root, options)
        self.unanchored_timeline_signals: list[dict[str, Any]] = []

    def _read_legacy_timeline(self) -> None:
        if not self.synthesis_path.exists() or not self.candidates:
            return
        connection = sqlite3.connect(f"file:{self.synthesis_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            if not table_exists(connection, "timeline_events"):
                return
            columns = table_columns(connection, "timeline_events")
            required_columns = {"asset_sha256", "date_normalized"}
            missing_columns = sorted(required_columns - columns)
            if missing_columns:
                self.warnings.append(
                    "legacy_timeline_columns_missing:" + ",".join(missing_columns)
                )
                return
            desired = [
                "event_id",
                "date_normalized",
                "date_precision",
                "event_type",
                "asset_sha256",
                "source",
            ]
            selected = [column for column in desired if column in columns]
            hashes = sorted(self.candidates)
            for offset in range(0, len(hashes), 500):
                batch = hashes[offset : offset + 500]
                placeholders = ",".join("?" for _ in batch)
                query = (
                    f"SELECT {', '.join(selected)} FROM timeline_events "
                    f"WHERE asset_sha256 IN ({placeholders})"
                )
                for row in connection.execute(query, batch):
                    payload = dict(row)
                    date_value = payload.get("date_normalized")
                    if not in_period(
                        date_value, self.options.start_year, self.options.end_year
                    ):
                        continue
                    candidate = self.candidates.get(str(payload.get("asset_sha256"))) or {}
                    self.unanchored_timeline_signals.append(
                        {
                            "timeline_candidate_id": stable_id(
                                "timeline", "legacy", payload.get("event_id")
                            ),
                            "asset_sha256": payload.get("asset_sha256"),
                            "proposed_date": date_value,
                            "date_precision": payload.get("date_precision"),
                            "event_type": payload.get("event_type"),
                            "source": payload.get("source"),
                            "source_role": "derived_locator",
                            "authority": "locator_only",
                            "legacy_event_id": payload.get("event_id"),
                            "subject_link_reason_ids": sorted(
                                reason.get("reason_id")
                                for reason in candidate.get("discovery_reasons", [])
                                if reason.get("reason_id")
                            ),
                            "subject_mention_evidence_ids": [],
                            "visibility": "curator",
                            "human_verified": False,
                        }
                    )
        finally:
            connection.close()

    def _hydrate_candidates(self) -> None:
        for sha256, candidate in self.candidates.items():
            catalog = self.catalog_by_sha.get(sha256)
            if catalog:
                candidate["catalog"] = catalog
                path = catalog.get("path")
                if path:
                    candidate["source_files"].add(str(path))
                if candidate["media_type"] == "unknown" and catalog.get("content_type"):
                    candidate["media_type"] = catalog["content_type"]
            manifest_versions = sorted(
                self.manifests_by_sha.get(sha256, []),
                key=lambda item: (item["run_id"], item["manifest_path"]),
            )
            candidate["manifest_versions"] = manifest_versions
            for manifest in manifest_versions:
                if manifest.get("source_file"):
                    candidate["source_files"].add(str(manifest["source_file"]))
                date_value = manifest.get("date_proposal")
                if in_period(date_value, self.options.start_year, self.options.end_year):
                    reason_ids = sorted(
                        reason.get("reason_id")
                        for reason in candidate.get("discovery_reasons", [])
                        if reason.get("reason_id")
                    )
                    evidence_ids = sorted(
                        item["evidence_id"]
                        for item in self.evidence_by_key.values()
                        if item["asset_sha256"] == sha256
                    )
                    self.unanchored_timeline_signals.append(
                        {
                            "timeline_candidate_id": stable_id(
                                "timeline",
                                "manifest",
                                sha256,
                                manifest["manifest_path"],
                                date_value,
                            ),
                            "asset_sha256": sha256,
                            "proposed_date": date_value,
                            "date_precision": manifest.get("date_precision"),
                            "original_confidence": manifest.get("date_confidence"),
                            "confidence_comparability": "within_run_only",
                            "source": manifest["media_type"],
                            "source_role": "machine_proposal",
                            "authority": "unverified",
                            "manifest_path": manifest["manifest_path"],
                            "run_id": manifest["run_id"],
                            "subject_link_reason_ids": reason_ids,
                            "subject_mention_evidence_ids": evidence_ids,
                            "visibility": "curator",
                            "human_verified": False,
                        }
                    )

            sensitivity_records = [
                item["sensitivity"]
                for item in manifest_versions
                if item["media_type"] == "document"
            ]
            sensitivity_level = (
                "high"
                if any(item.get("level") == "high" for item in sensitivity_records)
                else "review"
            )
            candidate["sensitivity"] = {
                "level": sensitivity_level,
                "document_types": sorted(
                    {
                        item.get("document_type", "unknown")
                        for item in sensitivity_records
                        if item.get("document_type")
                    }
                ),
                "requires_human_review": True,
            }
            reason_kinds = {reason["kind"] for reason in candidate["discovery_reasons"]}
            has_evidence = any(
                item["asset_sha256"] == sha256 for item in self.evidence_by_key.values()
            )
            if has_evidence:
                evidence_status = "exact_extracted_text_candidate"
            elif reason_kinds & {"manifest_source_path_match", "manifest_analysis_match"}:
                evidence_status = "machine_proposal_only"
            else:
                evidence_status = "locator_only"
            candidate["evidence_status"] = evidence_status
            candidate["visibility"] = "curator"
            candidate["human_verified"] = False

    def _compile_contradictions(self) -> list[dict[str, Any]]:
        contradictions: list[dict[str, Any]] = []
        for sha256, candidate in sorted(self.candidates.items()):
            proposals: dict[str, list[str]] = defaultdict(list)
            for manifest in candidate.get("manifest_versions", []):
                date_value = manifest.get("date_proposal")
                if date_value:
                    proposals[str(date_value)].append(manifest["manifest_path"])
            if len(proposals) < 2:
                continue
            proposal_years = [set(years_in(value)) for value in proposals]
            if all(proposal_years) and set.intersection(*proposal_years):
                continue
            contradictions.append(
                {
                    "contradiction_id": stable_id(
                        "contradiction", "date", sha256, *sorted(proposals)
                    ),
                    "asset_sha256": sha256,
                    "kind": "conflicting_machine_date_proposals",
                    "alternatives": [
                        {"value": value, "manifest_paths": sorted(paths)}
                        for value, paths in sorted(proposals.items())
                    ],
                    "status": "open",
                    "visibility": "curator",
                    "human_verified": False,
                }
            )
        return contradictions

    def _compile_questions(
        self, contradictions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        questions: list[dict[str, Any]] = []

        def add(question: str, trigger: str, priority: str, hashes: list[str]) -> None:
            questions.append(
                {
                    "question_id": stable_id("question", trigger, question, *hashes),
                    "question": question,
                    "trigger": trigger,
                    "priority": priority,
                    "candidate_asset_sha256s": sorted(hashes),
                    "status": "open",
                    "visibility": "curator",
                    "human_verified": False,
                }
            )

        photos = [
            sha for sha, item in self.candidates.items() if item["media_type"] == "photo"
        ]
        if photos:
            add(
                "Which candidate photographs can be grounded as depictions of the subject, rather than merely related family images?",
                "weak_identity",
                "high",
                photos,
            )
        locator_only = [
            sha
            for sha, item in self.candidates.items()
            if item.get("evidence_status") == "locator_only"
        ]
        if locator_only:
            add(
                "Which locator-only candidates actually contain evidence about the subject?",
                "unverified_locator",
                "high",
                locator_only,
            )
        if contradictions:
            add(
                "Which conflicting date proposals are supported by the original source, and which should remain alternatives?",
                "contradiction",
                "high",
                sorted({item["asset_sha256"] for item in contradictions}),
            )
        sensitive = [
            sha
            for sha, item in self.candidates.items()
            if item.get("sensitivity", {}).get("level") == "high"
        ]
        if sensitive:
            add(
                "Which biographical observations can be represented without exposing the underlying restricted documents?",
                "privacy_review",
                "high",
                sensitive,
            )
        add(
            "Can each useful timeline signal be re-grounded in an original page, passage, or photograph region?",
            "missing_source_anchor",
            "high",
            sorted(self.candidates),
        )
        return questions

    def _capture_input_state(self) -> dict[str, Any]:
        manifest_paths = sorted(
            (self.data_root / "documents" / "runs").glob("*/manifests/*.json")
        ) + sorted((self.data_root / "photos" / "runs").glob("*/manifests/*.json"))
        extraction_paths = sorted(
            (self.data_root / "documents" / "runs").glob("*/extracted-text/*.txt")
        )
        catalog_family = [
            self.catalog_path,
            Path(f"{self.catalog_path}-wal"),
        ]
        synthesis_family = [
            self.synthesis_path,
            Path(f"{self.synthesis_path}-wal"),
        ]
        return {
            "catalog_sqlite_family_sha256": fingerprint_files(
                catalog_family, self.project_root
            ),
            "synthesis_sqlite_family_sha256": fingerprint_files(
                synthesis_family, self.project_root
            ),
            "people_registry_sha256": file_sha256(self.registry_path),
            "manifest_set_sha256": fingerprint_files(manifest_paths, self.project_root),
            "extraction_set_sha256": fingerprint_files(
                extraction_paths, self.project_root
            ),
            "manifest_count": len(manifest_paths),
            "extraction_count": len(extraction_paths),
        }

    def _snapshot(self, input_state: dict[str, Any]) -> dict[str, Any]:
        experiment_root = Path(__file__).resolve().parents[1]
        code_repo_root = Path(__file__).resolve().parents[3]
        experiment_files = [
            experiment_root / "brief.md",
            experiment_root / "manifest.json",
            experiment_root / "seed-dossier.schema.json",
            *sorted((experiment_root / "src").glob("*.py")),
        ]
        return {
            "project_git": git_snapshot(self.project_root),
            "experiment_git": git_snapshot(code_repo_root),
            "experiment_source_sha256": fingerprint_files(
                experiment_files, code_repo_root
            ),
            **input_state,
            "matched_extraction_set_sha256": fingerprint_files(
                self.matched_text_paths, self.project_root
            ),
            "document_run_count": len(self.document_run_ids),
            "photo_run_count": len(self.photo_run_ids),
            "matched_extraction_count": len(set(self.matched_text_paths)),
        }

    @staticmethod
    def _dedupe_timeline_signals(
        signals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
        for signal in signals:
            key = (
                signal.get("asset_sha256"),
                signal.get("proposed_date"),
                signal.get("date_precision"),
                signal.get("event_type"),
                signal.get("source_role"),
                signal.get("authority"),
            )
            provenance = {
                name: signal[name]
                for name in ("manifest_path", "run_id", "legacy_event_id", "source")
                if signal.get(name) is not None
            }
            existing = grouped.get(key)
            if existing is None:
                existing = {
                    name: value
                    for name, value in signal.items()
                    if name
                    not in {"manifest_path", "run_id", "legacy_event_id", "source"}
                }
                existing["timeline_candidate_id"] = stable_id("timeline", *key)
                existing["provenance_refs"] = []
                grouped[key] = existing
            if provenance and provenance not in existing["provenance_refs"]:
                existing["provenance_refs"].append(provenance)
            for list_field in (
                "subject_link_reason_ids",
                "subject_mention_evidence_ids",
            ):
                existing[list_field] = sorted(
                    set(existing.get(list_field, [])) | set(signal.get(list_field, []))
                )
        return sorted(
            grouped.values(),
            key=lambda item: (
                str(item.get("proposed_date") or ""),
                str(item.get("asset_sha256") or ""),
                item["timeline_candidate_id"],
            ),
        )

    def build(self) -> dict[str, Any]:
        input_state_before = self._capture_input_state()
        self._read_catalog()
        self._read_synthesis_candidates()
        self._scan_manifests()
        self._read_people_registry()
        self._hydrate_candidates()
        self._read_legacy_timeline()
        input_state_after = self._capture_input_state()
        if input_state_before != input_state_after:
            raise RuntimeError("derived inputs changed while the dossier was being built")

        contradictions = self._compile_contradictions()
        questions = self._compile_questions(contradictions)
        evidence_items = sorted(
            self.evidence_by_key.values(),
            key=lambda item: (
                item["asset_sha256"],
                item["locator"].get("page") or 0,
                item["locator"]["char_start"],
                item["matched_alias"].casefold(),
            ),
        )
        for evidence in evidence_items:
            evidence["extraction_refs"] = sorted(
                evidence["extraction_refs"],
                key=lambda item: (item["run_id"], item["text_file"]),
            )
        observations = [
            {
                "observation_id": stable_id(
                    "observation", "name_mention", evidence["evidence_id"]
                ),
                "evidence_id": evidence["evidence_id"],
                "kind": "name_mention",
                "value": evidence["matched_alias"],
                "matched_aliases": evidence["matched_aliases"],
                "directness": "explicit_extracted_text",
                "producer": {"type": "deterministic", "schema_version": SCHEMA_VERSION},
                "status": "proposed",
                "human_verified": False,
                "visibility": "curator",
            }
            for evidence in evidence_items
        ]

        candidates: list[dict[str, Any]] = []
        for _, candidate in sorted(self.candidates.items()):
            candidate.pop("_reason_keys", None)
            candidate["source_files"] = sorted(candidate["source_files"])
            candidate["discovery_reasons"] = sorted(
                candidate["discovery_reasons"],
                key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False),
            )
            candidates.append(candidate)
        unanchored_timeline = self._dedupe_timeline_signals(
            self.unanchored_timeline_signals
        )
        evidence_assets = {item["asset_sha256"] for item in evidence_items}
        media_counts: dict[str, int] = defaultdict(int)
        sensitivity_counts: dict[str, int] = defaultdict(int)
        evidence_status_counts: dict[str, int] = defaultdict(int)
        for candidate in candidates:
            media_counts[candidate["media_type"]] += 1
            sensitivity_counts[candidate["sensitivity"]["level"]] += 1
            evidence_status_counts[candidate["evidence_status"]] += 1

        snapshot = self._snapshot(input_state_before)
        identity_payload = {
            "subject": self.options.subject_label,
            "aliases": self.matcher.aliases,
            "start_year": self.options.start_year,
            "end_year": self.options.end_year,
            "snapshot": snapshot,
        }
        identity_hash = hashlib.sha256(
            json.dumps(identity_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:12]
        dossier_id = f"dossier-{identity_hash}"

        coverage_gaps = [
            {
                "kind": "original_source_verification",
                "status": "not_performed",
                "detail": "This discovery pass did not inspect original PDFs or photographs.",
            },
            {
                "kind": "image_region_anchors",
                "status": "absent",
                "detail": "Photo candidates require original-image review and identity corroboration.",
            },
            {
                "kind": "durable_human_testimony",
                "status": "absent",
                "detail": "Chat context was not written into the archive as historical fact.",
            },
        ]
        if not self.subject_candidates:
            coverage_gaps.append(
                {
                    "kind": "named_people_registry_match",
                    "status": "absent",
                    "detail": "No named registry entry matched the supplied aliases.",
                }
            )

        return {
            "schema_version": SCHEMA_VERSION,
            "dossier_id": dossier_id,
            "generated_at": self.options.generated_at or utc_now(),
            "read_only": True,
            "human_verified": False,
            "visibility": "curator",
            "subject_seed": {
                "label": self.options.subject_label,
                "aliases": [
                    {
                        "value": alias,
                        "source": (
                            "subject_seed"
                            if alias.casefold() == self.options.subject_label.casefold()
                            else "cli_operator"
                        ),
                        "specificity": (
                            "low"
                            if alias.isascii() and len(alias.split()) < 3
                            else "normal"
                        ),
                    }
                    for alias in self.matcher.aliases
                ],
                "period": {
                    "start_year": self.options.start_year,
                    "end_year": self.options.end_year,
                },
            },
            "snapshot": snapshot,
            "build_options": {"excerpts_included": False},
            "authority_rules": [
                "catalog_is_locator_only",
                "legacy_synthesis_is_locator_only",
                "manifest_analysis_is_machine_proposal",
                "extracted_text_requires_original_source_verification",
                "no_accepted_claims_in_seed_dossier",
            ],
            "summary": {
                "candidate_assets": len(candidates),
                "candidate_assets_by_media_type": dict(sorted(media_counts.items())),
                "evidence_items": len(evidence_items),
                "assets_with_exact_text_candidates": len(evidence_assets),
                "evidence_status_counts": dict(sorted(evidence_status_counts.items())),
                "timeline_candidates_in_period": 0,
                "unanchored_timeline_signals_in_period": len(unanchored_timeline),
                "contradictions": len(contradictions),
                "research_questions": len(questions),
                "people_registry_matches": len(self.subject_candidates),
                "sensitivity_counts": dict(sorted(sensitivity_counts.items())),
                "accepted_claims": 0,
                "originals_verified": 0,
            },
            "subject_candidates": sorted(
                self.subject_candidates,
                key=lambda item: str(item.get("person_id") or ""),
            ),
            "candidate_assets": candidates,
            "evidence_items": evidence_items,
            "observations": observations,
            "claim_candidates": [],
            "timeline_candidates": [],
            "unanchored_timeline_signals": unanchored_timeline,
            "contradictions": contradictions,
            "research_questions": questions,
            "coverage_gaps": coverage_gaps,
            "warnings": sorted(set(self.warnings)),
        }


def build_seed_dossier(project_root: Path, options: BuildOptions) -> dict[str, Any]:
    if options.start_year > options.end_year:
        raise ValueError("start_year must be less than or equal to end_year")
    if not options.subject_label.strip():
        raise ValueError("subject_label cannot be empty")
    data_root = project_root.resolve() / "data"
    if not (data_root / "catalog.db").is_file():
        raise FileNotFoundError("seed dossier requires data/catalog.db")
    manifest_exists = any(
        True
        for media in ("documents", "photos")
        for _ in (data_root / media / "runs").glob("*/manifests/*.json")
    )
    if not manifest_exists:
        raise FileNotFoundError("seed dossier requires at least one run manifest")
    dossier = DossierBuilder(project_root, options).build()
    from validation import validate_dossier

    validate_dossier(dossier)
    return dossier
