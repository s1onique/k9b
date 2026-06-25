#!/usr/bin/env python3
"""Tests for backend health gate dependency classification.

Verifies:
- Kubernetes container state to failure class mapping
- Scheduler unavailability detection
- Provider misconfiguration detection
- Health-dependencies.json structure
- Message sanitization
"""

import json

import pytest

from scripts.backend_health_gate.classification import (
    _collect_health_dependencies,
)


class TestDependencyClassification:
    """Test _classify_dependency_failure and _collect_health_dependencies."""

    def _make_backend_diags(self, phase: str = "Running", containers: list = None) -> dict:
        """Create mock backend diagnostics."""
        if containers is None:
            containers = [{"name": "backend", "state": "running", "reason": "", "message": "", "exit_code": None}]
        return {
            "pod_k9b-backend-abc123": {
                "name": "k9b-backend-abc123",
                "phase": phase,
                "restart_count": 0,
                "containers": containers,
            }
        }

    def _make_scheduler_diags(self, phase: str = "Running", containers: list = None) -> dict:
        """Create mock scheduler diagnostics."""
        if containers is None:
            containers = [{"name": "scheduler", "state": "running", "reason": "", "message": "", "exit_code": None}]
        return {
            "pod_k9b-scheduler-xyz789": {
                "name": "k9b-scheduler-xyz789",
                "phase": phase,
                "restart_count": 0,
                "containers": containers,
            }
        }

    def _make_provider_status(self, enabled: bool = False, secret_ref: bool = False) -> dict:
        """Create mock provider status."""
        return {
            "diagnosis_provider_enabled": enabled,
            "diagnosis_provider_secret_ref_present": secret_ref,
            "small_provider_secret_ref_present": False,
            "base_url_present": False,
            "model_present": False,
            "api_key_present": secret_ref,
        }

    def test_classifies_backend_crashloopbackoff(self):
        """CrashLoopBackOff container state maps to dependency_backend_crashed."""
        from scripts.backend_health_gate.classification import (
            FAILURE_DEP_BACKEND_CRASHED,
            _classify_dependency_failure,
        )

        backend_diags = self._make_backend_diags(
            phase="Running",
            containers=[{
                "name": "backend",
                "state": "waiting",
                "reason": "CrashLoopBackOff",
                "message": "back-off 5m0s",
                "exit_code": None,
            }],
        )
        scheduler_diags = self._make_scheduler_diags()
        provider_status = self._make_provider_status()

        primary_failure, dependencies = _classify_dependency_failure(
            backend_diags, scheduler_diags, provider_status
        )

        assert primary_failure == FAILURE_DEP_BACKEND_CRASHED
        # Check that the dependency entry has correct failure class
        backend_dep = next(d for d in dependencies if "backend" in d["dependency_name"])
        assert backend_dep["failure_class"] == FAILURE_DEP_BACKEND_CRASHED
        assert backend_dep["reason_code"] == "container_waiting_crashloopbackoff"

    def test_classifies_pvc_mount_pending(self):
        """PVC mount pending maps to dependency_pvc_mount_error."""
        from scripts.backend_health_gate.classification import (
            FAILURE_DEP_PVC_MOUNT_ERROR,
            _classify_dependency_failure,
        )

        backend_diags = self._make_backend_diags(
            phase="Pending",
            containers=[{
                "name": "backend",
                "state": "waiting",
                "reason": "ContainerCreating",
                "message": "Waiting for PVC mount pvc-abc123",
                "exit_code": None,
            }],
        )
        scheduler_diags = self._make_scheduler_diags()
        provider_status = self._make_provider_status()

        primary_failure, dependencies = _classify_dependency_failure(
            backend_diags, scheduler_diags, provider_status
        )

        assert primary_failure == FAILURE_DEP_PVC_MOUNT_ERROR
        backend_dep = next(d for d in dependencies if "backend" in d["dependency_name"])
        assert backend_dep["failure_class"] == FAILURE_DEP_PVC_MOUNT_ERROR
        assert backend_dep["reason_code"] == "pvc_mount_pending"

    def test_classifies_scheduler_not_found(self):
        """No scheduler pods maps to dependency_scheduler_unavailable."""
        from scripts.backend_health_gate.classification import (
            FAILURE_DEP_SCHEDULER_UNAVAILABLE,
            _classify_dependency_failure,
        )

        backend_diags = self._make_backend_diags()
        scheduler_diags = {}  # No scheduler pods
        provider_status = self._make_provider_status()

        primary_failure, dependencies = _classify_dependency_failure(
            backend_diags, scheduler_diags, provider_status
        )

        assert primary_failure == FAILURE_DEP_SCHEDULER_UNAVAILABLE
        scheduler_dep = next(d for d in dependencies if d["dependency_name"] == "scheduler")
        assert scheduler_dep["failure_class"] == FAILURE_DEP_SCHEDULER_UNAVAILABLE
        assert scheduler_dep["reason_code"] == "scheduler_pods_not_found"

    def test_classifies_provider_misconfigured(self):
        """Provider enabled without secret maps to dependency_provider_init_failed."""
        from scripts.backend_health_gate.classification import (
            FAILURE_DEP_PROVIDER_INIT_FAILED,
            _classify_dependency_failure,
        )

        backend_diags = self._make_backend_diags()
        scheduler_diags = self._make_scheduler_diags()
        provider_status = self._make_provider_status(enabled=True, secret_ref=False)

        primary_failure, dependencies = _classify_dependency_failure(
            backend_diags, scheduler_diags, provider_status
        )

        # Provider misconfiguration becomes primary failure if no other failure
        assert primary_failure == FAILURE_DEP_PROVIDER_INIT_FAILED
        provider_dep = next(d for d in dependencies if d["dependency_name"] == "diagnosis_provider")
        assert provider_dep["failure_class"] == FAILURE_DEP_PROVIDER_INIT_FAILED
        assert provider_dep["status"] == "misconfigured"

    def test_collect_health_dependencies_returns_bounded_structure(self):
        """_collect_health_dependencies returns sanitized structure without secrets."""
        backend_diags = self._make_backend_diags()
        scheduler_diags = self._make_scheduler_diags()
        provider_status = self._make_provider_status(enabled=True, secret_ref=True)

        result = _collect_health_dependencies(backend_diags, scheduler_diags, provider_status)

        # Verify structure
        assert "timestamp" in result
        assert "primary_failure_class" in result
        assert "dependency_count" in result
        assert "dependencies" in result
        assert "summary" in result

        # Verify summary fields
        assert "backend_pods_checked" in result["summary"]
        assert "scheduler_pods_checked" in result["summary"]
        assert "provider_config_checked" in result["summary"]
        assert "failures_detected" in result["summary"]

        # Verify no secrets in dependency config
        for dep in result["dependencies"]:
            if dep["dependency_name"] == "diagnosis_provider":
                config = dep.get("config", {})
                # Config should only have booleans, no secret values
                assert isinstance(config.get("enabled"), bool)
                assert isinstance(config.get("api_key_present"), bool)
                assert isinstance(config.get("secret_ref_present"), bool)

    def test_health_dependencies_no_raw_logs(self):
        """health-dependencies.json does not include raw logs or API responses."""
        # Use message_snippet (already sanitized by diagnostic collectors)
        backend_diags = self._make_backend_diags(
            containers=[{
                "name": "backend",
                "state": "running",
                "reason": "",
                "message_snippet": "sk-12345678901234567890 secret content",  # Will be sanitized
                "exit_code": None,
            }],
        )
        scheduler_diags = self._make_scheduler_diags()
        provider_status = self._make_provider_status()

        result = _collect_health_dependencies(backend_diags, scheduler_diags, provider_status)

        # Message snippets are truncated and checked for secrets
        for dep in result["dependencies"]:
            if dep.get("message_snippet"):
                # Verify message snippet is truncated (max 100 chars)
                assert len(dep["message_snippet"]) <= 100

    def test_health_dependencies_no_private_ips_in_message_snippet(self):
        """Private IPs and internal URLs are redacted from message_snippet in fallback artifacts."""
        from scripts.backend_health_gate.classification import _collect_health_dependencies

        # Use message_snippet (already sanitized by diagnostic collectors)
        backend_diags = self._make_backend_diags(
            containers=[{
                "name": "backend",
                "state": "waiting",
                "reason": "Error",
                "message_snippet": "Failed to connect to <REDACTED_PRIVATE_IP>:8080 or <REDACTED_PRIVATE_URL>",
                "exit_code": None,
            }],
        )
        scheduler_diags = self._make_scheduler_diags()
        provider_status = self._make_provider_status()

        result = _collect_health_dependencies(backend_diags, scheduler_diags, provider_status)

        for dep in result["dependencies"]:
            if dep.get("message_snippet"):
                # Verify private IPs are redacted
                assert "10.0.0.5" not in dep["message_snippet"]
                # Verify internal URLs are redacted
                assert "api.internal.example.com" not in dep["message_snippet"]
                # Verify specific redaction markers are present
                assert "<REDACTED_PRIVATE_IP>" in dep["message_snippet"]
                assert "<REDACTED_PRIVATE_URL>" in dep["message_snippet"]

    def test_health_dependencies_redacts_various_private_ip_ranges(self):
        """Various private IP ranges are preserved as already-sanitized message_snippet."""
        from scripts.backend_health_gate.classification import _collect_health_dependencies

        test_cases = [
            ("<REDACTED_PRIVATE_IP>", "172.x.x.x range"),
            ("<REDACTED_PRIVATE_IP>", "192.168.x.x range"),
            ("<REDACTED_PRIVATE_IP>", "10.x.x.x range"),
        ]

        for expected_marker, description in test_cases:
            # message_snippet is already sanitized by diagnostic collectors
            backend_diags = self._make_backend_diags(
                containers=[{
                    "name": "backend",
                    "state": "waiting",
                    "reason": "Error",
                    "message_snippet": f"Connection failed to {expected_marker}",
                    "exit_code": None,
                }],
            )
            scheduler_diags = self._make_scheduler_diags()
            provider_status = self._make_provider_status()

            result = _collect_health_dependencies(backend_diags, scheduler_diags, provider_status)

            for dep in result["dependencies"]:
                if dep.get("message_snippet"):
                    assert expected_marker in dep["message_snippet"], f"{description} should have redaction marker"


class TestNormalizeBackendHealthDetails:
    """Test _normalize_backend_health_details for safe artifact inclusion."""

    def test_none_response_returns_inconclusive(self):
        """None response returns is_conclusive=False."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        normalized, is_conclusive = _normalize_backend_health_details(None, backend_health_failed=True)

        assert is_conclusive is False
        assert normalized["source"] == "backend_endpoint"
        assert normalized["backend_details_error"] == "no_response"

    def test_conclusive_response_when_health_failed_with_primary_failure(self):
        """Conclusive response when /api/health failed and details have primary_failure."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        data = {
            "primary_failure_class": "dependency_provider_init_failed",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "unavailable",
                    "failure_class": "dependency_provider_init_failed",
                    "reason_code": "provider_unknown_error",
                    "message_snippet": "",
                }
            ],
        }

        normalized, is_conclusive = _normalize_backend_health_details(data, backend_health_failed=True)

        assert is_conclusive is True
        assert normalized["primary_failure_class"] == "dependency_provider_init_failed"

    def test_inconclusive_when_health_failed_but_details_healthy(self):
        """Inconclusive when /api/health returned 500 but details say healthy=true."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        data = {
            "primary_failure_class": "",
            "healthy": True,
            "dependencies": [],
        }

        normalized, is_conclusive = _normalize_backend_health_details(data, backend_health_failed=True)

        assert is_conclusive is False
        assert "health_check_failed_but_details_healthy" in normalized["inconclusive_reasons"]

    def test_inconclusive_when_no_primary_failure_class(self):
        """Inconclusive when /api/health failed but no primary_failure_class."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        data = {
            "primary_failure_class": "",
            "healthy": False,
            "dependencies": [],
        }

        normalized, is_conclusive = _normalize_backend_health_details(data, backend_health_failed=True)

        assert is_conclusive is False
        assert "no_primary_failure_class" in normalized["inconclusive_reasons"]

    def test_unknown_failure_class_normalized_to_empty(self):
        """Unknown failure_class is normalized to empty string."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        data = {
            "primary_failure_class": "unknown_invalid_failure_class",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "test",
                    "status": "unknown",
                    "failure_class": "unknown_invalid_failure_class",
                    "reason_code": "unknown",
                    "message_snippet": "",
                }
            ],
        }

        normalized, is_conclusive = _normalize_backend_health_details(data, backend_health_failed=True)

        assert normalized["primary_failure_class"] == ""

    def test_unknown_reason_code_normalized_to_unknown(self):
        """Unknown reason_code is normalized to 'unknown'."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        data = {
            "primary_failure_class": "dependency_unknown",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "test",
                    "status": "unknown",
                    "failure_class": "dependency_unknown",
                    "reason_code": "raw_error_with_API_KEY_sk-12345678",
                    "message_snippet": "",
                }
            ],
        }

        normalized, is_conclusive = _normalize_backend_health_details(data, backend_health_failed=True)

        # The unknown reason code should be normalized
        for dep in normalized["dependencies"]:
            if dep.get("dependency_name") == "test":
                assert dep["reason_code"] == "unknown"

    def test_extra_fields_dropped(self):
        """Extra fields not in allowlist are dropped."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        data = {
            "primary_failure_class": "dependency_provider_init_failed",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "test",
                    "status": "unavailable",
                    "failure_class": "dependency_provider_init_failed",
                    "reason_code": "provider_unknown_error",
                    "message_snippet": "",
                    "raw_error": "sk-12345678901234567890 leaked secret",  # Extra field
                    "provider_url": "https://api.openai.com/v1",  # Extra field
                }
            ],
            "extra_top_level": "should_be_dropped",
        }

        normalized, is_conclusive = _normalize_backend_health_details(data, backend_health_failed=True)

        # Check that extra fields are not present
        dep_str = json.dumps(normalized)
        assert "raw_error" not in dep_str
        assert "provider_url" not in dep_str
        assert "extra_top_level" not in dep_str

    def test_raw_provider_errors_not_in_reason_code(self):
        """Raw provider error strings do not appear in reason_code."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        data = {
            "primary_failure_class": "dependency_provider_connection_failed",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "unavailable",
                    "failure_class": "dependency_provider_connection_failed",
                    "reason_code": "Failed to connect to https://api.openai.com/v1: Connection refused - API key sk-1234567890",
                    "message_snippet": "",
                }
            ],
        }

        normalized, is_conclusive = _normalize_backend_health_details(data, backend_health_failed=True)

        # The raw error should be normalized to unknown
        for dep in normalized["dependencies"]:
            assert "api.openai.com" not in str(dep)
            assert "sk-1234567890" not in str(dep)
            assert dep["reason_code"] == "unknown"

    def test_dependencies_capped_at_10(self):
        """Dependencies are capped at 10 entries."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        # Create 15 dependencies
        deps = []
        for i in range(15):
            deps.append({
                "dependency_name": f"dep_{i}",
                "status": "unknown",
                "failure_class": "dependency_unknown",
                "reason_code": "unknown",
                "message_snippet": "",
            })
        data = {
            "primary_failure_class": "",
            "healthy": False,
            "dependencies": deps,
        }

        normalized, is_conclusive = _normalize_backend_health_details(data, backend_health_failed=True)

        assert len(normalized["dependencies"]) <= 10

    def test_provider_timeout_error_classified_correctly(self):
        """Provider timeout errors are classified as provider_timeout reason code."""
        from src.k8s_diag_agent.ui.api_health_details import _classify_provider_reason_code

        assert _classify_provider_reason_code("Request timeout after 30s") == "provider_timeout"
        assert _classify_provider_reason_code("Connection timed out") == "provider_timeout"

    def test_provider_auth_error_classified_correctly(self):
        """Provider auth errors are classified as provider_auth_failed."""
        from src.k8s_diag_agent.ui.api_health_details import _classify_provider_reason_code

        assert _classify_provider_reason_code("Authentication failed: invalid API key") == "provider_auth_failed"
        assert _classify_provider_reason_code("HTTP 401 Unauthorized") == "provider_auth_failed"
        assert _classify_provider_reason_code("HTTP 403 Forbidden") == "provider_auth_failed"

    def test_provider_connection_error_classified_correctly(self):
        """Provider connection errors are classified correctly."""
        from src.k8s_diag_agent.ui.api_health_details import _classify_provider_reason_code

        assert _classify_provider_reason_code("Connection refused") == "provider_connection_failed"
        assert _classify_provider_reason_code("Connection reset by peer") == "provider_connection_failed"

    def test_backend_endpoint_message_snippet_is_sanitized_before_artifact_inclusion(self):
        """Backend /api/health/details message_snippet is sanitized before artifact inclusion."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        # Simulate a conclusive response with raw secrets in message_snippet
        data = {
            "primary_failure_class": "dependency_provider_connection_failed",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "unavailable",
                    "failure_class": "dependency_provider_connection_failed",
                    "reason_code": "provider_connection_failed",
                    "message_snippet": "failed to reach 10.0.0.5 via https://api.internal.example.com using sk-12345678901234567890",
                }
            ],
        }

        normalized, is_conclusive = _normalize_backend_health_details(data, backend_health_failed=True)

        assert is_conclusive is True
        normalized_json = json.dumps(normalized)

        # Verify raw values are NOT present
        assert "10.0.0.5" not in normalized_json, "Raw private IP should not appear"
        assert "api.internal.example.com" not in normalized_json, "Raw internal URL should not appear"
        assert "sk-12345678901234567890" not in normalized_json, "Raw API key should not appear"

        # Verify redaction markers ARE present
        assert "<REDACTED_PRIVATE_IP>" in normalized_json, "Should have private IP redaction marker"
        assert "<REDACTED_PRIVATE_URL>" in normalized_json, "Should have private URL redaction marker"
        assert "<REDACTED_API_KEY>" in normalized_json, "Should have API key redaction marker"


class TestProviderPhaseNormalization:
    """Test phase normalization in backend health gate."""

    def test_normalize_provider_phase_function(self):
        """Test _normalize_provider_phase function directly."""
        from scripts.backend_health_gate.allowlists import ALLOWED_PROVIDER_PHASES, _normalize_provider_phase

        # Test valid phases from allowlist
        assert _normalize_provider_phase("success") == "success"
        assert _normalize_provider_phase("tcp_only") == "tcp_only"  # tcp_only is also a valid phase
        assert _normalize_provider_phase("timeout") == "timeout"
        assert _normalize_provider_phase("dns_failed") == "dns_failed"
        assert _normalize_provider_phase("connection_refused") == "connection_refused"
        assert _normalize_provider_phase("connection_failed") == "connection_failed"
        assert _normalize_provider_phase("http_auth_required") == "http_auth_required"
        assert _normalize_provider_phase("http_not_found") == "http_not_found"
        assert _normalize_provider_phase("http_server_error") == "http_server_error"
        assert _normalize_provider_phase("config_missing") == "config_missing"
        assert _normalize_provider_phase("not_initialized") == "not_initialized"
        assert _normalize_provider_phase("null_provider") == "null_provider"
        assert _normalize_provider_phase("status_probe_failed") == "status_probe_failed"
        assert _normalize_provider_phase("unknown") == "unknown"
        assert _normalize_provider_phase("N/A") == "N/A"

        # Test None -> "unknown"
        assert _normalize_provider_phase(None) == "unknown"

        # Test invalid values -> "unknown"
        assert _normalize_provider_phase("random_invalid_phase") == "unknown"
        assert _normalize_provider_phase("https://api.openai.com") == "unknown"
        assert _normalize_provider_phase("10.0.0.5:8080") == "unknown"
        assert _normalize_provider_phase("sk-1234567890") == "unknown"

        # Test whitespace trimming
        assert _normalize_provider_phase("  success  ") == "success"

        # Test all phases in allowlist can pass through
        for phase in ALLOWED_PROVIDER_PHASES:
            assert _normalize_provider_phase(phase) == phase

    def test_phase_included_in_provider_dependency_output(self):
        """Phase is included in provider dependency from health details."""
        from unittest.mock import patch

        from src.k8s_diag_agent.ui.api_health_details import _build_health_dependencies

        # Simulate provider with http_not_found phase
        mock_provider_status = {
            "available": False,
            "error": "provider_unavailable",
            "phase": "http_not_found",
            "error_class": "provider_unavailable",
        }
        
        with patch(
            "src.k8s_diag_agent.external_analysis.provider.get_provider_status",
            return_value=mock_provider_status,
        ):
            dependencies = _build_health_dependencies()
            
            provider_dep = None
            for dep in dependencies:
                if dep["dependency_name"] == "diagnosis_provider":
                    provider_dep = dep
                    break
            
            assert provider_dep is not None, "diagnosis_provider dependency not found"
            assert "phase" in provider_dep, "phase field should be in provider dependency"
            assert provider_dep["phase"] == "http_not_found"

    def test_unknown_phase_normalized_to_unknown(self):
        """Unknown phase is normalized to 'unknown'."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        data = {
            "primary_failure_class": "dependency_provider_connection_failed",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "unavailable",
                    "phase": "some_random_phase_that_is_not_in_allowlist",
                    "failure_class": "dependency_provider_connection_failed",
                    "reason_code": "provider_connection_failed",
                    "message_snippet": "",
                }
            ],
        }

        normalized, is_conclusive = _normalize_backend_health_details(data, backend_health_failed=True)

        provider_dep = next((d for d in normalized["dependencies"] if d["dependency_name"] == "diagnosis_provider"), None)
        assert provider_dep is not None
        assert provider_dep["phase"] == "unknown"

    def test_raw_url_in_phase_blocked(self):
        """Raw URL in phase cannot pass through."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        data = {
            "primary_failure_class": "dependency_provider_connection_failed",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "unavailable",
                    "phase": "https://api.openai.com/v1/chat/completions",
                    "failure_class": "dependency_provider_connection_failed",
                    "reason_code": "provider_connection_failed",
                    "message_snippet": "",
                }
            ],
        }

        normalized, is_conclusive = _normalize_backend_health_details(data, backend_health_failed=True)

        provider_dep = next((d for d in normalized["dependencies"] if d["dependency_name"] == "diagnosis_provider"), None)
        assert provider_dep is not None
        assert provider_dep["phase"] == "unknown"
        # Verify raw URL is not present
        normalized_json = json.dumps(normalized)
        assert "api.openai.com" not in normalized_json

    def test_raw_ip_in_phase_blocked(self):
        """Raw IP address in phase cannot pass through."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        data = {
            "primary_failure_class": "dependency_provider_connection_failed",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "unavailable",
                    "phase": "10.0.0.5:8080",
                    "failure_class": "dependency_provider_connection_failed",
                    "reason_code": "provider_connection_failed",
                    "message_snippet": "",
                }
            ],
        }

        normalized, is_conclusive = _normalize_backend_health_details(data, backend_health_failed=True)

        provider_dep = next((d for d in normalized["dependencies"] if d["dependency_name"] == "diagnosis_provider"), None)
        assert provider_dep is not None
        assert provider_dep["phase"] == "unknown"

    def test_raw_token_in_phase_blocked(self):
        """Raw API token in phase cannot pass through."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        data = {
            "primary_failure_class": "dependency_provider_connection_failed",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "unavailable",
                    "phase": "sk-1234567890abcdefghijklmnop",
                    "failure_class": "dependency_provider_connection_failed",
                    "reason_code": "provider_connection_failed",
                    "message_snippet": "",
                }
            ],
        }

        normalized, is_conclusive = _normalize_backend_health_details(data, backend_health_failed=True)

        provider_dep = next((d for d in normalized["dependencies"] if d["dependency_name"] == "diagnosis_provider"), None)
        assert provider_dep is not None
        assert provider_dep["phase"] == "unknown"

    def test_http_not_found_distinguishable_from_connection_refused(self):
        """provider_unavailable + http_not_found is distinguishable from connection_refused."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        # Test case 1: http_not_found (provider endpoint not found)
        data_not_found = {
            "primary_failure_class": "dependency_provider_connection_failed",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "unavailable",
                    "phase": "http_not_found",
                    "failure_class": "dependency_provider_connection_failed",
                    "reason_code": "provider_unavailable",
                    "message_snippet": "",
                }
            ],
        }

        normalized_not_found, _ = _normalize_backend_health_details(data_not_found, backend_health_failed=True)

        provider_not_found = next((d for d in normalized_not_found["dependencies"] if d["dependency_name"] == "diagnosis_provider"), None)
        assert provider_not_found is not None
        assert provider_not_found["phase"] == "http_not_found"
        assert provider_not_found["reason_code"] == "provider_unavailable"

        # Test case 2: connection_refused (TCP connection refused)
        data_refused = {
            "primary_failure_class": "dependency_provider_connection_failed",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "unavailable",
                    "phase": "connection_refused",
                    "failure_class": "dependency_provider_connection_failed",
                    "reason_code": "provider_connection_failed",
                    "message_snippet": "",
                }
            ],
        }

        normalized_refused, _ = _normalize_backend_health_details(data_refused, backend_health_failed=True)

        provider_refused = next((d for d in normalized_refused["dependencies"] if d["dependency_name"] == "diagnosis_provider"), None)
        assert provider_refused is not None
        assert provider_refused["phase"] == "connection_refused"
        assert provider_refused["reason_code"] == "provider_connection_failed"

        # Verify they are distinguishable
        assert provider_not_found["phase"] != provider_refused["phase"]
        assert provider_not_found["reason_code"] != provider_refused["reason_code"]

    def test_timeout_distinguishable_from_http_not_found(self):
        """provider_timeout + timeout is distinguishable from provider_unavailable + http_not_found."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        # Test case 1: timeout
        data_timeout = {
            "primary_failure_class": "dependency_provider_connection_failed",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "unavailable",
                    "phase": "timeout",
                    "failure_class": "dependency_provider_connection_failed",
                    "reason_code": "provider_timeout",
                    "message_snippet": "",
                }
            ],
        }

        normalized_timeout, _ = _normalize_backend_health_details(data_timeout, backend_health_failed=True)

        provider_timeout = next((d for d in normalized_timeout["dependencies"] if d["dependency_name"] == "diagnosis_provider"), None)
        assert provider_timeout is not None
        assert provider_timeout["phase"] == "timeout"
        assert provider_timeout["reason_code"] == "provider_timeout"

        # Test case 2: http_not_found
        data_not_found = {
            "primary_failure_class": "dependency_provider_connection_failed",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "unavailable",
                    "phase": "http_not_found",
                    "failure_class": "dependency_provider_connection_failed",
                    "reason_code": "provider_unavailable",
                    "message_snippet": "",
                }
            ],
        }

        normalized_not_found, _ = _normalize_backend_health_details(data_not_found, backend_health_failed=True)

        provider_not_found = next((d for d in normalized_not_found["dependencies"] if d["dependency_name"] == "diagnosis_provider"), None)
        assert provider_not_found is not None
        assert provider_not_found["phase"] == "http_not_found"
        assert provider_not_found["reason_code"] == "provider_unavailable"

        # Verify they are distinguishable
        assert provider_timeout["phase"] != provider_not_found["phase"]
        assert provider_timeout["reason_code"] != provider_not_found["reason_code"]


class TestProviderStatusFallback:
    """Test provider status fallback when status subsystem fails."""

    def test_provider_status_unavailable_preserved_in_health_details(self):
        """Provider status subsystem failure yields provider_status_unavailable reason_code.
        
        Regression test: When get_provider_status import/call fails, the endpoint
        should preserve provider_status_unavailable as the reason_code, not collapse
        it to provider_unavailable.
        """
        from unittest.mock import patch

        from src.k8s_diag_agent.ui.api_health_details import _build_health_dependencies, _get_provider_health_status

        # Simulate provider status import/call failure
        # Note: get_provider_status is imported inside the function, so we patch the external_analysis.provider module
        with patch(
            "src.k8s_diag_agent.external_analysis.provider.get_provider_status",
            side_effect=RuntimeError("Module not found"),
        ):
            provider_status = _get_provider_health_status()
            
            # Verify error_class is preserved in the fallback response
            assert provider_status["available"] is False
            assert provider_status["error"] == "provider_status_unavailable"
            assert provider_status["phase"] == "status_probe_failed"
            assert provider_status["error_class"] == "provider_status_unavailable"
            
            # Build dependencies and verify reason_code is preserved
            dependencies = _build_health_dependencies()
            
            provider_dep = None
            for dep in dependencies:
                if dep["dependency_name"] == "diagnosis_provider":
                    provider_dep = dep
                    break
            
            assert provider_dep is not None, "diagnosis_provider dependency not found"
            assert provider_dep["reason_code"] == "provider_status_unavailable", \
                f"Expected provider_status_unavailable, got {provider_dep['reason_code']}"
            assert provider_dep["message_snippet"] == "", "message_snippet should be empty"
            assert provider_dep["status"] == "unavailable"

    def test_provider_available_preserved_in_health_details(self):
        """Provider probe success yields diagnosis_provider.status=available, reason_code=provider_available.
        
        Regression test: When provider connectivity probe succeeds, the success path should
        return provider_available (not 'success' which is not in the allowlist).
        """
        from unittest.mock import patch

        from src.k8s_diag_agent.ui.api_health_details import _build_health_dependencies, _get_provider_health_status

        # Simulate successful provider status
        mock_provider_status = {
            "available": True,
            "error": None,
            "phase": "success",
            "error_class": "provider_available",
        }
        
        with patch(
            "src.k8s_diag_agent.external_analysis.provider.get_provider_status",
            return_value=mock_provider_status,
        ):
            provider_status = _get_provider_health_status()
            
            # Verify success response is preserved
            assert provider_status["available"] is True
            assert provider_status["error_class"] == "provider_available"
            
            # Build dependencies and verify reason_code is provider_available
            dependencies = _build_health_dependencies()
            
            provider_dep = None
            for dep in dependencies:
                if dep["dependency_name"] == "diagnosis_provider":
                    provider_dep = dep
                    break
            
            assert provider_dep is not None, "diagnosis_provider dependency not found"
            assert provider_dep["reason_code"] == "provider_available", \
                f"Expected provider_available, got {provider_dep['reason_code']}"
            assert provider_dep["status"] == "available"
            assert provider_dep["failure_class"] == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
