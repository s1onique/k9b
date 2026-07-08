"""Tests for store wiring to typed lifecycle domain core - Transitions.

Tests that prove each lifecycle method delegates to typed transition functions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from incident_store_fixtures import TEST_TIME_1, TEST_TIME_2, make_candidate, make_store

from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.domain.incident_lifecycle import (
    DuplicateOfIncidentId,
    IncidentId,
    IncidentLifecycle,
    ReviewPacketId,
    SnapshotBundleId,
    SourceCandidateId,
    TransitionApplied,
    TransitionRejected,
)


class TestMarkCollectingEvidenceUsesTypedCore:
    """Test that mark_collecting_evidence uses typed domain transition."""

    def test_collecting_evidence_transitions_to_typed_core(self) -> None:
        """mark_collecting_evidence must call typed transition function."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")
        bundle_id = "bundle-123"

        store.promote_candidates([candidate], TEST_TIME_1)
        incident_id = store.list_incidents()[0].incident_id

        with patch(
            "k8s_diag_agent.collect.incident_lifecycle_transitions.domain_mark_collecting_evidence"
        ) as mock_transition:
            mock_transition.return_value = TransitionApplied(
                incident=IncidentLifecycle(
                    incident_id=IncidentId(incident_id),
                    source_candidate_id=SourceCandidateId("test-candidate"),
                    status="collecting_evidence",
                    first_observed_at=TEST_TIME_1,
                    last_observed_at=TEST_TIME_2,
                    signal_count=1,
                    evidence_count=1,
                ),
                events=(),
            )

            store.mark_collecting_evidence(incident_id, bundle_id)

            mock_transition.assert_called_once()
            call_kwargs = mock_transition.call_args.kwargs
            assert call_kwargs["bundle_id"] == SnapshotBundleId(bundle_id)
            assert call_kwargs["actor"] == "system"
            assert isinstance(call_kwargs["now"], datetime)

    def test_collecting_evidence_rejection_returns_current_state(self) -> None:
        """Rejection from typed core should return current state (no-op)."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")
        bundle_id = "bundle-123"

        store.promote_candidates([candidate], TEST_TIME_1, snapshot_bundle_id=bundle_id)
        incident_id = store.list_incidents()[0].incident_id

        with patch(
            "k8s_diag_agent.collect.incident_lifecycle_transitions.domain_mark_collecting_evidence"
        ) as mock_transition:
            mock_transition.return_value = TransitionRejected(
                incident=IncidentLifecycle(
                    incident_id=IncidentId(incident_id),
                    source_candidate_id=SourceCandidateId("test-candidate"),
                    status="collecting_evidence",
                    first_observed_at=TEST_TIME_1,
                    last_observed_at=TEST_TIME_1,
                    signal_count=1,
                    evidence_count=1,
                ),
                reason="invalid_transition",
            )

            result = store.mark_collecting_evidence(incident_id, bundle_id)
            assert result is not None
            assert result.status == IncidentStatus.COLLECTING_EVIDENCE


class TestMarkReadyForReviewUsesTypedCore:
    """Test that mark_ready_for_review uses typed domain transition."""

    def test_ready_for_review_transitions_to_typed_core(self) -> None:
        """mark_ready_for_review must call typed transition function."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")
        bundle_id = "bundle-123"
        review_packet_id = "review-456"

        store.promote_candidates([candidate], TEST_TIME_1, snapshot_bundle_id=bundle_id)
        incident_id = store.list_incidents()[0].incident_id

        with patch(
            "k8s_diag_agent.collect.incident_lifecycle_transitions.domain_mark_ready_for_review"
        ) as mock_transition:
            mock_transition.return_value = TransitionApplied(
                incident=IncidentLifecycle(
                    incident_id=IncidentId(incident_id),
                    source_candidate_id=SourceCandidateId("test-candidate"),
                    status="ready_for_review",
                    first_observed_at=TEST_TIME_1,
                    last_observed_at=TEST_TIME_2,
                    signal_count=1,
                    evidence_count=1,
                ),
                events=(),
            )

            store.mark_ready_for_review(incident_id, review_packet_id)

            mock_transition.assert_called_once()
            call_kwargs = mock_transition.call_args.kwargs
            assert call_kwargs["review_packet_id"] == ReviewPacketId(review_packet_id)
            assert call_kwargs["actor"] == "diagnosis_loop"

    def test_ready_for_review_rejection_returns_current_state(self) -> None:
        """Rejection from typed core should return current state (no-op)."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        store.promote_candidates([candidate], TEST_TIME_1)
        incident_id = store.list_incidents()[0].incident_id

        with patch(
            "k8s_diag_agent.collect.incident_lifecycle_transitions.domain_mark_ready_for_review"
        ) as mock_transition:
            mock_transition.return_value = TransitionRejected(
                incident=IncidentLifecycle(
                    incident_id=IncidentId(incident_id),
                    source_candidate_id=SourceCandidateId("test-candidate"),
                    status="open",
                    first_observed_at=TEST_TIME_1,
                    last_observed_at=TEST_TIME_1,
                    signal_count=1,
                    evidence_count=0,
                ),
                reason="invalid_transition",
            )

            result = store.mark_ready_for_review(incident_id, "review-123")
            assert result is not None
            assert result.status == IncidentStatus.OPEN

    def test_mark_ready_for_review_from_open_allows_transition(self) -> None:
        """OPEN -> READY_FOR_REVIEW: allows transition for legacy compatibility.

        The typed domain core now accepts OPEN -> READY_FOR_REVIEW transitions
        to preserve backward compatibility with pre-ACT behavior. This allows
        incidents to be marked ready even when they haven't gone through
        COLLECTING_EVIDENCE.
        """
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        # Promote candidate WITHOUT bundle_id -> incident starts in OPEN state
        store.promote_candidates([candidate], TEST_TIME_1)
        incident = store.list_incidents()[0]
        assert incident.status == IncidentStatus.OPEN

        # Mark ready for review from OPEN state (legacy path)
        result = store.mark_ready_for_review(incident.incident_id, "review-123")

        # Transition succeeds
        assert result is not None
        assert result.status == IncidentStatus.READY_FOR_REVIEW
        # Review packet is set when ID is provided
        assert result.review_packet.id == "review-123"


class TestSuppressUsesTypedCore:
    """Test that suppress uses typed domain transition."""

    def test_suppress_transitions_to_typed_core(self) -> None:
        """suppress must call typed transition function."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")
        reason = "known issue"

        store.promote_candidates([candidate], TEST_TIME_1)
        incident_id = store.list_incidents()[0].incident_id

        with patch(
            "k8s_diag_agent.collect.incident_lifecycle_transitions.domain_suppress_incident"
        ) as mock_transition:
            mock_transition.return_value = TransitionApplied(
                incident=IncidentLifecycle(
                    incident_id=IncidentId(incident_id),
                    source_candidate_id=SourceCandidateId("test-candidate"),
                    status="suppressed",
                    first_observed_at=TEST_TIME_1,
                    last_observed_at=TEST_TIME_2,
                    signal_count=1,
                    evidence_count=0,
                ),
                events=(),
            )

            store.suppress(incident_id, reason)

            mock_transition.assert_called_once()
            call_kwargs = mock_transition.call_args.kwargs
            assert call_kwargs["reason"] == reason
            assert call_kwargs["actor"] == "user"

    def test_suppress_rejection_returns_current_state(self) -> None:
        """Rejection from typed core should return current state (no-op)."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        store.promote_candidates([candidate], TEST_TIME_1)
        incident_id = store.list_incidents()[0].incident_id
        store.suppress(incident_id, "initial suppress")

        with patch(
            "k8s_diag_agent.collect.incident_lifecycle_transitions.domain_suppress_incident"
        ) as mock_transition:
            mock_transition.return_value = TransitionRejected(
                incident=IncidentLifecycle(
                    incident_id=IncidentId(incident_id),
                    source_candidate_id=SourceCandidateId("test-candidate"),
                    status="suppressed",
                    first_observed_at=TEST_TIME_1,
                    last_observed_at=TEST_TIME_1,
                    signal_count=1,
                    evidence_count=0,
                ),
                reason="terminal_incident",
            )

            result = store.suppress(incident_id, "second suppress")
            assert result is not None
            assert result.status == IncidentStatus.SUPPRESSED


class TestMarkDuplicateUsesTypedCore:
    """Test that mark_duplicate uses typed domain transition."""

    def test_mark_duplicate_transitions_to_typed_core(self) -> None:
        """mark_duplicate must call typed transition function."""
        store = make_store()
        candidate1 = make_candidate(name="pod-1")
        candidate2 = make_candidate(name="pod-2")
        duplicate_of_id = "test-incident-1"

        store.promote_candidates([candidate1, candidate2], TEST_TIME_1)
        incidents = store.list_incidents()
        incident2_id = incidents[1].incident_id

        with patch(
            "k8s_diag_agent.collect.incident_lifecycle_transitions.domain_mark_duplicate"
        ) as mock_transition:
            mock_transition.return_value = TransitionApplied(
                incident=IncidentLifecycle(
                    incident_id=IncidentId(incident2_id),
                    source_candidate_id=SourceCandidateId("test-candidate"),
                    status="duplicate",
                    first_observed_at=TEST_TIME_1,
                    last_observed_at=TEST_TIME_2,
                    signal_count=1,
                    evidence_count=0,
                ),
                events=(),
            )

            store.mark_duplicate(incident2_id, duplicate_of_id)

            mock_transition.assert_called_once()
            call_kwargs = mock_transition.call_args.kwargs
            assert call_kwargs["duplicate_of"] == DuplicateOfIncidentId(duplicate_of_id)
            assert call_kwargs["actor"] == "user"


class TestResolveUsesTypedCore:
    """Test that resolve uses typed domain transition."""

    def test_resolve_transitions_to_typed_core(self) -> None:
        """resolve must call typed transition function."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        store.promote_candidates([candidate], TEST_TIME_1, snapshot_bundle_id="bundle-1")
        incident_id = store.list_incidents()[0].incident_id

        with patch(
            "k8s_diag_agent.collect.incident_lifecycle_transitions.domain_mark_investigating"
        ) as mock_investigating:
            mock_investigating.return_value = TransitionApplied(
                incident=IncidentLifecycle(
                    incident_id=IncidentId(incident_id),
                    source_candidate_id=SourceCandidateId("test-candidate"),
                    status="investigating",
                    first_observed_at=TEST_TIME_1,
                    last_observed_at=TEST_TIME_2,
                    signal_count=1,
                    evidence_count=1,
                ),
                events=(),
            )
            store.mark_investigating(incident_id)

        with patch(
            "k8s_diag_agent.collect.incident_lifecycle_transitions.domain_resolve_incident"
        ) as mock_resolve:
            mock_resolve.return_value = TransitionApplied(
                incident=IncidentLifecycle(
                    incident_id=IncidentId(incident_id),
                    source_candidate_id=SourceCandidateId("test-candidate"),
                    status="resolved",
                    first_observed_at=TEST_TIME_1,
                    last_observed_at=datetime.now(UTC),
                    signal_count=1,
                    evidence_count=1,
                ),
                events=(),
            )

            store.resolve(incident_id)

            mock_resolve.assert_called_once()
            call_kwargs = mock_resolve.call_args.kwargs
            assert call_kwargs["actor"] == "user"


class TestMarkInvestigatingUsesTypedCore:
    """Test that mark_investigating uses typed domain transition."""

    def test_mark_investigating_transitions_to_typed_core(self) -> None:
        """mark_investigating must call typed transition function."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        store.promote_candidates([candidate], TEST_TIME_1, snapshot_bundle_id="bundle-1")
        incident_id = store.list_incidents()[0].incident_id

        with patch(
            "k8s_diag_agent.collect.incident_lifecycle_transitions.domain_mark_ready_for_review"
        ) as mock_ready:
            mock_ready.return_value = TransitionApplied(
                incident=IncidentLifecycle(
                    incident_id=IncidentId(incident_id),
                    source_candidate_id=SourceCandidateId("test-candidate"),
                    status="ready_for_review",
                    first_observed_at=TEST_TIME_1,
                    last_observed_at=TEST_TIME_2,
                    signal_count=1,
                    evidence_count=1,
                ),
                events=(),
            )
            store.mark_ready_for_review(incident_id, "review-123")

        with patch(
            "k8s_diag_agent.collect.incident_lifecycle_transitions.domain_mark_investigating"
        ) as mock_investigating:
            mock_investigating.return_value = TransitionApplied(
                incident=IncidentLifecycle(
                    incident_id=IncidentId(incident_id),
                    source_candidate_id=SourceCandidateId("test-candidate"),
                    status="investigating",
                    first_observed_at=TEST_TIME_1,
                    last_observed_at=datetime.now(UTC),
                    signal_count=1,
                    evidence_count=1,
                ),
                events=(),
            )

            store.mark_investigating(incident_id)

            mock_investigating.assert_called_once()
            call_kwargs = mock_investigating.call_args.kwargs
            assert call_kwargs["actor"] == "diagnosis_loop"


if __name__ == "__main__":
    import unittest
    unittest.main()
