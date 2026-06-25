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
