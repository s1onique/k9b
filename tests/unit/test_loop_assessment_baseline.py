"""Tests for loop_assessment_baseline module."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from k8s_diag_agent.health.loop_assessment_baseline import assess_baseline_policy
from k8s_diag_agent.models import Finding, Layer, Signal


class TestAssessBaselinePolicy:
    """Tests for assess_baseline_policy function."""

    def test_no_baseline_policy_produces_empty_results(self) -> None:
        """Empty baseline policy should produce no reasons, checks, or references."""
        from k8s_diag_agent.health.baseline import BaselinePolicy

        snapshot = _make_snapshot("v1.28.0")
        signals: list[Signal] = []
        findings: list[Finding] = []

        result = assess_baseline_policy(
            snapshot=snapshot,
            watched_helm_releases=(),
            baseline=BaselinePolicy.empty(),
            signal_adder=_make_signal_adder(signals),
            finding_recorder=_make_finding_recorder(findings),
        )

        assert result.baseline_reasons == []
        assert result.baseline_next_checks == []
        assert result.references == []
        assert len(signals) == 0
        assert len(findings) == 0

    def test_control_plane_violation_produces_signal_and_reason(self) -> None:
        """Control plane version violation should produce signal with reason."""
        from k8s_diag_agent.health.baseline import BaselinePolicy, ControlPlaneExpectation

        snapshot = _make_snapshot("v1.29.0")

        expectation = ControlPlaneExpectation(
            min_version="v1.28.0",
            max_version="v1.28.0",
            next_check="Upgrade or downgrade control plane to v1.28.0",
            why="We run only v1.28.0",
        )
        baseline = BaselinePolicy(
            control_plane_expectation=expectation,
            release_policies={},
            required_crds={},
            ignored_drift_categories=set(),
            expected_drift_categories=set(),
            peer_roles={},
        )

        signals: list[Signal] = []
        findings: list[Finding] = []

        result = assess_baseline_policy(
            snapshot=snapshot,
            watched_helm_releases=(),
            baseline=baseline,
            signal_adder=_make_signal_adder(signals),
            finding_recorder=_make_finding_recorder(findings),
        )

        assert len(signals) == 1
        assert "v1.29.0" in signals[0].description
        assert signals[0].layer == Layer.ROLLOUT
        assert signals[0].severity == "medium"
        assert len(result.baseline_reasons) == 1
        assert "v1.28.0" in result.baseline_reasons[0]
        assert len(result.baseline_next_checks) == 1
        assert result.baseline_next_checks[0].method == "kubectl"
        assert result.baseline_next_checks[0].evidence_needed == ["control plane version"]
        assert "control plane baseline" in result.references

    def test_control_plane_allowed_version_produces_no_signal(self) -> None:
        """Control plane version within allowed range should produce no signal."""
        from k8s_diag_agent.health.baseline import BaselinePolicy, ControlPlaneExpectation

        snapshot = _make_snapshot("v1.28.0")

        expectation = ControlPlaneExpectation(
            min_version="v1.28.0",
            max_version="v1.28.0",
            next_check="Upgrade or downgrade control plane to v1.28.0",
            why="We run only v1.28.0",
        )
        baseline = BaselinePolicy(
            control_plane_expectation=expectation,
            release_policies={},
            required_crds={},
            ignored_drift_categories=set(),
            expected_drift_categories=set(),
            peer_roles={},
        )

        signals: list[Signal] = []
        findings: list[Finding] = []

        result = assess_baseline_policy(
            snapshot=snapshot,
            watched_helm_releases=(),
            baseline=baseline,
            signal_adder=_make_signal_adder(signals),
            finding_recorder=_make_finding_recorder(findings),
        )

        assert len(signals) == 0
        assert len(result.baseline_reasons) == 0

    def test_missing_control_plane_version_produces_no_baseline_signal(self) -> None:
        """Missing control plane version should not trigger baseline check."""
        from k8s_diag_agent.health.baseline import BaselinePolicy, ControlPlaneExpectation

        snapshot = _make_snapshot(None)

        expectation = ControlPlaneExpectation(
            min_version="v1.28.0",
            max_version="v1.28.0",
            next_check="Upgrade to v1.28.0",
            why="We run only v1.28.0",
        )
        baseline = BaselinePolicy(
            control_plane_expectation=expectation,
            release_policies={},
            required_crds={},
            ignored_drift_categories=set(),
            expected_drift_categories=set(),
            peer_roles={},
        )

        signals: list[Signal] = []
        findings: list[Finding] = []

        result = assess_baseline_policy(
            snapshot=snapshot,
            watched_helm_releases=(),
            baseline=baseline,
            signal_adder=_make_signal_adder(signals),
            finding_recorder=_make_finding_recorder(findings),
        )

        # No baseline violations should be generated for missing version
        assert len(result.baseline_reasons) == 0


# Helper functions for creating test fixtures

def _make_signal_adder(signals: list[Signal]) -> Callable[[str, str, Layer], Signal]:
    """Create a signal adder that appends to the signals list."""
    def adder(description: str, severity: str, layer: Layer) -> Signal:
        signal = Signal(
            id=f"sig-{len(signals) + 1}",
            description=description,
            layer=layer,
            evidence_id="test-cluster",
            severity=severity,
        )
        signals.append(signal)
        return signal
    return adder


def _make_finding_recorder(findings: list[Finding]) -> Callable[[str, Layer, list[str]], None]:
    """Create a finding recorder that appends to the findings list."""
    def recorder(description: str, layer: Layer, signal_ids: list[str]) -> None:
        finding = Finding(
            id=f"finding-{len(findings) + 1}",
            description=description,
            supporting_signals=signal_ids,
            layer=layer,
        )
        findings.append(finding)
    return recorder


def _make_snapshot(control_plane_version: str | None) -> Any:
    """Create a minimal ClusterSnapshot for testing."""
    from datetime import datetime

    from k8s_diag_agent.collect.cluster_snapshot import (
        ClusterHealthSignals,
        ClusterSnapshot,
        ClusterSnapshotMetadata,
        CollectionStatus,
    )

    metadata = ClusterSnapshotMetadata(
        cluster_id="test-cluster",
        captured_at=datetime.now(),
        control_plane_version=control_plane_version or "unknown",
        node_count=0,
    )

    return ClusterSnapshot(
        metadata=metadata,
        crds={},
        health_signals=ClusterHealthSignals.empty(),
        collection_status=CollectionStatus(missing_evidence=()),
    )
