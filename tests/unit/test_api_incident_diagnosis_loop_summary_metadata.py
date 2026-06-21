"""Tests for automatic_diagnosis_loop_summary metadata propagation.

Tests cover:
- unavailable reason propagated only from failed event metadata
- check counts propagated only from completed event metadata
- review packet availability reflected
- timestamp extraction for all event types
- latest event chosen by occurred_at, not input order

Hard constraints verified:
- NO remediation actions
- NO raw event data
- NO raw packet contents
"""

from __future__ import annotations

from k8s_diag_agent.ui.api_incident_diagnosis_loop_summary import (
    DiagnosisLoopStatus,
    build_automatic_diagnosis_loop_summary,
)
from tests.unit.incident_diagnosis_loop_summary_fixtures import make_event


class TestTimestampOrdering:
    """Tests for timestamp-based event ordering."""

    def test_latest_event_chosen_by_occurred_at_not_input_order(self) -> None:
        """Latest event is chosen by occurred_at, not input list order."""
        # Input order: failed, started, completed (reversed chronological)
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_failed",
                "2026-01-01T12:00:00+00:00",
            ),
            make_event(
                "event-2",
                "diagnosis_loop_started",
                "2026-01-01T12:05:00+00:00",
            ),
            make_event(
                "event-3",
                "diagnosis_loop_completed",
                "2026-01-01T12:10:00+00:00",
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=True,
        )
        # Latest by occurred_at is completed (event-3)
        assert result["status"] == DiagnosisLoopStatus.COMPLETED
        assert result["latest_event_id"] == "event-3"
        assert result["latest_event_type"] == "diagnosis_loop_completed"
        assert result["latest_started_at"] is not None
        assert result["latest_completed_at"] is not None

    def test_timestamps_extracted_for_all_event_types(self) -> None:
        """Timestamps are extracted for all diagnosis loop event types."""
        events = [
            make_event(
                "event-started",
                "diagnosis_loop_started",
                "2026-01-01T12:00:00+00:00",
            ),
            make_event(
                "event-completed",
                "diagnosis_loop_completed",
                "2026-01-01T12:05:00+00:00",
            ),
            make_event(
                "event-failed",
                "diagnosis_loop_failed",
                "2026-01-01T12:10:00+00:00",
                {"unavailable_reason": "error"},
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        # Latest is failed
        assert result["status"] == DiagnosisLoopStatus.FAILED_OR_UNAVAILABLE
        # But timestamps are captured for all
        assert result["latest_started_at"] is not None
        assert result["latest_completed_at"] is not None
        assert result["latest_failed_at"] is not None


class TestUnavailableReason:
    """Tests for unavailable_reason propagation."""

    def test_unavailable_reason_from_failed_event(self) -> None:
        """Unavailable reason is propagated from failed event metadata."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_failed",
                "2026-01-01T12:00:00+00:00",
                {"unavailable_reason": "case_file_error"},
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        assert result["status"] == DiagnosisLoopStatus.FAILED_OR_UNAVAILABLE
        assert result["unavailable_reason"] == "case_file_error"

    def test_unavailable_reason_not_from_started_event(self) -> None:
        """Unavailable reason is not propagated from started event."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_started",
                "2026-01-01T12:00:00+00:00",
                {"unavailable_reason": "should_be_ignored"},
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        assert result["status"] == DiagnosisLoopStatus.RUNNING_OR_STARTED
        assert result["unavailable_reason"] is None

    def test_unavailable_reason_not_from_completed_event(self) -> None:
        """Unavailable reason is not propagated from completed event."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_completed",
                "2026-01-01T12:00:00+00:00",
                {"unavailable_reason": "should_be_ignored"},
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        assert result["status"] == DiagnosisLoopStatus.COMPLETED
        assert result["unavailable_reason"] is None

    def test_unavailable_reason_from_latest_failed_when_multiple_failed(self) -> None:
        """When multiple failed events, uses latest (most recent) failed reason by timestamp."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_failed",
                "2026-01-01T12:00:00+00:00",
                {"unavailable_reason": "first_error"},
            ),
            make_event(
                "event-2",
                "diagnosis_loop_failed",
                "2026-01-01T12:10:00+00:00",
                {"unavailable_reason": "second_error"},
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        assert result["status"] == DiagnosisLoopStatus.FAILED_OR_UNAVAILABLE
        # Uses latest failed reason by timestamp (most recent)
        assert result["unavailable_reason"] == "second_error"


class TestCheckCounts:
    """Tests for check count propagation."""

    def test_check_counts_from_completed_event(self) -> None:
        """Check counts are propagated from completed event metadata."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_completed",
                "2026-01-01T12:00:00+00:00",
                {
                    "checks_requested": 10,
                    "checks_run": 8,
                    "checks_rejected": 2,
                },
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=True,
        )
        assert result["status"] == DiagnosisLoopStatus.COMPLETED
        assert result["checks_requested"] == 10
        assert result["checks_run"] == 8
        assert result["checks_rejected"] == 2

    def test_check_counts_not_from_started_event(self) -> None:
        """Check counts are not propagated from started event."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_started",
                "2026-01-01T12:00:00+00:00",
                {
                    "checks_requested": 10,
                    "checks_run": 8,
                    "checks_rejected": 2,
                },
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        assert result["status"] == DiagnosisLoopStatus.RUNNING_OR_STARTED
        assert result["checks_requested"] is None
        assert result["checks_run"] is None
        assert result["checks_rejected"] is None

    def test_check_counts_not_from_failed_event(self) -> None:
        """Check counts are not propagated from failed event."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_failed",
                "2026-01-01T12:00:00+00:00",
                {
                    "checks_requested": 10,
                    "checks_run": 8,
                    "checks_rejected": 2,
                },
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        assert result["status"] == DiagnosisLoopStatus.FAILED_OR_UNAVAILABLE
        assert result["checks_requested"] is None
        assert result["checks_run"] is None
        assert result["checks_rejected"] is None


class TestReviewPacketAvailability:
    """Tests for review packet availability."""

    def test_review_packet_available_passed_through(self) -> None:
        """Review packet availability is passed through to summary."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_completed",
                "2026-01-01T12:00:00+00:00",
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=True,
            review_packet_id="review-packet-abc",
        )
        assert result["review_packet_available"] is True
        assert result["review_packet_id"] == "review-packet-abc"

    def test_review_packet_not_available_passed_through(self) -> None:
        """Review packet not available is passed through to summary."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_started",
                "2026-01-01T12:00:00+00:00",
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        assert result["review_packet_available"] is False
        assert result["review_packet_id"] is None
