"""Exhaustiveness tests for incident lifecycle transitions.

This module demonstrates pattern-matching with assert_never() for
exhaustiveness checking of TransitionResult union types.

The assert_never() pattern ensures that any new variants added to the
TransitionResult union will cause a compile-time or runtime error
if not handled in pattern matches.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import assert_never

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
    TransitionResult,
    mark_collecting_evidence,
    mark_duplicate,
    mark_investigating,
    mark_ready_for_review,
    resolve_incident,
    suppress_incident,
)

# -----------------------------------------------------------------------------
# Test fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def base_time() -> datetime:
    """Standard test timestamp."""
    return datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)


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


# -----------------------------------------------------------------------------
# Exhaustiveness helper
# -----------------------------------------------------------------------------

def render_transition_result(result: TransitionResult) -> str:
    """Render a transition result to a string.

    This function demonstrates exhaustiveness checking: if a new variant
    is added to TransitionResult and not handled here, assert_never() will
    fail at runtime.
    """
    match result:
        case TransitionApplied():
            return f"applied:{result.incident.status}"
        case TransitionRejected():
            return f"rejected:{result.reason}"
        case _:
            assert_never(result)


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------

class TestExhaustiveness:
    """Tests demonstrating exhaustiveness checking patterns."""

    def test_render_transition_result_handles_applied(self) -> None:
        """render_transition_result handles TransitionApplied."""
        result = mark_collecting_evidence(
            incident=IncidentLifecycle(
                incident_id=IncidentId("test"),
                source_candidate_id=SourceCandidateId("cand"),
                status="open",
                first_observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                last_observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                signal_count=1,
                evidence_count=0,
            ),
            bundle_id=SnapshotBundleId("bundle-1"),
            actor="system",
            now=datetime(2024, 1, 2, tzinfo=UTC),
        )

        rendered = render_transition_result(result)
        assert rendered == "applied:collecting_evidence"

    def test_render_transition_result_handles_rejected(self) -> None:
        """render_transition_result handles TransitionRejected."""
        result = mark_ready_for_review(
            incident=IncidentLifecycle(
                incident_id=IncidentId("test"),
                source_candidate_id=SourceCandidateId("cand"),
                status="open",  # Wrong state for this transition
                first_observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                last_observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                signal_count=1,
                evidence_count=0,
            ),
            review_packet_id=ReviewPacketId("review-1"),
            actor="system",
            now=datetime(2024, 1, 2, tzinfo=UTC),
        )

        rendered = render_transition_result(result)
        assert rendered == "rejected:invalid_transition"

    def test_all_transitions_return_exhaustible_results(self) -> None:
        """All transition functions return TransitionResult (exhaustible union)."""
        base_time = datetime(2024, 1, 1, tzinfo=UTC)
        later_time = datetime(2024, 1, 2, tzinfo=UTC)

        open_inc = IncidentLifecycle(
            incident_id=IncidentId("test"),
            source_candidate_id=SourceCandidateId("cand"),
            status="open",
            first_observed_at=base_time,
            last_observed_at=base_time,
            signal_count=1,
            evidence_count=0,
        )

        collecting_inc = IncidentLifecycle(
            incident_id=IncidentId("test"),
            source_candidate_id=SourceCandidateId("cand"),
            status="collecting_evidence",
            first_observed_at=base_time,
            last_observed_at=base_time,
            signal_count=1,
            evidence_count=1,
        )

        ready_inc = IncidentLifecycle(
            incident_id=IncidentId("test"),
            source_candidate_id=SourceCandidateId("cand"),
            status="ready_for_review",
            first_observed_at=base_time,
            last_observed_at=base_time,
            signal_count=1,
            evidence_count=1,
        )

        investigating_inc = IncidentLifecycle(
            incident_id=IncidentId("test"),
            source_candidate_id=SourceCandidateId("cand"),
            status="investigating",
            first_observed_at=base_time,
            last_observed_at=base_time,
            signal_count=1,
            evidence_count=1,
        )

        suppressed_inc = IncidentLifecycle(
            incident_id=IncidentId("test"),
            source_candidate_id=SourceCandidateId("cand"),
            status="suppressed",
            first_observed_at=base_time,
            last_observed_at=base_time,
            signal_count=1,
            evidence_count=0,
        )

        # Collect all transition results
        results: list[TransitionResult] = [
            mark_collecting_evidence(open_inc, bundle_id=SnapshotBundleId("b1"), actor="system", now=later_time),
            mark_ready_for_review(collecting_inc, review_packet_id=ReviewPacketId("r1"), actor="system", now=later_time),
            mark_investigating(ready_inc, actor="system", now=later_time),
            resolve_incident(investigating_inc, actor="system", now=later_time),
            suppress_incident(open_inc, reason="test", actor="system", now=later_time),
            mark_duplicate(open_inc, duplicate_of=DuplicateOfIncidentId("other"), actor="system", now=later_time),
            # Terminal state transitions (should all be rejected)
            mark_collecting_evidence(suppressed_inc, bundle_id=SnapshotBundleId("b2"), actor="system", now=later_time),
            mark_ready_for_review(suppressed_inc, review_packet_id=ReviewPacketId("r2"), actor="system", now=later_time),
            mark_investigating(suppressed_inc, actor="system", now=later_time),
            resolve_incident(suppressed_inc, actor="system", now=later_time),
            suppress_incident(suppressed_inc, reason="test", actor="system", now=later_time),
            mark_duplicate(suppressed_inc, duplicate_of=DuplicateOfIncidentId("other"), actor="system", now=later_time),
        ]

        # Verify all results can be rendered (exhaustiveness check)
        for result in results:
            rendered = render_transition_result(result)
            assert isinstance(rendered, str)
            assert ":" in rendered

    def test_pattern_match_exhaustiveness(self) -> None:
        """Pattern matching on TransitionResult is exhaustive."""
        result = mark_collecting_evidence(
            incident=IncidentLifecycle(
                incident_id=IncidentId("test"),
                source_candidate_id=SourceCandidateId("cand"),
                status="open",
                first_observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                last_observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                signal_count=1,
                evidence_count=0,
            ),
            bundle_id=SnapshotBundleId("bundle-1"),
            actor="system",
            now=datetime(2024, 1, 2, tzinfo=UTC),
        )

        # Exhaustive pattern match (both variants handled)
        match result:
            case TransitionApplied(incident=inc, events=evts):
                assert inc.status == "collecting_evidence"
                assert len(evts) == 1
            case TransitionRejected(incident=inc, reason=reason):
                pytest.fail(f"Expected TransitionApplied, got rejected: {reason}")
            case _:
                assert_never(result)


# -----------------------------------------------------------------------------
# Type annotation verification
# -----------------------------------------------------------------------------

def test_transition_result_is_union() -> None:
    """Verify TransitionResult is a union type for static analysis tools."""
    # This test documents the expected type structure
    # If TransitionResult changes to a non-union, this test will fail
    # at type-checking time with proper static analysis tools

    applied: TransitionApplied = TransitionApplied(
        incident=IncidentLifecycle(
            incident_id=IncidentId("test"),
            source_candidate_id=SourceCandidateId("cand"),
            status="open",
            first_observed_at=datetime(2024, 1, 1, tzinfo=UTC),
            last_observed_at=datetime(2024, 1, 1, tzinfo=UTC),
            signal_count=1,
            evidence_count=0,
        ),
        events=(),
    )

    rejected: TransitionRejected = TransitionRejected(
        incident=IncidentLifecycle(
            incident_id=IncidentId("test"),
            source_candidate_id=SourceCandidateId("cand"),
            status="open",
            first_observed_at=datetime(2024, 1, 1, tzinfo=UTC),
            last_observed_at=datetime(2024, 1, 1, tzinfo=UTC),
            signal_count=1,
            evidence_count=0,
        ),
        reason="test",
    )

    # Both should be assignable to TransitionResult
    result_applied: TransitionResult = applied
    result_rejected: TransitionResult = rejected

    assert isinstance(result_applied, TransitionApplied)
    assert isinstance(result_rejected, TransitionRejected)
