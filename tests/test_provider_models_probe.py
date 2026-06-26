#!/usr/bin/env python3
"""Tests for provider /models probe replacing /health probe.

Verifies:
- URL normalization for OpenAI-compatible endpoints
- /models endpoint probe with various HTTP responses
- Phase classification for models endpoint
- Privacy: no raw URLs, IPs, tokens, or model names in output
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.external_analysis.provider import (
    _normalize_openai_compatible_url,
    _probe_models_endpoint,
)


class TestNormalizeOpenAICompatibleUrl:
    """Test _normalize_openai_compatible_url function."""

    def test_url_with_v1_suffix(self) -> None:
        """URL ending with /v1 gets /models appended."""
        assert _normalize_openai_compatible_url("https://api.openai.com/v1") == "https://api.openai.com/v1/models"
        assert _normalize_openai_compatible_url("http://localhost:8080/v1") == "http://localhost:8080/v1/models"

    def test_url_with_v1_chat_completions(self) -> None:
        """URL with /v1/chat/completions normalizes to /v1/models."""
        assert _normalize_openai_compatible_url("https://api.deepseek.com/v1/chat/completions") == "https://api.deepseek.com/v1/models"
        assert _normalize_openai_compatible_url("https://api.openai.com/v1/chat/completions") == "https://api.openai.com/v1/models"

    def test_url_with_v1_responses(self) -> None:
        """URL with /v1/responses normalizes to /v1/models."""
        assert _normalize_openai_compatible_url("https://api.anthropic.com/v1/responses") == "https://api.anthropic.com/v1/models"

    def test_url_with_v1_completions(self) -> None:
        """URL with /v1/completions normalizes to /v1/models."""
        assert _normalize_openai_compatible_url("https://api.openai.com/v1/completions") == "https://api.openai.com/v1/models"

    def test_url_with_v1_embeddings(self) -> None:
        """URL with /v1/embeddings normalizes to /v1/models."""
        assert _normalize_openai_compatible_url("https://api.openai.com/v1/embeddings") == "https://api.openai.com/v1/models"

    def test_url_without_v1_suffix(self) -> None:
        """URL without /v1 gets /v1/models appended."""
        assert _normalize_openai_compatible_url("http://localhost:11434") == "http://localhost:11434/v1/models"
        assert _normalize_openai_compatible_url("https://api.openai.com") == "https://api.openai.com/v1/models"

    def test_url_with_trailing_slash(self) -> None:
        """URLs with trailing slashes are normalized correctly."""
        assert _normalize_openai_compatible_url("https://api.openai.com/v1/") == "https://api.openai.com/v1/models"
        assert _normalize_openai_compatible_url("http://localhost:11434/") == "http://localhost:11434/v1/models"

    def test_url_already_has_models_is_idempotent(self) -> None:
        """URL already ending with /v1/models stays unchanged (idempotent)."""
        assert _normalize_openai_compatible_url("https://api.openai.com/v1/models") == "https://api.openai.com/v1/models"
        assert _normalize_openai_compatible_url("https://api.deepseek.com/v1/models") == "https://api.deepseek.com/v1/models"


class TestProbeModelsEndpoint:
    """Test _probe_models_endpoint function with mocked requests."""

    def test_200_with_dict_response(self) -> None:
        """200 with JSON object containing data array returns models_list_ok."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "gpt-4"}]}

        with patch("requests.get", return_value=mock_response):
            success, phase, error_class = _probe_models_endpoint(
                "https://api.openai.com/v1/models", api_key="sk-test"
            )

        assert success is True
        assert phase == "models_list_ok"
        assert error_class == "provider_available"

    def test_200_with_list_response(self) -> None:
        """200 with JSON array returns models_list_ok."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": "gpt-4"}, {"id": "gpt-3.5"}]

        with patch("requests.get", return_value=mock_response):
            success, phase, error_class = _probe_models_endpoint(
                "https://api.openai.com/v1/models", api_key=None
            )

        assert success is True
        assert phase == "models_list_ok"
        assert error_class == "provider_available"

    def test_200_with_empty_response(self) -> None:
        """200 with unexpected JSON structure still returns models_list_ok."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"object": "list"}

        with patch("requests.get", return_value=mock_response):
            success, phase, error_class = _probe_models_endpoint(
                "https://api.openai.com/v1/models", api_key=None
            )

        assert success is True
        assert phase == "models_list_ok"

    def test_401_returns_auth_failed(self) -> None:
        """401 returns http_auth_required and provider_auth_failed."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("requests.get", return_value=mock_response):
            success, phase, error_class = _probe_models_endpoint(
                "https://api.openai.com/v1/models", api_key="sk-invalid"
            )

        assert success is False
        assert phase == "http_auth_required"
        assert error_class == "provider_auth_failed"

    def test_403_returns_auth_failed(self) -> None:
        """403 returns http_auth_required and provider_auth_failed."""
        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch("requests.get", return_value=mock_response):
            success, phase, error_class = _probe_models_endpoint(
                "https://api.openai.com/v1/models", api_key=None
            )

        assert success is False
        assert phase == "http_auth_required"
        assert error_class == "provider_auth_failed"

    def test_404_returns_endpoint_not_found(self) -> None:
        """404 returns models_endpoint_not_found and provider_unavailable."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("requests.get", return_value=mock_response):
            success, phase, error_class = _probe_models_endpoint(
                "https://api.openai.com/v1/models", api_key=None
            )

        assert success is False
        assert phase == "models_endpoint_not_found"
        assert error_class == "provider_unavailable"

    def test_429_returns_rate_limited(self) -> None:
        """429 returns http_rate_limited without raw body."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.json.return_value = {"error": {"message": "Rate limit exceeded", "details": "sk-1234567890"}}

        with patch("requests.get", return_value=mock_response):
            success, phase, error_class = _probe_models_endpoint(
                "https://api.openai.com/v1/models", api_key=None
            )

        assert success is False
        assert phase == "http_rate_limited"
        assert error_class == "provider_unavailable"
        # Verify no body content is in error
        assert error_class != "Rate limit exceeded"

    def test_500_returns_server_error(self) -> None:
        """5xx returns http_server_error and provider_unavailable."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("requests.get", return_value=mock_response):
            success, phase, error_class = _probe_models_endpoint(
                "https://api.openai.com/v1/models", api_key=None
            )

        assert success is False
        assert phase == "http_server_error"
        assert error_class == "provider_unavailable"

    def test_timeout_returns_timeout_phase(self) -> None:
        """Timeout returns timeout phase and provider_timeout."""
        import requests as req

        with patch("requests.get", side_effect=req.Timeout()):
            success, phase, error_class = _probe_models_endpoint(
                "https://api.openai.com/v1/models", api_key=None
            )

        assert success is False
        assert phase == "timeout"
        assert error_class == "provider_timeout"

    def test_connection_refused_returns_refused_phase(self) -> None:
        """Connection refused returns connection_refused phase."""
        import requests as req

        with patch("requests.get", side_effect=req.ConnectionError("Connection refused")):
            success, phase, error_class = _probe_models_endpoint(
                "https://api.openai.com/v1/models", api_key=None
            )

        assert success is False
        assert phase == "connection_refused"
        assert error_class == "provider_connection_failed"


class TestProbeModelsEndpointPrivacy:
    """Test that /models probe doesn't leak secrets in output."""

    def test_api_key_not_in_output(self) -> None:
        """API key never appears in phase or error_class."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("requests.get", return_value=mock_response):
            success, phase, error_class = _probe_models_endpoint(
                "https://api.openai.com/v1/models",
                api_key="sk-1234567890abcdefghijklmnop"
            )

        # Verify API key doesn't appear in any output
        output_str = json.dumps({"phase": phase, "error_class": error_class})
        assert "sk-1234567890" not in output_str
        assert "abcdefghijklmnop" not in output_str

    def test_url_not_in_output(self) -> None:
        """URL never appears in phase or error_class."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("requests.get", return_value=mock_response):
            success, phase, error_class = _probe_models_endpoint(
                "https://api.openai.com/v1/models",
                api_key=None
            )

        output_str = json.dumps({"phase": phase, "error_class": error_class})
        assert "api.openai.com" not in output_str
        assert "/v1/models" not in output_str

    def test_response_body_not_in_output(self) -> None:
        """Response body content doesn't appear in phase or error_class."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.json.return_value = {
            "error": {
                "message": "Rate limit exceeded for key sk-exposed-key",
                "models": ["gpt-4", "gpt-3.5-turbo"]
            }
        }

        with patch("requests.get", return_value=mock_response):
            success, phase, error_class = _probe_models_endpoint(
                "https://api.openai.com/v1/models",
                api_key="sk-safe-key"
            )

        output_str = json.dumps({"phase": phase, "error_class": error_class})
        # Verify no model names or raw error content
        assert "gpt-4" not in output_str
        assert "gpt-3.5" not in output_str
        assert "Rate limit exceeded" not in output_str
        assert "sk-exposed-key" not in output_str

    def test_sends_authorization_header(self) -> None:
        """Request includes Authorization header when api_key provided."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}

        with patch("requests.get") as mock_get:
            mock_get.return_value = mock_response
            _probe_models_endpoint(
                "https://api.openai.com/v1/models",
                api_key="sk-test-key"
            )

            # Verify headers were passed
            call_args = mock_get.call_args
            assert call_args is not None
            headers = call_args.kwargs.get("headers", {})
            assert "Authorization" in headers
            assert headers["Authorization"] == "Bearer sk-test-key"

    def test_no_authorization_header_when_no_key(self) -> None:
        """Request has no Authorization header when api_key is None."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}

        with patch("requests.get") as mock_get:
            mock_get.return_value = mock_response
            _probe_models_endpoint(
                "https://api.openai.com/v1/models",
                api_key=None
            )

            call_args = mock_get.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "Authorization" not in headers


class TestProviderPhaseNormalization:
    """Test phase normalization with new /models phases."""

    def test_models_list_ok_in_allowlist(self) -> None:
        """models_list_ok is a valid allowlisted phase."""
        from scripts.backend_health_gate.allowlists import ALLOWED_PROVIDER_PHASES, _normalize_provider_phase

        assert "models_list_ok" in ALLOWED_PROVIDER_PHASES
        assert _normalize_provider_phase("models_list_ok") == "models_list_ok"

    def test_models_endpoint_not_found_in_allowlist(self) -> None:
        """models_endpoint_not_found is a valid allowlisted phase."""
        from scripts.backend_health_gate.allowlists import ALLOWED_PROVIDER_PHASES, _normalize_provider_phase

        assert "models_endpoint_not_found" in ALLOWED_PROVIDER_PHASES
        assert _normalize_provider_phase("models_endpoint_not_found") == "models_endpoint_not_found"

    def test_http_rate_limited_in_allowlist(self) -> None:
        """http_rate_limited is a valid allowlisted phase."""
        from scripts.backend_health_gate.allowlists import ALLOWED_PROVIDER_PHASES, _normalize_provider_phase

        assert "http_rate_limited" in ALLOWED_PROVIDER_PHASES
        assert _normalize_provider_phase("http_rate_limited") == "http_rate_limited"

    def test_full_phase_roundtrip_in_health_details(self) -> None:
        """Full roundtrip: provider -> health details -> normalized."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        # Simulate health-dependencies.json with new phases
        data = {
            "primary_failure_class": "dependency_provider_connection_failed",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "unavailable",
                    "phase": "models_endpoint_not_found",
                    "failure_class": "dependency_provider_connection_failed",
                    "reason_code": "provider_unavailable",
                    "message_snippet": "",
                }
            ],
        }

        normalized, is_conclusive = _normalize_backend_health_details(data, backend_health_failed=True)

        provider_dep = next((d for d in normalized["dependencies"] if d["dependency_name"] == "diagnosis_provider"), None)
        assert provider_dep is not None
        assert provider_dep["phase"] == "models_endpoint_not_found"

    def test_health_dependencies_json_phase_normalization(self) -> None:
        """health-dependencies.json normalizes phases correctly."""
        from scripts.backend_health_gate.classification import _normalize_backend_health_details

        # Simulate provider returning auth failure - phase should pass through
        data = {
            "primary_failure_class": "dependency_provider_connection_failed",
            "healthy": False,
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "unavailable",
                    "phase": "http_auth_required",
                    "failure_class": "dependency_provider_connection_failed",
                    "reason_code": "provider_auth_failed",
                    "message_snippet": "",  # message_snippet should be empty per design
                }
            ],
        }

        normalized, _ = _normalize_backend_health_details(data, backend_health_failed=True)

        # Phase should be normalized to allowlisted value
        provider_dep = next((d for d in normalized["dependencies"] if d["dependency_name"] == "diagnosis_provider"), None)
        assert provider_dep is not None
        assert provider_dep["phase"] == "http_auth_required"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
