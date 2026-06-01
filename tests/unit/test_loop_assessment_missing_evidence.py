"""Tests for loop_assessment_missing_evidence module."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from k8s_diag_agent.health.loop_assessment_missing_evidence import (
    MissingEvidenceAssessment,
    assess_missing_evidence,
)
from k8s_diag_agent.health.loop_history import HealthHistoryEntry
from k8s_diag_agent.models import Finding, Layer, Signal


class _FakeHealthRating:
    """Fake HealthRating for testing - not actually a HealthRating enum."""
    value: str = "healthy"


def _make_history(missing_evidence: tuple[str, ...]) -> HealthHistoryEntry:
    """Create a minimal mock history entry for testing."""
    return HealthHistoryEntry(
        cluster_id="cluster-test",
        node_count=1,
        pod_count=10,
        control_plane_version="v1.28.0",
        health_rating=_FakeHealthRating(),
        missing_evidence=missing_evidence,
        watched_helm_releases={},
        watched_crd_families={},
        node_conditions={"not_ready": 0},
        pod_counts={"non_running": 0, "pending": 0, "crash_loop_backoff": 0, "image_pull_backoff": 0},
        job_failures=0,
        warning_event_count=0,
    )


class TestMissingEvidenceAssessment:
    """Tests for MissingEvidenceAssessment dataclass."""

    def test_signal_ids_empty_by_default(self) -> None:
        """Empty assessment has empty signal_ids."""
        assessment = MissingEvidenceAssessment(
            signal_ids=[],
            signal_map={},
            new_signal_ids=[],
            new_missing_items=[],
        )
        assert assessment.signal_ids == []
        assert assessment.signal_map == {}
        assert assessment.new_signal_ids == []
        assert assessment.new_missing_items == []


class TestAssessMissingEvidence:
    """Tests for assess_missing_evidence function."""

    def _signal_id_generator(self) -> Callable[[], str]:
        """Simple signal ID generator for testing."""
        counter = [0]

        def generator() -> str:
            counter[0] += 1
            return f"sig-{counter[0]}"

        return generator

    def test_empty_missing_no_signals(self) -> None:
        """No missing evidence produces no signals."""
        signals: list[Signal] = []
        findings: list[Finding] = []
        generator = self._signal_id_generator()

        def signal_adder(description: str, severity: str, layer: Layer) -> Signal:
            signal = Signal(
                id=generator(),
                description=description,
                layer=layer,
                evidence_id="cluster-test",
                severity=severity,
            )
            signals.append(signal)
            return signal

        def finding_recorder(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
            findings.append(
                Finding(
                    id=generator(),
                    description=description,
                    supporting_signals=list(signal_ids),
                    layer=layer,
                )
            )

        result = assess_missing_evidence(
            missing=(),
            previous=None,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )

        assert len(signals) == 0
        assert len(findings) == 0
        assert result.signal_ids == []
        assert result.signal_map == {}
        assert result.new_signal_ids == []
        assert result.new_missing_items == []

    def test_single_missing_creates_signal_and_finding(self) -> None:
        """Single missing evidence item creates one signal and one finding."""
        signals: list[Signal] = []
        findings: list[Finding] = []
        generator = self._signal_id_generator()

        def signal_adder(description: str, severity: str, layer: Layer) -> Signal:
            signal = Signal(
                id=generator(),
                description=description,
                layer=layer,
                evidence_id="cluster-test",
                severity=severity,
            )
            signals.append(signal)
            return signal

        def finding_recorder(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
            findings.append(
                Finding(
                    id=generator(),
                    description=description,
                    supporting_signals=list(signal_ids),
                    layer=layer,
                )
            )

        result = assess_missing_evidence(
            missing=("nodes",),
            previous=None,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )

        assert len(signals) == 1
        assert len(findings) == 1
        assert signals[0].description == "Missing evidence: nodes."
        assert signals[0].severity == "medium"
        assert signals[0].layer == Layer.OBSERVABILITY
        assert findings[0].description == "Snapshot is missing telemetry: nodes."
        assert result.signal_ids == ["sig-1"]
        assert result.signal_map == {"nodes": "sig-1"}

    def test_multiple_missing_creates_multiple_signals(self) -> None:
        """Multiple missing evidence items create multiple signals."""
        signals: list[Signal] = []
        findings: list[Finding] = []
        generator = self._signal_id_generator()

        def signal_adder(description: str, severity: str, layer: Layer) -> Signal:
            signal = Signal(
                id=generator(),
                description=description,
                layer=layer,
                evidence_id="cluster-test",
                severity=severity,
            )
            signals.append(signal)
            return signal

        def finding_recorder(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
            findings.append(
                Finding(
                    id=generator(),
                    description=description,
                    supporting_signals=list(signal_ids),
                    layer=layer,
                )
            )

        result = assess_missing_evidence(
            missing=("nodes", "pods", "events"),
            previous=None,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )

        assert len(signals) == 3
        assert len(findings) == 1  # Single finding aggregates all missing items
        assert "nodes" in findings[0].description
        assert "pods" in findings[0].description
        assert "events" in findings[0].description
        assert len(result.signal_ids) == 3
        assert len(result.signal_map) == 3

    def test_previous_none_no_new_missing_detection(self) -> None:
        """When previous is None, no new-missing detection occurs."""
        signals: list[Signal] = []
        findings: list[Finding] = []
        generator = self._signal_id_generator()

        def signal_adder(description: str, severity: str, layer: Layer) -> Signal:
            signal = Signal(
                id=generator(),
                description=description,
                layer=layer,
                evidence_id="cluster-test",
                severity=severity,
            )
            signals.append(signal)
            return signal

        def finding_recorder(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
            findings.append(
                Finding(
                    id=generator(),
                    description=description,
                    supporting_signals=list(signal_ids),
                    layer=layer,
                )
            )

        result = assess_missing_evidence(
            missing=("nodes",),
            previous=None,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )

        # No "New missing telemetry" finding when previous is None
        new_missing_findings = [f for f in findings if "New missing" in f.description]
        assert len(new_missing_findings) == 0
        assert result.new_signal_ids == []
        assert result.new_missing_items == []

    def test_new_missing_detected_when_items_added(self) -> None:
        """New missing evidence is detected when items were not in previous."""
        signals: list[Signal] = []
        findings: list[Finding] = []
        generator = self._signal_id_generator()

        def signal_adder(description: str, severity: str, layer: Layer) -> Signal:
            signal = Signal(
                id=generator(),
                description=description,
                layer=layer,
                evidence_id="cluster-test",
                severity=severity,
            )
            signals.append(signal)
            return signal

        def finding_recorder(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
            findings.append(
                Finding(
                    id=generator(),
                    description=description,
                    supporting_signals=list(signal_ids),
                    layer=layer,
                )
            )

        previous = _make_history(missing_evidence=("nodes",))

        result = assess_missing_evidence(
            missing=("nodes", "pods"),
            previous=previous,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )

        # Should have finding for "pods" as new missing
        new_missing_findings = [f for f in findings if "New missing" in f.description]
        assert len(new_missing_findings) == 1
        assert "pods" in new_missing_findings[0].description
        assert result.new_signal_ids == ["sig-2"]  # Second signal is for "pods"
        assert result.new_missing_items == ["pods"]

    def test_previously_missing_now_present_not_flagged_as_new(self) -> None:
        """Previously missing items now present are not flagged as new missing."""
        signals: list[Signal] = []
        findings: list[Finding] = []
        generator = self._signal_id_generator()

        def signal_adder(description: str, severity: str, layer: Layer) -> Signal:
            signal = Signal(
                id=generator(),
                description=description,
                layer=layer,
                evidence_id="cluster-test",
                severity=severity,
            )
            signals.append(signal)
            return signal

        def finding_recorder(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
            findings.append(
                Finding(
                    id=generator(),
                    description=description,
                    supporting_signals=list(signal_ids),
                    layer=layer,
                )
            )

        previous = _make_history(missing_evidence=("nodes", "pods", "events"))

        result = assess_missing_evidence(
            missing=("nodes",),  # Only nodes remain missing, pods and events resolved
            previous=previous,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )

        # No "New missing telemetry" finding - previously missing items resolved
        new_missing_findings = [f for f in findings if "New missing" in f.description]
        assert len(new_missing_findings) == 0
        assert result.new_signal_ids == []
        assert result.new_missing_items == []

    def test_ordering_preserved_in_signal_ids(self) -> None:
        """Signal IDs preserve the order of missing items."""
        signals: list[Signal] = []
        generator = self._signal_id_generator()

        def signal_adder(description: str, severity: str, layer: Layer) -> Signal:
            signal = Signal(
                id=generator(),
                description=description,
                layer=layer,
                evidence_id="cluster-test",
                severity=severity,
            )
            signals.append(signal)
            return signal

        def finding_recorder(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
            pass  # No-op for this test

        result = assess_missing_evidence(
            missing=("alpha", "beta", "gamma"),
            previous=None,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )

        assert result.signal_ids == ["sig-1", "sig-2", "sig-3"]
        assert result.signal_map["alpha"] == "sig-1"
        assert result.signal_map["beta"] == "sig-2"
        assert result.signal_map["gamma"] == "sig-3"

    def test_missing_signal_map_keys_match_input(self) -> None:
        """Signal map keys exactly match the input missing items."""
        signals: list[Signal] = []
        generator = self._signal_id_generator()

        def signal_adder(description: str, severity: str, layer: Layer) -> Signal:
            signal = Signal(
                id=generator(),
                description=description,
                layer=layer,
                evidence_id="cluster-test",
                severity=severity,
            )
            signals.append(signal)
            return signal

        def finding_recorder(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
            pass  # No-op for this test

        result = assess_missing_evidence(
            missing=("nodes", "pods"),
            previous=None,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )

        assert set(result.signal_map.keys()) == {"nodes", "pods"}

    def test_no_signal_ids_no_finding_recorded(self) -> None:
        """When there are no missing items, no finding is recorded."""
        signals: list[Signal] = []
        findings: list[Finding] = []
        generator = self._signal_id_generator()

        def signal_adder(description: str, severity: str, layer: Layer) -> Signal:
            signal = Signal(
                id=generator(),
                description=description,
                layer=layer,
                evidence_id="cluster-test",
                severity=severity,
            )
            signals.append(signal)
            return signal

        def finding_recorder(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
            findings.append(
                Finding(
                    id=generator(),
                    description=description,
                    supporting_signals=list(signal_ids),
                    layer=layer,
                )
            )

        result = assess_missing_evidence(
            missing=(),
            previous=None,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )

        assert len(findings) == 0
        assert len(result.signal_ids) == 0

    def test_duplicate_missing_items_handled(self) -> None:
        """Duplicate items in missing sequence are handled correctly."""
        signals: list[Signal] = []
        generator = self._signal_id_generator()

        def signal_adder(description: str, severity: str, layer: Layer) -> Signal:
            signal = Signal(
                id=generator(),
                description=description,
                layer=layer,
                evidence_id="cluster-test",
                severity=severity,
            )
            signals.append(signal)
            return signal

        def finding_recorder(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
            pass  # No-op for this test

        # Note: duplicates would create multiple signals for the same item
        # This is consistent with original loop.py behavior
        result = assess_missing_evidence(
            missing=("nodes", "nodes"),  # Duplicate
            previous=None,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )

        # Two signals created for duplicate items (matches original behavior)
        assert len(signals) == 2
        assert len(result.signal_ids) == 2

    def test_signal_ids_empty_when_no_missing(self) -> None:
        """Result signal_ids is empty when no missing evidence."""
        signals: list[Signal] = []
        generator = self._signal_id_generator()

        def signal_adder(description: str, severity: str, layer: Layer) -> Signal:
            signal = Signal(
                id=generator(),
                description=description,
                layer=layer,
                evidence_id="cluster-test",
                severity=severity,
            )
            signals.append(signal)
            return signal

        def finding_recorder(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
            pass  # No-op for this test

        result = assess_missing_evidence(
            missing=(),
            previous=None,
            signal_adder=signal_adder,
            finding_recorder=finding_recorder,
        )

        assert result.signal_ids == []
        assert result.signal_map == {}
