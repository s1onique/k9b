#!/usr/bin/env python3
"""Tests for backend health details normalization.

Verifies:
- Normalization of backend health API responses
- Security sanitization of sensitive data
- Allowlist-based field filtering
"""

import json

import pytest

from scripts.backend_health_gate.classification import (
    _normalize_backend_health_details,
)


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
