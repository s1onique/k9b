"""Tests for assess_previous_run_drift function."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from unittest.mock import MagicMock

from k8s_diag_agent.health.loop_assessment_history_drift import assess_previous_run_drift
from k8s_diag_agent.health.loop_history import HealthHistoryEntry
from k8s_diag_agent.models import Finding, Layer, Signal


@dataclass
class SimpleMetadata:
    cluster_id: str = "test-cluster"
    node_count: int = 3
    pod_count: int | None = 10
    control_plane_version: str = "v1.28.0"


@dataclass
class SimpleSnapshot:
    metadata: SimpleMetadata

    def __init__(self, **attrs: object) -> None:
        for key, value in attrs.items():
            setattr(self, key, value)


@dataclass
class SimpleHelmRelease:
    chart_version: str | None = "1.0.0"


def make_signal_adder() -> tuple[list[Signal], Callable[..., Signal]]:
    signals: list[Signal] = []
    call_count = [0]

    def adder(description: str, severity: str, layer: Layer) -> Signal:
        call_count[0] += 1
        signal = MagicMock(spec=Signal)
        signal.id = f"sig-{call_count[0]}"
        signal.description = description
        signal.layer = layer
        signal.severity = severity
        signals.append(signal)
        return signal

    return signals, adder


def make_finding_recorder() -> tuple[list[Finding], Callable[..., None]]:
    findings: list[Finding] = []

    def recorder(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
        finding = MagicMock(spec=Finding)
        finding.id = f"finding-{len(findings) + 1}"
        finding.description = description
        finding.layer = layer
        findings.append(finding)

    return findings, recorder


class TestAssessPreviousRunDrift:
    """Test assess_previous_run_drift function."""

    def test_previous_none_produces_no_signals_findings(self) -> None:
        signals, signal_adder = make_signal_adder()
        findings, finding_recorder = make_finding_recorder()
        snapshot = SimpleSnapshot(
            metadata=SimpleMetadata(cluster_id="test-cluster", node_count=3, pod_count=10, control_plane_version="v1.28.0"),
            helm_releases={},
            crds={},
        )
        result = assess_previous_run_drift(
            previous=None,
            control_plane_version="v1.28.0",
            snapshot_node_count=3,
            snapshot_pod_count=10,
            watched_helm_releases=(),
            watched_crd_families=(),
            snapshot=snapshot,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )
        assert result.has_drift is False
        assert signals == []
        assert findings == []

    def test_unchanged_control_plane_version_creates_signal_but_no_drift(self) -> None:
        signals, signal_adder = make_signal_adder()
        _, finding_recorder = make_finding_recorder()
        previous = HealthHistoryEntry(
            cluster_id="test-cluster",
            node_count=3,
            pod_count=10,
            control_plane_version="v1.28.0",
            health_rating=None,
            missing_evidence=(),
            watched_helm_releases={},
            watched_crd_families={},
        )
        snapshot = SimpleSnapshot(
            metadata=SimpleMetadata(cluster_id="test-cluster", node_count=3, pod_count=10, control_plane_version="v1.28.0"),
            helm_releases={},
            crds={},
        )
        result = assess_previous_run_drift(
            previous=previous,
            control_plane_version="v1.28.0",
            snapshot_node_count=3,
            snapshot_pod_count=10,
            watched_helm_releases=(),
            watched_crd_families=(),
            snapshot=snapshot,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )
        assert result.has_drift is False
        assert len(signals) == 1
        assert "v1.28.0" in signals[0].description

    def test_changed_control_plane_version_produces_drift(self) -> None:
        signals, signal_adder = make_signal_adder()
        findings, finding_recorder = make_finding_recorder()
        previous = HealthHistoryEntry(
            cluster_id="test-cluster",
            node_count=3,
            pod_count=10,
            control_plane_version="v1.27.0",
            health_rating=None,
            missing_evidence=(),
            watched_helm_releases={},
            watched_crd_families={},
        )
        snapshot = SimpleSnapshot(
            metadata=SimpleMetadata(cluster_id="test-cluster", node_count=3, pod_count=10, control_plane_version="v1.28.0"),
            helm_releases={},
            crds={},
        )
        result = assess_previous_run_drift(
            previous=previous,
            control_plane_version="v1.28.0",
            snapshot_node_count=3,
            snapshot_pod_count=10,
            watched_helm_releases=(),
            watched_crd_families=(),
            snapshot=snapshot,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )
        assert result.has_drift is True
        assert len(signals) == 1
        assert signals[0].severity == "medium"
        assert signals[0].layer == Layer.ROLLOUT
        assert "v1.27.0" in signals[0].description
        assert "v1.28.0" in signals[0].description
        assert len(findings) == 1

    def test_changed_helm_release_version_produces_drift(self) -> None:
        signals, signal_adder = make_signal_adder()
        findings, finding_recorder = make_finding_recorder()
        previous = HealthHistoryEntry(
            cluster_id="test-cluster",
            node_count=3,
            pod_count=10,
            control_plane_version="v1.28.0",
            health_rating=None,
            missing_evidence=(),
            watched_helm_releases={"prometheus": "1.0.0"},
            watched_crd_families={},
        )
        helm_releases = {"prometheus": MagicMock(spec=SimpleHelmRelease)}
        helm_releases["prometheus"].chart_version = "2.0.0"
        snapshot = SimpleSnapshot(
            metadata=SimpleMetadata(cluster_id="test-cluster", node_count=3, pod_count=10, control_plane_version="v1.28.0"),
            helm_releases=helm_releases,
            crds={},
        )
        result = assess_previous_run_drift(
            previous=previous,
            control_plane_version="v1.28.0",
            snapshot_node_count=3,
            snapshot_pod_count=10,
            watched_helm_releases=("prometheus",),
            watched_crd_families=(),
            snapshot=snapshot,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )
        assert result.has_drift is True
        assert len(signals) == 2
        helm_signal = next(s for s in signals if "prometheus" in s.description)
        assert helm_signal.layer == Layer.ROLLOUT

    def test_changed_crd_family_version_produces_drift(self) -> None:
        signals, signal_adder = make_signal_adder()
        findings, finding_recorder = make_finding_recorder()
        previous = HealthHistoryEntry(
            cluster_id="test-cluster",
            node_count=3,
            pod_count=10,
            control_plane_version="v1.28.0",
            health_rating=None,
            missing_evidence=(),
            watched_helm_releases={},
            watched_crd_families={"certificates.crt-manager.io": "v1"},
        )
        crds = {"certificates.crt-manager.io": MagicMock()}
        crds["certificates.crt-manager.io"].storage_version = "v2"
        snapshot = SimpleSnapshot(
            metadata=SimpleMetadata(cluster_id="test-cluster", node_count=3, pod_count=10, control_plane_version="v1.28.0"),
            helm_releases={},
            crds=crds,
        )
        result = assess_previous_run_drift(
            previous=previous,
            control_plane_version="v1.28.0",
            snapshot_node_count=3,
            snapshot_pod_count=10,
            watched_helm_releases=(),
            watched_crd_families=("certificates.crt-manager.io",),
            snapshot=snapshot,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )
        assert result.has_drift is True
        assert len(signals) == 2
        crd_signal = next(s for s in signals if "certificates.crt-manager.io" in s.description)
        assert crd_signal.layer == Layer.ROLLOUT

    def test_node_count_drift(self) -> None:
        signals, signal_adder = make_signal_adder()
        findings, finding_recorder = make_finding_recorder()
        previous = HealthHistoryEntry(
            cluster_id="test-cluster",
            node_count=5,
            pod_count=10,
            control_plane_version="v1.28.0",
            health_rating=None,
            missing_evidence=(),
            watched_helm_releases={},
            watched_crd_families={},
        )
        snapshot = SimpleSnapshot(
            metadata=SimpleMetadata(cluster_id="test-cluster", node_count=3, pod_count=10, control_plane_version="v1.28.0"),
            helm_releases={},
            crds={},
        )
        result = assess_previous_run_drift(
            previous=previous,
            control_plane_version="v1.28.0",
            snapshot_node_count=3,
            snapshot_pod_count=10,
            watched_helm_releases=(),
            watched_crd_families=(),
            snapshot=snapshot,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )
        assert result.has_drift is True
        assert len(signals) == 2
        node_signal = next(s for s in signals if "Node count" in s.description)
        assert node_signal.layer == Layer.NODE
        assert "5" in node_signal.description
        assert "3" in node_signal.description

    def test_pod_count_drift(self) -> None:
        signals, signal_adder = make_signal_adder()
        findings, finding_recorder = make_finding_recorder()
        previous = HealthHistoryEntry(
            cluster_id="test-cluster",
            node_count=3,
            pod_count=10,
            control_plane_version="v1.28.0",
            health_rating=None,
            missing_evidence=(),
            watched_helm_releases={},
            watched_crd_families={},
        )
        snapshot = SimpleSnapshot(
            metadata=SimpleMetadata(cluster_id="test-cluster", node_count=3, pod_count=15, control_plane_version="v1.28.0"),
            helm_releases={},
            crds={},
        )
        result = assess_previous_run_drift(
            previous=previous,
            control_plane_version="v1.28.0",
            snapshot_node_count=3,
            snapshot_pod_count=15,
            watched_helm_releases=(),
            watched_crd_families=(),
            snapshot=snapshot,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )
        assert result.has_drift is True
        assert len(signals) == 2
        pod_signal = next(s for s in signals if "Pod count" in s.description)
        assert pod_signal.layer == Layer.WORKLOAD
        assert "10" in pod_signal.description
        assert "15" in pod_signal.description

    def test_multiple_drift_types_preserve_ordering(self) -> None:
        signals, signal_adder = make_signal_adder()
        findings, finding_recorder = make_finding_recorder()
        previous = HealthHistoryEntry(
            cluster_id="test-cluster",
            node_count=5,
            pod_count=20,
            control_plane_version="v1.27.0",
            health_rating=None,
            missing_evidence=(),
            watched_helm_releases={"prometheus": "1.0.0"},
            watched_crd_families={"certificates.crt-manager.io": "v1"},
        )
        helm_releases = {"prometheus": MagicMock(spec=SimpleHelmRelease)}
        helm_releases["prometheus"].chart_version = "2.0.0"
        crds = {"certificates.crt-manager.io": MagicMock()}
        crds["certificates.crt-manager.io"].storage_version = "v2"
        snapshot = SimpleSnapshot(
            metadata=SimpleMetadata(cluster_id="test-cluster", node_count=3, pod_count=10, control_plane_version="v1.28.0"),
            helm_releases=helm_releases,
            crds=crds,
        )
        result = assess_previous_run_drift(
            previous=previous,
            control_plane_version="v1.28.0",
            snapshot_node_count=3,
            snapshot_pod_count=10,
            watched_helm_releases=("prometheus",),
            watched_crd_families=("certificates.crt-manager.io",),
            snapshot=snapshot,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )
        assert result.has_drift is True
        assert len(signals) == 5
        assert len(findings) == 5
        assert "control plane version" in signals[0].description.lower()
        assert "node count" in signals[1].description.lower()
        assert "pod count" in signals[2].description.lower()
        assert "helm release prometheus" in signals[3].description.lower()
        assert "crd certificates.crt-manager.io" in signals[4].description.lower()

    def test_id_generation_deterministic(self) -> None:
        signals_first, signal_adder_first = make_signal_adder()
        _, finding_recorder_first = make_finding_recorder()
        signals_second, signal_adder_second = make_signal_adder()
        _, finding_recorder_second = make_finding_recorder()
        previous = HealthHistoryEntry(
            cluster_id="test-cluster",
            node_count=5,
            pod_count=20,
            control_plane_version="v1.27.0",
            health_rating=None,
            missing_evidence=(),
            watched_helm_releases={"prometheus": "1.0.0"},
            watched_crd_families={"certificates.crt-manager.io": "v1"},
        )
        helm_releases = {"prometheus": MagicMock(spec=SimpleHelmRelease)}
        helm_releases["prometheus"].chart_version = "2.0.0"
        crds = {"certificates.crt-manager.io": MagicMock()}
        crds["certificates.crt-manager.io"].storage_version = "v2"
        snapshot = SimpleSnapshot(
            metadata=SimpleMetadata(cluster_id="test-cluster", node_count=3, pod_count=10, control_plane_version="v1.28.0"),
            helm_releases=helm_releases,
            crds=crds,
        )
        assess_previous_run_drift(
            previous=previous,
            control_plane_version="v1.28.0",
            snapshot_node_count=3,
            snapshot_pod_count=10,
            watched_helm_releases=("prometheus",),
            watched_crd_families=("certificates.crt-manager.io",),
            snapshot=snapshot,
            signal_adder=signal_adder_first,
            finding_recorder=finding_recorder_first,
        )
        assess_previous_run_drift(
            previous=previous,
            control_plane_version="v1.28.0",
            snapshot_node_count=3,
            snapshot_pod_count=10,
            watched_helm_releases=("prometheus",),
            watched_crd_families=("certificates.crt-manager.io",),
            snapshot=snapshot,
            signal_adder=signal_adder_second,
            finding_recorder=finding_recorder_second,
        )
        assert len(signals_first) == len(signals_second) == 5
        for s1, s2 in zip(signals_first, signals_second):
            assert s1.id == s2.id
