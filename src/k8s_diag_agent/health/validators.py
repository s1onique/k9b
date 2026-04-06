"""Structural validators for health artifacts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .drilldown import DrilldownArtifact


class ArtifactValidationError(ValueError):
    """Raised when a health artifact fails structural validation."""


def _require_keys(data: Mapping[str, Any], required: Iterable[str]) -> None:
    missing = [key for key in required if key not in data]
    if missing:
        raise ArtifactValidationError(f"Missing keys: {', '.join(missing)}")


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


class HealthAssessmentValidator:
    required_keys = [
        "run_label",
        "run_id",
        "timestamp",
        "context",
        "label",
        "cluster_id",
        "snapshot_path",
        "assessment",
        "health_rating",
    ]

    @classmethod
    def validate(cls, data: Mapping[str, Any]) -> None:
        if not isinstance(data, Mapping):
            raise ArtifactValidationError("Health assessment must be a mapping")
        _require_keys(data, cls.required_keys)
        if not isinstance(data["assessment"], Mapping):
            raise ArtifactValidationError("assessment must be an object")
        for text_key in ("run_label", "run_id", "context", "label", "cluster_id", "snapshot_path", "health_rating"):
            if not isinstance(data.get(text_key), str):
                raise ArtifactValidationError(f"{text_key} must be a string")
        if "missing_evidence" in data and not _is_sequence(data["missing_evidence"]):
            raise ArtifactValidationError("missing_evidence must be a list")


class DrilldownArtifactValidator:
    @classmethod
    def validate(cls, data: Mapping[str, Any]) -> None:
        if not isinstance(data, Mapping):
            raise ArtifactValidationError("Drilldown artifact must be a mapping")
        try:
            DrilldownArtifact.from_dict(data)
        except ValueError as exc:
            raise ArtifactValidationError(f"invalid drilldown artifact: {exc}") from exc


class HealthProposalValidator:
    required_keys = [
        "proposal_id",
        "source_run_id",
        "target",
        "proposed_change",
        "rationale",
        "confidence",
        "expected_benefit",
        "rollback_note",
        "promotion_payload",
        "lifecycle_history",
    ]

    @classmethod
    def validate(cls, data: Mapping[str, Any]) -> None:
        if not isinstance(data, Mapping):
            raise ArtifactValidationError("Proposal must be a mapping")
        _require_keys(data, cls.required_keys)
        if not isinstance(data["promotion_payload"], Mapping):
            raise ArtifactValidationError("promotion_payload must be a mapping")
        history = data["lifecycle_history"]
        if not _is_sequence(history):
            raise ArtifactValidationError("lifecycle_history must be a list")
        for entry in history:
            if not isinstance(entry, Mapping):
                raise ArtifactValidationError("lifecycle entries must be mappings")
            if "status" not in entry or "timestamp" not in entry:
                raise ArtifactValidationError("lifecycle entries must include status and timestamp")
        evaluation = data.get("promotion_evaluation")
        if evaluation is not None:
            if not isinstance(evaluation, Mapping):
                raise ArtifactValidationError("promotion_evaluation must be a mapping")
            for key in ("proposal_id", "noise_reduction", "signal_loss", "test_outcome"):
                if key not in evaluation:
                    raise ArtifactValidationError(f"promotion_evaluation missing {key}")


class ComparisonDecisionValidator:
    required_keys = [
        "primary_label",
        "secondary_label",
        "policy_eligible",
        "triggered",
        "comparison_intent",
        "reason",
    ]

    @classmethod
    def validate(cls, data: Mapping[str, Any]) -> None:
        if not isinstance(data, Mapping):
            raise ArtifactValidationError("Comparison decision must be a mapping")
        _require_keys(data, cls.required_keys)
        if not isinstance(data["policy_eligible"], bool):
            raise ArtifactValidationError("policy_eligible must be a boolean")
        if not isinstance(data["triggered"], bool):
            raise ArtifactValidationError("triggered must be a boolean")
        for field in ("expected_drift_categories", "ignored_drift_categories"):
            if field in data and not _is_sequence(data[field]):
                raise ArtifactValidationError(f"{field} must be a list")
