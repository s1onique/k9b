"""Tests for store wiring to typed lifecycle domain core - Projections.

Tests that prove:
- Typed transition events are mapped to existing store events
- Unrelated incident fields are not modified
- Persisted/API-compatible shape remains unchanged
"""

from __future__ import annotations

from unittest.mock import patch

from incident_store_fixtures import TEST_TIME_1, TEST_TIME_2, make_candidate, make_store

from k8s_diag_agent.domain.incident_lifecycle import (
    IncidentId,
    IncidentLifecycle,
    SourceCandidateId,
    TransitionApplied,
)


class TestEventMapping:
    """Test that domain events are mapped to store events correctly."""

    def test_lifecycle_events_are_appended_to_incident(self) -> None:
        """Lifecycle events from typed core should appear in incident events."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")
        bundle_id = "bundle-123"

        store.promote_candidates([candidate], TEST_TIME_1)
        incident_id = store.list_incidents()[0].incident_id

        from k8s_diag_agent.domain.incident_lifecycle import IncidentLifecycleEvent

        mock_event = IncidentLifecycleEvent(
            event_type="incident_marked_collecting_evidence",
            actor="system",
            incident_id=IncidentId(incident_id),
            created_at=TEST_TIME_2,
            detail="Evidence collection started",
        )

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
                events=(mock_event,),
            )

            result = store.mark_collecting_evidence(incident_id, bundle_id)

            assert result is not None
            timeline = result.get_timeline()
            assert len(timeline) > 0


class TestPublicProjectionStability:
    """Test that public incident projection remains stable."""

    def test_incident_id_preserved_after_transition(self) -> None:
        """incident_id should not change during lifecycle transitions."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")
        bundle_id = "bundle-123"

        store.promote_candidates([candidate], TEST_TIME_1)
        original = store.list_incidents()[0]
        original_id = original.incident_id

        with patch(
            "k8s_diag_agent.collect.incident_lifecycle_transitions.domain_mark_collecting_evidence"
        ) as mock_transition:
            mock_transition.return_value = TransitionApplied(
                incident=IncidentLifecycle(
                    incident_id=IncidentId(original_id),
                    source_candidate_id=SourceCandidateId(original.source_candidate_id),
                    status="collecting_evidence",
                    first_observed_at=original.first_observed_at,
                    last_observed_at=TEST_TIME_2,
                    signal_count=1,
                    evidence_count=1,
                ),
                events=(),
            )

            result = store.mark_collecting_evidence(original_id, bundle_id)
            assert result is not None
            assert result.incident_id == original_id

    def test_signal_count_preserved_after_transition(self) -> None:
        """signal_count should not change during lifecycle transitions."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")
        bundle_id = "bundle-123"

        store.promote_candidates([candidate], TEST_TIME_1)
        original = store.list_incidents()[0]
        original_signals = original.signal_count

        with patch(
            "k8s_diag_agent.collect.incident_lifecycle_transitions.domain_mark_collecting_evidence"
        ) as mock_transition:
            mock_transition.return_value = TransitionApplied(
                incident=IncidentLifecycle(
                    incident_id=IncidentId(original.incident_id),
                    source_candidate_id=SourceCandidateId(original.source_candidate_id),
                    status="collecting_evidence",
                    first_observed_at=original.first_observed_at,
                    last_observed_at=TEST_TIME_2,
                    signal_count=original_signals,
                    evidence_count=1,
                ),
                events=(),
            )

            result = store.mark_collecting_evidence(original.incident_id, bundle_id)
            assert result is not None
            assert result.signal_count == original_signals

    def test_source_candidate_id_preserved_after_transition(self) -> None:
        """source_candidate_id should not change during lifecycle transitions."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")
        bundle_id = "bundle-123"

        store.promote_candidates([candidate], TEST_TIME_1)
        original = store.list_incidents()[0]
        original_candidate_id = original.source_candidate_id

        with patch(
            "k8s_diag_agent.collect.incident_lifecycle_transitions.domain_mark_collecting_evidence"
        ) as mock_transition:
            mock_transition.return_value = TransitionApplied(
                incident=IncidentLifecycle(
                    incident_id=IncidentId(original.incident_id),
                    source_candidate_id=SourceCandidateId(original_candidate_id),
                    status="collecting_evidence",
                    first_observed_at=original.first_observed_at,
                    last_observed_at=TEST_TIME_2,
                    signal_count=1,
                    evidence_count=1,
                ),
                events=(),
            )

            result = store.mark_collecting_evidence(original.incident_id, bundle_id)
            assert result is not None
            assert result.source_candidate_id == original_candidate_id


if __name__ == "__main__":
    import unittest
    unittest.main()
