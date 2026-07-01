"""Integration tests: P4c uses backend-targeted diagnosis (success paths)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from helpers.otel_demo_k8s_diagnosis_backend_integration_helpers import (
    mock_budget_reset_result,
    mock_budget_status_success,
)

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    BackendIncidentDetail,
    TargetedDiagnosisInvocationResult,
    TargetedDiagnosisPollResult,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution import (
    run_backend_targeted_diagnosis,
)


class TestP4cUsesBackendTargetedDiagnosis:
    """Integration tests verifying P4c uses backend-targeted diagnosis."""

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.get_budget_status_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.reset_diagnosis_loop_budget_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.fetch_backend_incident_detail_result")
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
        mock_fetch_result: MagicMock,
        mock_reset: MagicMock,
        mock_status: MagicMock,
    ) -> None:
        """Test P4c invokes backend targeted diagnosis endpoint.

        This is the key integration test: the one-pass diagnosis loop
        should use the backend-targeted endpoint, not the scheduler
        periodic loop.
        """
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            BackendIncidentFetchResult,
        )

        # Configure budget reset mocks to return successful results
        mock_reset.return_value = mock_budget_reset_result("inc-otel-demo")
        mock_status.return_value = mock_budget_status_success("inc-otel-demo")

        # Setup: incident exists, invocation succeeds, diagnosis completes
        # fetch_backend_incident_detail_result returns BackendIncidentFetchResult
        mock_fetch_result.return_value = BackendIncidentFetchResult(
            success=True,
            incident=BackendIncidentDetail(
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
            ),
        )

        # fetch_backend_incident_detail returns BackendIncidentDetail directly (used in phase2)
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

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.get_budget_status_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.reset_diagnosis_loop_budget_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.fetch_backend_incident_detail_result")
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
        mock_fetch_result: MagicMock,
        mock_reset: MagicMock,
        mock_status: MagicMock,
    ) -> None:
        """Test P4c validates pass artifacts after diagnosis."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            BackendIncidentFetchResult,
        )

        # Configure budget reset mocks to return successful results
        mock_reset.return_value = mock_budget_reset_result("inc-otel-demo")
        mock_status.return_value = mock_budget_status_success("inc-otel-demo")

        # fetch_backend_incident_detail_result returns BackendIncidentFetchResult
        mock_fetch_result.return_value = BackendIncidentFetchResult(
            success=True,
            incident=BackendIncidentDetail(
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
            ),
        )

        # fetch_backend_incident_detail returns BackendIncidentDetail directly (used in phase2)
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

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.get_budget_status_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.reset_diagnosis_loop_budget_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.fetch_backend_incident_detail_result")
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
        mock_fetch_result: MagicMock,
        mock_reset: MagicMock,
        mock_status: MagicMock,
    ) -> None:
        """Test backend-targeted diagnosis bypasses scheduler view.

        This is the key regression test: the backend-targeted diagnosis
        should work even when the scheduler periodic loop would fail
        with incidents_eligible=0.
        """
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            BackendIncidentFetchResult,
        )

        # Configure budget reset mocks to return successful results
        mock_reset.return_value = mock_budget_reset_result("inc-otel-demo")
        mock_status.return_value = mock_budget_status_success("inc-otel-demo")

        # Setup: incident visible in backend (include raw for pass_count extraction)
        mock_fetch_result.return_value = BackendIncidentFetchResult(
            success=True,
            incident=BackendIncidentDetail(
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
            ),
        )

        # fetch_backend_incident_detail returns BackendIncidentDetail directly (used in phase2)
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
