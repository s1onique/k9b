"""Tests for OpenAICompatibleDiagnosisProvider endpoint construction.

These tests verify that the endpoint URL is constructed correctly from base_url.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from k8s_diag_agent.collect.diagnosis_provider_config import DiagnosisProviderConfig
from k8s_diag_agent.collect.diagnosis_provider_runtime import (
    OpenAICompatibleDiagnosisProvider,
)


class TestEndpointConstruction:
    """Tests for OpenAI-compatible endpoint URL construction."""

    def test_endpoint_with_v1_base_url(self) -> None:
        """base_url=https://api.openai.com/v1 -> endpoint https://api.openai.com/v1/chat/completions."""
        config = MagicMock(spec=DiagnosisProviderConfig)
        config.base_url = "https://api.openai.com/v1"
        config.model = "gpt-4o"
        config.timeout_seconds = 120
        config.max_output_chars = 50000
        config.get_api_key.return_value = None

        provider = OpenAICompatibleDiagnosisProvider(config)

        assert provider._endpoint == "https://api.openai.com/v1/chat/completions"
        # Verify no double /v1/v1/
        assert "/v1/v1/" not in provider._endpoint

    def test_endpoint_with_trailing_slash(self) -> None:
        """base_url=https://api.openai.com/v1/ -> endpoint https://api.openai.com/v1/chat/completions."""
        config = MagicMock(spec=DiagnosisProviderConfig)
        config.base_url = "https://api.openai.com/v1/"
        config.model = "gpt-4o"
        config.timeout_seconds = 120
        config.max_output_chars = 50000
        config.get_api_key.return_value = None

        provider = OpenAICompatibleDiagnosisProvider(config)

        assert provider._endpoint == "https://api.openai.com/v1/chat/completions"
        # Verify no double slash
        assert "//chat" not in provider._endpoint

    def test_endpoint_with_custom_provider(self) -> None:
        """base_url=http://llm-service:8080/v1 -> endpoint http://llm-service:8080/v1/chat/completions."""
        config = MagicMock(spec=DiagnosisProviderConfig)
        config.base_url = "http://llm-service:8080/v1"
        config.model = "qwen/qwen2.5-7b-instruct"
        config.timeout_seconds = 120
        config.max_output_chars = 8000
        config.get_api_key.return_value = "sk-test-key"

        provider = OpenAICompatibleDiagnosisProvider(config)

        assert provider._endpoint == "http://llm-service:8080/v1/chat/completions"
        assert "/v1/v1/" not in provider._endpoint

    def test_endpoint_no_double_v1(self) -> None:
        """Verify no generated endpoint contains /v1/v1/."""
        test_cases = [
            "https://api.openai.com/v1",
            "https://api.openai.com/v1/",
            "https://api.anthropic.com/v1",
            "http://localhost:8080/v1",
            "https://api.gigachat.com/v1",
        ]

        for base_url in test_cases:
            config = MagicMock(spec=DiagnosisProviderConfig)
            config.base_url = base_url
            config.model = "test-model"
            config.timeout_seconds = 120
            config.max_output_chars = 50000
            config.get_api_key.return_value = None

            provider = OpenAICompatibleDiagnosisProvider(config)

            # The endpoint should contain exactly one /v1/ before /chat/completions
            assert "/v1/chat/completions" in provider._endpoint
            # And should not have /v1/v1/
            assert "/v1/v1/" not in provider._endpoint

    @pytest.mark.parametrize(
        ("base_url", "expected_endpoint"),
        [
            # OpenRouter provider API root
            (
                "https://openrouter.ai/api",
                "https://openrouter.ai/api/v1/chat/completions",
            ),
            # OpenRouter API version root
            (
                "https://openrouter.ai/api/v1",
                "https://openrouter.ai/api/v1/chat/completions",
            ),
            # llama.cpp-style server root
            (
                "http://localhost:8080",
                "http://localhost:8080/v1/chat/completions",
            ),
            # Full endpoint already provided
            (
                "https://openrouter.ai/api/v1/chat/completions",
                "https://openrouter.ai/api/v1/chat/completions",
            ),
        ],
    )
    def test_endpoint_openrouter_and_llamacpp_urls(
        self, base_url: str, expected_endpoint: str
    ) -> None:
        """OpenRouter SDK-style and llama.cpp-style base URLs normalize correctly."""
        config = MagicMock(spec=DiagnosisProviderConfig)
        config.base_url = base_url
        config.model = "test-model"
        config.timeout_seconds = 120
        config.max_output_chars = 50000
        config.get_api_key.return_value = None

        provider = OpenAICompatibleDiagnosisProvider(config)

        assert provider._endpoint == expected_endpoint
        assert "/v1/v1/" not in provider._endpoint

    def test_openrouter_sdk_base_url_no_v1_v1(self) -> None:
        """Regression: OpenRouter SDK-style base URL should not produce /v1/v1/."""
        config = MagicMock(spec=DiagnosisProviderConfig)
        config.base_url = "https://openrouter.ai/api/v1"
        config.model = "anthropic/claude-3.5-sonnet"
        config.timeout_seconds = 120
        config.max_output_chars = 50000
        config.get_api_key.return_value = "sk-or-test"

        provider = OpenAICompatibleDiagnosisProvider(config)

        assert provider._endpoint == "https://openrouter.ai/api/v1/chat/completions"
        assert "/v1/v1/" not in provider._endpoint
