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
    from .baseline import BaselinePolicy
    from .loop_comparison_policy import BaselineRegistry
    from .loop_types import HealthSnapshotRecord


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


def determine_pair_trigger_reasons(
    primary: HealthSnapshotRecord,
    secondary: HealthSnapshotRecord,
    policy: TriggerPolicy,
    history: dict[str, object],
    manual_keys: set[tuple[str, str]],
    baseline_policy: BaselinePolicy,
    baseline_registry: BaselineRegistry | None,
    classification: str | None = None,
) -> list[TriggerDetail]:
    """Determine trigger reasons for a pair of health snapshot records.

    This is a standalone function that can be imported by helper modules
    without importing loop.py.
    """
    from .baseline import BaselineDriftCategory
    from .loop_history import HealthHistoryEntry, HealthRating

    details: list[TriggerDetail] = []
    primary_ref, _ = primary.refs()
    secondary_ref, _ = secondary.refs()
    pair_key = (primary_ref, secondary_ref)

    # Type the history dict for proper access
    typed_history: dict[str, HealthHistoryEntry] = history  # type: ignore[assignment]

    def _peer_role_summary() -> str | None:
        primary_role = baseline_registry.role_for(primary_ref) if baseline_registry else None
        if not primary_role:
            primary_role = baseline_registry.role_for(primary.target.label) if baseline_registry else None
        secondary_role = baseline_registry.role_for(secondary_ref) if baseline_registry else None
        if not secondary_role:
            secondary_role = baseline_registry.role_for(secondary.target.label) if baseline_registry else None
        if not primary_role and not secondary_role:
            return None
        summary_parts: list[str] = []
        summary_parts.append(f"{primary.target.label} ({primary_role})" if primary_role else primary.target.label)
        summary_parts.append(f"{secondary.target.label} ({secondary_role})" if secondary_role else secondary.target.label)
        return " vs ".join(summary_parts)

    role_summary = _peer_role_summary()

    def _path_label(record: HealthSnapshotRecord) -> str:
        return record.baseline_policy_path or "<default>"

    primary_path = _path_label(primary)
    secondary_path = _path_label(secondary)
    if primary_path != secondary_path:
        details.append(
            TriggerDetail(
                type="baseline_mismatch",
                reason=(f"baseline mismatch ({primary_path} vs {secondary_path})" if primary_path and secondary_path else "baseline mismatch"),
                baseline_expectation=None,
                actual_value=f"{primary_path} vs {secondary_path}",
                previous_run_value=None,
                why=("Targets rely on different baseline policies, so expected parity between them may not hold."),
                next_check="Confirm the cohorts and baseline policies align before treating drift as actionable.",
                peer_roles=role_summary,
                classification=classification,
            )
        )

    def _format_previous_control_plane(cluster_id: str) -> str:
        prev = typed_history.get(cluster_id)
        if not prev:
            return "unknown"
        return prev.control_plane_version or "unknown"

    def _format_previous_release(cluster_id: str, release_key: str) -> str:
        prev = typed_history.get(cluster_id)
        if not prev:
            return "unknown"
        return prev.watched_helm_releases.get(release_key) or "missing"

    def _format_previous_crd(cluster_id: str, crd_key: str) -> str:
        prev = typed_history.get(cluster_id)
        if not prev:
            return "unknown"
        return prev.watched_crd_families.get(crd_key) or "missing"

    if policy.manual and pair_key in manual_keys:
        details.append(
            TriggerDetail(
                type="manual",
                reason="manual comparison requested",
                baseline_expectation=None,
                actual_value="manual comparison",
                previous_run_value=None,
                why="Manual comparison requested",
                next_check=None,
                peer_roles=role_summary,
                classification=classification,
            )
        )
    if policy.control_plane_version and not baseline_policy.is_drift_allowed(BaselineDriftCategory.CONTROL_PLANE_VERSION):
        primary_version = primary.snapshot.metadata.control_plane_version or "unknown"
        secondary_version = secondary.snapshot.metadata.control_plane_version or "unknown"
        if primary_version != secondary_version:
            expectation = baseline_policy.control_plane_expectation
            expectation_desc = expectation.describe() if expectation else None
            reason = f"control plane version drift ({primary_version} vs {secondary_version})"
            previous_value = f"{primary.target.label}: {_format_previous_control_plane(primary.snapshot.metadata.cluster_id)} | {secondary.target.label}: {_format_previous_control_plane(secondary.snapshot.metadata.cluster_id)}"
            why_parts = []
            if expectation and expectation.why:
                why_parts.append(expectation.why)
            else:
                why_parts.append("Control plane divergence can affect platform stability.")
            if role_summary:
                why_parts.append(role_summary)
            details.append(
                TriggerDetail(
                    type=BaselineDriftCategory.CONTROL_PLANE_VERSION.value,
                    reason=reason,
                    baseline_expectation=expectation_desc,
                    actual_value=f"{primary_version} vs {secondary_version}",
                    previous_run_value=previous_value,
                    why=" ".join(why_parts).strip(),
                    next_check=expectation.next_check if expectation else None,
                    peer_roles=role_summary,
                    classification=classification,
                )
            )
    if policy.watched_helm_release and not baseline_policy.is_drift_allowed(BaselineDriftCategory.WATCHED_HELM_RELEASE):
        watched_releases = set(primary.target.watched_helm_releases) | set(secondary.target.watched_helm_releases)
        for release_key in sorted(watched_releases):
            primary_release = primary.snapshot.helm_releases.get(release_key)
            secondary_release = secondary.snapshot.helm_releases.get(release_key)
            if not primary_release and not secondary_release:
                continue
            primary_version = primary_release.chart_version if primary_release else "missing"
            secondary_version = secondary_release.chart_version if secondary_release else "missing"
            if primary_version == secondary_version:
                continue
            release_policy = baseline_policy.release_policy(release_key)
            expectation_desc = release_policy.describe() if release_policy else None
            next_check_value = release_policy.next_check if release_policy else None
            reason = f"watched Helm release {release_key} drift ({primary_version} vs {secondary_version})"
            previous_value = f"{primary.target.label}: {_format_previous_release(primary.snapshot.metadata.cluster_id, release_key)} | {secondary.target.label}: {_format_previous_release(secondary.snapshot.metadata.cluster_id, release_key)}"
            why_parts = []
            if release_policy:
                if release_policy.why:
                    why_parts.append(release_policy.why)
            else:
                why_parts.append(f"Watched Helm release {release_key} drift can cause workload unpredictability.")
            if role_summary:
                why_parts.append(role_summary)
            details.append(
                TriggerDetail(
                    type=BaselineDriftCategory.WATCHED_HELM_RELEASE.value,
                    reason=reason,
                    baseline_expectation=expectation_desc,
                    actual_value=f"{primary_version} vs {secondary_version}",
                    previous_run_value=previous_value,
                    why=" ".join(why_parts).strip(),
                    next_check=next_check_value,
                    peer_roles=role_summary,
                    classification=classification,
                )
            )
    if policy.watched_crd and not baseline_policy.is_drift_allowed(BaselineDriftCategory.WATCHED_CRD):
        watched_crds = set(primary.target.watched_crd_families) | set(secondary.target.watched_crd_families)
        for crd_name in sorted(watched_crds):
            primary_crd = primary.snapshot.crds.get(crd_name)
            secondary_crd = secondary.snapshot.crds.get(crd_name)
            if not primary_crd and not secondary_crd:
                continue
            primary_storage = primary_crd.storage_version if primary_crd else "missing"
            secondary_storage = secondary_crd.storage_version if secondary_crd else "missing"
            if primary_storage == secondary_storage:
                continue
            crd_policy = baseline_policy.crd_policy(crd_name)
            expectation_desc = f"CRD {crd_name} must exist" if crd_policy else None
            next_crd_check = crd_policy.next_check if crd_policy else None
            reason = f"watched CRD {crd_name} storage drift ({primary_storage} vs {secondary_storage})"
            previous_value = f"{primary.target.label}: {_format_previous_crd(primary.snapshot.metadata.cluster_id, crd_name)} | {secondary.target.label}: {_format_previous_crd(secondary.snapshot.metadata.cluster_id, crd_name)}"
            why_parts = []
            if crd_policy:
                if crd_policy.why:
                    why_parts.append(crd_policy.why)
            else:
                why_parts.append(f"CRD {crd_name} drift can impact dependent controllers.")
            if role_summary:
                why_parts.append(role_summary)
            details.append(
                TriggerDetail(
                    type=BaselineDriftCategory.WATCHED_CRD.value,
                    reason=reason,
                    baseline_expectation=expectation_desc,
                    actual_value=f"{primary_storage} vs {secondary_storage}",
                    previous_run_value=previous_value,
                    why=" ".join(why_parts).strip(),
                    next_check=next_crd_check,
                    peer_roles=role_summary,
                    classification=classification,
                )
            )
    if policy.health_regression:
        primary_prev = typed_history.get(primary.snapshot.metadata.cluster_id)
        if primary_prev and primary_prev.health_rating == HealthRating.HEALTHY and (primary.assessment and primary.assessment.rating == HealthRating.DEGRADED):
            details.append(
                TriggerDetail(
                    type="health_regression",
                    reason=f"health regression detected for {primary.target.label}",
                    baseline_expectation=None,
                    actual_value="health regression",
                    previous_run_value=None,
                    why="Health rating degraded since last healthy run.",
                    next_check=None,
                    peer_roles=role_summary,
                    classification=classification,
                )
            )
        secondary_prev = typed_history.get(secondary.snapshot.metadata.cluster_id)
        if secondary_prev and secondary_prev.health_rating == HealthRating.HEALTHY and (secondary.assessment and secondary.assessment.rating == HealthRating.DEGRADED):
            details.append(
                TriggerDetail(
                    type="health_regression",
                    reason=f"health regression detected for {secondary.target.label}",
                    baseline_expectation=None,
                    actual_value="health regression",
                    previous_run_value=None,
                    why="Health rating degraded since last healthy run.",
                    next_check=None,
                    peer_roles=role_summary,
                    classification=classification,
                )
            )
    if policy.missing_evidence:

        def _missing_delta(entry: HealthSnapshotRecord) -> None:
            prev = typed_history.get(entry.snapshot.metadata.cluster_id)
            prev_missing = set(prev.missing_evidence) if prev else set()
            current_missing = set(entry.assessment.missing_evidence) if entry.assessment else set()
            new_missing = current_missing - prev_missing
            if new_missing:
                details.append(
                    TriggerDetail(
                        type="missing_evidence",
                        reason=(f"missing evidence anomaly for {entry.target.label}: {', '.join(sorted(new_missing))}"),
                        baseline_expectation=None,
                        actual_value=", ".join(sorted(new_missing)),
                        previous_run_value=None,
                        why="Missing telemetry appeared since last run.",
                        next_check=None,
                        peer_roles=role_summary,
                        classification=classification,
                    )
                )

        _missing_delta(primary)
        _missing_delta(secondary)
    return details