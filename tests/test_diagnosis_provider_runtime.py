"""Tests for diagnosis provider runtime.

These tests verify:
- Production provider builder
- OpenAICompatibleDiagnosisProvider behavior
- Error handling (timeout, connection, auth, malformed response)
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from k8s_diag_agent.collect.diagnosis_provider_config import DiagnosisProviderConfig
from k8s_diag_agent.collect.diagnosis_provider_runtime import (
    OpenAICompatibleDiagnosisProvider,
    build_diagnosis_provider_from_config,
)


def test_build_provider_from_config_none() -> None:
    """Returns None when config is None."""
    provider = build_diagnosis_provider_from_config(None)
    assert provider is None


def test_build_provider_openai_compatible() -> None:
    """Builds OpenAI-compatible provider correctly."""
    config = DiagnosisProviderConfig(
        provider_name="openai_compatible",
        model="gpt-4o",
        base_url="https://api.openai.com/v1",
    )
    provider = build_diagnosis_provider_from_config(config)

    assert provider is not None
    assert isinstance(provider, OpenAICompatibleDiagnosisProvider)


def test_build_provider_gigachat() -> None:
    """Builds GigaChat provider as OpenAI-compatible."""
    config = DiagnosisProviderConfig(
        provider_name="gigachat",
        model="gigachat-4",
        base_url="https://gigachat.example.com",
    )
    provider = build_diagnosis_provider_from_config(config)

    assert provider is not None
    assert isinstance(provider, OpenAICompatibleDiagnosisProvider)


def test_build_provider_unsupported() -> None:
    """Raises ValueError for unsupported provider type."""
    config = DiagnosisProviderConfig(
        provider_name="unsupported",
        model="model",
        base_url="https://example.com",
    )
    with pytest.raises(ValueError) as exc_info:
        build_diagnosis_provider_from_config(config)

    assert "Unsupported diagnosis provider type" in str(exc_info.value)


def test_provider_complete_success() -> None:
    """Provider.complete returns model output on success."""
    config = DiagnosisProviderConfig(
        provider_name="openai_compatible",
        model="gpt-4o",
        base_url="https://api.openai.com/v1",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"summary": "test diagnosis"}'}}],
    }
    mock_session = MagicMock()
    mock_session.post.return_value = mock_response

    def session_factory() -> MagicMock:
        return mock_session

    provider = OpenAICompatibleDiagnosisProvider(config, session_factory=session_factory)
    result = provider.complete("test prompt")

    assert result == '{"summary": "test diagnosis"}'


def test_provider_complete_timeout() -> None:
    """Provider.complete raises RuntimeError on timeout."""
    import requests

    config = DiagnosisProviderConfig(
        provider_name="openai_compatible",
        model="gpt-4o",
        base_url="https://api.openai.com/v1",
        timeout_seconds=5,
    )

    def session_factory() -> MagicMock:
        mock_session = MagicMock()
        mock_session.post.side_effect = requests.Timeout("Connection timed out")
        return mock_session

    provider = OpenAICompatibleDiagnosisProvider(config, session_factory=session_factory)

    with pytest.raises(RuntimeError) as exc_info:
        provider.complete("test prompt")

    assert "timeout" in str(exc_info.value).lower()


def test_provider_complete_connection_error() -> None:
    """Provider.complete raises RuntimeError on connection error."""
    import requests

    config = DiagnosisProviderConfig(
        provider_name="openai_compatible",
        model="gpt-4o",
        base_url="https://api.openai.com/v1",
    )

    def session_factory() -> MagicMock:
        mock_session = MagicMock()
        mock_session.post.side_effect = requests.ConnectionError("Connection refused")
        return mock_session

    provider = OpenAICompatibleDiagnosisProvider(config, session_factory=session_factory)

    with pytest.raises(RuntimeError) as exc_info:
        provider.complete("test prompt")

    assert "connection" in str(exc_info.value).lower()


def test_provider_complete_auth_failure() -> None:
    """Provider.complete raises RuntimeError on auth failure."""
    from requests.exceptions import HTTPError

    config = DiagnosisProviderConfig(
        provider_name="openai_compatible",
        model="gpt-4o",
        base_url="https://api.openai.com/v1",
    )

    mock_response = MagicMock()
    mock_response.status_code = 401

    def session_factory() -> MagicMock:
        mock_session = MagicMock()
        mock_session.post.side_effect = HTTPError(
            "401 Unauthorized",
            response=mock_response,
        )
        return mock_session

    provider = OpenAICompatibleDiagnosisProvider(config, session_factory=session_factory)

    with pytest.raises(RuntimeError) as exc_info:
        provider.complete("test prompt")

    assert "authentication" in str(exc_info.value).lower() or "401" in str(exc_info.value)


def test_provider_complete_malformed_response() -> None:
    """Provider.complete raises RuntimeError on malformed response."""
    config = DiagnosisProviderConfig(
        provider_name="openai_compatible",
        model="gpt-4o",
        base_url="https://api.openai.com/v1",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)

    def session_factory() -> MagicMock:
        mock_session = MagicMock()
        mock_session.post.return_value = mock_response
        return mock_session

    provider = OpenAICompatibleDiagnosisProvider(config, session_factory=session_factory)

    with pytest.raises(RuntimeError) as exc_info:
        provider.complete("test prompt")

    assert "malformed" in str(exc_info.value).lower()


def test_provider_complete_sends_authorization_header() -> None:
    """Provider.complete sends Authorization: Bearer header when API key is set."""
    config = DiagnosisProviderConfig(
        provider_name="openai_compatible",
        model="gpt-4o",
        base_url="https://api.openai.com/v1",
        _api_key="sk-test-secret-key-12345",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"summary": "test"}'}}],
    }

    captured_headers: dict[str, str] = {}

    def session_factory() -> MagicMock:
        mock_session = MagicMock()

        def capture_post(url: str, **kwargs: Any) -> MagicMock:
            captured_headers.update(kwargs.get("headers", {}))
            return mock_response

        mock_session.post.side_effect = capture_post
        return mock_session

    provider = OpenAICompatibleDiagnosisProvider(config, session_factory=session_factory)
    provider.complete("test prompt")

    # Verify Authorization header was sent with Bearer token
    assert "Authorization" in captured_headers
    assert captured_headers["Authorization"] == "Bearer sk-test-secret-key-12345"
    # Verify no raw key in safe logs (header value not logged)
    # The actual provider class doesn't log headers, only config.to_safe_dict()
    # which never includes raw keys
