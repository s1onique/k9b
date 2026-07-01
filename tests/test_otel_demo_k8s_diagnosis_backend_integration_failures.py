"""Integration tests: P4c fails on endpoint errors."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from helpers.otel_demo_k8s_diagnosis_backend_integration_helpers import (
    mock_budget_reset_result,
    mock_budget_status_success,
)

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
    BackendIncidentDetail,
    TargetedDiagnosisInvocationResult,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution import (
    run_backend_targeted_diagnosis,
)


class TestP4cFailsOnEndpointErrors:
    """Tests verifying P4c fails appropriately on endpoint errors."""

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.get_budget_status_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.reset_diagnosis_loop_budget_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.fetch_backend_incident_detail_result")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.invoke_targeted_automatic_diagnosis_loop")
    def test_fails_on_transport_error(
        self,
        mock_invoke: MagicMock,
        mock_fetch_result: MagicMock,
        mock_reset: MagicMock,
        mock_status: MagicMock,
    ) -> None:
        """Test P4c fails with structured error on transport error."""
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
                status="collecting_evidence",
                evidence_count=1,
                review_packet_status=None,
                loop_summary_status="pending",
                review_available=False,
            ),
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

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.get_budget_status_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.reset_diagnosis_loop_budget_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.fetch_backend_incident_detail_result")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases.invoke_targeted_automatic_diagnosis_loop")
    def test_fails_on_http_error(
        self,
        mock_invoke: MagicMock,
        mock_fetch_result: MagicMock,
        mock_reset: MagicMock,
        mock_status: MagicMock,
    ) -> None:
        """Test P4c fails with structured error on HTTP error."""
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
                status="collecting_evidence",
                evidence_count=1,
                review_packet_status=None,
                loop_summary_status="pending",
                review_available=False,
            ),
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
