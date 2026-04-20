"""Validators for feedback artifacts."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from ..datetime_utils import ensure_utc, parse_iso_to_utc
from ..models import ConfidenceLevel
from . import models


class ArtifactValidationError(ValueError):
    """Raised when an artifact fails structural validation."""


def _require_keys(data: dict[str, Any], required: Iterable[str]) -> None:
    missing = [key for key in required if key not in data]
    if missing:
        raise ArtifactValidationError(f"Missing keys: {', '.join(missing)}")


def _parse_datetime(value: Any) -> datetime:
    """Parse timestamp to timezone-aware UTC datetime for validation."""
    if isinstance(value, datetime):
        return ensure_utc(value)
    if isinstance(value, str):
        parsed = parse_iso_to_utc(value)
        if parsed is not None:
            return parsed
        raise ArtifactValidationError(f"Invalid timestamp: {value!r}")
    raise ArtifactValidationError("timestamp must be an ISO string or datetime")


def _parse_failure_mode(value: Any) -> models.FailureMode:
    if isinstance(value, models.FailureMode):
        return value
    if isinstance(value, str):
        try:
            return models.FailureMode(value)
        except ValueError as exc:
            raise ArtifactValidationError(f"Unknown failure_mode '{value}'") from exc
    raise ArtifactValidationError("failure_mode must be a string")


def _parse_confidence(value: Any) -> ConfidenceLevel:
    if isinstance(value, ConfidenceLevel):
        return value
    if isinstance(value, str):
        try:
            return ConfidenceLevel(value)
        except ValueError as exc:
            raise ArtifactValidationError(f"Unknown confidence level '{value}'") from exc
    raise ArtifactValidationError("confidence must be a ConfidenceLevel name")


class SnapshotPairArtifactValidator:
    required_keys = ["primary_snapshot_id", "primary_snapshot_path"]

    @classmethod
    def validate(cls, data: dict[str, Any]) -> None:
        _require_keys(data, cls.required_keys)
        if not isinstance(data.get("comparison_summary", {}), dict):
            raise ArtifactValidationError("comparison_summary must be an object")
        if not isinstance(data.get("missing_evidence", []), list):
            raise ArtifactValidationError("missing_evidence must be a list")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> models.SnapshotPairArtifact:
        cls.validate(data)
        start_time = data.get("start_time")
        end_time = data.get("end_time")
        return models.SnapshotPairArtifact(
            primary_snapshot_id=str(data["primary_snapshot_id"]),
            primary_snapshot_path=str(data["primary_snapshot_path"]),
            comparison_summary={
                str(k): int(v) for k, v in data.get("comparison_summary", {}).items()
            },
            secondary_snapshot_id=data.get("secondary_snapshot_id"),
            secondary_snapshot_path=data.get("secondary_snapshot_path"),
            status=data.get("status", "complete"),
            start_time=_parse_datetime(start_time) if start_time else None,
            end_time=_parse_datetime(end_time) if end_time else None,
            missing_evidence=[str(item) for item in data.get("missing_evidence", [])],
        )


class AssessmentArtifactValidator:
    required_keys = ["assessment_id", "schema_version", "assessment"]

    @classmethod
    def validate(cls, data: dict[str, Any]) -> None:
        _require_keys(data, cls.required_keys)
        if not isinstance(data["assessment"], dict):
            raise ArtifactValidationError("assessment must be an object")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> models.AssessmentArtifact:
        cls.validate(data)
        return models.AssessmentArtifact(
            assessment_id=str(data["assessment_id"]),
            schema_version=str(data["schema_version"]),
            assessment=data["assessment"],
            overall_confidence=data.get("overall_confidence"),
        )


class ValidationResultValidator:
    required_keys = ["name", "passed"]

    @classmethod
    def validate(cls, data: dict[str, Any]) -> None:
        _require_keys(data, cls.required_keys)
        if not isinstance(data["passed"], bool):
            raise ArtifactValidationError("passed must be a boolean")
        if "errors" in data and not isinstance(data["errors"], list):
            raise ArtifactValidationError("errors must be a list")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> models.ValidationResult:
        cls.validate(data)
        failure_mode = data.get("failure_mode")
        return models.ValidationResult(
            name=str(data["name"]),
            passed=data["passed"],
            errors=[str(item) for item in data.get("errors", [])],
            checked_at=_parse_datetime(data.get("checked_at", datetime.now(UTC))),
            failure_mode=_parse_failure_mode(failure_mode) if failure_mode else None,
        )


class ProposedImprovementValidator:
    required_keys = ["id", "description", "target"]

    @classmethod
    def validate(cls, data: dict[str, Any]) -> None:
        _require_keys(data, cls.required_keys)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> models.ProposedImprovement:
        cls.validate(data)
        confidence = data.get("confidence")
        return models.ProposedImprovement(
            id=str(data["id"]),
            description=str(data["description"]),
            target=str(data["target"]),
            owner=data.get("owner"),
            confidence=_parse_confidence(confidence) if confidence else None,
            rationale=data.get("rationale"),
            related_failure_modes=[
                _parse_failure_mode(entry) for entry in data.get("related_failure_modes", [])
            ],
        )


class RunArtifactValidator:
    required_keys = ["run_id", "timestamp", "snapshot_pair"]

    @classmethod
    def validate(cls, data: dict[str, Any]) -> None:
        _require_keys(data, cls.required_keys)
        if not isinstance(data.get("snapshot_pair"), dict):
            raise ArtifactValidationError("snapshot_pair must be an object")
        summary = data.get("comparison_summary", {})
        if not isinstance(summary, dict):
            raise ArtifactValidationError("comparison_summary must be an object")
        if "failure_modes" in data and not isinstance(data["failure_modes"], list):
            raise ArtifactValidationError("failure_modes must be a list")
        if "validation_results" in data and not isinstance(data["validation_results"], list):
            raise ArtifactValidationError("validation_results must be a list")
        if "proposed_improvements" in data and not isinstance(data["proposed_improvements"], list):
            raise ArtifactValidationError("proposed_improvements must be a list")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> models.RunArtifact:
        cls.validate(data)
        timestamp = _parse_datetime(data["timestamp"])
        snapshot_pair = SnapshotPairArtifactValidator.from_dict(data["snapshot_pair"])
        assessment_data = data.get("assessment")
        assessment = (
            AssessmentArtifactValidator.from_dict(assessment_data)
            if isinstance(assessment_data, dict)
            else None
        )
        validation_results = [
            ValidationResultValidator.from_dict(entry)
            for entry in data.get("validation_results", [])
            if isinstance(entry, dict)
        ]
        failure_modes = [
            _parse_failure_mode(entry) for entry in data.get("failure_modes", [])
        ]
        proposed_improvements = [
            ProposedImprovementValidator.from_dict(entry)
            for entry in data.get("proposed_improvements", [])
            if isinstance(entry, dict)
        ]
        return models.RunArtifact(
            run_id=str(data["run_id"]),
            timestamp=timestamp,
            context_name=data.get("context_name"),
            comparison_intent=data.get("comparison_intent"),
            comparison_notes=data.get("comparison_notes"),
            collector_version=str(data.get("collector_version", "unknown")),
            collection_status=str(data.get("collection_status", "complete")),
            comparison_summary={
                str(k): int(v) for k, v in data.get("comparison_summary", {}).items()
            },
            missing_evidence=[str(item) for item in data.get("missing_evidence", [])],
            snapshot_pair=snapshot_pair,
            assessment=assessment,
            validation_results=validation_results,
            failure_modes=failure_modes,
            proposed_improvements=proposed_improvements,
            notes=data.get("notes"),
            expected_drift_categories=tuple(str(item) for item in data.get("expected_drift_categories", [])),
            unexpected_drift_categories=tuple(str(item) for item in data.get("unexpected_drift_categories", [])),
        )
