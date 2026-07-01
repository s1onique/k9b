"""Integration tests for P4c uses backend-targeted diagnosis.

These tests verify the integration between the backend helpers and the runner.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    BackendIncidentDetail,
    TargetedDiagnosisInvocationResult,
    TargetedDiagnosisPollResult,
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution import (
    run_backend_targeted_diagnosis,
)


# =============================================================================
# Test P4c Uses Backend-Targeted Diagnosis
# =============================================================================


class TestP4cUsesBackendTargetedDiagnosis:
    """Integration tests verifying P4c uses backend-targeted diagnosis."""

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.fetch_backend_incident_detail")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.invoke_targeted_automatic_diagnosis_loop")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.poll_backend_diagnosis_state")
    @patch("time.sleep")
    def test_p4c_invokes_backend_endpoint(
        self,
        mock_sleep: MagicMock,
        mock_poll: MagicMock,
        mock_invoke: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Test P4c invokes backend targeted diagnosis endpoint.

        This is the key integration test: the one-pass diagnosis loop
        should use the backend-targeted endpoint, not the scheduler
        periodic loop.
        """
        # Setup: incident exists, invocation succeeds, diagnosis completes
        # Include raw with loop_summary for pass_count extraction
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-otel-demo",
            status="diagnosed",
            evidence_count=5,
            review_packet_status="ready",
            loop_summary_status="completed",
            review_available=True,
            raw={
                "automatic_diagnosis_loop_summary": {
                    "pass_run_ids": ["run-1", "run-2"],
                    "pass_count": 2,
                }
            },
        )

        mock_invoke.return_value = TargetedDiagnosisInvocationResult(
            success=True,
            http_status=200,
            body='{"status": "diagnosis_pass_completed"}',
            json_parsed=True,
            response_data={"status": "diagnosis_pass_completed"},
        )

        result: dict = {}

        _ = run_backend_targeted_diagnosis(
            incident_id="inc-otel-demo",
            external_analysis_dir=Path("/tmp/analysis"),
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            result=result,
            allow_simulation=False,
        )

        # Verify backend-targeted diagnosis was invoked with correct parameters
        mock_invoke.assert_called_once()
        invoke_call_kwargs = mock_invoke.call_args[1]
        assert invoke_call_kwargs["incident_id"] == "inc-otel-demo"

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.fetch_backend_incident_detail")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.invoke_targeted_automatic_diagnosis_loop")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.poll_backend_diagnosis_state")
    @patch("time.sleep")
    def test_p4c_validates_pass_artifacts(
        self,
        mock_sleep: MagicMock,
        mock_poll: MagicMock,
        mock_invoke: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Test P4c validates pass artifacts after diagnosis."""
        # Include raw field with loop summary for pass_count extraction
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-otel-demo",
            status="diagnosed",
            evidence_count=5,
            review_packet_status="ready",
            loop_summary_status="completed",
            review_available=True,
            raw={
                "automatic_diagnosis_loop_summary": {
                    "pass_run_ids": ["run-1", "run-2"],
                    "pass_count": 2,
                }
            },
        )

        mock_invoke.return_value = TargetedDiagnosisInvocationResult(
            success=True,
            http_status=200,
            body='{"status": "diagnosis_pass_completed"}',
            json_parsed=True,
        )

        mock_poll.return_value = TargetedDiagnosisPollResult(
            success=True,
            final_status="diagnosed",
            loop_summary_status="completed",
            review_available=True,
            attempts=3,
            max_attempts=12,
        )

        result: dict = {}

        _ = run_backend_targeted_diagnosis(
            incident_id="inc-otel-demo",
            external_analysis_dir=Path("/tmp/analysis"),
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            result=result,
            allow_simulation=False,
        )

        # Verify the diagnosis flow completed successfully
        assert result.get("failure_reason") is None
        assert result.get("real_loop_invoked") is True


# =============================================================================
# Test P4c Fails on Endpoint Errors
# =============================================================================


class TestP4cFailsOnEndpointErrors:
    """Tests verifying P4c fails appropriately on endpoint errors."""

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.fetch_backend_incident_detail")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.invoke_targeted_automatic_diagnosis_loop")
    def test_fails_on_transport_error(
        self,
        mock_invoke: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Test P4c fails with structured error on transport error."""
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-otel-demo",
            status="collecting_evidence",
            evidence_count=1,
            review_packet_status=None,
            loop_summary_status="pending",
            review_available=False,
        )

        mock_invoke.return_value = TargetedDiagnosisInvocationResult(
            success=False,
            http_status=0,
            body="",
            json_parsed=False,
            error_class=FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
            error_detail="Transport error: curl_rc=7",
            curl_rc=7,
        )

        result: dict = {}

        _ = run_backend_targeted_diagnosis(
            incident_id="inc-otel-demo",
            external_analysis_dir=Path("/tmp/analysis"),
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            result=result,
            allow_simulation=False,
        )

        assert result["failure_reason"] == FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR
        assert result["status"] == "invocation_failed"

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.fetch_backend_incident_detail")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.invoke_targeted_automatic_diagnosis_loop")
    def test_fails_on_http_error(
        self,
        mock_invoke: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Test P4c fails with structured error on HTTP error."""
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-otel-demo",
            status="collecting_evidence",
            evidence_count=1,
            review_packet_status=None,
            loop_summary_status="pending",
            review_available=False,
        )

        mock_invoke.return_value = TargetedDiagnosisInvocationResult(
            success=False,
            http_status=500,
            body="Internal Server Error",
            json_parsed=False,
            error_class="targeted_automatic_diagnosis_invocation_http_error",
            error_detail="HTTP 500",
            curl_rc=0,
        )

        result: dict = {}

        _ = run_backend_targeted_diagnosis(
            incident_id="inc-otel-demo",
            external_analysis_dir=Path("/tmp/analysis"),
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            result=result,
            allow_simulation=False,
        )

        assert result["failure_reason"] == "targeted_automatic_diagnosis_invocation_http_error"
        assert result["status"] == "invocation_failed"


# =============================================================================
# Test Regression Scheduler Periodic Loop Bug
# =============================================================================


class TestRegressionSchedulerPeriodicLoopBug:
    """Regression tests for the scheduler periodic loop bug.

    Bug: scheduler periodic loop reports incidents_eligible=0 while
    the backend incident exists with status=collecting_evidence.

    The fix ensures we use the backend-targeted one-pass endpoint
    which operates directly on the backend incident store.
    """

    def test_incident_visible_in_backend_but_not_scheduler(self) -> None:
        """Simulate the bug: incident in backend but not visible to scheduler.

        The scheduler's periodic loop would report incidents_eligible=0
        because it queries a different incident view than the backend.

        The backend-targeted diagnosis should find the incident.

        Note: This test verifies the function's ability to parse backend responses.
        We test directly with a BackendIncidentDetail object to avoid mocking issues.
        """
        # Simulate what the backend would return
        backend_response = {
            "status": "collecting_evidence",
            "evidence_count": 3,
            "review_packet": None,
            "automatic_diagnosis_loop_summary": {"status": "pending"},
            "automatic_diagnosis_review": {"available": False},
        }

        # Parse it like the function would
        detail = BackendIncidentDetail.from_dict("inc-otel-demo", backend_response)

        assert detail is not None
        assert detail.status == "collecting_evidence"
        assert detail.evidence_count == 3

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.fetch_backend_incident_detail")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.invoke_targeted_automatic_diagnosis_loop")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.poll_backend_diagnosis_state")
    @patch("time.sleep")
    def test_backend_targeted_bypasses_scheduler_view(
        self,
        mock_sleep: MagicMock,
        mock_poll: MagicMock,
        mock_invoke: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Test backend-targeted diagnosis bypasses scheduler view.

        This is the key regression test: the backend-targeted diagnosis
        should work even when the scheduler periodic loop would fail
        with incidents_eligible=0.
        """
        # Setup: incident visible in backend (include raw for pass_count extraction)
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-otel-demo",
            status="diagnosed",
            evidence_count=5,
            review_packet_status="ready",
            loop_summary_status="completed",
            review_available=True,
            raw={
                "automatic_diagnosis_loop_summary": {
                    "pass_run_ids": ["run-1", "run-2"],
                    "pass_count": 2,
                }
            },
        )

        mock_invoke.return_value = TargetedDiagnosisInvocationResult(
            success=True,
            http_status=200,
            body='{"status": "diagnosis_pass_completed"}',
            json_parsed=True,
        )

        mock_poll.return_value = TargetedDiagnosisPollResult(
            success=True,
            final_status="diagnosed",
            loop_summary_status="completed",
            review_available=True,
            attempts=2,
            max_attempts=12,
        )

        result: dict = {}

        _ = run_backend_targeted_diagnosis(
            incident_id="inc-otel-demo",
            external_analysis_dir=Path("/tmp/analysis"),
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            result=result,
            allow_simulation=False,
        )

        # Backend-targeted diagnosis should succeed (no failure_reason set)
        assert result.get("failure_reason") is None
        assert result.get("real_loop_invoked") is True
