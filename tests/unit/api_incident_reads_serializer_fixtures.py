"""Shared fixtures for incident read-model serializer tests.

This module provides test builders for incidents, candidates,
timestamps, and payload helpers used across serializer test files.
"""

from __future__ import annotations

from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_events import IncidentEvent, IncidentEventActor, IncidentEventType, make_event_id
from k8s_diag_agent.collect.incident_evidence import EvidenceLink, EvidenceRole
from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal

# =============================================================================
# Shared Test Timestamps
# =============================================================================

TEST_TIME_1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
TEST_TIME_2 = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)
TEST_TIME_3 = datetime(2024, 1, 1, 14, 0, 0, tzinfo=UTC)

# =============================================================================
# Shared Incident Builders
# =============================================================================


def make_test_signal(
    source: str = "pod",
    reason: str = "CrashLoopBackOff",
    message: str = "back-off restarting",
    captured_at: datetime | None = None,
    run_id: str = "run-123",
) -> IncidentSignal:
    """Create a test signal."""
    return IncidentSignal(
        source=source,
        reason=reason,
        message=message,
        captured_at=captured_at or TEST_TIME_1,
        run_id=run_id,
    )


def make_test_evidence_link(
    incident_id: str = "inc-123",
    artifact_id: str = "bundle-abc",
    role: EvidenceRole = EvidenceRole.SNAPSHOT,
    attached_at: datetime | None = None,
) -> EvidenceLink:
    """Create a test evidence link."""
    return EvidenceLink(
        incident_id=incident_id,
        artifact_id=artifact_id,
        role=role,
        attached_at=attached_at or TEST_TIME_1,
    )


def make_test_event(
    event_id: str | None = None,
    incident_id: str = "inc-456",
    event_type: IncidentEventType = IncidentEventType.OPENED,
    actor: IncidentEventActor = IncidentEventActor.SYSTEM,
    occurred_at: datetime | None = None,
    message: str = "Test event",
    data: dict | None = None,
) -> IncidentEvent:
    """Create a test event."""
    if event_id is None:
        event_id = make_event_id(incident_id, "test", occurred_at or TEST_TIME_1)
    return IncidentEvent(
        event_id=event_id,
        incident_id=incident_id,
        event_type=event_type,
        actor=actor,
        occurred_at=occurred_at or TEST_TIME_1,
        message=message,
        data=data or {},
    )


def make_next_check_plan_payload(
    candidates: list[dict],
    run_id: str = "run-123",
) -> dict:
    """Create a next-check plan payload dict."""
    return {
        "run_id": run_id,
        "linkage_schema_version": 1,
        "candidates": candidates,
    }
