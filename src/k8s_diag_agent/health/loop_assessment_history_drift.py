"""Previous-run drift assessment helpers for health assessment building.

Extracts history-drift comparison logic from build_health_assessment() into a focused module.
Preserves behavior exactly - no schema or artifact contract changes.

This module handles:
1. Control plane version drift (previous vs current)
2. Node count drift (previous vs current)
3. Pod count drift (previous vs current)
4. Watched Helm release version drift
5. Watched CRD family storage version drift

The module does not modify issues_detected - the caller owns that state.

This is distinct from baseline policy checks:
- Baseline policy asks: "Does current state violate declared policy?"
- History drift asks: "Did current state change compared to the previous run?"
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from ..models import Layer, Signal
from .loop_history import HealthHistoryEntry, _watched_crd_versions, _watched_release_versions

__all__ = [
    "HistoryDriftAssessment",
    "assess_previous_run_drift",
]


@dataclass
class HistoryDriftAssessment:
    """Result of previous-run drift assessment."""

    __slots__ = ("has_drift",)

    has_drift: bool
    """Whether any drift was detected."""


def assess_previous_run_drift(
    *,
    previous: HealthHistoryEntry | None,
    control_plane_version: str,
    snapshot_node_count: int | None,
    snapshot_pod_count: int | None,
    watched_helm_releases: tuple[str, ...],
    watched_crd_families: tuple[str, ...],
    snapshot: Any,
    signal_adder: Callable[[str, str, Layer], Signal],
    finding_recorder: Callable[[str, Layer, Sequence[str]], None],
) -> HistoryDriftAssessment:
    """Assess previous-run drift and create signals, findings, and next checks.

    This function extracts history-drift comparison logic from build_health_assessment().
    It compares current cluster state against the previous run's state, creating signals
    and findings for any detected drift.

    Args:
        previous: Previous run's health history entry, or None if no history.
        control_plane_version: Current control plane version string.
        snapshot_node_count: Current node count from cluster snapshot.
        snapshot_pod_count: Current pod count from cluster snapshot.
        watched_helm_releases: Tuple of watched Helm release names.
        watched_crd_families: Tuple of watched CRD family names.
        snapshot: Current cluster snapshot for release/CRD version extraction.
        signal_adder: Callable that adds a signal and returns it.
                     Signature: (description, severity, layer) -> Signal
        finding_recorder: Callable that records a finding.
                          Signature: (description, layer, signal_ids) -> None

    Returns:
        HistoryDriftAssessment with has_drift flag only.
        The caller owns signal/finding creation for control plane, node, and pod count drift.
    """
    has_drift = False

    # 1. Control plane version drift
    # Note: original code creates signal/finding whenever previous exists,
    # regardless of whether version actually changed
    if previous:
        previous_version = previous.control_plane_version or "unknown"
        if previous_version != control_plane_version:
            has_drift = True
        signal = signal_adder(
            f"Control plane version changed since last run ({previous_version} -> {control_plane_version}).",
            "medium",
            Layer.ROLLOUT,
        )
        finding_recorder(
            f"Control plane version changed since last run ({previous_version} -> {control_plane_version}).",
            Layer.ROLLOUT,
            [signal.id],
        )

    # 2. Node count drift - direct comparison, no None guard
    if previous and snapshot_node_count is not None and snapshot.metadata.node_count != previous.node_count:
        has_drift = True
        signal = signal_adder(
            f"Node count changed since last run ({previous.node_count} -> {snapshot.metadata.node_count}).",
            "medium",
            Layer.NODE,
        )
        finding_recorder(
            f"Node count changed since last run ({previous.node_count} -> {snapshot.metadata.node_count}).",
            Layer.NODE,
            [signal.id],
        )

    # 3. Pod count drift - direct comparison, no None guard
    if previous and snapshot.metadata.pod_count != previous.pod_count:
        has_drift = True
        prev_label = str(previous.pod_count) if previous.pod_count is not None else "unknown"
        curr_label = str(snapshot.metadata.pod_count) if snapshot.metadata.pod_count is not None else "unknown"
        signal = signal_adder(
            f"Pod count changed since last run ({prev_label} -> {curr_label}).",
            "medium",
            Layer.WORKLOAD,
        )
        finding_recorder(
            f"Pod count changed since last run ({prev_label} -> {curr_label}).",
            Layer.WORKLOAD,
            [signal.id],
        )

    # 4. Watched Helm release version drift
    watched_release_versions = _watched_release_versions(snapshot, watched_helm_releases)
    if previous:
        previous_release_versions = previous.watched_helm_releases
        for release_key in sorted(set(watched_release_versions) | set(previous_release_versions)):
            release_current_version: str | None = watched_release_versions.get(release_key)
            release_previous_version: str | None = previous_release_versions.get(release_key)
            if release_current_version == release_previous_version:
                continue
            has_drift = True
            release_prev_label: str = release_previous_version if release_previous_version is not None else "missing"
            release_curr_label: str = release_current_version if release_current_version is not None else "missing"
            signal = signal_adder(
                f"Watched Helm release {release_key} changed since last run ({release_prev_label} -> {release_curr_label}).",
                "medium",
                Layer.ROLLOUT,
            )
            finding_recorder(
                f"Watched Helm release {release_key} changed since last run ({release_prev_label} -> {release_curr_label}).",
                Layer.ROLLOUT,
                [signal.id],
            )

    # 5. Watched CRD family storage version drift
    watched_crd_versions = _watched_crd_versions(snapshot, watched_crd_families)
    if previous:
        previous_crd_versions = previous.watched_crd_families
        for crd_key in sorted(set(watched_crd_versions) | set(previous_crd_versions)):
            crd_current_version: str | None = watched_crd_versions.get(crd_key)
            crd_previous_version: str | None = previous_crd_versions.get(crd_key)
            if crd_current_version == crd_previous_version:
                continue
            has_drift = True
            crd_prev_label: str = crd_previous_version if crd_previous_version is not None else "missing"
            crd_curr_label: str = crd_current_version if crd_current_version is not None else "missing"
            signal = signal_adder(
                f"Watched CRD {crd_key} storage version changed since last run ({crd_prev_label} -> {crd_curr_label}).",
                "medium",
                Layer.ROLLOUT,
            )
            finding_recorder(
                f"Watched CRD {crd_key} storage version changed since last run ({crd_prev_label} -> {crd_curr_label}).",
                Layer.ROLLOUT,
                [signal.id],
            )

    return HistoryDriftAssessment(has_drift=has_drift)