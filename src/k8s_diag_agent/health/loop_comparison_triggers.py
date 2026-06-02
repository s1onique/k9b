"""Trigger reason determination helpers for health loop comparisons.

This module provides the determine_pair_trigger_reasons() function
for building trigger details from comparison pairs.

No runner logic - pure function with no HealthLoopRunner dependency.
"""

from __future__ import annotations

from .baseline import BaselinePolicy
from .loop_comparison_policy import BaselineRegistry
from .loop_comparison_types import (
    TriggerDetail,
    TriggerPolicy,
)
from .loop_history import HealthHistoryEntry, HealthRating
from .loop_types import HealthSnapshotRecord


def determine_pair_trigger_reasons(
    primary: HealthSnapshotRecord,
    secondary: HealthSnapshotRecord,
    policy: TriggerPolicy,
    history: dict[str, HealthHistoryEntry],
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

    details: list[TriggerDetail] = []
    primary_ref, _ = primary.refs()
    secondary_ref, _ = secondary.refs()
    pair_key = (primary_ref, secondary_ref)

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
        prev = history.get(cluster_id)
        if not prev:
            return "unknown"
        return prev.control_plane_version or "unknown"

    def _format_previous_release(cluster_id: str, release_key: str) -> str:
        prev = history.get(cluster_id)
        if not prev:
            return "unknown"
        return prev.watched_helm_releases.get(release_key) or "missing"

    def _format_previous_crd(cluster_id: str, crd_key: str) -> str:
        prev = history.get(cluster_id)
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
        primary_prev = history.get(primary.snapshot.metadata.cluster_id)
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
        secondary_prev = history.get(secondary.snapshot.metadata.cluster_id)
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
            prev = history.get(entry.snapshot.metadata.cluster_id)
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

