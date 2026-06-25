"""Tests for diagnosis provider configuration.

These tests verify:
- Provider config parsing from environment variables
- Fail-closed behavior on missing/invalid config
- Timeout and output bounds validation
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.diagnosis_provider_config import (
    DEFAULT_MAX_OUTPUT_CHARS,
    DEFAULT_TIMEOUT_SECONDS,
    ENV_DIAGNOSIS_API_KEY,
    ENV_DIAGNOSIS_BASE_URL,
    ENV_DIAGNOSIS_MAX_OUTPUT,
    ENV_DIAGNOSIS_MODEL,
    ENV_DIAGNOSIS_PROVIDER_NAME,
    ENV_DIAGNOSIS_TIMEOUT,
    MAX_MAX_OUTPUT_CHARS,
    MAX_TIMEOUT_SECONDS,
    MIN_MAX_OUTPUT_CHARS,
    MIN_TIMEOUT_SECONDS,
    SUPPORTED_PROVIDERS,
    DiagnosisProviderConfig,
)


def test_config_from_env_valid() -> None:
    """Config is parsed correctly when all required vars are set."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "openai_compatible",
        ENV_DIAGNOSIS_MODEL: "gpt-4o",
        ENV_DIAGNOSIS_BASE_URL: "https://api.openai.com/v1",
    }
    config = DiagnosisProviderConfig.from_env(env)

    assert config is not None
    assert config.provider_name == "openai_compatible"
    assert config.model == "gpt-4o"
    assert config.base_url == "https://api.openai.com/v1"
    assert config.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert config.max_output_chars == DEFAULT_MAX_OUTPUT_CHARS


def test_config_from_env_with_optional_vars() -> None:
    """Config parses optional vars correctly."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "gigachat",
        ENV_DIAGNOSIS_MODEL: "gigachat-4",
        ENV_DIAGNOSIS_BASE_URL: "https://gigachat.example.com",
        ENV_DIAGNOSIS_API_KEY: "sk-test-key-12345",
        ENV_DIAGNOSIS_TIMEOUT: "60",
        ENV_DIAGNOSIS_MAX_OUTPUT: "30000",
    }
    config = DiagnosisProviderConfig.from_env(env)

    assert config is not None
    assert config.provider_name == "gigachat"
    assert config.get_api_key() == "sk-test-key-12345"
    assert config.timeout_seconds == 60
    assert config.max_output_chars == 30000


def test_config_from_env_case_insensitive_provider() -> None:
    """Provider name is normalized to lowercase."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "OpenAI_Compatible",
        ENV_DIAGNOSIS_MODEL: "gpt-4o",
        ENV_DIAGNOSIS_BASE_URL: "https://api.openai.com/v1",
    }
    config = DiagnosisProviderConfig.from_env(env)

    assert config is not None
    assert config.provider_name == "openai_compatible"


def test_config_from_env_missing_required_returns_none() -> None:
    """Returns None when required fields are missing (required=False)."""
    env: dict[str, str] = {}
    config = DiagnosisProviderConfig.from_env(env, required=False)

    assert config is None


def test_config_from_env_missing_required_raises_when_required() -> None:
    """Raises RuntimeError when required=True and fields are missing."""
    env: dict[str, str] = {}
    with pytest.raises(RuntimeError) as exc_info:
        DiagnosisProviderConfig.from_env(env, required=True)

    assert "Missing required diagnosis provider environment variables" in str(exc_info.value)
    assert ENV_DIAGNOSIS_PROVIDER_NAME in str(exc_info.value)
    assert ENV_DIAGNOSIS_MODEL in str(exc_info.value)
    assert ENV_DIAGNOSIS_BASE_URL in str(exc_info.value)


def test_config_from_env_missing_base_url() -> None:
    """Returns None when base_url is missing."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "openai_compatible",
        ENV_DIAGNOSIS_MODEL: "gpt-4o",
    }
    config = DiagnosisProviderConfig.from_env(env, required=False)

    assert config is None


def test_config_from_env_whitespace_only() -> None:
    """Whitespace-only values are treated as missing."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "   ",
        ENV_DIAGNOSIS_MODEL: "gpt-4o",
        ENV_DIAGNOSIS_BASE_URL: "https://api.openai.com/v1",
    }
    config = DiagnosisProviderConfig.from_env(env, required=False)

    assert config is None


def test_config_from_env_unsupported_provider_returns_none() -> None:
    """Returns None for unsupported provider when required=False."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "unsupported_provider",
        ENV_DIAGNOSIS_MODEL: "model",
        ENV_DIAGNOSIS_BASE_URL: "https://example.com",
    }
    config = DiagnosisProviderConfig.from_env(env, required=False)

    assert config is None


def test_config_from_env_unsupported_provider_raises_when_required() -> None:
    """Raises ValueError for unsupported provider when required=True."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "unsupported_provider",
        ENV_DIAGNOSIS_MODEL: "model",
        ENV_DIAGNOSIS_BASE_URL: "https://example.com",
    }
    with pytest.raises(ValueError) as exc_info:
        DiagnosisProviderConfig.from_env(env, required=True)

    assert "Unsupported diagnosis provider" in str(exc_info.value)
    assert "unsupported_provider" in str(exc_info.value)


def test_config_from_env_timeout_out_of_bounds_low() -> None:
    """Raises ValueError when timeout is below minimum."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "openai_compatible",
        ENV_DIAGNOSIS_MODEL: "gpt-4o",
        ENV_DIAGNOSIS_BASE_URL: "https://api.openai.com/v1",
        ENV_DIAGNOSIS_TIMEOUT: "0",
    }
    with pytest.raises(ValueError) as exc_info:
        DiagnosisProviderConfig.from_env(env)

    assert "must be between" in str(exc_info.value)


def test_config_from_env_timeout_out_of_bounds_high() -> None:
    """Raises ValueError when timeout is above maximum."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "openai_compatible",
        ENV_DIAGNOSIS_MODEL: "gpt-4o",
        ENV_DIAGNOSIS_BASE_URL: "https://api.openai.com/v1",
        ENV_DIAGNOSIS_TIMEOUT: "500",
    }
    with pytest.raises(ValueError) as exc_info:
        DiagnosisProviderConfig.from_env(env)

    assert "must be between" in str(exc_info.value)


def test_config_from_env_timeout_invalid() -> None:
    """Raises ValueError when timeout is not a valid integer."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "openai_compatible",
        ENV_DIAGNOSIS_MODEL: "gpt-4o",
        ENV_DIAGNOSIS_BASE_URL: "https://api.openai.com/v1",
        ENV_DIAGNOSIS_TIMEOUT: "invalid",
    }
    with pytest.raises(ValueError) as exc_info:
        DiagnosisProviderConfig.from_env(env)

    assert "must be an integer" in str(exc_info.value)


def test_config_from_env_max_output_out_of_bounds_low() -> None:
    """Raises ValueError when max_output_chars is below minimum."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "openai_compatible",
        ENV_DIAGNOSIS_MODEL: "gpt-4o",
        ENV_DIAGNOSIS_BASE_URL: "https://api.openai.com/v1",
        ENV_DIAGNOSIS_MAX_OUTPUT: "50",
    }
    with pytest.raises(ValueError) as exc_info:
        DiagnosisProviderConfig.from_env(env)

    assert "must be between" in str(exc_info.value)


def test_config_from_env_max_output_out_of_bounds_high() -> None:
    """Raises ValueError when max_output_chars is above maximum."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "openai_compatible",
        ENV_DIAGNOSIS_MODEL: "gpt-4o",
        ENV_DIAGNOSIS_BASE_URL: "https://api.openai.com/v1",
        ENV_DIAGNOSIS_MAX_OUTPUT: "200000",
    }
    with pytest.raises(ValueError) as exc_info:
        DiagnosisProviderConfig.from_env(env)

    assert "must be between" in str(exc_info.value)


def test_config_from_env_max_output_invalid() -> None:
    """Raises ValueError when max_output_chars is not a valid integer."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "openai_compatible",
        ENV_DIAGNOSIS_MODEL: "gpt-4o",
        ENV_DIAGNOSIS_BASE_URL: "https://api.openai.com/v1",
        ENV_DIAGNOSIS_MAX_OUTPUT: "invalid",
    }
    with pytest.raises(ValueError) as exc_info:
        DiagnosisProviderConfig.from_env(env)

    assert "must be an integer" in str(exc_info.value)


def test_config_get_api_key_present() -> None:
    """get_api_key returns raw value from K9B_DIAGNOSIS_API_KEY (Helm secretKeyRef style)."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "openai_compatible",
        ENV_DIAGNOSIS_MODEL: "gpt-4o",
        ENV_DIAGNOSIS_BASE_URL: "https://api.openai.com/v1",
        # With Helm secretKeyRef, this env var contains the raw secret value directly
        ENV_DIAGNOSIS_API_KEY: "sk-1234567890abcdef",
    }
    config = DiagnosisProviderConfig.from_env(env)

    assert config is not None
    assert config.get_api_key() == "sk-1234567890abcdef"


def test_config_get_api_key_not_set() -> None:
    """get_api_key returns None when env var is not set."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "openai_compatible",
        ENV_DIAGNOSIS_MODEL: "gpt-4o",
        ENV_DIAGNOSIS_BASE_URL: "https://api.openai.com/v1",
    }
    config = DiagnosisProviderConfig.from_env(env)

    assert config is not None
    assert config.get_api_key() is None


def test_config_to_safe_dict() -> None:
    """to_safe_dict returns metadata without raw secrets."""
    env: dict[str, str] = {
        ENV_DIAGNOSIS_PROVIDER_NAME: "openai_compatible",
        ENV_DIAGNOSIS_MODEL: "gpt-4o",
        ENV_DIAGNOSIS_BASE_URL: "https://api.openai.com/v1",
        ENV_DIAGNOSIS_API_KEY: "sk-secret-value",
    }
    config = DiagnosisProviderConfig.from_env(env)

    assert config is not None
    safe = config.to_safe_dict()

    assert "provider_name" in safe
    assert "model" in safe
    # base_url is redacted, only presence is indicated
    assert "base_url_present" in safe
    assert "base_url" not in safe
    assert "api_key_present" in safe
    assert "timeout_seconds" in safe
    assert "max_output_chars" in safe
    # Raw API key and base URL should never appear in safe dict
    assert "sk-" not in str(safe)
    assert "https://" not in str(safe)
    assert "api_key" not in safe
    assert "_api_key" not in safe


def test_supported_providers_defined() -> None:
    """SUPPORTED_PROVIDERS contains expected values."""
    assert "openai_compatible" in SUPPORTED_PROVIDERS
    assert "gigachat" in SUPPORTED_PROVIDERS
    assert "qwen" in SUPPORTED_PROVIDERS
    assert len(SUPPORTED_PROVIDERS) == 3


def test_timeout_bounds() -> None:
    """Timeout bounds are reasonable."""
    assert MIN_TIMEOUT_SECONDS >= 1
    assert MAX_TIMEOUT_SECONDS <= 600
    assert MIN_TIMEOUT_SECONDS < MAX_TIMEOUT_SECONDS


def test_max_output_bounds() -> None:
    """Max output bounds are reasonable."""
    assert MIN_MAX_OUTPUT_CHARS >= 100
    assert MAX_MAX_OUTPUT_CHARS <= 1000000
    assert MIN_MAX_OUTPUT_CHARS < MAX_MAX_OUTPUT_CHARS
