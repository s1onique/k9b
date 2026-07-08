"""Tests for IncidentCandidate serialization.

These tests verify that IncidentCandidate objects can be correctly
serialized and deserialized for API transmission.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_candidate_serialization import (
    incident_candidate_from_dict,
    incident_candidate_to_dict,
    incident_candidates_from_dict_list,
    incident_candidates_to_dict_list,
)
from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    CandidateSignal,
    IncidentCandidate,
    ObjectKind,
    Severity,
)


class TestIncidentCandidateToDict:
    """Tests for incident_candidate_to_dict."""

    def test_basic_serialization(self) -> None:
        """Basic candidate should serialize correctly."""
        candidate = IncidentCandidate(
            candidate_id="default-test-nginx-crash-loop",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="test-nginx",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(
                CandidateSignal(
                    source="pod",
                    reason="CrashLoopBackOff",
                    message="Container crashed",
                ),
            ),
            evidence_needed=("pod_logs", "pod_describe"),
        )

        result = incident_candidate_to_dict(candidate)

        assert result["candidate_id"] == "default-test-nginx-crash-loop"
        assert result["namespace"] == "default"
        assert result["object_kind"] == "Pod"
        assert result["object_name"] == "test-nginx"
        assert result["class"] == "crash_loop"
        assert result["severity"] == "error"
        assert len(result["signals"]) == 1
        assert result["signals"][0]["source"] == "pod"
        assert result["signals"][0]["reason"] == "CrashLoopBackOff"
        assert result["signals"][0]["message"] == "Container crashed"
        assert result["evidence_needed"] == ["pod_logs", "pod_describe"]

    def test_raw_object_kind_preserved(self) -> None:
        """raw_object_kind should be preserved when set."""
        candidate = IncidentCandidate(
            candidate_id="default-replicaset-test-unknown",
            namespace="default",
            object_kind=ObjectKind.UNKNOWN,
            object_name="test-rs",
            candidate_class=CandidateClass.UNKNOWN,
            severity=Severity.WARNING,
            signals=(),
            evidence_needed=(),
            raw_object_kind="ReplicaSet",
        )

        result = incident_candidate_to_dict(candidate)

        assert result["object_kind"] == "Unknown"
        assert result["raw_object_kind"] == "ReplicaSet"

    def test_empty_signals(self) -> None:
        """Empty signals should serialize correctly."""
        candidate = IncidentCandidate(
            candidate_id="default-test-unknown",
            namespace="default",
            object_kind=ObjectKind.UNKNOWN,
            object_name="test",
            candidate_class=CandidateClass.UNKNOWN,
            severity=Severity.WARNING,
            signals=(),
            evidence_needed=(),
        )

        result = incident_candidate_to_dict(candidate)

        assert result["signals"] == []
        assert result["evidence_needed"] == []


class TestIncidentCandidateFromDict:
    """Tests for incident_candidate_from_dict."""

    def test_basic_deserialization(self) -> None:
        """Basic dict should deserialize correctly."""
        data = {
            "candidate_id": "default-test-nginx-crash-loop",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-nginx",
            "class": "crash_loop",
            "severity": "error",
            "signals": [
                {"source": "pod", "reason": "CrashLoopBackOff", "message": "Container crashed"}
            ],
            "evidence_needed": ["pod_logs", "pod_describe"],
        }

        result = incident_candidate_from_dict(data)

        assert result.candidate_id == "default-test-nginx-crash-loop"
        assert result.namespace == "default"
        assert result.object_kind == ObjectKind.POD
        assert result.object_name == "test-nginx"
        assert result.candidate_class == CandidateClass.CRASH_LOOP
        assert result.severity == Severity.ERROR
        assert len(result.signals) == 1
        assert result.signals[0].source == "pod"
        assert result.signals[0].reason == "CrashLoopBackOff"
        assert result.signals[0].message == "Container crashed"
        assert result.evidence_needed == ("pod_logs", "pod_describe")

    def test_candidate_class_key(self) -> None:
        """Both 'class' and 'candidate_class' keys should work."""
        data = {
            "candidate_id": "test",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test",
            "candidate_class": "crash_loop",
            "severity": "error",
            "signals": [],
            "evidence_needed": [],
        }

        result = incident_candidate_from_dict(data)
        assert result.candidate_class == CandidateClass.CRASH_LOOP

    def test_unknown_object_kind(self) -> None:
        """Unknown object_kind should map to ObjectKind.UNKNOWN."""
        data = {
            "candidate_id": "test",
            "namespace": "default",
            "object_kind": "ReplicaSet",
            "object_name": "test",
            "candidate_class": "unknown",
            "severity": "warning",
            "signals": [],
            "evidence_needed": [],
            "raw_object_kind": "ReplicaSet",
        }

        result = incident_candidate_from_dict(data)

        assert result.object_kind == ObjectKind.UNKNOWN
        assert result.raw_object_kind == "ReplicaSet"

    def test_unknown_candidate_class(self) -> None:
        """Unknown candidate_class should map to CandidateClass.UNKNOWN."""
        data = {
            "candidate_id": "test",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test",
            "candidate_class": "some_unknown_class",
            "severity": "warning",
            "signals": [],
            "evidence_needed": [],
        }

        result = incident_candidate_from_dict(data)

        assert result.candidate_class == CandidateClass.UNKNOWN

    def test_warning_severity(self) -> None:
        """Warning severity should parse correctly."""
        data = {
            "candidate_id": "test",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test",
            "candidate_class": "unknown",
            "severity": "warning",
            "signals": [],
            "evidence_needed": [],
        }

        result = incident_candidate_from_dict(data)

        assert result.severity == Severity.WARNING

    def test_error_severity(self) -> None:
        """Error severity should parse correctly."""
        data = {
            "candidate_id": "test",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test",
            "candidate_class": "unknown",
            "severity": "error",
            "signals": [],
            "evidence_needed": [],
        }

        result = incident_candidate_from_dict(data)

        assert result.severity == Severity.ERROR

    def test_missing_candidate_id_raises(self) -> None:
        """Missing candidate_id should raise ValueError."""
        data = {
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test",
            "candidate_class": "unknown",
            "severity": "warning",
            "signals": [],
            "evidence_needed": [],
        }

        with pytest.raises(ValueError, match="candidate_id"):
            incident_candidate_from_dict(data)

    def test_missing_namespace_raises(self) -> None:
        """Missing namespace should raise ValueError."""
        data = {
            "candidate_id": "test",
            "object_kind": "Pod",
            "object_name": "test",
            "candidate_class": "unknown",
            "severity": "warning",
            "signals": [],
            "evidence_needed": [],
        }

        with pytest.raises(ValueError, match="namespace"):
            incident_candidate_from_dict(data)

    def test_missing_object_name_raises(self) -> None:
        """Missing object_name should raise ValueError."""
        data = {
            "candidate_id": "test",
            "namespace": "default",
            "object_kind": "Pod",
            "candidate_class": "unknown",
            "severity": "warning",
            "signals": [],
            "evidence_needed": [],
        }

        with pytest.raises(ValueError, match="object_name"):
            incident_candidate_from_dict(data)


class TestIncidentCandidatesListSerialization:
    """Tests for list serialization functions."""

    def test_to_dict_list(self) -> None:
        """List of candidates should serialize correctly."""
        candidates = [
            IncidentCandidate(
                candidate_id="test1",
                namespace="default",
                object_kind=ObjectKind.POD,
                object_name="test1",
                candidate_class=CandidateClass.CRASH_LOOP,
                severity=Severity.ERROR,
                signals=(),
                evidence_needed=(),
            ),
            IncidentCandidate(
                candidate_id="test2",
                namespace="default",
                object_kind=ObjectKind.DEPLOYMENT,
                object_name="test2",
                candidate_class=CandidateClass.DEPLOYMENT_UNAVAILABLE,
                severity=Severity.WARNING,
                signals=(),
                evidence_needed=(),
            ),
        ]

        result = incident_candidates_to_dict_list(candidates)

        assert len(result) == 2
        assert result[0]["candidate_id"] == "test1"
        assert result[1]["candidate_id"] == "test2"

    def test_from_dict_list(self) -> None:
        """List of dicts should deserialize correctly."""
        data = [
            {
                "candidate_id": "test1",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test1",
                "candidate_class": "crash_loop",
                "severity": "error",
                "signals": [],
                "evidence_needed": [],
            },
            {
                "candidate_id": "test2",
                "namespace": "default",
                "object_kind": "Deployment",
                "object_name": "test2",
                "candidate_class": "deployment_unavailable",
                "severity": "warning",
                "signals": [],
                "evidence_needed": [],
            },
        ]

        result = incident_candidates_from_dict_list(data)

        assert len(result) == 2
        assert result[0].candidate_id == "test1"
        assert result[0].object_kind == ObjectKind.POD
        assert result[1].candidate_id == "test2"
        assert result[1].object_kind == ObjectKind.DEPLOYMENT

    def test_roundtrip(self) -> None:
        """Serialization and deserialization should be lossless."""
        original = IncidentCandidate(
            candidate_id="default-test-crash-loop",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="test-nginx",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(
                CandidateSignal(
                    source="pod",
                    reason="CrashLoopBackOff",
                    message="Container crashed 5 times",
                ),
            ),
            evidence_needed=("pod_logs", "pod_describe", "events"),
            raw_object_kind=None,
        )

        # Serialize
        serialized = incident_candidate_to_dict(original)

        # Deserialize
        restored = incident_candidate_from_dict(serialized)

        # Compare
        assert restored.candidate_id == original.candidate_id
        assert restored.namespace == original.namespace
        assert restored.object_kind == original.object_kind
        assert restored.object_name == original.object_name
        assert restored.candidate_class == original.candidate_class
        assert restored.severity == original.severity
        assert len(restored.signals) == len(original.signals)
        assert restored.signals[0].source == original.signals[0].source
        assert restored.signals[0].reason == original.signals[0].reason
        assert restored.signals[0].message == original.signals[0].message
        assert restored.evidence_needed == original.evidence_needed
        assert restored.raw_object_kind == original.raw_object_kind
