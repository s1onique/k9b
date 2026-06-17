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
    EvidenceLink,
    EvidenceRole,
    Incident,
    IncidentEvent,
    IncidentEventActor,
    IncidentEventType,
    IncidentSignal,
    IncidentStatus,
    ReviewPacketState,
    ReviewPacketStatus,
    make_event_id,
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
    latest_snapshot_bundle_id: str | None = None,
    review_packet_id: str | None = None,
    review_packet_status: ReviewPacketStatus = ReviewPacketStatus.NOT_GENERATED,
) -> Incident:
    """Create an incident with all relevant fields set."""
    now = datetime.now(UTC)
    
    # Build review packet state
    if review_packet_status == ReviewPacketStatus.AVAILABLE and review_packet_id:
        review_packet = ReviewPacketState.available(id=review_packet_id, generated_at=now)
    elif review_packet_status == ReviewPacketStatus.GENERATING and review_packet_id:
        review_packet = ReviewPacketState.generating(id=review_packet_id)
    elif review_packet_status == ReviewPacketStatus.FAILED:
        review_packet = ReviewPacketState.failed()
    else:
        review_packet = ReviewPacketState.not_generated()
    
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
        latest_snapshot_bundle_id=latest_snapshot_bundle_id,
        review_packet=review_packet,
        signal_count=1,
        evidence_count=0,
    )


def make_incident_with_events(
    incident_id: str = "test-incident",
    namespace: str = "default",
    object_name: str = "test-pod",
    status: IncidentStatus = IncidentStatus.OPEN,
) -> Incident:
    """Create an incident with timeline events."""
    now = datetime.now(UTC)
    
    # Create opening event
    opened_event = IncidentEvent(
        event_id=make_event_id(incident_id, "opened", now),
        incident_id=incident_id,
        event_type=IncidentEventType.OPENED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=now,
        message="Incident opened from candidate",
    )
    
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
        signal_count=1,
        evidence_count=0,
        events=[opened_event],
    )


def make_incident_with_evidence_links(
    incident_id: str = "test-incident",
    namespace: str = "default",
    object_name: str = "test-pod",
    status: IncidentStatus = IncidentStatus.COLLECTING_EVIDENCE,
) -> Incident:
    """Create an incident with evidence links."""
    now = datetime.now(UTC)
    
    # Create evidence link
    evidence_link = EvidenceLink(
        incident_id=incident_id,
        artifact_id="bundle-abc",
        role=EvidenceRole.SNAPSHOT,
        attached_at=now,
    )
    
    # Create evidence collection event
    event = IncidentEvent(
        event_id=make_event_id(incident_id, "evidence_collection_started", now),
        incident_id=incident_id,
        event_type=IncidentEventType.EVIDENCE_COLLECTION_STARTED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=now,
        message="Evidence collection started with bundle bundle-abc",
        data={"bundle_id": "bundle-abc"},
    )
    
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
        evidence_links=[evidence_link],
        latest_snapshot_bundle_id="bundle-abc",
        signal_count=1,
        evidence_count=1,
        events=[event],
    )


# Standard test timestamps
TEST_TIME_1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
TEST_TIME_2 = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)
TEST_TIME_3 = datetime(2024, 1, 1, 14, 0, 0, tzinfo=UTC)


__all__ = [
    "make_candidate",
    "make_base_incident",
    "make_full_incident",
    "make_incident_with_events",
    "make_incident_with_evidence_links",
    "TEST_TIME_1",
    "TEST_TIME_2",
    "TEST_TIME_3",
]
