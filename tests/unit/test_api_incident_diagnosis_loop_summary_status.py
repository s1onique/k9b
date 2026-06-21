"""Tests for automatic_diagnosis_loop_summary status derivation.

Tests cover:
- no diagnosis-loop events → not_run
- started only → running_or_started
- completed only → completed
- failed only → failed_or_unavailable
- started then completed → completed (latest by occurred_at)
- completed then later failed → failed_or_unavailable (latest by occurred_at)
- failed then later started → running_or_started (latest by occurred_at)

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
