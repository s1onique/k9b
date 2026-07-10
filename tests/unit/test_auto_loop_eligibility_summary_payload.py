"""Tests for automatic diagnosis loop eligibility summary payload builder.

Related to: ACT-K9B-AUTO-DIAGNOSIS-ELIGIBILITY-SUMMARY-PROD-PATH01
"""

from __future__ import annotations


class TestBuildEligibilitySummaryPayload:
    """Tests for the build_eligibility_summary_payload helper function."""

    def test_payload_uses_hyphenated_event_name(self):
        """Prove payload uses 'automatic-diagnosis-eligibility-summary' (hyphens)."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
            AutoLoopCollectorResult,
            build_eligibility_summary_payload,
        )

        result = AutoLoopCollectorResult(
            run_id="test-run-123",
            generated_at="2026-01-01T00:00:00+00:00",
            enabled=True,
            config={},
            incident_results=[],
        )

        payload = build_eligibility_summary_payload(
            collector_run_id="test-run-123",
            result=result,
        )

        # Critical: must use hyphens, not underscores
        assert payload["event"] == "automatic-diagnosis-eligibility-summary"
        assert "automatic_diagnosis_eligibility_summary" not in payload["event"]

    def test_payload_includes_all_required_fields(self):
        """Prove payload includes all required schema fields."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
            AutoLoopCollectorResult,
            build_eligibility_summary_payload,
        )

        result = AutoLoopCollectorResult(
            run_id="test-run-123",
            generated_at="2026-01-01T00:00:00+00:00",
            enabled=True,
            config={},
            incidents_processed=10,
            incidents_eligible=0,
            incidents_skipped=10,
            incidents_ineligible=0,
            incidents_with_errors=0,
            incident_results=[
                {"skipped": True, "eligibility_reason": "budget_exhausted"},
                {"skipped": True, "eligibility_reason": "budget_exhausted"},
            ],
        )

        payload = build_eligibility_summary_payload(
            collector_run_id="test-run-123",
            result=result,
        )

        # Required fields
        assert "event" in payload
        assert "collector_run_id" in payload
        assert "eligibility_version" in payload
        assert "incidents_processed" in payload
        assert "incidents_eligible" in payload
        assert "incidents_skipped" in payload
        assert "incidents_ineligible" in payload
        assert "incidents_with_errors" in payload
        assert "skip_reasons" in payload
        assert "error_reasons" in payload

    def test_payload_aggregates_skip_reasons(self):
        """Prove payload aggregates skip reasons from incident results."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
            AutoLoopCollectorResult,
            build_eligibility_summary_payload,
        )

        result = AutoLoopCollectorResult(
            run_id="test-run-123",
            generated_at="2026-01-01T00:00:00+00:00",
            enabled=True,
            config={},
            incidents_skipped=3,
            incident_results=[
                {"skipped": True, "eligibility_reason": "budget_exhausted"},
                {"skipped": True, "eligibility_reason": "budget_exhausted"},
                {"skipped": True, "eligibility_reason": "terminal_status_resolved"},
            ],
        )

        payload = build_eligibility_summary_payload(
            collector_run_id="test-run-123",
            result=result,
        )

        assert payload["skip_reasons"]["budget_exhausted"] == 2
        assert payload["skip_reasons"]["terminal_status_resolved"] == 1

    def test_payload_prefers_eligibility_reason_over_skip_reason(self):
        """Prove payload prefers eligibility_reason when both exist."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
            AutoLoopCollectorResult,
            build_eligibility_summary_payload,
        )

        result = AutoLoopCollectorResult(
            run_id="test-run-123",
            generated_at="2026-01-01T00:00:00+00:00",
            enabled=True,
            config={},
            incidents_skipped=1,
            incident_results=[
                {"skipped": True, "eligibility_reason": "budget_exhausted", "skip_reason": "old_skip"},
            ],
        )

        payload = build_eligibility_summary_payload(
            collector_run_id="test-run-123",
            result=result,
        )

        assert "budget_exhausted" in payload["skip_reasons"]
        assert "old_skip" not in payload["skip_reasons"]

    def test_payload_falls_back_to_unknown(self):
        """Prove payload uses 'unknown' when neither eligibility_reason nor skip_reason exists."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
            AutoLoopCollectorResult,
            build_eligibility_summary_payload,
        )

        result = AutoLoopCollectorResult(
            run_id="test-run-123",
            generated_at="2026-01-01T00:00:00+00:00",
            enabled=True,
            config={},
            incidents_skipped=1,
            incident_results=[
                {"skipped": True},  # No reason fields
            ],
        )

        payload = build_eligibility_summary_payload(
            collector_run_id="test-run-123",
            result=result,
        )

        assert "unknown" in payload["skip_reasons"]
        assert payload["skip_reasons"]["unknown"] == 1

    def test_payload_includes_error_reasons(self):
        """Prove payload includes error_reasons separately."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
            AutoLoopCollectorResult,
            build_eligibility_summary_payload,
        )

        result = AutoLoopCollectorResult(
            run_id="test-run-123",
            generated_at="2026-01-01T00:00:00+00:00",
            enabled=True,
            config={},
            incidents_with_errors=1,
            incident_results=[
                {"error": "KeyError: 'missing_key'"},
            ],
        )

        payload = build_eligibility_summary_payload(
            collector_run_id="test-run-123",
            result=result,
        )

        # Should extract error type from message
        assert "KeyError" in payload["error_reasons"]
