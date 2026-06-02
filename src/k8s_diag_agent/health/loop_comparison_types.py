"""Shared comparison-related type definitions for health loop modules.

This module provides comparison-related types that can be imported by
extracted helper modules without creating circular import cycles.

Types are defined here to enable clean module boundaries while maintaining
type safety. The dataclasses here can be imported by helper modules without
needing to import loop.py.

No runner logic - this is a pure types and helper functions module with no
HealthLoopRunner dependency.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class ComparisonIntent(StrEnum):
    """Intent classification for comparison pairs."""

    EXPECTED_DRIFT = "expected-drift"
    SUSPICIOUS_DRIFT = "suspicious-drift"
    IRRELEVANT_DRIFT = "irrelevant-drift"

    def label(self) -> str:
        if self == ComparisonIntent.EXPECTED_DRIFT:
            return "expected drift"
        if self == ComparisonIntent.SUSPICIOUS_DRIFT:
            return "suspicious drift"
        if self == ComparisonIntent.IRRELEVANT_DRIFT:
            return "irrelevant drift"
        return str(self)


@dataclass(frozen=True)
class ComparisonPeer:
    """Peer comparison configuration for a pair of clusters."""

    primary: str
    secondary: str
    intent: ComparisonIntent
    expected_drift_categories: tuple[str, ...] = field(default_factory=tuple)
    notes: str | None = None


@dataclass(frozen=True)
class TriggerPolicy:
    """Policy for determining which conditions trigger comparison."""

    control_plane_version: bool
    watched_helm_release: bool
    watched_crd: bool
    health_regression: bool
    missing_evidence: bool
    manual: bool
    warning_event_threshold: int = 3


@dataclass(frozen=True)
class TriggerDetail:
    """Detail about why a comparison was triggered."""

    type: str
    reason: str
    baseline_expectation: str | None
    actual_value: str
    previous_run_value: str | None
    why: str
    next_check: str | None
    peer_roles: str | None = None
    classification: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "type": self.type,
            "reason": self.reason,
            "baseline_expectation": self.baseline_expectation,
            "actual_value": self.actual_value,
            "previous_run_value": self.previous_run_value,
            "why": self.why,
            "next_check": self.next_check,
        }
        if self.peer_roles:
            data["peer_roles"] = self.peer_roles
        if self.classification:
            data["classification"] = self.classification
        return data


@dataclass(frozen=True)
class ComparisonDecision:
    """Decision record for a comparison pair."""

    primary_label: str
    secondary_label: str
    policy_eligible: bool
    triggered: bool
    comparison_intent: str
    reason: str
    primary_class: str | None
    secondary_class: str | None
    primary_role: str | None
    secondary_role: str | None
    primary_cohort: str | None
    secondary_cohort: str | None
    expected_drift_categories: tuple[str, ...]
    ignored_drift_categories: tuple[str, ...]
    notes: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_label": self.primary_label,
            "secondary_label": self.secondary_label,
            "policy_eligible": self.policy_eligible,
            "triggered": self.triggered,
            "comparison_intent": self.comparison_intent,
            "reason": self.reason,
            "primary_class": self.primary_class,
            "secondary_class": self.secondary_class,
            "primary_role": self.primary_role,
            "secondary_role": self.secondary_role,
            "primary_cohort": self.primary_cohort,
            "secondary_cohort": self.secondary_cohort,
            "expected_drift_categories": list(self.expected_drift_categories),
            "ignored_drift_categories": list(self.ignored_drift_categories),
            "notes": self.notes,
        }


@dataclass
class ComparisonTriggerArtifact:
    """Artifact for a triggered comparison between two clusters."""

    run_label: str
    run_id: str
    timestamp: datetime
    primary: str
    secondary: str
    primary_label: str
    secondary_label: str
    trigger_reasons: tuple[str, ...]
    comparison_summary: dict[str, int]
    differences: dict[str, dict[str, Any]]
    trigger_details: tuple[TriggerDetail, ...]
    comparison_intent: str
    expected_drift_categories: tuple[str, ...]
    ignored_drift_categories: tuple[str, ...]
    peer_notes: str | None = None
    notes: str | None = None
    artifact_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "run_label": self.run_label,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "primary": self.primary,
            "secondary": self.secondary,
            "primary_label": self.primary_label,
            "secondary_label": self.secondary_label,
            "trigger_reasons": list(self.trigger_reasons),
            "comparison_summary": self.comparison_summary,
            "differences": self.differences,
            "trigger_details": [detail.to_dict() for detail in self.trigger_details],
            "comparison_intent": self.comparison_intent,
            "expected_drift_categories": list(self.expected_drift_categories),
            "ignored_drift_categories": list(self.ignored_drift_categories),
            "peer_notes": self.peer_notes,
            "notes": self.notes,
        }
        if self.artifact_id is not None:
            data["artifact_id"] = self.artifact_id
        return data

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ComparisonTriggerArtifact:
        """Parse a trigger artifact from a dict, with backward compatibility for legacy artifacts."""
        from ..datetime_utils import parse_iso_to_utc

        # Parse artifact_id for backward compatibility (legacy artifacts without it)
        artifact_id_value = raw.get("artifact_id")
        parsed_artifact_id: str | None = None
        if artifact_id_value is not None and isinstance(artifact_id_value, str) and artifact_id_value:
            parsed_artifact_id = artifact_id_value

        # Parse timestamp
        timestamp_value = raw.get("timestamp")
        parsed_timestamp: datetime
        if isinstance(timestamp_value, str):
            parsed_timestamp = parse_iso_to_utc(timestamp_value) or datetime.now(UTC)
        else:
            parsed_timestamp = datetime.now(UTC)

        # Parse trigger details
        trigger_details_raw = raw.get("trigger_details") or []
        parsed_trigger_details: list[TriggerDetail] = []
        if isinstance(trigger_details_raw, list):
            for detail_raw in trigger_details_raw:
                if isinstance(detail_raw, Mapping):
                    parsed_trigger_details.append(
                        TriggerDetail(
                            type=str(detail_raw.get("type", "")),
                            reason=str(detail_raw.get("reason", "")),
                            baseline_expectation=str(detail_raw.get("baseline_expectation")) if detail_raw.get("baseline_expectation") else None,
                            actual_value=str(detail_raw.get("actual_value", "")),
                            previous_run_value=str(detail_raw.get("previous_run_value")) if detail_raw.get("previous_run_value") else None,
                            why=str(detail_raw.get("why", "")),
                            next_check=str(detail_raw.get("next_check")) if detail_raw.get("next_check") else None,
                            peer_roles=str(detail_raw.get("peer_roles")) if detail_raw.get("peer_roles") else None,
                            classification=str(detail_raw.get("classification")) if detail_raw.get("classification") else None,
                        )
                    )

        # Parse trigger_reasons
        trigger_reasons_raw = raw.get("trigger_reasons") or []
        parsed_trigger_reasons: tuple[str, ...]
        if isinstance(trigger_reasons_raw, list):
            parsed_trigger_reasons = tuple(str(item) for item in trigger_reasons_raw)
        else:
            parsed_trigger_reasons = ()

        # Parse categories
        def _parse_tuple(value: Any) -> tuple[str, ...]:
            if isinstance(value, list):
                return tuple(str(item) for item in value)
            return ()

        return cls(
            run_label=str(raw.get("run_label", "")),
            run_id=str(raw.get("run_id", "")),
            timestamp=parsed_timestamp,
            primary=str(raw.get("primary", "")),
            secondary=str(raw.get("secondary", "")),
            primary_label=str(raw.get("primary_label", "")),
            secondary_label=str(raw.get("secondary_label", "")),
            trigger_reasons=parsed_trigger_reasons,
            comparison_summary=dict(raw.get("comparison_summary") or {}),
            differences=dict(raw.get("differences") or {}),
            trigger_details=tuple(parsed_trigger_details),
            comparison_intent=str(raw.get("comparison_intent", "")),
            expected_drift_categories=_parse_tuple(raw.get("expected_drift_categories")),
            ignored_drift_categories=_parse_tuple(raw.get("ignored_drift_categories")),
            peer_notes=str(raw.get("peer_notes")) if raw.get("peer_notes") else None,
            notes=str(raw.get("notes")) if raw.get("notes") else None,
            artifact_id=parsed_artifact_id,
        )

