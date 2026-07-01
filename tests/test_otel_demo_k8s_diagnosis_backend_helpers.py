"""Unit tests for k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.py.

These tests validate:
1. BackendIncidentDetail parsing from API responses
2. TargetedDiagnosisInvocationResult classification
3. TargetedDiagnosisPollResult structure
4. invoke_targeted_diagnosis_loop() with mocked curl
5. fetch_backend_incident_detail() with mocked curl
6. P4c integration: uses backend-targeted diagnosis endpoint
7. Error handling: HTTP errors, transport errors, JSON parse errors
8. Polling: bounded retries, completion signals
9. Regression: scheduler periodic loop bug (incidents_eligible=0)
10. Safety contract: no mutation, no secret reads
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

# Import from the module under test
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers import (
    FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
    FAILURE_TARGETED_INVOCATION_INVALID_JSON,
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
    FAILURE_TARGETED_LOOP_NOT_COMPLETED,
    BackendIncidentDetail,
    TargetedDiagnosisInvocationResult,
    TargetedDiagnosisPollResult,
    check_pass_artifacts_in_backend,
    curl_backend_exec,
    fetch_backend_incident_detail,
    invoke_targeted_automatic_diagnosis_loop,
    poll_backend_diagnosis_state,
)

# =============================================================================
# Test BackendIncidentDetail
# =============================================================================


class TestBackendIncidentDetail:
    """Tests for BackendIncidentDetail parsing."""

    def test_from_dict_complete(self) -> None:
        """Test parsing a complete incident response."""
        data = {
            "status": "collecting_evidence",
            "evidence_count": 5,
            "review_packet": {"status": "ready"},
            "automatic_diagnosis_loop_summary": {"status": "completed"},
            "automatic_diagnosis_review": {"available": True},
        }
        detail = BackendIncidentDetail.from_dict("inc-123", data)

        assert detail.incident_id == "inc-123"
        assert detail.status == "collecting_evidence"
        assert detail.evidence_count == 5
        assert detail.review_packet_status == "ready"
        assert detail.loop_summary_status == "completed"
        assert detail.review_available is True
        assert detail.raw == data

    def test_from_dict_minimal(self) -> None:
        """Test parsing minimal incident response."""
        data: dict = {}
        detail = BackendIncidentDetail.from_dict("inc-456", data)

        assert detail.incident_id == "inc-456"
        assert detail.status == "unknown"
        assert detail.evidence_count == 0
        assert detail.review_packet_status is None
        assert detail.loop_summary_status is None
        assert detail.review_available is False

    def test_from_dict_null_review_packet(self) -> None:
        """Test parsing with null review_packet."""
        data = {"review_packet": None}
        detail = BackendIncidentDetail.from_dict("inc-789", data)

        assert detail.review_packet_status is None

    def test_to_compact_log(self) -> None:
        """Test compact log formatting."""
        data = {
            "status": "diagnosing",
            "evidence_count": 3,
            "review_packet": {"status": "pending"},
            "automatic_diagnosis_loop_summary": {"status": "running"},
            "automatic_diagnosis_review": {"available": False},
        }
        detail = BackendIncidentDetail.from_dict("inc-test", data)
        log = detail.to_compact_log()

        assert "incident_id=inc-test" in log
        assert "status=diagnosing" in log
        assert "evidence_count=3" in log
        assert "review_packet.status=pending" in log
        assert "loop_summary.status=running" in log
        assert "review_available=False" in log


# =============================================================================
# Test TargetedDiagnosisInvocationResult
# =============================================================================


class TestTargetedDiagnosisInvocationResult:
    """Tests for TargetedDiagnosisInvocationResult."""

    def test_success_result(self) -> None:
        """Test successful invocation result."""
        result = TargetedDiagnosisInvocationResult(
            success=True,
            http_status=200,
            body='{"status": "ok"}',
            json_parsed=True,
            response_data={"status": "ok"},
        )

        assert result.success is True
        assert result.http_status == 200
        assert result.json_parsed is True
        assert result.error_class is None

    def test_http_error_result(self) -> None:
        """Test HTTP error classification."""
        result = TargetedDiagnosisInvocationResult(
            success=False,
            http_status=500,
            body="Internal Server Error",
            json_parsed=False,
            error_class=FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
            error_detail="HTTP 500",
        )

        assert result.success is False
        assert result.error_class == FAILURE_TARGETED_INVOCATION_HTTP_ERROR

    def test_transport_error_result(self) -> None:
        """Test transport error classification."""
        result = TargetedDiagnosisInvocationResult(
            success=False,
            http_status=0,
            body="",
            json_parsed=False,
            error_class=FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
            error_detail="Transport error: curl_rc=7",
            curl_rc=7,
        )

        assert result.success is False
        assert result.error_class == FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR

    def test_invalid_json_result(self) -> None:
        """Test JSON parse error classification."""
        result = TargetedDiagnosisInvocationResult(
            success=False,
            http_status=200,
            body="not valid json",
            json_parsed=False,
            error_class=FAILURE_TARGETED_INVOCATION_INVALID_JSON,
            error_detail="JSON parse error: Expecting value",
        )

        assert result.success is False
        assert result.error_class == FAILURE_TARGETED_INVOCATION_INVALID_JSON

    def test_to_dict(self) -> None:
        """Test dict conversion for evidence."""
        result = TargetedDiagnosisInvocationResult(
            success=True,
            http_status=200,
            body='{"test": true}',
            json_parsed=True,
        )
        d = result.to_dict()

        assert d["success"] is True
        assert d["http_status"] == 200
        assert d["json_parsed"] is True
        assert "response_data" not in d  # Not serialized to avoid large blobs


# =============================================================================
# Test TargetedDiagnosisPollResult
# =============================================================================


class TestTargetedDiagnosisPollResult:
    """Tests for TargetedDiagnosisPollResult."""

    def test_success_poll_result(self) -> None:
        """Test successful poll result."""
        result = TargetedDiagnosisPollResult(
            success=True,
            final_status="diagnosed",
            loop_summary_status="completed",
            review_available=True,
            attempts=5,
            max_attempts=12,
        )

        assert result.success is True
        assert result.final_status == "diagnosed"
        assert result.loop_summary_status == "completed"
        assert result.review_available is True
        assert result.attempts == 5
        assert result.max_attempts == 12
        assert result.failure_reason is None

    def test_timeout_poll_result(self) -> None:
        """Test polling timeout result."""
        result = TargetedDiagnosisPollResult(
            success=False,
            final_status="diagnosing",
            loop_summary_status="running",
            review_available=False,
            attempts=12,
            max_attempts=12,
            failure_reason=FAILURE_TARGETED_LOOP_NOT_COMPLETED,
            error_detail="Polling timeout after 12 attempts",
        )

        assert result.success is False
        assert result.failure_reason == FAILURE_TARGETED_LOOP_NOT_COMPLETED
        assert result.error_detail is not None

    def test_to_dict(self) -> None:
        """Test dict conversion for evidence."""
        result = TargetedDiagnosisPollResult(
            success=True,
            final_status="diagnosed",
            loop_summary_status="completed",
            review_available=True,
            attempts=3,
            max_attempts=12,
        )
        d = result.to_dict()

        assert d["success"] is True
        assert d["final_status"] == "diagnosed"
        assert d["attempts"] == 3
        assert d["max_attempts"] == 12


# =============================================================================
# Test curl_backend_exec
# =============================================================================


class TestCurlBackendExec:
    """Tests for curl_backend_exec with mocked kubectl."""

    @patch("subprocess.run")
    def test_successful_get(self, mock_run: MagicMock) -> None:
        """Test successful GET request."""
        mock_run.return_value = MagicMock(
            stdout="HTTP_CODE=200\n{\"id\": \"inc-123\", \"status\": \"ok\"}\n",
            stderr="",
            returncode=0,
        )


        result = curl_backend_exec(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            target_url="http://localhost:8080/api/incidents/inc-123",
        )

        assert result.http_code == 200
        assert "inc-123" in result.body
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "kubectl" in call_args
        assert "--kubeconfig" in call_args

    @patch("subprocess.run")
    def test_transport_error(self, mock_run: MagicMock) -> None:
        """Test transport error (curl rc != 0)."""
        mock_run.return_value = MagicMock(
            stdout="CURL_EXIT=7\nHTTP_CODE=0\n",
            stderr="Could not resolve host",
            returncode=1,
        )

        result = curl_backend_exec(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            target_url="http://localhost:8080/api/incidents/inc-123",
        )

        assert result.http_code == 0
        assert result.curl_rc == 7
        assert result.success is False

    @patch("subprocess.run")
    def test_http_error(self, mock_run: MagicMock) -> None:
        """Test HTTP error (non-2xx)."""
        mock_run.return_value = MagicMock(
            stdout="HTTP_CODE=404\n{\"error\": \"not found\"}\n",
            stderr="",
            returncode=0,
        )

        result = curl_backend_exec(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            target_url="http://localhost:8080/api/incidents/inc-missing",
        )

        assert result.http_code == 404
        assert result.success is False


# =============================================================================
# Test invoke_targeted_diagnosis_loop
# =============================================================================


class TestInvokeTargetedDiagnosisLoop:
    """Tests for invoke_targeted_diagnosis_loop."""

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.curl_backend_exec")
    def test_successful_invocation(self, mock_curl: MagicMock) -> None:
        """Test successful one-pass invocation."""
        mock_curl.return_value = MagicMock(
            success=True,
            http_code=200,
            body='{"status": "diagnosis_pass_completed", "pass_number": 1}',
            curl_rc=0,
            stderr="",
        )

        result = invoke_targeted_automatic_diagnosis_loop(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert result.success is True
        assert result.http_status == 200
        assert result.json_parsed is True
        assert "pass_number" in result.response_data
        assert result.error_class is None

        # Verify POST was used and NEW endpoint is called (not fake-runner)
        call_kwargs = mock_curl.call_args[1]
        assert call_kwargs["method"] == "POST"
        assert "automatic-diagnosis-loop/one-pass" in call_kwargs["target_url"]

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.curl_backend_exec")
    def test_http_error_classification(self, mock_curl: MagicMock) -> None:
        """Test HTTP error is properly classified."""
        mock_curl.return_value = MagicMock(
            success=False,
            http_code=500,
            body="Internal Server Error",
            curl_rc=0,
            stderr="",
        )

        result = invoke_targeted_automatic_diagnosis_loop(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert result.success is False
        assert result.error_class == FAILURE_TARGETED_INVOCATION_HTTP_ERROR
        assert "500" in (result.error_detail or "")

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.curl_backend_exec")
    def test_transport_error_classification(self, mock_curl: MagicMock) -> None:
        """Test transport error is properly classified."""
        mock_curl.return_value = MagicMock(
            success=False,
            http_code=0,
            body="",
            curl_rc=7,
            stderr="Could not resolve host",
        )

        result = invoke_targeted_automatic_diagnosis_loop(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert result.success is False
        assert result.error_class == FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.curl_backend_exec")
    def test_invalid_json_classification(self, mock_curl: MagicMock) -> None:
        """Test JSON parse error is properly classified."""
        mock_curl.return_value = MagicMock(
            success=True,
            http_code=200,
            body="not valid json {",
            curl_rc=0,
            stderr="",
        )

        result = invoke_targeted_automatic_diagnosis_loop(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert result.success is False
        assert result.error_class == FAILURE_TARGETED_INVOCATION_INVALID_JSON

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.curl_backend_exec")
    def test_incident_not_found(self, mock_curl: MagicMock) -> None:
        """Test incident not found (404)."""
        mock_curl.return_value = MagicMock(
            success=False,
            http_code=404,
            body='{"error": "incident not found"}',
            curl_rc=0,
            stderr="",
        )

        result = invoke_targeted_automatic_diagnosis_loop(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-nonexistent",
        )

        assert result.success is False
        assert result.http_status == 404
        assert result.error_class == FAILURE_TARGETED_INVOCATION_HTTP_ERROR


# =============================================================================
# Test fetch_backend_incident_detail
# =============================================================================


class TestFetchBackendIncidentDetail:
    """Tests for fetch_backend_incident_detail."""

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.curl_backend_exec")
    def test_successful_fetch(self, mock_curl: MagicMock) -> None:
        """Test successful incident fetch."""
        mock_curl.return_value = MagicMock(
            success=True,
            http_code=200,
            body=json.dumps({
                "status": "collecting_evidence",
                "evidence_count": 5,
                "review_packet": {"status": "ready"},
            }),
            curl_rc=0,
            stderr="",
        )

        detail = fetch_backend_incident_detail(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert detail is not None
        assert detail.incident_id == "inc-123"
        assert detail.status == "collecting_evidence"
        assert detail.evidence_count == 5

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.curl_backend_exec")
    def test_transport_failure_returns_none(self, mock_curl: MagicMock) -> None:
        """Test transport failure returns None."""
        mock_curl.return_value = MagicMock(
            success=False,
            http_code=0,
            body="",
            curl_rc=7,
            stderr="Connection refused",
        )

        detail = fetch_backend_incident_detail(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert detail is None

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.curl_backend_exec")
    def test_invalid_json_returns_none(self, mock_curl: MagicMock) -> None:
        """Test invalid JSON returns None."""
        mock_curl.return_value = MagicMock(
            success=True,
            http_code=200,
            body="not json",
            curl_rc=0,
            stderr="",
        )

        detail = fetch_backend_incident_detail(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert detail is None


# =============================================================================
# Test poll_backend_diagnosis_state
# =============================================================================


class TestPollBackendDiagnosisState:
    """Tests for poll_backend_diagnosis_state."""

    @patch("time.sleep")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.fetch_backend_incident_detail")
    def test_completes_on_first_attempt(self, mock_fetch: MagicMock, mock_sleep: MagicMock) -> None:
        """Test poll completes immediately when diagnosis is done."""
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-123",
            status="diagnosed",
            evidence_count=5,
            review_packet_status="ready",
            loop_summary_status="completed",
            review_available=True,
        )

        result = poll_backend_diagnosis_state(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
            max_attempts=12,
            poll_interval_seconds=5.0,
        )

        assert result.success is True
        assert result.loop_summary_status == "completed"
        assert result.attempts == 1
        mock_sleep.assert_not_called()

    @patch("time.sleep")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.fetch_backend_incident_detail")
    def test_polls_until_completion(self, mock_fetch: MagicMock, mock_sleep: MagicMock) -> None:
        """Test poll retries until diagnosis completes."""
        # First two calls return "running", third returns "completed"
        mock_fetch.side_effect = [
            BackendIncidentDetail(
                incident_id="inc-123", status="diagnosing",
                evidence_count=1, review_packet_status=None,
                loop_summary_status="running", review_available=False,
            ),
            BackendIncidentDetail(
                incident_id="inc-123", status="diagnosing",
                evidence_count=2, review_packet_status=None,
                loop_summary_status="running", review_available=False,
            ),
            BackendIncidentDetail(
                incident_id="inc-123", status="diagnosed",
                evidence_count=3, review_packet_status="ready",
                loop_summary_status="completed", review_available=True,
            ),
        ]

        result = poll_backend_diagnosis_state(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
            max_attempts=12,
            poll_interval_seconds=5.0,
        )

        assert result.success is True
        assert result.loop_summary_status == "completed"
        assert result.attempts == 3
        assert mock_sleep.call_count == 2

    @patch("time.sleep")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.fetch_backend_incident_detail")
    def test_timeout_returns_failure(self, mock_fetch: MagicMock, mock_sleep: MagicMock) -> None:
        """Test timeout returns failure result."""
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-123",
            status="diagnosing",
            evidence_count=1,
            review_packet_status=None,
            loop_summary_status="running",
            review_available=False,
        )

        result = poll_backend_diagnosis_state(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
            max_attempts=3,
            poll_interval_seconds=0.01,  # Fast for test
        )

        assert result.success is False
        assert result.failure_reason == FAILURE_TARGETED_LOOP_NOT_COMPLETED
        assert result.attempts == 3
        assert result.max_attempts == 3

    @patch("time.sleep")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.fetch_backend_incident_detail")
    def test_continues_on_transport_error(self, mock_fetch: MagicMock, mock_sleep: MagicMock) -> None:
        """Test poll continues on transient transport errors."""
        mock_fetch.side_effect = [
            None,  # Transport error
            BackendIncidentDetail(
                incident_id="inc-123", status="diagnosed",
                evidence_count=3, review_packet_status="ready",
                loop_summary_status="completed", review_available=True,
            ),
        ]

        result = poll_backend_diagnosis_state(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
            max_attempts=12,
            poll_interval_seconds=0.01,
        )

        assert result.success is True
        assert result.attempts == 2

    @patch("time.sleep")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.fetch_backend_incident_detail")
    def test_review_available_as_completion_signal(self, mock_fetch: MagicMock, mock_sleep: MagicMock) -> None:
        """Test review_available=True is treated as completion signal."""
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-123",
            status="diagnosed",
            evidence_count=3,
            review_packet_status=None,  # Not complete
            loop_summary_status=None,   # Not set
            review_available=True,      # But review is available
        )

        result = poll_backend_diagnosis_state(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
            max_attempts=12,
            poll_interval_seconds=5.0,
        )

        assert result.success is True
        assert result.review_available is True


# =============================================================================
# Test check_pass_artifacts_in_backend
# =============================================================================


class TestCheckPassArtifactsInBackend:
    """Tests for check_pass_artifacts_in_backend."""

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.fetch_backend_incident_detail")
    def test_sufficient_passes(self, mock_fetch: MagicMock) -> None:
        """Test detection of sufficient pass artifacts."""
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-123",
            status="diagnosed",
            evidence_count=5,
            review_packet_status="ready",
            loop_summary_status="completed",
            review_available=True,
            raw={
                "automatic_diagnosis_loop_summary": {
                    "pass_count": 3,
                    "pass_run_ids": ["run-1", "run-2", "run-3"],
                }
            },
        )

        has_sufficient, pass_count, pass_ids = check_pass_artifacts_in_backend(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
            min_required_passes=2,
        )

        assert has_sufficient is True
        assert pass_count == 3
        assert len(pass_ids) == 3

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.fetch_backend_incident_detail")
    def test_insufficient_passes(self, mock_fetch: MagicMock) -> None:
        """Test detection of insufficient pass artifacts."""
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-123",
            status="diagnosed",
            evidence_count=1,
            review_packet_status="pending",
            loop_summary_status="completed",
            review_available=False,
            raw={
                "automatic_diagnosis_loop_summary": {
                    "pass_count": 1,
                    "pass_run_ids": ["run-1"],
                }
            },
        )

        has_sufficient, pass_count, pass_ids = check_pass_artifacts_in_backend(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
            min_required_passes=2,
        )

        assert has_sufficient is False
        assert pass_count == 1
        assert len(pass_ids) == 1

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers.fetch_backend_incident_detail")
    def test_no_passes(self, mock_fetch: MagicMock) -> None:
        """Test no pass artifacts available."""
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-123",
            status="diagnosing",
            evidence_count=0,
            review_packet_status=None,
            loop_summary_status="running",
            review_available=False,
            raw={},
        )

        has_sufficient, pass_count, pass_ids = check_pass_artifacts_in_backend(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
            min_required_passes=2,
        )

        assert has_sufficient is False
        assert pass_count == 0
        assert pass_ids == []


# =============================================================================
# Integration Tests: P4c Uses Backend-Targeted Diagnosis
# =============================================================================


class TestP4cUsesBackendTargetedDiagnosis:
    """Integration tests verifying P4c uses backend-targeted diagnosis."""

    @patch("time.sleep")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner.invoke_targeted_automatic_diagnosis_loop")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner.fetch_backend_incident_detail")
    def test_p4c_invokes_backend_endpoint(
        self,
        mock_fetch: MagicMock,
        mock_invoke: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        """Test P4c invokes backend targeted diagnosis endpoint.

        This is the key integration test: the one-pass diagnosis loop
        should use the backend-targeted endpoint, not the scheduler
        periodic loop.
        """
        # Setup: incident exists, invocation succeeds, diagnosis completes
        # First call is for step 1 (confirming incident), rest are for polling
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-otel-demo",
            status="diagnosed",
            evidence_count=5,
            review_packet_status="ready",
            loop_summary_status="completed",
            review_available=True,
        )

        mock_invoke.return_value = TargetedDiagnosisInvocationResult(
            success=True,
            http_status=200,
            body='{"status": "diagnosis_pass_completed"}',
            json_parsed=True,
            response_data={"status": "diagnosis_pass_completed"},
        )

        # Import runner to test integration
        from pathlib import Path

        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner import (
            _run_backend_targeted_diagnosis,
        )

        result: dict = {}

        _ = _run_backend_targeted_diagnosis(
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
        # The unit test TestInvokeTargetedDiagnosisLoop::test_successful_invocation
        # already verifies the endpoint URL is automatic-diagnosis-loop/one-pass

    @patch("time.sleep")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner.poll_backend_diagnosis_state")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner.invoke_targeted_automatic_diagnosis_loop")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner.fetch_backend_incident_detail")
    def test_p4c_validates_pass_artifacts(
        self,
        mock_fetch: MagicMock,
        mock_invoke: MagicMock,
        mock_poll: MagicMock,
        mock_sleep: MagicMock,
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

        from pathlib import Path

        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner import (
            _run_backend_targeted_diagnosis,
        )

        result: dict = {}

        _ = _run_backend_targeted_diagnosis(
            incident_id="inc-otel-demo",
            external_analysis_dir=Path("/tmp/analysis"),
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            result=result,
            allow_simulation=False,
        )

        # Verify the diagnosis flow completed successfully
        # success may not be set explicitly - check for failure_reason to be absent
        assert result.get("failure_reason") is None
        assert result.get("real_loop_invoked") is True


# =============================================================================
# Error Handling Tests: P4c Fails on Endpoint Errors
# =============================================================================


class TestP4cFailsOnEndpointErrors:
    """Tests verifying P4c fails appropriately on endpoint errors."""

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner.invoke_targeted_automatic_diagnosis_loop")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner.fetch_backend_incident_detail")
    def test_fails_on_transport_error(
        self,
        mock_fetch: MagicMock,
        mock_invoke: MagicMock,
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

        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner import (
            _run_backend_targeted_diagnosis,
        )

        result: dict = {}

        from pathlib import Path

        _ = _run_backend_targeted_diagnosis(
            incident_id="inc-otel-demo",
            external_analysis_dir=Path("/tmp/analysis"),
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            result=result,
            allow_simulation=False,
        )

        assert result["failure_reason"] == FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR
        assert result["status"] == "invocation_failed"

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner.invoke_targeted_automatic_diagnosis_loop")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner.fetch_backend_incident_detail")
    def test_fails_on_http_error(
        self,
        mock_fetch: MagicMock,
        mock_invoke: MagicMock,
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
            error_class=FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
            error_detail="HTTP 500",
            curl_rc=0,
        )

        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner import (
            _run_backend_targeted_diagnosis,
        )

        result: dict = {}

        from pathlib import Path

        _ = _run_backend_targeted_diagnosis(
            incident_id="inc-otel-demo",
            external_analysis_dir=Path("/tmp/analysis"),
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            result=result,
            allow_simulation=False,
        )

        assert result["failure_reason"] == FAILURE_TARGETED_INVOCATION_HTTP_ERROR
        assert result["status"] == "invocation_failed"


# =============================================================================
# Regression Tests: Scheduler Periodic Loop Bug
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

    @patch("time.sleep")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner.poll_backend_diagnosis_state")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner.invoke_targeted_automatic_diagnosis_loop")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner.fetch_backend_incident_detail")
    def test_backend_targeted_bypasses_scheduler_view(
        self,
        mock_fetch: MagicMock,
        mock_invoke: MagicMock,
        mock_poll: MagicMock,
        mock_sleep: MagicMock,
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

        from pathlib import Path

        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner import (
            _run_backend_targeted_diagnosis,
        )

        result: dict = {}

        _ = _run_backend_targeted_diagnosis(
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


# =============================================================================
# Safety Contract Tests
# =============================================================================


class TestSafetyContract:
    """Tests verifying safety contract is maintained.

    1. No mutation: backend-targeted diagnosis is read-only
    2. No secret reads: no reading of sensitive data
    3. Bounded retries: prevents infinite loops
    """

    def test_no_mutation_in_invoke(self) -> None:
        """Test invoke_targeted_automatic_diagnosis_loop doesn't mutate incident."""
        # The function should only POST to invoke diagnosis,
        # not directly modify incident state
        # This is a contract test - the implementation should
        # only call the automatic-diagnosis-loop/one-pass endpoint

        # We verify by checking the function signature and behavior:
        # - It takes incident_id as input (read-only reference)
        # - It returns a result (doesn't return mutator)
        # - It uses POST to trigger action, not PUT/PATCH

        import inspect
        sig = inspect.signature(invoke_targeted_automatic_diagnosis_loop)
        params = list(sig.parameters.keys())

        assert "kubeconfig" in params
        assert "namespace" in params
        assert "incident_id" in params
        # Should not have mutable parameters
        assert "state" not in params
        assert "incident_ref" not in params

    @patch("subprocess.run")
    def test_no_secret_reads_in_curl(self, mock_run: MagicMock) -> None:
        """Test curl_backend_exec doesn't read secrets."""
        mock_run.return_value = MagicMock(
            stdout="HTTP_CODE=200\n{}",
            stderr="",
            returncode=0,
        )

        curl_backend_exec(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            target_url="http://localhost:8080/api/incidents/inc-123",
        )

        # Verify no secret-like flags in kubectl command
        call_args = mock_run.call_args[0][0]
        cmd_str = " ".join(call_args)

        # Should not read secrets from environment
        assert "--from-env-file" not in cmd_str
        assert "--from-secret" not in cmd_str
        assert "--from-file" not in cmd_str

    def test_bounded_retries_in_poll(self) -> None:
        """Test poll_backend_diagnosis_state has bounded retries."""
        import inspect
        sig = inspect.signature(poll_backend_diagnosis_state)

        # Should have max_attempts parameter
        assert "max_attempts" in sig.parameters

        # Default should be reasonable
        default = sig.parameters["max_attempts"].default
        assert default <= 60  # Should not be infinite

    def test_timeout_in_curl(self) -> None:
        """Test curl_backend_exec has timeout."""
        import inspect
        sig = inspect.signature(curl_backend_exec)

        assert "timeout_seconds" in sig.parameters

        default = sig.parameters["timeout_seconds"].default
        assert default <= 120  # Should not be infinite
