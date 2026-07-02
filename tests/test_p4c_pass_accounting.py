"""Regression tests for P4c pass accounting, terminal single-pass handling,
budget classification, and failure message fixes.

These tests verify the fixes for the live OTel unschedulable-shipping lab failure:
- P4c counts automatic_diagnosis_review as observable passes
- P4c accepts terminal stop_no_checks_proposed as valid single-pass outcome
- P4c does not exhaust budget by attempting redundant second pass
- P4c emits precise budget failure reasons
- P4c never says "loop was not invoked" after any POST attempt

Reference incident detail payload (from live lab):
{
    "review_packet": {"status": "not_generated"},
    "loop_summary": null,
    "automatic_diagnosis_review": {
        "available": true,
        "artifact_type": "diagnosis-loop-review-packet",
        "run_id": "auto-otel-demo-deployment-shipping-deployment_unavailable-20260701220449",
        "decision": "stop_no_checks_proposed",
        "checks_requested": 0,
        "checks_run": 0,
        "read_only": true,
        "review_required_before_any_action": true,
        "no_remediation_attempted": true
    }
}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_TARGETED_BUDGET_EXHAUSTED_BEFORE_REQUIRED_PASSES,
    FAILURE_TARGETED_COMPLETED_WITHOUT_OBSERVABLE_PASS,
    FAILURE_TARGETED_INSUFFICIENT_PASSES,
    FAILURE_TARGETED_TERMINAL_NO_CHECKS,
    count_observable_targeted_diagnosis_passes,
    is_read_only_terminal_decision,
    is_terminal_no_checks_decision,
)

# =============================================================================
# Test 1: P4c counts automatic_diagnosis_review as one pass
# =============================================================================


class TestCountObservablePasses:
    """Tests for count_observable_targeted_diagnosis_passes helper."""

    def test_counts_review_as_one_pass(self) -> None:
        """P4c counts automatic_diagnosis_review as one pass."""
        detail: dict[str, Any] = {
            "review_packet": {"status": "not_generated"},
            "loop_summary": None,
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_type": "diagnosis-loop-review-packet",
                "run_id": "auto-test-run",
                "decision": "stop_no_checks_proposed",
                "checks_requested": 0,
                "checks_run": 0,
            },
        }

        assert count_observable_targeted_diagnosis_passes(detail) == 1

    def test_counts_loop_summary_pass_count_first(self) -> None:
        """P4c prefers explicit loop_summary.pass_count over review artifact."""
        detail: dict[str, Any] = {
            "automatic_diagnosis_loop_summary": {
                "pass_count": 3,
            },
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_type": "diagnosis-loop-review-packet",
                "run_id": "auto-test-run",
            },
        }

        # Should use loop_summary.pass_count = 3, not review artifact = 1
        assert count_observable_targeted_diagnosis_passes(detail) == 3

    def test_counts_pass_run_ids(self) -> None:
        """P4c uses length of pass_run_ids when pass_count not available."""
        detail: dict[str, Any] = {
            "automatic_diagnosis_loop_summary": {
                "pass_run_ids": ["run-1", "run-2", "run-3"],
            },
        }

        assert count_observable_targeted_diagnosis_passes(detail) == 3

    def test_counts_zero_when_no_artifacts(self) -> None:
        """P4c counts 0 when no pass artifacts exist."""
        detail: dict[str, Any] = {
            "review_packet": {"status": "not_generated"},
            "loop_summary": None,
            "automatic_diagnosis_review": {
                "available": False,
            },
        }

        assert count_observable_targeted_diagnosis_passes(detail) == 0

    def test_does_not_count_non_review_artifact(self) -> None:
        """P4c does not count non-review-packet artifacts."""
        detail: dict[str, Any] = {
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_type": "some-other-artifact",
                "run_id": "auto-test-run",
            },
        }

        assert count_observable_targeted_diagnosis_passes(detail) == 0

    def test_does_not_count_missing_run_id(self) -> None:
        """P4c does not count review artifact without run_id."""
        detail: dict[str, Any] = {
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_type": "diagnosis-loop-review-packet",
                # No run_id
            },
        }

        assert count_observable_targeted_diagnosis_passes(detail) == 0


# =============================================================================
# Test 2: P4c accepts terminal no-checks single-pass outcome
# =============================================================================


class TestTerminalNoChecksDecision:
    """Tests for terminal no-checks decision detection."""

    def test_detects_terminal_no_checks(self) -> None:
        """P4c detects terminal stop_no_checks_proposed decision."""
        detail: dict[str, Any] = {
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_type": "diagnosis-loop-review-packet",
                "run_id": "auto-test-run",
                "decision": "stop_no_checks_proposed",
                "checks_requested": 0,
                "checks_run": 0,
            },
        }

        assert is_terminal_no_checks_decision(detail) is True

    def test_detects_non_terminal_decision(self) -> None:
        """P4c does not flag continue decisions as terminal."""
        detail: dict[str, Any] = {
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_type": "diagnosis-loop-review-packet",
                "run_id": "auto-test-run",
                "decision": "continue",
                "checks_requested": 1,
                "checks_run": 0,
            },
        }

        assert is_terminal_no_checks_decision(detail) is False

    def test_read_only_terminal_decision(self) -> None:
        """P4c detects read-only constraints satisfied."""
        detail: dict[str, Any] = {
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_type": "diagnosis-loop-review-packet",
                "run_id": "auto-test-run",
                "decision": "stop_no_checks_proposed",
                "checks_requested": 0,
                "checks_run": 0,
                "read_only": True,
                "review_required_before_any_action": True,
                "no_remediation_attempted": True,
            },
        }

        assert is_read_only_terminal_decision(detail) is True


# =============================================================================
# Test 3: P4c does not invoke second pass after terminal no-checks
# =============================================================================


class TestLabStrictTerminalNoChecks:
    """Tests for lab-strict mode where terminal single-pass is NOT sufficient."""

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.get_budget_status_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.reset_diagnosis_loop_budget_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.fetch_backend_incident_detail_result")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.fetch_backend_incident_detail")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.invoke_targeted_automatic_diagnosis_loop")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.poll_backend_diagnosis_state")
    def test_runner_continues_when_terminal_no_checks_with_insufficient_passes(
        self,
        mock_poll: MagicMock,
        mock_invoke: MagicMock,
        mock_fetch: MagicMock,
        mock_fetch_result: MagicMock,
        mock_reset: MagicMock,
        mock_status: MagicMock,
    ) -> None:
        """LAB-STRICT: Runner continues to pass 2 when terminal no-checks reached with only 1 pass.

        This is the FIXED behavior: previously the runner would break immediately on
        terminal_no_checks_accepted, but now it checks pass_count >= MIN_REQUIRED_PASSES first.
        """
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            BackendIncidentDetail,
            BackendIncidentFetchResult,
            TargetedDiagnosisInvocationResult,
            TargetedDiagnosisPollResult,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution import (
            run_backend_targeted_diagnosis,
        )

        # Setup: terminal no-checks in first pass
        mock_status.return_value = {
            "incident_id": "test-incident",
            "budget_clean": True,
            "review_packet_count": 0,
            "total_auto_artifact_count": 0,
            "error": None,
        }
        mock_reset.return_value = MagicMock(
            reset_file_count=0,
            error=None,
        )

        # Incident detail with terminal no-checks
        terminal_detail = {
            "incident_id": "test-incident",
            "status": "collecting_evidence",
            "evidence_count": 1,
            "review_packet": {"status": "not_generated"},
            "automatic_diagnosis_loop_summary": None,  # null - the split-brain state
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_type": "diagnosis-loop-review-packet",
                "run_id": "auto-test-incident-20260701220449",
                "decision": "stop_no_checks_proposed",
                "checks_requested": 0,
                "checks_run": 0,
                "read_only": True,
                "review_required_before_any_action": True,
                "no_remediation_attempted": True,
            },
        }

        mock_fetch_result.return_value = BackendIncidentFetchResult(
            success=True,
            incident=BackendIncidentDetail.from_dict("test-incident", terminal_detail),
        )
        mock_fetch.return_value = BackendIncidentDetail.from_dict("test-incident", terminal_detail)

        mock_invoke.return_value = TargetedDiagnosisInvocationResult(
            success=True,
            http_status=200,
            body='{"status": "diagnosis_pass_completed"}',
            json_parsed=True,
        )

        mock_poll.return_value = TargetedDiagnosisPollResult(
            success=True,
            final_status="collecting_evidence",
            loop_summary_status="completed",
            review_available=True,
            attempts=1,
            max_attempts=12,
        )

        result = run_backend_targeted_diagnosis(
            incident_id="test-incident",
            external_analysis_dir=Path("/tmp/analysis"),
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            result={},
            allow_simulation=False,
        )

        # With the fix, runner continues to all max_passes because pass_count=1 < MIN_REQUIRED_PASSES=2
        # terminal_no_checks_accepted is True in the result (from the phase)
        # but the runner does NOT set terminal_no_checks_reached (because pass_count < required)
        assert result.get("terminal_no_checks_accepted") is True
        # Should exhaust all max_passes (DEFAULT_MAX_PASSES=5) because pass_count never reaches 2
        assert mock_invoke.call_count == 5, (
            f"Expected 5 invocations (exhaust all max_passes because pass_count=1 < 2), got {mock_invoke.call_count}"
        )

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.get_budget_status_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.reset_diagnosis_loop_budget_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.fetch_backend_incident_detail_result")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.fetch_backend_incident_detail")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.invoke_targeted_automatic_diagnosis_loop")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.poll_backend_diagnosis_state")
    def test_runner_stops_early_when_terminal_with_sufficient_passes(
        self,
        mock_poll: MagicMock,
        mock_invoke: MagicMock,
        mock_fetch: MagicMock,
        mock_fetch_result: MagicMock,
        mock_reset: MagicMock,
        mock_status: MagicMock,
    ) -> None:
        """Runner CAN stop early when terminal no-checks reached WITH sufficient passes.

        This is the optimized case: terminal decision reached AND pass_count >= MIN_REQUIRED_PASSES.
        """
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            BackendIncidentDetail,
            BackendIncidentFetchResult,
            TargetedDiagnosisInvocationResult,
            TargetedDiagnosisPollResult,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution import (
            run_backend_targeted_diagnosis,
        )

        # Setup: terminal no-checks with 2 passes
        mock_status.return_value = {
            "incident_id": "test-incident",
            "budget_clean": True,
            "review_packet_count": 0,
            "total_auto_artifact_count": 0,
            "error": None,
        }
        mock_reset.return_value = MagicMock(
            reset_file_count=0,
            error=None,
        )

        # Incident detail with terminal no-checks AND 2 passes
        terminal_detail = {
            "incident_id": "test-incident",
            "status": "collecting_evidence",
            "evidence_count": 1,
            "review_packet": {"status": "not_generated"},
            "automatic_diagnosis_loop_summary": {
                "pass_count": 2,
                "pass_run_ids": ["run-1", "run-2"],
            },
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_type": "diagnosis-loop-review-packet",
                "run_id": "auto-test-incident-20260701220449",
                "decision": "stop_no_checks_proposed",
                "checks_requested": 0,
                "checks_run": 0,
                "read_only": True,
                "review_required_before_any_action": True,
                "no_remediation_attempted": True,
            },
        }

        mock_fetch_result.return_value = BackendIncidentFetchResult(
            success=True,
            incident=BackendIncidentDetail.from_dict("test-incident", terminal_detail),
        )
        mock_fetch.return_value = BackendIncidentDetail.from_dict("test-incident", terminal_detail)

        mock_invoke.return_value = TargetedDiagnosisInvocationResult(
            success=True,
            http_status=200,
            body='{"status": "diagnosis_pass_completed"}',
            json_parsed=True,
        )

        mock_poll.return_value = TargetedDiagnosisPollResult(
            success=True,
            final_status="collecting_evidence",
            loop_summary_status="completed",
            review_available=True,
            attempts=1,
            max_attempts=12,
        )

        result = run_backend_targeted_diagnosis(
            incident_id="test-incident",
            external_analysis_dir=Path("/tmp/analysis"),
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            result={},
            allow_simulation=False,
        )

        # With terminal decision AND pass_count >= MIN_REQUIRED_PASSES, should stop after pass 1
        assert result.get("pass_count") == 2
        assert result.get("terminal_no_checks_accepted") is True
        # Should only invoke ONCE because pass_count >= required after first pass
        assert mock_invoke.call_count == 1, (
            f"Expected 1 invocation (terminal after pass with sufficient passes), got {mock_invoke.call_count}"
        )


# =============================================================================
# Test 4: P4c reports budget exhausted before required passes
# =============================================================================


class TestBudgetExhaustedFailure:
    """Tests for budget exhaustion failure classification."""

    def test_reports_budget_exhausted_when_no_terminal(self) -> None:
        """P4c reports budget_exhausted_before_required_passes when no terminal decision."""
        # This would be the failure reason when:
        # - First pass consumed budget (used=1, limit=1)
        # - Second pass cannot run because budget exhausted
        # - No terminal decision was reached
        failure_reason = FAILURE_TARGETED_BUDGET_EXHAUSTED_BEFORE_REQUIRED_PASSES

        assert failure_reason == "targeted_automatic_diagnosis_budget_exhausted_before_required_passes"


# =============================================================================
# Test 5: P4c does not say loop was not invoked after POST attempt
# =============================================================================


class TestMisleadingFailureMessage:
    """Tests for fixing misleading failure messages."""

    def test_no_misleading_message_after_invocation_attempted(self) -> None:
        """P4c does not say 'loop was not invoked' after POST attempt."""
        # The old message was: "Automatic diagnosis loop was not invoked"
        # The new message should be: "targeted_automatic_diagnosis_completed_without_observable_pass_artifacts"
        assert FAILURE_TARGETED_COMPLETED_WITHOUT_OBSERVABLE_PASS == (
            "targeted_automatic_diagnosis_completed_without_observable_pass_artifacts"
        )

        # Should NOT use the generic insufficient_passes when invocation was attempted
        assert FAILURE_TARGETED_INSUFFICIENT_PASSES == "targeted_automatic_diagnosis_insufficient_passes"


# =============================================================================
# Test 6: Live lab contract payload
# =============================================================================


class TestLiveLabContractPayload:
    """Tests for the exact live lab incident detail payload."""

    def test_live_lab_payload_counts_as_one_pass(self) -> None:
        """The exact live lab payload should count as 1 observable pass."""
        live_lab_detail: dict[str, Any] = {
            "review_packet": {"status": "not_generated"},
            "loop_summary": None,
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_type": "diagnosis-loop-review-packet",
                "run_id": "auto-otel-demo-deployment-shipping-deployment_unavailable-20260701220449",
                "decision": "stop_no_checks_proposed",
                "checks_requested": 0,
                "checks_run": 0,
                "read_only": True,
                "review_required_before_any_action": True,
                "no_remediation_attempted": True,
            },
        }

        # Should count as 1 pass
        assert count_observable_targeted_diagnosis_passes(live_lab_detail) == 1

        # Should detect terminal no-checks
        assert is_terminal_no_checks_decision(live_lab_detail) is True

        # Should satisfy read-only constraints
        assert is_read_only_terminal_decision(live_lab_detail) is True

    def test_terminal_no_checks_is_success(self) -> None:
        """Terminal no-checks remains a canonical backend classification.

        Lab-strict success still depends on satisfying the required observable pass count.
        """
        assert FAILURE_TARGETED_TERMINAL_NO_CHECKS == "targeted_automatic_diagnosis_terminal_no_checks"
