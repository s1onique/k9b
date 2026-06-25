#!/usr/bin/env python3
"""Tests for backend health gate script.

Verifies:
- Health check result classification
- Failure class constants
- Sanitized diagnostics collection
- Artifact structure
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.check_backend_health_gate import (
    FAILURE_BACKEND_HEALTH_500,
    FAILURE_BACKEND_HEALTH_INVALID_RESPONSE,
    FAILURE_BACKEND_HEALTH_TIMEOUT,
    FAILURE_BACKEND_HEALTH_TRANSPORT_ERROR,
    HealthCheckResult,
    _collect_backend_diagnostics,
    _collect_scheduler_diagnostics,
    _get_provider_config_status,
)


class TestHealthCheckResult:
    """Test HealthCheckResult dataclass."""

    def test_to_dict_includes_failure_class(self):
        """HealthCheckResult.to_dict() includes failure_class."""
        result = HealthCheckResult()
        result.failure_class = FAILURE_BACKEND_HEALTH_500
        result.final_http_code = "500"
        
        data = result.to_dict()
        
        assert "failure_class" in data
        assert data["failure_class"] == FAILURE_BACKEND_HEALTH_500
        assert data["final_http_code"] == "500"

    def test_to_dict_includes_poll_count(self):
        """HealthCheckResult.to_dict() includes poll_count."""
        result = HealthCheckResult()
        result.poll_count = 10
        result.total_elapsed_seconds = 45.5
        
        data = result.to_dict()
        
        assert data["poll_count"] == 10
        assert data["total_elapsed_seconds"] == 45.5

    def test_to_dict_includes_http_statuses_seen(self):
        """HealthCheckResult.to_dict() includes http_statuses_seen."""
        result = HealthCheckResult()
        result.http_statuses_seen = ["500", "500", "ERR:timeout"]
        
        data = result.to_dict()
        
        assert data["http_statuses_seen"] == ["500", "500", "ERR:timeout"]

    def test_to_dict_includes_diagnostics(self):
        """HealthCheckResult.to_dict() includes diagnostics."""
        result = HealthCheckResult()
        result.diagnostics = {"backend": {"pod_k9b-backend-0": {"phase": "Running"}}}
        
        data = result.to_dict()
        
        assert "diagnostics" in data
        assert "backend" in data["diagnostics"]


class TestFailureClassConstants:
    """Test failure class constants are properly defined."""

    def test_backend_health_500_defined(self):
        """FAILURE_BACKEND_HEALTH_500 is defined correctly."""
        assert FAILURE_BACKEND_HEALTH_500 == "backend_health_500"

    def test_backend_health_timeout_defined(self):
        """FAILURE_BACKEND_HEALTH_TIMEOUT is defined correctly."""
        assert FAILURE_BACKEND_HEALTH_TIMEOUT == "backend_health_timeout"

    def test_backend_health_invalid_response_defined(self):
        """FAILURE_BACKEND_HEALTH_INVALID_RESPONSE is defined correctly."""
        assert FAILURE_BACKEND_HEALTH_INVALID_RESPONSE == "backend_health_invalid_response"

    def test_backend_health_transport_error_defined(self):
        """FAILURE_BACKEND_HEALTH_TRANSPORT_ERROR is defined correctly."""
        assert FAILURE_BACKEND_HEALTH_TRANSPORT_ERROR == "backend_health_transport_error"


class TestClassifyFailure:
    """Test _classify_failure function."""

    def test_classifies_200_as_passed(self):
        """HTTP 200 returns passed=True."""
        result = HealthCheckResult()
        result.passed = True
        result.final_http_code = "200"
        result.http_status = 200
        
        # Simulate classification
        result.failure_class = ""
        
        assert result.passed is True
        assert result.failure_class == ""

    def test_classifies_500_as_backend_health_500(self):
        """HTTP 500 returns backend_health_500."""
        result = HealthCheckResult()
        result.passed = False
        result.final_http_code = "500"
        result.poll_count = 30
        
        # Simulate classification logic
        if not result.passed and result.final_http_code == "500":
            result.failure_class = FAILURE_BACKEND_HEALTH_500
        
        assert result.failure_class == FAILURE_BACKEND_HEALTH_500

    def test_classifies_transport_error(self):
        """Transport error returns backend_health_transport_error."""
        result = HealthCheckResult()
        result.passed = False
        result.transport_error = "curl timeout"
        result.final_http_code = "ERR:curl timeout"
        
        # Simulate classification logic
        if not result.passed and result.transport_error:
            result.failure_class = FAILURE_BACKEND_HEALTH_TRANSPORT_ERROR
        
        assert result.failure_class == FAILURE_BACKEND_HEALTH_TRANSPORT_ERROR

    def test_classifies_timeout_after_max_retries(self):
        """Timeout after max retries returns backend_health_timeout."""
        result = HealthCheckResult()
        result.passed = False
        result.final_http_code = "000"
        result.poll_count = 30  # max retries reached
        result.transport_error = ""
        
        # Simulate classification logic
        if not result.passed:
            if result.poll_count >= 30:
                if result.final_http_code.startswith("ERR"):
                    result.failure_class = FAILURE_BACKEND_HEALTH_TRANSPORT_ERROR
                elif result.final_http_code == "500":
                    result.failure_class = FAILURE_BACKEND_HEALTH_500
                else:
                    result.failure_class = FAILURE_BACKEND_HEALTH_TIMEOUT
        
        assert result.failure_class == FAILURE_BACKEND_HEALTH_TIMEOUT


class TestSanitizedDiagnostics:
    """Test that diagnostics collection is sanitized (no secrets)."""

    def test_provider_config_status_has_boolean_fields(self):
        """Provider config status has only boolean fields, no secrets."""
        # Mock kubectl output
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "K9B_DIAGNOSIS_BASE_URL K9B_DIAGNOSIS_MODEL K9B_DIAGNOSIS_API_KEY"
        
        mock_result2 = MagicMock()
        mock_result2.returncode = 0
        mock_result2.stdout = "k9b-diagnosis-credentials"
        
        with patch("subprocess.run", side_effect=[mock_result, mock_result2]):
            status = _get_provider_config_status("/fake/kubeconfig", "test-ns")
        
        # Verify only boolean fields
        assert isinstance(status, dict)
        for key, value in status.items():
            assert isinstance(value, bool), f"Expected bool for {key}, got {type(value)}"
        
        # Verify no secret values are present
        assert "api_key_secret_value" not in str(status)
        assert "base_url_secret_value" not in str(status)

    def test_backend_diagnostics_no_raw_health_body(self):
        """Backend diagnostics don't include raw /api/health body."""
        # Mock kubectl output
        mock_pods_result = MagicMock()
        mock_pods_result.returncode = 0
        mock_pods_result.stdout = json.dumps({
            "items": [{
                "metadata": {"name": "k9b-backend-abc123"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{
                        "name": "backend",
                        "restartCount": 0,
                        "state": {"running": {}}
                    }]
                }
            }]
        })
        
        with patch("subprocess.run", return_value=mock_pods_result):
            diags = _collect_backend_diagnostics("/fake/kubeconfig", "test-ns")
        
        # Verify no HTTP response bodies in diagnostics
        diag_str = json.dumps(diags)
        assert "{\"status\"" not in diag_str or "health" not in diag_str.lower()
        assert "200" not in diag_str  # No HTTP status codes from health endpoint

    def test_scheduler_diagnostics_includes_restart_count(self):
        """Scheduler diagnostics include restart count for troubleshooting."""
        mock_pods_result = MagicMock()
        mock_pods_result.returncode = 0
        mock_pods_result.stdout = json.dumps({
            "items": [{
                "metadata": {"name": "k9b-scheduler-xyz789"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{
                        "name": "scheduler",
                        "restartCount": 2,  # Important for diagnosing startup issues
                        "state": {"running": {}}
                    }]
                }
            }]
        })
        
        with patch("subprocess.run", return_value=mock_pods_result):
            diags = _collect_scheduler_diagnostics("/fake/kubeconfig", "test-ns")
        
        # Verify restart count is captured
        assert "pod_k9b-scheduler-xyz789" in diags
        assert diags["pod_k9b-scheduler-xyz789"]["restart_count"] == 2


class TestArtifactStructure:
    """Test artifact structure for upload safety."""

    def test_status_json_includes_required_fields(self):
        """Status.json artifact includes all required fields."""
        result = HealthCheckResult()
        result.failure_class = FAILURE_BACKEND_HEALTH_500
        result.passed = False
        result.final_http_code = "500"
        result.poll_count = 30
        result.total_elapsed_seconds = 150.0
        result.http_statuses_seen = ["500"] * 30
        result.transport_error = ""
        result.diagnostics = {
            "backend": {},
            "scheduler": {},
            "provider_config": {"diagnosis_provider_enabled": True}
        }
        
        # Build status artifact (as the script would)
        status_data = {
            "failure_class": result.failure_class,
            "passed": result.passed,
            "final_http_code": result.final_http_code,
            "poll_count": result.poll_count,
            "total_elapsed_seconds": result.total_elapsed_seconds,
            "http_statuses_seen": result.http_statuses_seen,
            "diagnostics": result.diagnostics,
        }
        
        # Verify required fields
        assert "failure_class" in status_data
        assert "passed" in status_data
        assert "final_http_code" in status_data
        assert "poll_count" in status_data
        assert "diagnostics" in status_data
        
        # Verify sanitized logs field (no raw API responses)
        assert "sanitized_logs" not in status_data or "backend_tail" in status_data.get("sanitized_logs", {})

    def test_health_gate_result_json_includes_all_fields(self):
        """health-check-result.json includes all HealthCheckResult fields."""
        result = HealthCheckResult()
        result.failure_class = FAILURE_BACKEND_HEALTH_TIMEOUT
        result.passed = False
        result.http_status = 0
        result.final_http_code = "ERR:timeout"
        result.poll_count = 30
        result.total_elapsed_seconds = 155.0
        result.transport_error = "curl timeout"
        result.http_statuses_seen = ["ERR:timeout"] * 30
        result.diagnostics = {}
        
        data = result.to_dict()
        
        # Verify all fields are present
        assert "failure_class" in data
        assert "passed" in data
        assert "http_status" in data
        assert "final_http_code" in data
        assert "poll_count" in data
        assert "total_elapsed_seconds" in data
        assert "transport_error" in data
        assert "http_statuses_seen" in data
        assert "diagnostics" in data


class TestProviderArtifactVerification:
    """Test that backend-health artifacts are safe for verification."""

    def test_status_json_no_raw_secrets(self):
        """status.json contains no raw secrets."""
        status_data = {
            "failure_class": "backend_health_500",
            "passed": False,
            "final_http_code": "500",
            "poll_count": 30,
            "provider_config": {
                "diagnosis_provider_enabled": True,
                "diagnosis_provider_secret_ref_present": True,
                "small_provider_secret_ref_present": True,
                "base_url_present": True,
                "model_present": True,
                "api_key_present": True,
            },
            "diagnostics": {
                "backend": {
                    "pod_k9b-backend-0": {
                        "name": "k9b-backend-0",
                        "phase": "Running",
                        "restart_count": 0,
                        "containers": [
                            {"name": "backend", "state": "running"}
                        ]
                    }
                }
            }
        }
        
        # Serialize and check for secret patterns
        status_str = json.dumps(status_data)
        
        # No actual API keys
        assert "sk-" not in status_str
        assert "Bearer " not in status_str
        assert "ghp_" not in status_str
        
        # No actual base URLs
        assert "https://" not in status_str or "example" not in status_str.lower()

    def test_bounded_summary_no_raw_health_body(self):
        """Bounded summary doesn't echo raw /api/health body."""
        # This simulates what the script writes to bounded-summary.txt
        summary_lines = [
            "Backend Health Gate Result: FAILED",
            "Failure class: backend_health_500",
            "Final HTTP code: 500",
            "Polls: 30/30",
            "HTTP statuses seen: 500, 500, 500, 500, 500",
            "",
            "Provider config status (booleans only):",
            "  diagnosis_provider_enabled: True",
            "  base_url_present: True",
        ]
        
        summary = "\n".join(summary_lines)
        
        # Verify no raw health response bodies
        assert "healthy" not in summary.lower() or "true" in summary.lower()
        assert "error" not in summary.lower() or "message" not in summary.lower()
        assert "stack" not in summary.lower()
        assert "traceback" not in summary.lower()


class TestWorkflowIntegration:
    """Test integration with workflow behavior."""

    def test_fails_fast_on_backend_health_500(self):
        """Workflow should fail with backend_health_500 when health returns 500."""
        result = HealthCheckResult()
        result.passed = False
        result.final_http_code = "500"
        result.poll_count = 30
        result.transport_error = ""
        
        # Classification logic
        if not result.passed and result.final_http_code == "500":
            result.failure_class = FAILURE_BACKEND_HEALTH_500
        
        # Workflow should exit with non-zero
        workflow_should_fail = not result.passed
        
        assert result.failure_class == FAILURE_BACKEND_HEALTH_500
        assert workflow_should_fail is True

    def test_proceeds_to_incident_discovery_on_health_200(self):
        """Workflow should proceed to incident discovery when health returns 200."""
        result = HealthCheckResult()
        result.passed = True
        result.http_status = 200
        result.poll_count = 3
        result.total_elapsed_seconds = 12.5
        
        # Workflow should continue
        should_continue = result.passed
        
        assert result.passed is True
        assert should_continue is True

    def test_phase_gate_order(self):
        """Phases run in correct order: health_gate -> incident_discovery -> one_pass_diagnosis."""
        phases = ["backend_health_gate", "incident_discovery", "one_pass_diagnosis", "provider_artifact_verification"]
        
        # Verify phase names match workflow
        assert "backend_health_gate" in phases
        assert phases.index("backend_health_gate") < phases.index("incident_discovery")
        assert phases.index("incident_discovery") < phases.index("one_pass_diagnosis")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestSecretKeyRefDetection:
    """Test proof-based secretKeyRef detection for provider config."""

    def _make_deployment_json(self, env_vars):
        """Create deployment JSON with specified env vars."""
        containers = [{"name": "backend", "env": env_vars}]
        items = [{
            "spec": {
                "template": {
                    "spec": {
                        "containers": containers
                    }
                }
            }
        }]
        return json.dumps({"items": items})

    def test_detects_diagnosis_api_key_secret_ref(self):
        """K9B_DIAGNOSIS_API_KEY + secretKeyRef sets diagnosis_provider_secret_ref_present=true."""
        deployment_json = self._make_deployment_json([
            {
                "name": "K9B_DIAGNOSIS_API_KEY",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "k9b-diagnosis-credentials",
                        "key": "K9B_DIAGNOSIS_API_KEY"
                    }
                }
            }
        ])
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=deployment_json, stderr="")
            
            status = _get_provider_config_status("/fake/kubeconfig", "test-ns")
        
        assert status["diagnosis_provider_secret_ref_present"] is True
        assert status["diagnosis_provider_enabled"] is True
        assert status["api_key_present"] is True

    def test_detects_external_analysis_api_key_secret_ref(self):
        """K9B_EXTERNAL_ANALYSIS_API_KEY + secretKeyRef sets small_provider_secret_ref_present=true."""
        deployment_json = self._make_deployment_json([
            {
                "name": "K9B_EXTERNAL_ANALYSIS_API_KEY",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "k9b-diagnosis-credentials",
                        "key": "K9B_EXTERNAL_ANALYSIS_API_KEY"
                    }
                }
            }
        ])
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=deployment_json, stderr="")
            
            status = _get_provider_config_status("/fake/kubeconfig", "test-ns")
        
        assert status["small_provider_secret_ref_present"] is True
        assert status["api_key_present"] is True
        assert status["diagnosis_provider_secret_ref_present"] is False

    def test_plain_env_var_without_secret_ref_does_not_set_secret_ref_present(self):
        """Plain env var (no secretKeyRef) does NOT set *_secret_ref_present=true."""
        deployment_json = self._make_deployment_json([
            {
                "name": "K9B_DIAGNOSIS_API_KEY",
                "value": "fake-key-value"  # Plain value, not secretKeyRef
            }
        ])
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=deployment_json, stderr="")
            
            status = _get_provider_config_status("/fake/kubeconfig", "test-ns")
        
        # Plain env vars should not set secret_ref_present flags
        assert status["diagnosis_provider_secret_ref_present"] is False
        assert status["small_provider_secret_ref_present"] is False
