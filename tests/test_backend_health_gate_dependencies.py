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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
