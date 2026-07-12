"""Strict runtime validation for the seed-dossier v0.1 contract."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from common import SCHEMA_VERSION


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ContractError(ValueError):
    pass


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{path} must be an array")
    return value


def _exact_keys(
    value: dict[str, Any],
    path: str,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = required - set(value)
    extra = set(value) - required - optional
    if missing:
        raise ContractError(f"{path} is missing: {', '.join(sorted(missing))}")
    if extra:
        raise ContractError(f"{path} has unexpected fields: {', '.join(sorted(extra))}")


def _sha256(value: Any, path: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise ContractError(f"{path} must be a lowercase SHA-256")


def _boolean(value: Any, path: str, expected: bool | None = None) -> None:
    if not isinstance(value, bool):
        raise ContractError(f"{path} must be boolean")
    if expected is not None and value is not expected:
        raise ContractError(f"{path} must be {expected}")


def _string_list(value: Any, path: str) -> None:
    if not all(isinstance(item, str) for item in _list(value, path)):
        raise ContractError(f"{path} must contain only strings")


def _validate_git(value: Any, path: str) -> None:
    item = _mapping(value, path)
    _exact_keys(
        item,
        path,
        required={"commit", "dirty", "status_sha256", "dirty_diff_sha256"},
    )
    if item["commit"] is not None and not isinstance(item["commit"], str):
        raise ContractError(f"{path}.commit must be string or null")
    if item["dirty"] is not None:
        _boolean(item["dirty"], f"{path}.dirty")
    _sha256(item["status_sha256"], f"{path}.status_sha256", nullable=True)
    _sha256(item["dirty_diff_sha256"], f"{path}.dirty_diff_sha256", nullable=True)


def _validate_snapshot(value: Any) -> None:
    snapshot = _mapping(value, "snapshot")
    required = {
        "project_git",
        "experiment_git",
        "experiment_source_sha256",
        "catalog_sqlite_family_sha256",
        "synthesis_sqlite_family_sha256",
        "people_registry_sha256",
        "manifest_set_sha256",
        "extraction_set_sha256",
        "matched_extraction_set_sha256",
        "document_run_count",
        "photo_run_count",
        "manifest_count",
        "extraction_count",
        "matched_extraction_count",
    }
    _exact_keys(snapshot, "snapshot", required=required)
    _validate_git(snapshot["project_git"], "snapshot.project_git")
    _validate_git(snapshot["experiment_git"], "snapshot.experiment_git")
    for field in (
        "experiment_source_sha256",
        "catalog_sqlite_family_sha256",
        "synthesis_sqlite_family_sha256",
        "manifest_set_sha256",
        "extraction_set_sha256",
        "matched_extraction_set_sha256",
    ):
        _sha256(snapshot[field], f"snapshot.{field}")
    _sha256(snapshot["people_registry_sha256"], "snapshot.people_registry_sha256", nullable=True)
    for field in (
        "document_run_count",
        "photo_run_count",
        "manifest_count",
        "extraction_count",
        "matched_extraction_count",
    ):
        if not isinstance(snapshot[field], int) or snapshot[field] < 0:
            raise ContractError(f"snapshot.{field} must be a nonnegative integer")


def _validate_reason(value: Any, path: str) -> None:
    reason = _mapping(value, path)
    _exact_keys(
        reason,
        path,
        required={"reason_id", "kind", "authority"},
        optional={
            "alias",
            "aliases",
            "entity_id",
            "field",
            "manifest_path",
            "original_confidence",
            "page",
            "source",
        },
    )
    if reason["authority"] not in {
        "locator_only",
        "machine_proposal",
        "exact_extracted_text",
    }:
        raise ContractError(f"{path}.authority is invalid")
    if not isinstance(reason["reason_id"], str) or not isinstance(reason["kind"], str):
        raise ContractError(f"{path} identifiers must be strings")
    for field in ("alias", "field", "manifest_path"):
        if field in reason and not isinstance(reason[field], str):
            raise ContractError(f"{path}.{field} must be a string")
    if "source" in reason and reason["source"] is not None and not isinstance(
        reason["source"], str
    ):
        raise ContractError(f"{path}.source must be string or null")
    if "entity_id" in reason and not isinstance(reason["entity_id"], (int, str)):
        raise ContractError(f"{path}.entity_id must be integer or string")
    if "original_confidence" in reason and reason["original_confidence"] is not None:
        if not isinstance(reason["original_confidence"], (int, float)):
            raise ContractError(f"{path}.original_confidence must be numeric or null")
    if "page" in reason and (
        not isinstance(reason["page"], int) or reason["page"] < 1
    ):
        raise ContractError(f"{path}.page must be positive")
    if "aliases" in reason:
        _string_list(reason["aliases"], f"{path}.aliases")


def _validate_manifest(value: Any, path: str) -> None:
    manifest = _mapping(value, path)
    _exact_keys(
        manifest,
        path,
        required={
            "manifest_path",
            "run_id",
            "media_type",
            "source_file",
            "date_proposal",
            "date_confidence",
            "date_precision",
            "document_type",
            "people_count",
            "sensitivity",
            "inference",
            "status",
        },
    )
    if manifest["media_type"] not in {"document", "photo"}:
        raise ContractError(f"{path}.media_type is invalid")
    if manifest["status"] != "machine_proposal":
        raise ContractError(f"{path}.status must be machine_proposal")
    for field in ("manifest_path", "run_id"):
        if not isinstance(manifest[field], str):
            raise ContractError(f"{path}.{field} must be a string")
    for field in ("source_file", "date_proposal", "date_precision", "document_type"):
        if manifest[field] is not None and not isinstance(manifest[field], str):
            raise ContractError(f"{path}.{field} must be string or null")
    if manifest["date_confidence"] is not None and not isinstance(
        manifest["date_confidence"], (int, float)
    ):
        raise ContractError(f"{path}.date_confidence must be numeric or null")
    if manifest["people_count"] is not None and not isinstance(
        manifest["people_count"], int
    ):
        raise ContractError(f"{path}.people_count must be integer or null")
    sensitivity = _mapping(manifest["sensitivity"], f"{path}.sensitivity")
    if sensitivity.get("level") not in {"high", "review"}:
        raise ContractError(f"{path}.sensitivity.level is invalid")
    inference = _mapping(manifest["inference"], f"{path}.inference")
    allowed_inference = {"method", "provider", "model", "prompt_version", "timestamp"}
    if set(inference) - allowed_inference:
        raise ContractError(f"{path}.inference has unexpected fields")
    if not all(isinstance(item, str) for item in inference.values()):
        raise ContractError(f"{path}.inference values must be strings")


def _validate_candidate(value: Any, path: str) -> None:
    candidate = _mapping(value, path)
    _exact_keys(
        candidate,
        path,
        required={
            "asset_sha256",
            "media_type",
            "source_files",
            "discovery_reasons",
            "manifest_versions",
            "sensitivity",
            "evidence_status",
            "visibility",
            "human_verified",
        },
        optional={"catalog"},
    )
    _sha256(candidate["asset_sha256"], f"{path}.asset_sha256")
    if candidate["media_type"] not in {"document", "photo", "unknown"}:
        raise ContractError(f"{path}.media_type is invalid")
    _string_list(candidate["source_files"], f"{path}.source_files")
    reasons = _list(candidate["discovery_reasons"], f"{path}.discovery_reasons")
    if not reasons:
        raise ContractError(f"{path}.discovery_reasons cannot be empty")
    for index, reason in enumerate(reasons):
        _validate_reason(reason, f"{path}.discovery_reasons[{index}]")
    for index, manifest in enumerate(
        _list(candidate["manifest_versions"], f"{path}.manifest_versions")
    ):
        _validate_manifest(manifest, f"{path}.manifest_versions[{index}]")
    sensitivity = _mapping(candidate["sensitivity"], f"{path}.sensitivity")
    _exact_keys(
        sensitivity,
        f"{path}.sensitivity",
        required={"level", "document_types", "requires_human_review"},
    )
    if sensitivity["level"] not in {"high", "review"}:
        raise ContractError(f"{path}.sensitivity.level is invalid")
    _string_list(sensitivity["document_types"], f"{path}.sensitivity.document_types")
    _boolean(
        sensitivity["requires_human_review"],
        f"{path}.sensitivity.requires_human_review",
        True,
    )
    if candidate["evidence_status"] not in {
        "exact_extracted_text_candidate",
        "machine_proposal_only",
        "locator_only",
    }:
        raise ContractError(f"{path}.evidence_status is invalid")
    if candidate["visibility"] != "curator":
        raise ContractError(f"{path}.visibility must be curator")
    _boolean(candidate["human_verified"], f"{path}.human_verified", False)
    if "catalog" in candidate:
        catalog = _mapping(candidate["catalog"], f"{path}.catalog")
        allowed = {
            "sha256",
            "path",
            "content_type",
            "manifest_path",
            "run_id",
            "status",
            "slice",
            "file_size",
            "file_mtime",
        }
        if "sha256" not in catalog or set(catalog) - allowed:
            raise ContractError(f"{path}.catalog has an invalid shape")
        _sha256(catalog["sha256"], f"{path}.catalog.sha256")
        if catalog["sha256"] != candidate["asset_sha256"]:
            raise ContractError(f"{path}.catalog SHA does not match candidate")


def _validate_evidence(value: Any, path: str) -> None:
    evidence = _mapping(value, path)
    _exact_keys(
        evidence,
        path,
        required={
            "evidence_id",
            "asset_sha256",
            "media_type",
            "source_role",
            "locator",
            "matched_alias",
            "matched_aliases",
            "extraction_refs",
            "sensitivity",
            "visibility",
            "human_verified",
        },
    )
    _sha256(evidence["asset_sha256"], f"{path}.asset_sha256")
    if evidence["media_type"] != "document":
        raise ContractError(f"{path}.media_type must be document")
    if evidence["source_role"] != "extracted_text_candidate":
        raise ContractError(f"{path}.source_role is invalid")
    _string_list(evidence["matched_aliases"], f"{path}.matched_aliases")
    if evidence["matched_alias"] not in evidence["matched_aliases"]:
        raise ContractError(f"{path}.matched_alias must occur in matched_aliases")
    locator = _mapping(evidence["locator"], f"{path}.locator")
    locator_fields = {
        "page",
        "char_start",
        "char_end",
        "coordinate_space",
        "page_body_char_start_in_artifact",
        "artifact_char_start",
        "artifact_char_end",
        "artifact_byte_start",
        "artifact_byte_end",
        "extraction_sha256",
        "raw_artifact_sha256",
    }
    _exact_keys(locator, f"{path}.locator", required=locator_fields)
    if not isinstance(locator["page"], int) or locator["page"] < 1:
        raise ContractError(f"{path}.locator.page must be positive")
    for field in locator_fields - {
        "page",
        "coordinate_space",
        "extraction_sha256",
        "raw_artifact_sha256",
    }:
        if not isinstance(locator[field], int) or locator[field] < 0:
            raise ContractError(f"{path}.locator.{field} must be nonnegative")
    if locator["char_end"] <= locator["char_start"]:
        raise ContractError(f"{path}.locator char range is invalid")
    if locator["artifact_byte_end"] <= locator["artifact_byte_start"]:
        raise ContractError(f"{path}.locator byte range is invalid")
    _sha256(locator["extraction_sha256"], f"{path}.locator.extraction_sha256")
    _sha256(locator["raw_artifact_sha256"], f"{path}.locator.raw_artifact_sha256")
    refs = _list(evidence["extraction_refs"], f"{path}.extraction_refs")
    if not refs:
        raise ContractError(f"{path}.extraction_refs cannot be empty")
    for index, ref_value in enumerate(refs):
        ref = _mapping(ref_value, f"{path}.extraction_refs[{index}]")
        _exact_keys(
            ref,
            f"{path}.extraction_refs[{index}]",
            required={"run_id", "text_file", "manifest_path"},
        )
    sensitivity = _mapping(evidence["sensitivity"], f"{path}.sensitivity")
    _exact_keys(
        sensitivity,
        f"{path}.sensitivity",
        required={"level", "reasons"},
        optional={"document_type", "flags"},
    )
    if sensitivity["level"] not in {"high", "review"}:
        raise ContractError(f"{path}.sensitivity.level is invalid")
    _string_list(sensitivity["reasons"], f"{path}.sensitivity.reasons")
    if evidence["visibility"] != "curator":
        raise ContractError(f"{path}.visibility must be curator")
    _boolean(evidence["human_verified"], f"{path}.human_verified", False)


def _validate_timeline_signal(value: Any, path: str) -> None:
    signal = _mapping(value, path)
    _exact_keys(
        signal,
        path,
        required={
            "timeline_candidate_id",
            "asset_sha256",
            "proposed_date",
            "source_role",
            "authority",
            "subject_link_reason_ids",
            "subject_mention_evidence_ids",
            "provenance_refs",
            "visibility",
            "human_verified",
        },
        optional={
            "date_precision",
            "event_type",
            "original_confidence",
            "confidence_comparability",
        },
    )
    _sha256(signal["asset_sha256"], f"{path}.asset_sha256")
    if signal["source_role"] not in {"derived_locator", "machine_proposal"}:
        raise ContractError(f"{path}.source_role is invalid")
    if signal["authority"] not in {"locator_only", "unverified"}:
        raise ContractError(f"{path}.authority is invalid")
    if not isinstance(signal["proposed_date"], str):
        raise ContractError(f"{path}.proposed_date must be a string")
    for field in ("date_precision", "event_type"):
        if field in signal and signal[field] is not None and not isinstance(
            signal[field], str
        ):
            raise ContractError(f"{path}.{field} must be string or null")
    if "original_confidence" in signal and signal["original_confidence"] is not None:
        if not isinstance(signal["original_confidence"], (int, float)):
            raise ContractError(f"{path}.original_confidence must be numeric or null")
    _string_list(signal["subject_link_reason_ids"], f"{path}.subject_link_reason_ids")
    _string_list(
        signal["subject_mention_evidence_ids"],
        f"{path}.subject_mention_evidence_ids",
    )
    for index, ref_value in enumerate(
        _list(signal["provenance_refs"], f"{path}.provenance_refs")
    ):
        ref = _mapping(ref_value, f"{path}.provenance_refs[{index}]")
        allowed = {"manifest_path", "run_id", "legacy_event_id", "source"}
        if not ref or set(ref) - allowed:
            raise ContractError(f"{path}.provenance_refs[{index}] is invalid")
    if signal["visibility"] != "curator":
        raise ContractError(f"{path}.visibility must be curator")
    _boolean(signal["human_verified"], f"{path}.human_verified", False)


def validate_dossier(payload: Any) -> None:
    dossier = _mapping(payload, "dossier")
    required = {
        "schema_version",
        "dossier_id",
        "generated_at",
        "read_only",
        "human_verified",
        "visibility",
        "subject_seed",
        "snapshot",
        "build_options",
        "authority_rules",
        "summary",
        "subject_candidates",
        "candidate_assets",
        "evidence_items",
        "observations",
        "claim_candidates",
        "timeline_candidates",
        "unanchored_timeline_signals",
        "contradictions",
        "research_questions",
        "coverage_gaps",
        "warnings",
    }
    _exact_keys(dossier, "dossier", required=required)
    if dossier["schema_version"] != SCHEMA_VERSION:
        raise ContractError("dossier.schema_version is unsupported")
    if not isinstance(dossier["dossier_id"], str) or not re.fullmatch(
        r"dossier-[0-9a-f]{12}", dossier["dossier_id"]
    ):
        raise ContractError("dossier.dossier_id is invalid")
    _boolean(dossier["read_only"], "dossier.read_only", True)
    _boolean(dossier["human_verified"], "dossier.human_verified", False)
    if dossier["visibility"] != "curator":
        raise ContractError("dossier.visibility must be curator")
    try:
        datetime.fromisoformat(str(dossier["generated_at"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError("dossier.generated_at must be an ISO datetime") from error

    subject = _mapping(dossier["subject_seed"], "subject_seed")
    _exact_keys(subject, "subject_seed", required={"label", "aliases", "period"})
    for index, alias_value in enumerate(_list(subject["aliases"], "subject_seed.aliases")):
        alias = _mapping(alias_value, f"subject_seed.aliases[{index}]")
        _exact_keys(
            alias,
            f"subject_seed.aliases[{index}]",
            required={"value", "source", "specificity"},
        )
        if alias["source"] not in {"subject_seed", "cli_operator"}:
            raise ContractError(f"subject_seed.aliases[{index}].source is invalid")
        if alias["specificity"] not in {"low", "normal"}:
            raise ContractError(f"subject_seed.aliases[{index}].specificity is invalid")
    period = _mapping(subject["period"], "subject_seed.period")
    _exact_keys(period, "subject_seed.period", required={"start_year", "end_year"})
    if period["start_year"] > period["end_year"]:
        raise ContractError("subject_seed.period is inverted")

    _validate_snapshot(dossier["snapshot"])
    build_options = _mapping(dossier["build_options"], "build_options")
    _exact_keys(build_options, "build_options", required={"excerpts_included"})
    _boolean(build_options["excerpts_included"], "build_options.excerpts_included", False)
    _string_list(dossier["authority_rules"], "authority_rules")
    if "no_accepted_claims_in_seed_dossier" not in dossier["authority_rules"]:
        raise ContractError("authority_rules must prohibit accepted claims")

    summary = _mapping(dossier["summary"], "summary")
    required_summary = {
        "candidate_assets",
        "candidate_assets_by_media_type",
        "evidence_items",
        "assets_with_exact_text_candidates",
        "evidence_status_counts",
        "timeline_candidates_in_period",
        "unanchored_timeline_signals_in_period",
        "contradictions",
        "research_questions",
        "people_registry_matches",
        "sensitivity_counts",
        "accepted_claims",
        "originals_verified",
    }
    _exact_keys(summary, "summary", required=required_summary)
    integer_fields = required_summary - {
        "candidate_assets_by_media_type",
        "evidence_status_counts",
        "sensitivity_counts",
    }
    for field in integer_fields:
        if not isinstance(summary[field], int) or summary[field] < 0:
            raise ContractError(f"summary.{field} must be a nonnegative integer")
    for field in (
        "candidate_assets_by_media_type",
        "evidence_status_counts",
        "sensitivity_counts",
    ):
        count_map = _mapping(summary[field], f"summary.{field}")
        if not all(
            isinstance(key, str) and isinstance(value, int) and value >= 0
            for key, value in count_map.items()
        ):
            raise ContractError(f"summary.{field} must map strings to counts")
    if summary["accepted_claims"] != 0 or summary["originals_verified"] != 0:
        raise ContractError("seed dossier cannot contain accepted claims or verified originals")

    for index, candidate in enumerate(_list(dossier["candidate_assets"], "candidate_assets")):
        _validate_candidate(candidate, f"candidate_assets[{index}]")
    for index, evidence in enumerate(_list(dossier["evidence_items"], "evidence_items")):
        _validate_evidence(evidence, f"evidence_items[{index}]")

    for index, subject_value in enumerate(
        _list(dossier["subject_candidates"], "subject_candidates")
    ):
        subject_candidate = _mapping(subject_value, f"subject_candidates[{index}]")
        _exact_keys(
            subject_candidate,
            f"subject_candidates[{index}]",
            required={
                "person_id",
                "name_en",
                "name_zh",
                "matched_aliases",
                "immich_person_ids",
                "source_role",
                "human_verified",
                "visibility",
            },
        )
        _string_list(
            subject_candidate["matched_aliases"],
            f"subject_candidates[{index}].matched_aliases",
        )
        _string_list(
            subject_candidate["immich_person_ids"],
            f"subject_candidates[{index}].immich_person_ids",
        )
        if subject_candidate["source_role"] != "machine_derived_locator":
            raise ContractError(f"subject_candidates[{index}].source_role is invalid")
        if subject_candidate["visibility"] != "curator":
            raise ContractError(f"subject_candidates[{index}].visibility is invalid")
        _boolean(
            subject_candidate["human_verified"],
            f"subject_candidates[{index}].human_verified",
            False,
        )
        for field in ("person_id", "name_en", "name_zh"):
            if subject_candidate[field] is not None and not isinstance(
                subject_candidate[field], str
            ):
                raise ContractError(f"subject_candidates[{index}].{field} is invalid")

    evidence_ids = {item["evidence_id"] for item in dossier["evidence_items"]}
    if len(evidence_ids) != len(dossier["evidence_items"]):
        raise ContractError("evidence IDs must be unique")
    for index, observation_value in enumerate(
        _list(dossier["observations"], "observations")
    ):
        observation = _mapping(observation_value, f"observations[{index}]")
        _exact_keys(
            observation,
            f"observations[{index}]",
            required={
                "observation_id",
                "evidence_id",
                "kind",
                "value",
                "matched_aliases",
                "directness",
                "producer",
                "status",
                "human_verified",
                "visibility",
            },
        )
        if observation["evidence_id"] not in evidence_ids:
            raise ContractError(f"observations[{index}] has unknown evidence")
        if observation["kind"] != "name_mention" or observation["status"] != "proposed":
            raise ContractError(f"observations[{index}] has invalid authority state")
        _string_list(
            observation["matched_aliases"], f"observations[{index}].matched_aliases"
        )
        if observation["directness"] != "explicit_extracted_text":
            raise ContractError(f"observations[{index}].directness is invalid")
        producer = _mapping(observation["producer"], f"observations[{index}].producer")
        _exact_keys(
            producer,
            f"observations[{index}].producer",
            required={"type", "schema_version"},
        )
        if producer != {"type": "deterministic", "schema_version": SCHEMA_VERSION}:
            raise ContractError(f"observations[{index}].producer is invalid")

    if _list(dossier["claim_candidates"], "claim_candidates"):
        raise ContractError("claim_candidates must remain empty in v0.1")
    if _list(dossier["timeline_candidates"], "timeline_candidates"):
        raise ContractError("timeline_candidates must remain empty until claims are grounded")
    for index, signal in enumerate(
        _list(dossier["unanchored_timeline_signals"], "unanchored_timeline_signals")
    ):
        _validate_timeline_signal(signal, f"unanchored_timeline_signals[{index}]")

    reason_ids = {
        reason["reason_id"]
        for candidate in dossier["candidate_assets"]
        for reason in candidate["discovery_reasons"]
    }
    for index, signal in enumerate(dossier["unanchored_timeline_signals"]):
        if not set(signal["subject_link_reason_ids"]).issubset(reason_ids):
            raise ContractError(
                f"unanchored_timeline_signals[{index}] has unknown subject link"
            )
        if not set(signal["subject_mention_evidence_ids"]).issubset(evidence_ids):
            raise ContractError(
                f"unanchored_timeline_signals[{index}] has unknown evidence"
            )

    for index, contradiction_value in enumerate(
        _list(dossier["contradictions"], "contradictions")
    ):
        contradiction = _mapping(contradiction_value, f"contradictions[{index}]")
        _exact_keys(
            contradiction,
            f"contradictions[{index}]",
            required={
                "contradiction_id",
                "asset_sha256",
                "kind",
                "alternatives",
                "status",
                "visibility",
                "human_verified",
            },
        )
        _sha256(contradiction["asset_sha256"], f"contradictions[{index}].asset_sha256")
        alternatives = _list(
            contradiction["alternatives"], f"contradictions[{index}].alternatives"
        )
        if len(alternatives) < 2:
            raise ContractError(f"contradictions[{index}] requires alternatives")
        for alternative_index, alternative_value in enumerate(alternatives):
            alternative = _mapping(
                alternative_value,
                f"contradictions[{index}].alternatives[{alternative_index}]",
            )
            _exact_keys(
                alternative,
                f"contradictions[{index}].alternatives[{alternative_index}]",
                required={"value", "manifest_paths"},
            )
            if not isinstance(alternative["value"], str):
                raise ContractError("contradiction alternative value must be a string")
            _string_list(
                alternative["manifest_paths"],
                f"contradictions[{index}].alternatives[{alternative_index}].manifest_paths",
            )

    for index, question_value in enumerate(
        _list(dossier["research_questions"], "research_questions")
    ):
        question = _mapping(question_value, f"research_questions[{index}]")
        _exact_keys(
            question,
            f"research_questions[{index}]",
            required={
                "question_id",
                "question",
                "trigger",
                "priority",
                "candidate_asset_sha256s",
                "status",
                "visibility",
                "human_verified",
            },
        )
        for asset_index, sha256 in enumerate(question["candidate_asset_sha256s"]):
            _sha256(
                sha256,
                f"research_questions[{index}].candidate_asset_sha256s[{asset_index}]",
            )
        for field in ("question_id", "question", "trigger"):
            if not isinstance(question[field], str):
                raise ContractError(f"research_questions[{index}].{field} is invalid")
        if question["priority"] not in {"high", "medium", "low"}:
            raise ContractError(f"research_questions[{index}].priority is invalid")

    for index, gap_value in enumerate(_list(dossier["coverage_gaps"], "coverage_gaps")):
        gap = _mapping(gap_value, f"coverage_gaps[{index}]")
        _exact_keys(
            gap,
            f"coverage_gaps[{index}]",
            required={"kind", "status", "detail"},
        )
    _string_list(dossier["warnings"], "warnings")

    if summary["candidate_assets"] != len(dossier["candidate_assets"]):
        raise ContractError("summary candidate count does not match payload")
    if summary["evidence_items"] != len(dossier["evidence_items"]):
        raise ContractError("summary evidence count does not match payload")
    if summary["timeline_candidates_in_period"] != 0:
        raise ContractError("summary cannot report grounded timeline candidates in v0.1")
    if summary["unanchored_timeline_signals_in_period"] != len(
        dossier["unanchored_timeline_signals"]
    ):
        raise ContractError("summary unanchored timeline count does not match payload")
