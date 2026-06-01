"""Baseline-policy assessment helpers for health assessment building.

Extracts baseline derivation logic from build_health_assessment() into a focused module.
Preserves behavior exactly - no schema or artifact contract changes.

This module handles:
1. Control plane version baseline checks
2. Watched Helm release version baseline checks
3. Required CRD family existence baseline checks

The module does not modify issues_detected - the caller owns that state.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ..collect.cluster_snapshot import ClusterSnapshot
from ..models import Layer, NextCheck, Signal
from .baseline import BaselineDriftCategory, BaselinePolicy
from .loop_history import _watched_release_versions

__all__ = [
    "BaselineAssessmentResult",
    "assess_baseline_policy",
]


@dataclass
class BaselineAssessmentResult:
    """Result of baseline policy assessment."""

    __slots__ = ("baseline_reasons", "baseline_next_checks", "references")

    baseline_reasons: list[str]
    """List of reason strings for baseline violations."""

    baseline_next_checks: list[NextCheck]
    """List of NextCheck objects for baseline violations."""

    references: list[str]
    """List of reference strings for baseline violations."""


def assess_baseline_policy(
    *,
    snapshot: ClusterSnapshot,
    watched_helm_releases: tuple[str, ...],
    watched_crd_families: tuple[str, ...],
    baseline: BaselinePolicy,
    signal_adder: Callable[[str, str, Layer], Signal],
    finding_recorder: Callable[[str, Layer, Sequence[str]], None],
) -> BaselineAssessmentResult:
    """Assess baseline policy violations and create signals, findings, and next checks.

    This function extracts baseline policy derivation logic from build_health_assessment().
    It checks control plane version, watched Helm releases, and required CRD families against
    the baseline policy, creating signals and findings for any violations.

    Args:
        snapshot: Current cluster snapshot with metadata and resources.
        watched_helm_releases: Tuple of watched Helm release names.
        watched_crd_families: Tuple of watched CRD family names.
        baseline: Baseline policy to check against.
        signal_adder: Callable that adds a signal and returns it.
                     Signature: (description, severity, layer) -> Signal
        finding_recorder: Callable that records a finding.
                          Signature: (description, layer, signal_ids) -> None

    Returns:
        BaselineAssessmentResult with baseline reasons, next checks, and references.
    """
    baseline_reasons: list[str] = []
    baseline_next_checks: list[NextCheck] = []
    references: list[str] = []

    # Get control plane version
    control_plane_version = snapshot.metadata.control_plane_version or "unknown"
    has_control_plane_version = bool(control_plane_version.strip()) and control_plane_version.lower() != "unknown"

    # Check control plane baseline policy
    control_plane_expectation = baseline.control_plane_expectation
    if control_plane_expectation and has_control_plane_version and not baseline.is_drift_allowed(BaselineDriftCategory.CONTROL_PLANE_VERSION) and not control_plane_expectation.allows(control_plane_version):
        expectation_desc = control_plane_expectation.describe()
        signal = signal_adder(
            f"Control plane version {control_plane_version} falls outside baseline ({expectation_desc}).",
            "medium",
            Layer.ROLLOUT,
        )
        finding_recorder(
            (f"Control plane version {control_plane_version} violates the baseline expectation ({expectation_desc}). {control_plane_expectation.why}"),
            Layer.ROLLOUT,
            [signal.id],
        )
        baseline_next_checks.append(
            NextCheck(
                description=control_plane_expectation.next_check,
                owner="platform engineer",
                method="kubectl",
                evidence_needed=["control plane version"],
            )
        )
        baseline_reasons.append(control_plane_expectation.why)
        references.append("control plane baseline")

    # Get watched release versions
    watched_release_versions = _watched_release_versions(snapshot, watched_helm_releases)

    # Check watched Helm releases baseline policy
    if baseline.release_policies and not baseline.is_drift_allowed(BaselineDriftCategory.WATCHED_HELM_RELEASE):
        for release_key in sorted(watched_helm_releases):
            policy = baseline.release_policy(release_key)
            if not policy:
                continue
            current_version = watched_release_versions.get(release_key)
            if policy.allows(current_version):
                continue
            actual_label = current_version if current_version is not None else "missing"
            expectation_desc = policy.describe()
            signal = signal_adder(
                (f"Watched Helm release {release_key} ({actual_label}) violates baseline policy ({expectation_desc})."),
                "medium",
                Layer.ROLLOUT,
            )
            finding_recorder(
                (f"Watched Helm release {release_key} reported {actual_label} but baseline requires {expectation_desc}. {policy.why}"),
                Layer.ROLLOUT,
                [signal.id],
            )
            baseline_next_checks.append(
                NextCheck(
                    description=policy.next_check,
                    owner="platform engineer",
                    method="helm",
                    evidence_needed=[f"Helm release {release_key}"],
                )
            )
            baseline_reasons.append(policy.why)
            references.append(f"baseline release {release_key}")

    # Check required CRD families baseline policy
    if baseline.required_crds and not baseline.is_drift_allowed(BaselineDriftCategory.WATCHED_CRD):
        for family, crd_policy in baseline.required_crds.items():
            if snapshot.crds.get(family):
                continue
            signal = signal_adder(
                f"Required CRD family {family} is missing from the snapshot.",
                "medium",
                Layer.STORAGE,
            )
            finding_recorder(
                (f"Baseline expects CRD family {family} to exist. {crd_policy.why}"),
                Layer.STORAGE,
                [signal.id],
            )
            baseline_next_checks.append(
                NextCheck(
                    description=crd_policy.next_check,
                    owner="platform engineer",
                    method="kubectl",
                    evidence_needed=[f"CRD {family}"],
                )
            )
            baseline_reasons.append(crd_policy.why)
            references.append(f"baseline CRD {family}")

    return BaselineAssessmentResult(
        baseline_reasons=baseline_reasons,
        baseline_next_checks=baseline_next_checks,
        references=references,
    )
