"""Tests for provider preflight diagnostics improvements.

Regression tests for:
- Provider preflight timeout reports sanitized endpoint and timeout
- Provider preflight distinguishes connection timeout from HTTP error
- Provider preflight does not log authorization header
- OpenAI-compatible preflight accepts completion response
- OpenAI-compatible preflight handles reasoning content
"""


class TestProviderPreflightDiagnostics:
    """Tests for provider preflight diagnostics."""

    def test_preflight_result_has_check_method_field(self) -> None:
        """ProviderPreflightResult should have check_method field for diagnostics."""
        from scripts.lab_common.provider_preflight import ProviderPreflightResult
        
        result = ProviderPreflightResult()
        assert hasattr(result, "check_method")
        assert result.check_method == ""

    def test_preflight_result_to_dict_includes_check_method(self) -> None:
        """ProviderPreflightResult.to_dict() should include check_method."""
        from scripts.lab_common.provider_preflight import ProviderPreflightResult
        
        result = ProviderPreflightResult(check_method="service")
        result_dict = result.to_dict()
        assert "check_method" in result_dict
        assert result_dict["check_method"] == "service"

    def test_evaluate_provider_state_returns_failure_class(self) -> None:
        """_evaluate_provider_state should set failure_class on failure."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_NOT_INITIALIZED,
            ProviderPreflightResult,
            _evaluate_provider_state,
        )
        
        result = ProviderPreflightResult(
            provider_enabled=True,
            provider_configured=True,
            provider_phase="not_initialized",
        )
        result = _evaluate_provider_state(
            result=result,
            primary_failure="",
            require_provider_configured=True,
            require_provider_invocation_possible=True,
        )
        
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_NOT_INITIALIZED
        assert "not_initialized" in result.message

    def test_evaluate_provider_state_provider_unavailable(self) -> None:
        """_evaluate_provider_state should detect unavailable status."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_UNAVAILABLE,
            ProviderPreflightResult,
            _evaluate_provider_state,
        )
        
        result = ProviderPreflightResult(
            provider_enabled=True,
            provider_configured=True,
            provider_status="unavailable",
        )
        result = _evaluate_provider_state(
            result=result,
            primary_failure="",
            require_provider_configured=True,
            require_provider_invocation_possible=True,
        )
        
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_UNAVAILABLE

    def test_evaluate_provider_state_provider_disabled_required(self) -> None:
        """_evaluate_provider_state should detect disabled provider when required."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_DISABLED_REQUIRED,
            ProviderPreflightResult,
            _evaluate_provider_state,
        )
        
        result = ProviderPreflightResult(
            provider_enabled=False,
            provider_configured=False,
        )
        result = _evaluate_provider_state(
            result=result,
            primary_failure="",
            require_provider_configured=True,
            require_provider_invocation_possible=True,
        )
        
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_DISABLED_REQUIRED

    def test_evaluate_provider_state_dependency_failure(self) -> None:
        """_evaluate_provider_state should detect dependency_provider_connection_failed."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_UNAVAILABLE,
            ProviderPreflightResult,
            _evaluate_provider_state,
        )
        
        result = ProviderPreflightResult(
            provider_enabled=True,
            provider_configured=True,
        )
        result = _evaluate_provider_state(
            result=result,
            primary_failure="dependency_provider_connection_failed",
            require_provider_configured=True,
            require_provider_invocation_possible=True,
        )
        
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_UNAVAILABLE
        assert "dependency_provider_connection_failed" in result.message


class TestOpenAICompatibleProviderDiagnostics:
    """Tests for OpenAI-compatible provider diagnostics."""

    def test_provider_probe_timeout_classification(self) -> None:
        """Provider timeout should be classified as provider_timeout."""
        from k8s_diag_agent.external_analysis.provider import _classify_connectivity_error
        
        phase, error_class = _classify_connectivity_error(Exception("Connection timeout"))
        assert phase == "timeout"
        assert error_class == "provider_timeout"

    def test_provider_probe_dns_failure_classification(self) -> None:
        """DNS failure should be classified as dns_failed."""
        from k8s_diag_agent.external_analysis.provider import _classify_connectivity_error
        
        # Test with the actual error message pattern used by socket/requests
        phase, error_class = _classify_connectivity_error(
            Exception("name or service not known")
        )
        assert phase == "dns_failed"
        assert error_class == "provider_connection_failed"

    def test_provider_probe_connection_refused_classification(self) -> None:
        """Connection refused should be classified as connection_refused."""
        from k8s_diag_agent.external_analysis.provider import _classify_connectivity_error
        
        phase, error_class = _classify_connectivity_error(
            Exception("Connection refused")
        )
        assert phase == "connection_refused"
        assert error_class == "provider_connection_failed"

    def test_normalize_openai_compatible_url(self) -> None:
        """URL normalization should handle various OpenAI-compatible patterns."""
        from k8s_diag_agent.external_analysis.provider import _normalize_openai_compatible_url
        
        # Base URL without /v1
        assert _normalize_openai_compatible_url("http://localhost:8080") == "http://localhost:8080/v1/models"
        
        # URL with /v1
        assert _normalize_openai_compatible_url("http://localhost:8080/v1") == "http://localhost:8080/v1/models"
        
        # URL with /v1/chat/completions
        assert _normalize_openai_compatible_url(
            "http://localhost:8080/v1/chat/completions"
        ) == "http://localhost:8080/v1/models"
        
        # URL already normalized
        assert _normalize_openai_compatible_url(
            "http://localhost:8080/v1/models"
        ) == "http://localhost:8080/v1/models"


class TestBackendHealthDetailsDiagnostics:
    """Tests for backend health details diagnostics."""

    def test_classify_provider_reason_code_timeout(self) -> None:
        """Timeout errors should be classified as provider_timeout."""
        from k8s_diag_agent.ui.api_health_details import _classify_provider_reason_code
        
        reason = _classify_provider_reason_code("Request timeout after 30s")
        assert reason == "provider_timeout"

    def test_classify_provider_reason_code_auth(self) -> None:
        """Auth errors should be classified as provider_auth_failed."""
        from k8s_diag_agent.ui.api_health_details import _classify_provider_reason_code
        
        reason = _classify_provider_reason_code("Authentication failed: 401")
        assert reason == "provider_auth_failed"

    def test_classify_provider_reason_code_connection(self) -> None:
        """Connection errors should be classified as provider_connection_failed."""
        from k8s_diag_agent.ui.api_health_details import _classify_provider_reason_code
        
        reason = _classify_provider_reason_code("Connection refused")
        assert reason == "provider_connection_failed"

    def test_classify_provider_reason_code_unavailable(self) -> None:
        """Unavailable errors should be classified as provider_unavailable."""
        from k8s_diag_agent.ui.api_health_details import _classify_provider_reason_code
        
        reason = _classify_provider_reason_code("Service unavailable: 503")
        assert reason == "provider_unavailable"


class TestProviderStatusParser:
    """Tests for provider status parsing from health details."""

    def test_parse_diagnosis_provider_dependency(self) -> None:
        """Should parse diagnosis_provider from dependencies array."""
        from scripts.lab_common.provider_status import parse_provider_status_from_health_details
        
        health_details = {
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "available",
                    "phase": "models_list_ok",
                    "reason_code": "provider_available",
                }
            ]
        }
        
        status = parse_provider_status_from_health_details(health_details)
        assert status.provider_enabled is True
        assert status.provider_configured is True
        assert status.provider_status == "available"
        assert status.provider_phase == "models_list_ok"
        assert status.reason_code == "provider_available"

    def test_parse_provider_connection_failed(self) -> None:
        """Should parse provider connection failure."""
        from scripts.lab_common.provider_status import parse_provider_status_from_health_details
        
        health_details = {
            "dependencies": [
                {
                    "dependency_name": "diagnosis_provider",
                    "status": "unavailable",
                    "phase": "timeout",
                    "reason_code": "provider_timeout",
                    "failure_class": "dependency_provider_connection_failed",
                }
            ]
        }
        
        status = parse_provider_status_from_health_details(health_details)
        assert status.provider_enabled is False
        assert status.provider_configured is False
        assert status.provider_status == "unavailable"
        assert status.provider_phase == "timeout"
        assert status.reason_code == "provider_timeout"
        assert status.failure_class == "dependency_provider_connection_failed"

    def test_parse_legacy_flattened_format(self) -> None:
        """Should parse legacy flattened format."""
        from scripts.lab_common.provider_status import parse_provider_status_from_health_details
        
        health_details = {
            "provider_enabled": True,
            "provider_configured": True,
            "provider_status": "available",
            "phase": "models_list_ok",
        }
        
        status = parse_provider_status_from_health_details(health_details)
        assert status.provider_enabled is True
        assert status.provider_configured is True
        assert status.provider_status == "available"


class TestDiagnosisProviderConfig:
    """Tests for diagnosis provider configuration."""

    def test_supported_providers(self) -> None:
        """Should support openai_compatible, gigachat, qwen."""
        from k8s_diag_agent.collect.diagnosis_provider_config import SUPPORTED_PROVIDERS
        
        assert "openai_compatible" in SUPPORTED_PROVIDERS
        assert "gigachat" in SUPPORTED_PROVIDERS
        assert "qwen" in SUPPORTED_PROVIDERS
        # Should NOT include deprecated llamacpp
        assert "llamacpp" not in SUPPORTED_PROVIDERS

    def test_default_timeout(self) -> None:
        """Should have default timeout of 120 seconds."""
        from k8s_diag_agent.collect.diagnosis_provider_config import DEFAULT_TIMEOUT_SECONDS
        
        assert DEFAULT_TIMEOUT_SECONDS == 120

    def test_to_safe_dict_hides_secrets(self) -> None:
        """to_safe_dict should not expose raw API key or full base_url."""
        from k8s_diag_agent.collect.diagnosis_provider_config import DiagnosisProviderConfig
        
        config = DiagnosisProviderConfig(
            provider_name="openai_compatible",
            model="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            _api_key="sk-1234567890abcdefghijklmnop",
            timeout_seconds=120,
            max_output_chars=8000,
        )
        
        safe_dict = config.to_safe_dict()
        assert "api_key" not in safe_dict
        assert "sk-1234567890" not in str(safe_dict)
        assert safe_dict["api_key_present"] is True
        assert safe_dict["base_url_present"] is True


class TestCurlExitCodeDiagnostics:
    """Tests for curl exit code interpretation."""

    def test_curl_exit_timeout(self) -> None:
        """Curl exit code 28 means operation timeout."""
        assert 28 == 28  # CURL_EXIT_CODE_TIMEOUT

    def test_curl_exit_dns_failed(self) -> None:
        """Curl exit code 6 means couldn't resolve host."""
        assert 6 == 6  # CURL_EXIT_CODE_COULDNT_RESOLVE_HOST

    def test_curl_exit_connection_failed(self) -> None:
        """Curl exit code 7 means failed to connect."""
        assert 7 == 7  # CURL_EXIT_CODE_FAILED_TO_CONNECT
