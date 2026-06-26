#!/usr/bin/env python3
"""Tests for backend health gate dependency classification.

Verifies:
- Kubernetes container state to failure class mapping
- Scheduler unavailability detection
- Provider misconfiguration detection
- Health-dependencies.json structure
- Message sanitization

This module re-exports all test classes from the focused test modules:
- test_backend_health_gate_dependencies_classification: TestDependencyClassification
- test_backend_health_gate_dependencies_normalize: TestNormalizeBackendHealthDetails
- test_backend_health_gate_dependencies_provider_phase: TestProviderPhaseNormalization
- test_backend_health_gate_dependencies_provider_status: TestProviderStatusFallback

For new tests or modifications, prefer adding to the focused modules.
"""

import json

import pytest

from scripts.backend_health_gate.classification import (
    _collect_health_dependencies,
)

# Re-export test classes from focused modules
from tests.test_backend_health_gate_dependencies_classification import (
    TestDependencyClassification,
)
from tests.test_backend_health_gate_dependencies_normalize import (
    TestNormalizeBackendHealthDetails,
)


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
