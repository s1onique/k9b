"""Tests for budget_exhausted fail-fast behavior.

When the backend returns HTTP 200 + skipped=true + eligible=false
with eligibility_reason=budget_exhausted, the runner should fail
immediately WITHOUT polling.

Bug: P4c would poll 5 times (up to max_passes) even when the invocation
response clearly indicated budget exhaustion.

Fix: Check is_runtime_state() after invocation and fail fast if
budget is exhausted.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestBudgetExhaustedFailFast:
    """Tests for budget_exhausted fail-fast behavior."""

    def test_budget_exhausted_returns_runtime_state(self) -> None:
        """Test that budget_exhausted response has is_runtime_state=True."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            FAILURE_TARGETED_LOOP_NOT_ELIGIBLE,
            TargetedDiagnosisInvocationResult,
        )

        result = TargetedDiagnosisInvocationResult(
            success=True,
            http_status=200,
            body='{"skipped": true, "eligible": false, "eligibility_reason": "budget_exhausted"}',
            json_parsed=True,
            response_data={
                "skipped": True,
                "eligible": False,
                "eligibility_reason": "budget_exhausted",
            },
            error_class=FAILURE_TARGETED_LOOP_NOT_ELIGIBLE,
            error_detail="Loop not eligible: budget_exhausted",
        )

        assert result.is_runtime_state() is True, (
            "budget_exhausted should be classified as runtime state, not transport error"
        )

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.poll_backend_diagnosis_state")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.invoke_targeted_automatic_diagnosis_loop")
    def test_runner_fails_fast_on_budget_exhausted(
        self,
        mock_invoke: MagicMock,
        mock_poll: MagicMock,
    ) -> None:
        """Test that runner fails immediately on budget_exhausted without polling.

        This is the critical test: when the invocation returns budget_exhausted,
        the runner should NOT poll. If polling occurs, this test fails.
        """
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases import (
            phase2_invoke_and_poll_pass,
        )

        # Simulate budget_exhausted response
        budget_exhausted_result = MagicMock()
        budget_exhausted_result.success = True
        budget_exhausted_result.http_status = 200
        budget_exhausted_result.error_class = "targeted_automatic_diagnosis_loop_not_eligible"
        budget_exhausted_result.error_detail = "Loop not eligible: budget_exhausted"
        budget_exhausted_result.is_runtime_state.return_value = True

        mock_invoke.return_value = budget_exhausted_result

        result: dict[str, object] = {}
        success, pass_count, pass_run_ids, post_attempted = phase2_invoke_and_poll_pass(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="test-incident",
            pass_attempt=1,
            max_passes=5,
            result=result,
        )

        # Should fail immediately
        assert success is False, "Should fail on budget_exhausted"
        assert pass_count == 0
        assert pass_run_ids == []
        # POST was made (got HTTP 200 + budget_exhausted response), but loop was not eligible
        assert post_attempted is True, (
            "post_attempted should be True for budget_exhausted (POST was made, got response)"
        )

        # Should NOT poll - real_loop_invoked should be False
        assert result.get("real_loop_invoked") is False, (
            "real_loop_invoked should be False for budget_exhausted"
        )
        # Verify actionable detail is preserved (budget_exhausted not just not_eligible)
        failure_reason = result.get("failure_reason", "")
        assert isinstance(failure_reason, str)
        assert "budget_exhausted" in failure_reason, (
            f"failure_reason should include 'budget_exhausted' detail, got: {result.get('failure_reason')}"
        )

        # Verify invocation was called once
        mock_invoke.assert_called_once()
        # DIRECT GUARD: poll should never be called on budget exhaustion
        mock_poll.assert_not_called()
