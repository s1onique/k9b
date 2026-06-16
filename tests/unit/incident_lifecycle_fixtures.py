"""Test fixtures for incident lifecycle tests.

This module contains shared test helpers used by multiple test files.
"""

from __future__ import annotations

from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    CandidateSignal,
    IncidentCandidate,
    ObjectKind,
    Severity,
)
from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentSignal,
    IncidentStatus,
)


def make_candidate(
    name: str,
    namespace: str = "default",
    candidate_class: CandidateClass = CandidateClass.CRASH_LOOP,
    object_kind: ObjectKind = ObjectKind.POD,
    raw_object_kind: str | None = None,
) -> IncidentCandidate:
    """Helper to create test candidates."""
    return IncidentCandidate(
        candidate_id=f"{namespace}-{object_kind.value.lower()}-{name}-{candidate_class.value}",
        namespace=namespace,
        object_kind=object_kind,
        object_name=name,
        candidate_class=candidate_class,
        severity=Severity.ERROR,
        signals=(
            CandidateSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="Back-off restarting",
            ),
        ),
        evidence_needed=("pod_logs", "pod_describe"),
        raw_object_kind=raw_object_kind,
    )


def make_base_incident(
    incident_id: str = "test-incident",
    namespace: str = "default",
    object_name: str = "test-pod",
    status: IncidentStatus = IncidentStatus.OPEN,
) -> Incident:
    """Create a minimal incident for transition tests."""
    now = datetime.now(UTC)
    return Incident(
        incident_id=incident_id,
        source_candidate_id="test-candidate",
        namespace=namespace,
        object_kind="Pod",
        object_name=object_name,
        raw_object_kind=None,
        candidate_class="crash_loop",
        severity="error",
        status=status,
        first_observed_at=now,
        last_observed_at=now,
    )


def make_full_incident(
    incident_id: str = "test-incident",
    namespace: str = "default",
    object_name: str = "test-pod",
    status: IncidentStatus = IncidentStatus.OPEN,
    snapshot_bundle_id: str | None = None,
    review_packet_id: str | None = None,
    review_packet_available: bool = False,
) -> Incident:
    """Create an incident with all relevant fields set."""
    now = datetime.now(UTC)
    return Incident(
        incident_id=incident_id,
        source_candidate_id="test-candidate",
        namespace=namespace,
        object_kind="Pod",
        object_name=object_name,
        raw_object_kind=None,
        candidate_class="crash_loop",
        severity="error",
        status=status,
        first_observed_at=now,
        last_observed_at=now,
        signals=[
            IncidentSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="back-off",
                captured_at=now,
            ),
        ],
        evidence_needed=["pod_logs", "pod_describe"],
        snapshot_bundle_id=snapshot_bundle_id,
        review_packet_id=review_packet_id,
        review_packet_available=review_packet_available,
    )


# Standard test timestamps
TEST_TIME_1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
TEST_TIME_2 = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)


__all__ = [
    "make_candidate",
    "make_base_incident",
    "make_full_incident",
    "TEST_TIME_1",
    "TEST_TIME_2",
]
