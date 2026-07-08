"""Unit tests for incident lifecycle domain transitions.

This module tests the pure transition functions in the domain module.
Each test verifies:
- Valid transitions succeed with correct result
- Invalid transitions return TransitionRejected with stable reason
- Terminal states reject follow-up transitions
- Returned incident is a new value
- Input incident is unchanged
- Each applied transition emits exactly one event
- Event actor and timestamp are preserved
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from k8s_diag_agent.domain import (
    DuplicateOfIncidentId,
    IncidentId,
    IncidentLifecycle,
    ReviewPacketId,
    SnapshotBundleId,
    SourceCandidateId,
    TransitionApplied,
    TransitionRejected,
    mark_collecting_evidence,
    mark_duplicate,
    mark_investigating,
    mark_ready_for_review,
    resolve_incident,
    suppress_incident,
)

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def base_time() -> datetime:
    """Standard test timestamp."""
    return datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)


@pytest.fixture
def later_time() -> datetime:
    """Later test timestamp."""
    return datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC)


@pytest.fixture
def open_incident(base_time: datetime) -> IncidentLifecycle:
    """Create a minimal open incident for testing."""
    return IncidentLifecycle(
        incident_id=IncidentId("test-incident-1"),
        source_candidate_id=SourceCandidateId("test-candidate-1"),
        status="open",
        first_observed_at=base_time,
        last_observed_at=base_time,
        signal_count=1,
        evidence_count=0,
    )


@pytest.fixture
def collecting_incident(base_time: datetime) -> IncidentLifecycle:
    """Create an incident in collecting_evidence state."""
    return IncidentLifecycle(
        incident_id=IncidentId("test-incident-1"),
        source_candidate_id=SourceCandidateId("test-candidate-1"),
        status="collecting_evidence",
        first_observed_at=base_time,
        last_observed_at=base_time,
        signal_count=1,
        evidence_count=1,
    )


@pytest.fixture
def ready_incident(base_time: datetime) -> IncidentLifecycle:
    """Create an incident in ready_for_review state."""
    return IncidentLifecycle(
        incident_id=IncidentId("test-incident-1"),
        source_candidate_id=SourceCandidateId("test-candidate-1"),
        status="ready_for_review",
        first_observed_at=base_time,
        last_observed_at=base_time,
        signal_count=1,
        evidence_count=1,
    )


@pytest.fixture
def investigating_incident(base_time: datetime) -> IncidentLifecycle:
    """Create an incident in investigating state."""
    return IncidentLifecycle(
        incident_id=IncidentId("test-incident-1"),
        source_candidate_id=SourceCandidateId("test-candidate-1"),
        status="investigating",
        first_observed_at=base_time,
        last_observed_at=base_time,
        signal_count=1,
        evidence_count=1,
    )


@pytest.fixture
def suppressed_incident(base_time: datetime) -> IncidentLifecycle:
    """Create an incident in suppressed state."""
    return IncidentLifecycle(
        incident_id=IncidentId("test-incident-1"),
        source_candidate_id=SourceCandidateId("test-candidate-1"),
        status="suppressed",
        first_observed_at=base_time,
        last_observed_at=base_time,
        signal_count=1,
        evidence_count=0,
    )


@pytest.fixture
def duplicate_incident(base_time: datetime) -> IncidentLifecycle:
    """Create an incident in duplicate state."""
    return IncidentLifecycle(
        incident_id=IncidentId("test-incident-1"),
        source_candidate_id=SourceCandidateId("test-candidate-1"),
        status="duplicate",
        first_observed_at=base_time,
        last_observed_at=base_time,
        signal_count=1,
        evidence_count=0,
    )


@pytest.fixture
def resolved_incident(base_time: datetime) -> IncidentLifecycle:
    """Create an incident in resolved state."""
    return IncidentLifecycle(
        incident_id=IncidentId("test-incident-1"),
        source_candidate_id=SourceCandidateId("test-candidate-1"),
        status="resolved",
        first_observed_at=base_time,
        last_observed_at=base_time,
        signal_count=1,
        evidence_count=1,
    )


# -----------------------------------------------------------------------------
# Tests: mark_collecting_evidence
# -----------------------------------------------------------------------------

class TestMarkCollectingEvidence:
    """Tests for mark_collecting_evidence transition."""

    def test_valid_transition_from_open(
        self,
        open_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """open -> collecting_evidence succeeds."""
        result = mark_collecting_evidence(
            incident=open_incident,
            bundle_id=SnapshotBundleId("bundle-123"),
            actor="system",
            now=later_time,
        )

        assert isinstance(result, TransitionApplied)
        assert result.incident.status == "collecting_evidence"
        assert result.incident.last_observed_at == later_time
        assert len(result.events) == 1
        assert result.events[0].event_type == "incident_marked_collecting_evidence"
        assert result.events[0].actor == "system"

    def test_returns_new_incident(
        self,
        open_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """Applied transition returns a new incident instance."""
        original_last_observed = open_incident.last_observed_at

        result = mark_collecting_evidence(
            incident=open_incident,
            bundle_id=SnapshotBundleId("bundle-123"),
            actor="system",
            now=later_time,
        )

        assert isinstance(result, TransitionApplied)
        assert result.incident is not open_incident
        assert open_incident.last_observed_at == original_last_observed

    def test_rejects_from_collecting(
        self,
        collecting_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """collecting_evidence -> collecting_evidence is rejected."""
        result = mark_collecting_evidence(
            incident=collecting_incident,
            bundle_id=SnapshotBundleId("bundle-456"),
            actor="system",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "invalid_transition"

    def test_rejects_from_ready(
        self,
        ready_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """ready_for_review -> collecting_evidence is rejected."""
        result = mark_collecting_evidence(
            incident=ready_incident,
            bundle_id=SnapshotBundleId("bundle-456"),
            actor="system",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "invalid_transition"

    def test_rejects_from_investigating(
        self,
        investigating_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """investigating -> collecting_evidence is rejected."""
        result = mark_collecting_evidence(
            incident=investigating_incident,
            bundle_id=SnapshotBundleId("bundle-456"),
            actor="system",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "invalid_transition"

    def test_rejects_from_suppressed(
        self,
        suppressed_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """suppressed -> collecting_evidence is rejected (terminal)."""
        result = mark_collecting_evidence(
            incident=suppressed_incident,
            bundle_id=SnapshotBundleId("bundle-456"),
            actor="system",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "terminal_incident"

    def test_rejects_from_duplicate(
        self,
        duplicate_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """duplicate -> collecting_evidence is rejected (terminal)."""
        result = mark_collecting_evidence(
            incident=duplicate_incident,
            bundle_id=SnapshotBundleId("bundle-456"),
            actor="system",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "terminal_incident"

    def test_rejects_from_resolved(
        self,
        resolved_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """resolved -> collecting_evidence is rejected (terminal)."""
        result = mark_collecting_evidence(
            incident=resolved_incident,
            bundle_id=SnapshotBundleId("bundle-456"),
            actor="system",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "terminal_incident"


# -----------------------------------------------------------------------------
# Tests: mark_ready_for_review
# -----------------------------------------------------------------------------

class TestMarkReadyForReview:
    """Tests for mark_ready_for_review transition."""

    def test_valid_transition_from_collecting(
        self,
        collecting_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """collecting_evidence -> ready_for_review succeeds."""
        result = mark_ready_for_review(
            incident=collecting_incident,
            review_packet_id=ReviewPacketId("review-123"),
            actor="diagnosis_loop",
            now=later_time,
        )

        assert isinstance(result, TransitionApplied)
        assert result.incident.status == "ready_for_review"
        assert result.incident.last_observed_at == later_time
        assert len(result.events) == 1
        assert result.events[0].event_type == "incident_marked_ready_for_review"
        assert result.events[0].actor == "diagnosis_loop"

    def test_rejects_from_open(
        self,
        open_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """open -> ready_for_review is rejected."""
        result = mark_ready_for_review(
            incident=open_incident,
            review_packet_id=ReviewPacketId("review-123"),
            actor="diagnosis_loop",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "invalid_transition"

    def test_rejects_from_ready(
        self,
        ready_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """ready_for_review -> ready_for_review is rejected."""
        result = mark_ready_for_review(
            incident=ready_incident,
            review_packet_id=ReviewPacketId("review-123"),
            actor="diagnosis_loop",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "invalid_transition"

    def test_rejects_from_investigating(
        self,
        investigating_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """investigating -> ready_for_review is rejected."""
        result = mark_ready_for_review(
            incident=investigating_incident,
            review_packet_id=ReviewPacketId("review-123"),
            actor="diagnosis_loop",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "invalid_transition"

    def test_rejects_from_suppressed(
        self,
        suppressed_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """suppressed -> ready_for_review is rejected (terminal)."""
        result = mark_ready_for_review(
            incident=suppressed_incident,
            review_packet_id=ReviewPacketId("review-123"),
            actor="diagnosis_loop",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "terminal_incident"


# -----------------------------------------------------------------------------
# Tests: mark_investigating
# -----------------------------------------------------------------------------

class TestMarkInvestigating:
    """Tests for mark_investigating transition."""

    def test_valid_transition_from_ready(
        self,
        ready_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """ready_for_review -> investigating succeeds."""
        result = mark_investigating(
            incident=ready_incident,
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionApplied)
        assert result.incident.status == "investigating"
        assert result.incident.last_observed_at == later_time
        assert len(result.events) == 1
        assert result.events[0].event_type == "incident_marked_investigating"
        assert result.events[0].actor == "user"

    def test_rejects_from_open(
        self,
        open_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """open -> investigating is rejected."""
        result = mark_investigating(
            incident=open_incident,
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "invalid_transition"

    def test_rejects_from_collecting(
        self,
        collecting_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """collecting_evidence -> investigating is rejected."""
        result = mark_investigating(
            incident=collecting_incident,
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "invalid_transition"

    def test_rejects_from_investigating(
        self,
        investigating_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """investigating -> investigating is rejected."""
        result = mark_investigating(
            incident=investigating_incident,
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "invalid_transition"

    def test_rejects_from_resolved(
        self,
        resolved_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """resolved -> investigating is rejected (terminal)."""
        result = mark_investigating(
            incident=resolved_incident,
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "terminal_incident"


# -----------------------------------------------------------------------------
# Tests: resolve_incident
# -----------------------------------------------------------------------------

class TestResolveIncident:
    """Tests for resolve_incident transition."""

    def test_valid_transition_from_investigating(
        self,
        investigating_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """investigating -> resolved succeeds."""
        result = resolve_incident(
            incident=investigating_incident,
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionApplied)
        assert result.incident.status == "resolved"
        assert result.incident.last_observed_at == later_time
        assert len(result.events) == 1
        assert result.events[0].event_type == "incident_resolved"
        assert result.events[0].actor == "user"

    def test_rejects_from_open(
        self,
        open_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """open -> resolved is rejected."""
        result = resolve_incident(
            incident=open_incident,
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "invalid_transition"

    def test_rejects_from_collecting(
        self,
        collecting_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """collecting_evidence -> resolved is rejected."""
        result = resolve_incident(
            incident=collecting_incident,
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "invalid_transition"

    def test_rejects_from_ready(
        self,
        ready_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """ready_for_review -> resolved is rejected."""
        result = resolve_incident(
            incident=ready_incident,
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "invalid_transition"

    def test_rejects_from_suppressed(
        self,
        suppressed_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """suppressed -> resolved is rejected (terminal)."""
        result = resolve_incident(
            incident=suppressed_incident,
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "terminal_incident"

    def test_rejects_from_duplicate(
        self,
        duplicate_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """duplicate -> resolved is rejected (terminal)."""
        result = resolve_incident(
            incident=duplicate_incident,
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "terminal_incident"

    def test_rejects_from_resolved(
        self,
        resolved_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """resolved -> resolved is rejected (terminal)."""
        result = resolve_incident(
            incident=resolved_incident,
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "terminal_incident"


# -----------------------------------------------------------------------------
# Tests: suppress_incident
# -----------------------------------------------------------------------------

class TestSuppressIncident:
    """Tests for suppress_incident transition."""

    def test_valid_from_open(
        self,
        open_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """open -> suppressed succeeds."""
        result = suppress_incident(
            incident=open_incident,
            reason="noise",
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionApplied)
        assert result.incident.status == "suppressed"
        assert len(result.events) == 1
        assert result.events[0].event_type == "incident_suppressed"
        assert "noise" in (result.events[0].detail or "")

    def test_valid_from_collecting(
        self,
        collecting_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """collecting_evidence -> suppressed succeeds."""
        result = suppress_incident(
            incident=collecting_incident,
            reason="not_relevant",
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionApplied)
        assert result.incident.status == "suppressed"

    def test_valid_from_ready(
        self,
        ready_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """ready_for_review -> suppressed succeeds."""
        result = suppress_incident(
            incident=ready_incident,
            reason="suppressed_by_user",
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionApplied)
        assert result.incident.status == "suppressed"

    def test_valid_from_investigating(
        self,
        investigating_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """investigating -> suppressed succeeds."""
        result = suppress_incident(
            incident=investigating_incident,
            reason="no_longer_needed",
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionApplied)
        assert result.incident.status == "suppressed"

    def test_rejects_from_suppressed(
        self,
        suppressed_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """suppressed -> suppressed is rejected (terminal)."""
        result = suppress_incident(
            incident=suppressed_incident,
            reason="whatever",
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "terminal_incident"

    def test_rejects_from_duplicate(
        self,
        duplicate_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """duplicate -> suppressed is rejected (terminal)."""
        result = suppress_incident(
            incident=duplicate_incident,
            reason="whatever",
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "terminal_incident"

    def test_rejects_from_resolved(
        self,
        resolved_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """resolved -> suppressed is rejected (terminal)."""
        result = suppress_incident(
            incident=resolved_incident,
            reason="whatever",
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "terminal_incident"


# -----------------------------------------------------------------------------
# Tests: mark_duplicate
# -----------------------------------------------------------------------------

class TestMarkDuplicate:
    """Tests for mark_duplicate transition."""

    def test_valid_from_open(
        self,
        open_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """open -> duplicate succeeds."""
        result = mark_duplicate(
            incident=open_incident,
            duplicate_of=DuplicateOfIncidentId("other-incident"),
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionApplied)
        assert result.incident.status == "duplicate"
        assert len(result.events) == 1
        assert result.events[0].event_type == "incident_marked_duplicate"

    def test_valid_from_collecting(
        self,
        collecting_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """collecting_evidence -> duplicate succeeds."""
        result = mark_duplicate(
            incident=collecting_incident,
            duplicate_of=DuplicateOfIncidentId("other-incident"),
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionApplied)
        assert result.incident.status == "duplicate"

    def test_rejects_self_reference(
        self,
        open_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """Marking as duplicate of itself is rejected."""
        result = mark_duplicate(
            incident=open_incident,
            duplicate_of=DuplicateOfIncidentId("test-incident-1"),
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "duplicate_self_reference"

    def test_rejects_from_suppressed(
        self,
        suppressed_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """suppressed -> duplicate is rejected (terminal)."""
        result = mark_duplicate(
            incident=suppressed_incident,
            duplicate_of=DuplicateOfIncidentId("other-incident"),
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "terminal_incident"

    def test_rejects_from_duplicate(
        self,
        duplicate_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """duplicate -> duplicate is rejected (terminal)."""
        result = mark_duplicate(
            incident=duplicate_incident,
            duplicate_of=DuplicateOfIncidentId("other-incident"),
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "terminal_incident"

    def test_rejects_from_resolved(
        self,
        resolved_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """resolved -> duplicate is rejected (terminal)."""
        result = mark_duplicate(
            incident=resolved_incident,
            duplicate_of=DuplicateOfIncidentId("other-incident"),
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "terminal_incident"


# -----------------------------------------------------------------------------
# Tests: Input immutability
# -----------------------------------------------------------------------------

class TestInputImmutability:
    """Tests verifying that input incidents are not modified."""

    def test_mark_collecting_evidence_preserves_input(
        self,
        open_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """Input incident is not modified by mark_collecting_evidence."""
        original_status = open_incident.status
        original_last_observed = open_incident.last_observed_at

        mark_collecting_evidence(
            incident=open_incident,
            bundle_id=SnapshotBundleId("bundle-123"),
            actor="system",
            now=later_time,
        )

        assert open_incident.status == original_status
        assert open_incident.last_observed_at == original_last_observed

    def test_mark_ready_for_review_preserves_input(
        self,
        collecting_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """Input incident is not modified by mark_ready_for_review."""
        original_status = collecting_incident.status

        mark_ready_for_review(
            incident=collecting_incident,
            review_packet_id=ReviewPacketId("review-123"),
            actor="diagnosis_loop",
            now=later_time,
        )

        assert collecting_incident.status == original_status

    def test_resolve_incident_preserves_input(
        self,
        investigating_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """Input incident is not modified by resolve_incident."""
        original_status = investigating_incident.status

        resolve_incident(
            incident=investigating_incident,
            actor="user",
            now=later_time,
        )

        assert investigating_incident.status == original_status


# -----------------------------------------------------------------------------
# Tests: Event attributes
# -----------------------------------------------------------------------------

class TestEventAttributes:
    """Tests for event actor and timestamp preservation."""

    def test_actor_preserved_in_event(
        self,
        open_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """Event preserves the actor passed to transition."""
        result = mark_collecting_evidence(
            incident=open_incident,
            bundle_id=SnapshotBundleId("bundle-123"),
            actor="test",
            now=later_time,
        )

        assert isinstance(result, TransitionApplied)
        assert result.events[0].actor == "test"

    def test_timestamp_preserved_in_event(
        self,
        open_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """Event preserves the timestamp passed to transition."""
        result = mark_collecting_evidence(
            incident=open_incident,
            bundle_id=SnapshotBundleId("bundle-123"),
            actor="system",
            now=later_time,
        )

        assert isinstance(result, TransitionApplied)
        assert result.events[0].created_at == later_time

    def test_incident_id_in_event(
        self,
        open_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """Event includes the incident ID."""
        result = mark_collecting_evidence(
            incident=open_incident,
            bundle_id=SnapshotBundleId("bundle-123"),
            actor="system",
            now=later_time,
        )

        assert isinstance(result, TransitionApplied)
        assert result.events[0].incident_id == open_incident.incident_id


# -----------------------------------------------------------------------------
# Tests: Stable reason codes
# -----------------------------------------------------------------------------

class TestStableReasonCodes:
    """Tests verifying rejection reason codes are stable strings."""

    def test_terminal_incident_reason(
        self,
        suppressed_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """Terminal state rejection uses stable reason code."""
        result = mark_collecting_evidence(
            incident=suppressed_incident,
            bundle_id=SnapshotBundleId("bundle-123"),
            actor="system",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "terminal_incident"
        assert isinstance(result.reason, str)

    def test_invalid_transition_reason(
        self,
        open_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """Invalid transition uses stable reason code."""
        result = mark_ready_for_review(
            incident=open_incident,
            review_packet_id=ReviewPacketId("review-123"),
            actor="system",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "invalid_transition"
        assert isinstance(result.reason, str)

    def test_duplicate_self_reference_reason(
        self,
        open_incident: IncidentLifecycle,
        later_time: datetime,
    ) -> None:
        """Self-reference uses stable reason code."""
        result = mark_duplicate(
            incident=open_incident,
            duplicate_of=DuplicateOfIncidentId("test-incident-1"),
            actor="user",
            now=later_time,
        )

        assert isinstance(result, TransitionRejected)
        assert result.reason == "duplicate_self_reference"
        assert isinstance(result.reason, str)
