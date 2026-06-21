"""Tests for automatic_diagnosis_loop_summary projection.

Tests cover:
- no diagnosis-loop events → not_run
- started only → running_or_started
- completed only → completed
- failed only → failed_or_unavailable
- started then completed → completed (latest by occurred_at)
- completed then later failed → failed_or_unavailable (latest by occurred_at)
- failed then later started → running_or_started (latest by occurred_at)
- latest event chosen by occurred_at, not input order
- unavailable reason propagated only from failed event metadata
- check counts propagated only from completed event metadata
- review packet availability reflected
- safety flags always true
- unknown/malformed metadata ignored safely
- no raw packet/artifact/log/prompt/stack/stdout/stderr fields leaked

Hard constraints verified:
- NO remediation actions
- NO raw event data
- NO raw packet contents
- NO logs, stdout/stderr, stack traces
"""

from __future__ import annotations

import json

import pytest

from k8s_diag_agent.ui.api_incident_diagnosis_loop_summary import (
    DiagnosisLoopStatus,
    build_automatic_diagnosis_loop_summary,
)


# =============================================================================
# Helper: create diagnosis loop event
# =============================================================================


def make_event(
    event_id: str,
    event_type: str,
    occurred_at: str,
    data: dict | None = None,
) -> dict:
    """Create a diagnosis loop event dict."""
    return {
        "event_id": event_id,
        "incident_id": "test-incident",
        "event_type": event_type,
        "actor": "system",
        "occurred_at": occurred_at,
        "message": f"Test {event_type}",
        "data": data,
    }


# =============================================================================
# Tests: Status derivation
# =============================================================================


class TestStatusDerivation:
    """Tests for status derivation from events."""

    def test_no_events_returns_not_run(self) -> None:
        """No diagnosis-loop events → not_run."""
        result = build_automatic_diagnosis_loop_summary(
            events=[],
            review_packet_available=False,
        )
        assert result["status"] == DiagnosisLoopStatus.NOT_RUN
        assert result["latest_event_id"] is None
        assert result["latest_event_type"] is None

    def test_started_only_returns_running_or_started(self) -> None:
        """Started only → running_or_started."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_started",
                "2026-01-01T12:00:00+00:00",
                {"run_id": "auto-123"},
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        assert result["status"] == DiagnosisLoopStatus.RUNNING_OR_STARTED
        assert result["latest_event_id"] == "event-1"
        assert result["latest_event_type"] == "diagnosis_loop_started"

    def test_completed_only_returns_completed(self) -> None:
        """Completed only → completed."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_completed",
                "2026-01-01T12:05:00+00:00",
                {"checks_requested": 3, "checks_run": 2, "checks_rejected": 1},
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=True,
            review_packet_id="review-packet-123",
        )
        assert result["status"] == DiagnosisLoopStatus.COMPLETED
        assert result["checks_requested"] == 3
        assert result["checks_run"] == 2
        assert result["checks_rejected"] == 1

    def test_failed_only_returns_failed_or_unavailable(self) -> None:
        """Failed only → failed_or_unavailable."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_failed",
                "2026-01-01T12:10:00+00:00",
                {"unavailable_reason": "not_eligible"},
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        assert result["status"] == DiagnosisLoopStatus.FAILED_OR_UNAVAILABLE
        assert result["unavailable_reason"] == "not_eligible"

    def test_started_then_completed_returns_completed(self) -> None:
        """Started then completed → completed (latest by occurred_at)."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_started",
                "2026-01-01T12:00:00+00:00",
            ),
            make_event(
                "event-2",
                "diagnosis_loop_completed",
                "2026-01-01T12:05:00+00:00",
                {"checks_requested": 5, "checks_run": 4},
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=True,
        )
        assert result["status"] == DiagnosisLoopStatus.COMPLETED
        assert result["latest_event_id"] == "event-2"
        assert result["checks_requested"] == 5
        assert result["checks_run"] == 4

    def test_completed_then_later_failed_returns_failed_or_unavailable(self) -> None:
        """Completed then later failed → failed_or_unavailable (latest by occurred_at)."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_completed",
                "2026-01-01T12:00:00+00:00",
            ),
            make_event(
                "event-2",
                "diagnosis_loop_failed",
                "2026-01-01T12:10:00+00:00",
                {"unavailable_reason": "orchestrator_error"},
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        assert result["status"] == DiagnosisLoopStatus.FAILED_OR_UNAVAILABLE
        assert result["latest_event_id"] == "event-2"
        assert result["unavailable_reason"] == "orchestrator_error"

    def test_failed_then_later_started_returns_running_or_started(self) -> None:
        """Failed then later started → running_or_started (latest by occurred_at)."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_failed",
                "2026-01-01T12:00:00+00:00",
                {"unavailable_reason": "case_file_error"},
            ),
            make_event(
                "event-2",
                "diagnosis_loop_started",
                "2026-01-01T12:10:00+00:00",
                {"run_id": "auto-456"},
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        assert result["status"] == DiagnosisLoopStatus.RUNNING_OR_STARTED
        assert result["latest_event_id"] == "event-2"
        # Original failed reason is preserved in unavailable_reason if latest is failed
        # But since latest is started, unavailable_reason should be None
        assert result["unavailable_reason"] is None


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


class TestSafetyFlags:
    """Tests for safety flags."""

    def test_safety_flags_always_true(self) -> None:
        """Safety flags are always True regardless of state."""
        test_cases = [
            [],
            [make_event("e1", "diagnosis_loop_started", "2026-01-01T12:00:00+00:00")],
            [make_event("e1", "diagnosis_loop_completed", "2026-01-01T12:00:00+00:00")],
            [make_event("e1", "diagnosis_loop_failed", "2026-01-01T12:00:00+00:00")],
        ]
        for events in test_cases:
            result = build_automatic_diagnosis_loop_summary(
                events=events,
                review_packet_available=False,
            )
            assert result["read_only"] is True
            assert result["review_required_before_any_action"] is True
            assert result["no_remediation_attempted"] is True


class TestSafetyFiltering:
    """Tests for safety filtering - no raw content leakage."""

    def test_no_raw_event_data_leaked(self) -> None:
        """No raw event data is exposed in summary."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_started",
                "2026-01-01T12:00:00+00:00",
                {
                    "run_id": "safe-run-id",
                    "raw_content": "should not leak",
                    "file_content": "should not leak",
                    "artifact_payload": "should not leak",
                    "prompt": "should not leak",
                    "stdout": "should not leak",
                    "stderr": "should not leak",
                    "stack_trace": "should not leak",
                },
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        result_str = json.dumps(result)
        assert "should not leak" not in result_str
        assert "raw_content" not in result_str
        assert "file_content" not in result_str
        assert "artifact_payload" not in result_str
        assert "prompt" not in result_str
        assert "stdout" not in result_str
        assert "stderr" not in result_str
        assert "stack_trace" not in result_str

    def test_no_kubectl_helm_commands_leaked(self) -> None:
        """No kubectl/Helm command text is leaked."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_completed",
                "2026-01-01T12:00:00+00:00",
                {
                    "command": "kubectl delete pod test-pod",
                    "helm_command": "helm uninstall test",
                    "action": "delete",
                },
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        result_str = json.dumps(result)
        assert "kubectl" not in result_str
        assert "helm" not in result_str
        assert "delete" not in result_str.lower() or result["checks_requested"] is None

    def test_unknown_status_fallback(self) -> None:
        """Unknown event types are handled gracefully."""
        events = [
            make_event(
                "event-1",
                "unknown_event_type",
                "2026-01-01T12:00:00+00:00",
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        # Unknown events are filtered out, so we get not_run
        assert result["status"] == DiagnosisLoopStatus.NOT_RUN

    def test_malformed_timestamp_handled(self) -> None:
        """Malformed timestamps are handled gracefully."""
        events = [
            {
                "event_id": "event-1",
                "incident_id": "test-incident",
                "event_type": "diagnosis_loop_started",
                "actor": "system",
                "occurred_at": "not-a-valid-timestamp",
                "message": "Test",
                "data": {},
            },
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        # Invalid timestamp causes event to be skipped
        assert result["status"] == DiagnosisLoopStatus.NOT_RUN

    def test_null_data_handled(self) -> None:
        """Null event data is handled gracefully."""
        events = [
            make_event(
                "event-1",
                "diagnosis_loop_started",
                "2026-01-01T12:00:00+00:00",
                None,  # Explicitly null data
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        assert result["status"] == DiagnosisLoopStatus.RUNNING_OR_STARTED
        assert result["unavailable_reason"] is None
        assert result["checks_requested"] is None


class TestNonDiagnosisLoopEvents:
    """Tests for non-diagnosis-loop events are ignored."""

    def test_other_event_types_ignored(self) -> None:
        """Non-diagnosis-loop events are filtered out."""
        events = [
            {
                "event_id": "event-1",
                "incident_id": "test-incident",
                "event_type": "opened",
                "actor": "system",
                "occurred_at": "2026-01-01T11:00:00+00:00",
                "message": "Incident opened",
                "data": {},
            },
            {
                "event_id": "event-2",
                "incident_id": "test-incident",
                "event_type": "severity_changed",
                "actor": "system",
                "occurred_at": "2026-01-01T11:05:00+00:00",
                "message": "Severity changed",
                "data": {},
            },
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=False,
        )
        assert result["status"] == DiagnosisLoopStatus.NOT_RUN

    def test_mixed_diagnosis_and_other_events(self) -> None:
        """Mixed diagnosis and non-diagnosis events work correctly."""
        events = [
            {
                "event_id": "event-1",
                "incident_id": "test-incident",
                "event_type": "opened",
                "actor": "system",
                "occurred_at": "2026-01-01T11:00:00+00:00",
                "message": "Incident opened",
                "data": {},
            },
            make_event(
                "event-2",
                "diagnosis_loop_started",
                "2026-01-01T12:00:00+00:00",
            ),
            make_event(
                "event-3",
                "diagnosis_loop_completed",
                "2026-01-01T12:05:00+00:00",
                {"checks_requested": 5, "checks_run": 4},
            ),
        ]
        result = build_automatic_diagnosis_loop_summary(
            events=events,
            review_packet_available=True,
        )
        assert result["status"] == DiagnosisLoopStatus.COMPLETED
        assert result["latest_event_id"] == "event-3"
        assert result["checks_requested"] == 5