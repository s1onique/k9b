"""Tests for external analysis provider config loading from environment variables."""

from __future__ import annotations

import pytest

from k8s_diag_agent.external_analysis.config import parse_external_analysis_settings
from k8s_diag_agent.llm.llamacpp_provider_config import (
    _CANONICAL_ENV_API_KEY,
    _CANONICAL_ENV_BASE_URL,
    _CANONICAL_ENV_MODEL,
    LlamaCppProviderConfig,
)
from k8s_diag_agent.llm.openai_compatible_urls import build_chat_completions_url


class TestBuildChatCompletionsUrl:
    """Tests for build_chat_completions_url URL normalization."""

    @pytest.mark.parametrize(
        ("base_url", "expected"),
        [
            # Provider API root -> appends /v1/chat/completions
            (
                "http://localhost:8080",
                "http://localhost:8080/v1/chat/completions",
            ),
            (
                "https://openrouter.ai/api",
                "https://openrouter.ai/api/v1/chat/completions",
            ),
            # API version root -> appends /chat/completions
            (
                "http://localhost:8080/v1",
                "http://localhost:8080/v1/chat/completions",
            ),
            (
                "https://openrouter.ai/api/v1",
                "https://openrouter.ai/api/v1/chat/completions",
            ),
            (
                "https://api.openai.com/v1",
                "https://api.openai.com/v1/chat/completions",
            ),
            # Full endpoint -> returns as-is
            (
                "https://openrouter.ai/api/v1/chat/completions",
                "https://openrouter.ai/api/v1/chat/completions",
            ),
            (
                "http://localhost:8080/v1/chat/completions",
                "http://localhost:8080/v1/chat/completions",
            ),
            # Trailing slash variants
            (
                "http://localhost:8080/",
                "http://localhost:8080/v1/chat/completions",
            ),
            (
                "https://openrouter.ai/api/v1/",
                "https://openrouter.ai/api/v1/chat/completions",
            ),
        ],
    )
    def test_chat_completions_url_normalization(self, base_url: str, expected: str) -> None:
        """URL normalization handles provider API root, /v1 suffix, or full path."""
        assert build_chat_completions_url(base_url) == expected

    def test_openrouter_base_url_does_not_duplicate_v1(self) -> None:
        """Regression test: OpenRouter /v1 base URL should not produce /v1/v1/."""
        url = build_chat_completions_url("https://openrouter.ai/api/v1")

        assert url == "https://openrouter.ai/api/v1/chat/completions"
        assert "/v1/v1/" not in url

    def test_provider_api_root_does_not_duplicate_v1(self) -> None:
        """Regression test: Provider API root should not produce /v1/v1/."""
        url = build_chat_completions_url("https://openrouter.ai/api")

        assert url == "https://openrouter.ai/api/v1/chat/completions"
        assert "/v1/v1/" not in url

    def test_full_endpoint_unchanged(self) -> None:
        """Full /chat/completions endpoint should be returned unchanged."""
        url = build_chat_completions_url("https://openrouter.ai/api/v1/chat/completions")

        assert url == "https://openrouter.ai/api/v1/chat/completions"
        assert "/v1/v1/" not in url

    def test_whitespace_is_stripped(self) -> None:
        """Whitespace in base_url is stripped to protect against env var mistakes."""
        url = build_chat_completions_url("  https://openrouter.ai/api/v1  ")

        assert url == "https://openrouter.ai/api/v1/chat/completions"
        assert "/v1/v1/" not in url


class TestLlamaCppProviderConfigEndpoint:
    """Tests for LlamaCppProviderConfig.endpoint property URL normalization."""

    @pytest.mark.parametrize(
        ("base_url", "expected_endpoint"),
        [
            # Provider API root -> appends /v1/chat/completions
            (
                "http://localhost:8080",
                "http://localhost:8080/v1/chat/completions",
            ),
            (
                "https://openrouter.ai/api",
                "https://openrouter.ai/api/v1/chat/completions",
            ),
            # API version root -> appends /chat/completions
            (
                "http://localhost:8080/v1",
                "http://localhost:8080/v1/chat/completions",
            ),
            (
                "https://openrouter.ai/api/v1",
                "https://openrouter.ai/api/v1/chat/completions",
            ),
            (
                "https://api.openai.com/v1",
                "https://api.openai.com/v1/chat/completions",
            ),
            # Full endpoint -> returns as-is
            (
                "https://openrouter.ai/api/v1/chat/completions",
                "https://openrouter.ai/api/v1/chat/completions",
            ),
        ],
    )
    def test_endpoint_normalization(self, base_url: str, expected_endpoint: str) -> None:
        """LlamaCppProviderConfig.endpoint uses URL normalization."""
        config = LlamaCppProviderConfig(base_url=base_url, model="test-model")
        assert config.endpoint == expected_endpoint
        assert "/v1/v1/" not in config.endpoint

    def test_openrouter_endpoint_no_duplicate_v1(self) -> None:
        """Regression: OpenRouter /v1 base URL produces correct endpoint."""
        config = LlamaCppProviderConfig(
            base_url="https://openrouter.ai/api/v1",
            model="anthropic/claude-3.5-sonnet",
        )
        assert config.endpoint == "https://openrouter.ai/api/v1/chat/completions"
        assert "/v1/v1/" not in config.endpoint


class TestLlamaCppProviderConfigFromEnv:
    """Tests for LlamaCppProviderConfig.from_env()."""

    def test_config_from_env_all_required_vars(self) -> None:
        env = {
            _CANONICAL_ENV_BASE_URL: "https://llm.example.com/v1",
            _CANONICAL_ENV_MODEL: "qwen/qwen2.5-7b-instruct",
        }
        config = LlamaCppProviderConfig.from_env(env)
        assert config is not None
        assert config.base_url == "https://llm.example.com/v1"
        assert config.model == "qwen/qwen2.5-7b-instruct"

    def test_config_from_env_with_api_key(self) -> None:
        env = {
            _CANONICAL_ENV_BASE_URL: "https://llm.example.com/v1",
            _CANONICAL_ENV_MODEL: "qwen/qwen2.5-7b-instruct",
            _CANONICAL_ENV_API_KEY: "sk-test-key-1234567890abcdefghij",
        }
        config = LlamaCppProviderConfig.from_env(env)
        assert config is not None
        assert config.api_key == "sk-test-key-1234567890abcdefghij"

    def test_config_from_env_missing_base_url_raises(self) -> None:
        env = {_CANONICAL_ENV_MODEL: "qwen/qwen2.5-7b-instruct"}
        with pytest.raises(RuntimeError) as exc_info:
            LlamaCppProviderConfig.from_env(env)
        assert "K9B_EXTERNAL_ANALYSIS_BASE_URL" in str(exc_info.value)

    def test_config_from_env_missing_model_raises(self) -> None:
        env = {_CANONICAL_ENV_BASE_URL: "https://llm.example.com/v1"}
        with pytest.raises(RuntimeError) as exc_info:
            LlamaCppProviderConfig.from_env(env)
        assert "K9B_EXTERNAL_ANALYSIS_MODEL" in str(exc_info.value)


class TestExternalAnalysisSettingsParsing:
    """Tests for ExternalAnalysisSettings parsing."""

    def test_parse_review_enrichment_enabled(self) -> None:
        raw = {"review_enrichment": {"enabled": True, "provider": "openai_compatible"}}
        settings = parse_external_analysis_settings(raw)
        assert settings.review_enrichment.enabled is True
        assert settings.review_enrichment.provider == "openai_compatible"

    def test_parse_review_enrichment_disabled(self) -> None:
        raw = {"review_enrichment": {"enabled": False, "provider": None}}
        settings = parse_external_analysis_settings(raw)
        assert settings.review_enrichment.enabled is False

    def test_parse_empty_config_returns_defaults(self) -> None:
        settings = parse_external_analysis_settings(None)
        assert settings.review_enrichment.enabled is False


class TestConfigEnvVarCompleteness:
    """Verify all required env vars are documented."""

    def test_required_env_vars_documented(self) -> None:
        assert _CANONICAL_ENV_BASE_URL == "K9B_EXTERNAL_ANALYSIS_BASE_URL"
        assert _CANONICAL_ENV_MODEL == "K9B_EXTERNAL_ANALYSIS_MODEL"
        assert _CANONICAL_ENV_API_KEY == "K9B_EXTERNAL_ANALYSIS_API_KEY"
