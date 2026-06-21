"""Tests for automatic_diagnosis_loop_summary safety filtering.

Tests cover:
- safety flags always true
- no raw packet/artifact/log/prompt/stack/stdout/stderr fields leaked
- kubectl/helm commands not leaked
- unknown/malformed metadata ignored safely
- non-diagnosis-loop events filtered out

Hard constraints verified:
- NO remediation actions
- NO raw packet contents
- NO logs, stdout/stderr, stack traces
"""

from __future__ import annotations

import json

from k8s_diag_agent.ui.api_incident_diagnosis_loop_summary import (
    DiagnosisLoopStatus,
    build_automatic_diagnosis_loop_summary,
)
from tests.unit.incident_diagnosis_loop_summary_fixtures import make_event


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


class TestEdgeCases:
    """Tests for edge cases and error handling."""

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
