"""Tests for response_format_json configuration in llama.cpp provider.

Tests cover:
- LlamaCppProviderConfig defaults response_format_json=false
- LLAMA_CPP_RESPONSE_FORMAT_JSON=true enables response_format in payload
- Production assess() omits response_format by default
- Explicit response_format_json=True still includes response_format for tests/manual use
- Assess with None uses config default
"""
import unittest
from typing import Any, cast

import requests

from k8s_diag_agent.llm.llamacpp_provider import (
    LlamaCppProvider,
    LlamaCppProviderConfig,
)


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _CapturingSession:
    """Session that captures the last request payload for verification."""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.last_payload: dict[str, Any] = {}

    def post(
        self, url: str, json: dict[str, Any], headers: dict[str, str], timeout: int
    ) -> Any:
        self.last_payload = json
        return self.response


def _dummy_payload() -> dict[str, Any]:
    return {
        "primary_snapshot": {"foo": "bar"},
        "secondary_snapshot": {"foo": "baz"},
        "comparison": {"differences": {}},
        "comparison_metadata": None,
        "collection_statuses": {"primary": {"status": "ok"}, "secondary": {"status": "ok"}},
    }


class TestResponseFormatJsonConfigDefault(unittest.TestCase):
    """Test that response_format_json defaults to False."""

    def test_config_default_is_false(self) -> None:
        """Test that response_format_json field defaults to False."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
        )
        self.assertFalse(config.response_format_json)

    def test_config_from_env_defaults_false(self) -> None:
        """Test that from_env defaults response_format_json to False when env var not set."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertFalse(config.response_format_json)

    def test_config_from_env_with_true(self) -> None:
        """Test that from_env parses LLAMA_CPP_RESPONSE_FORMAT_JSON=true."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_RESPONSE_FORMAT_JSON": "true",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertTrue(config.response_format_json)

    def test_config_from_env_with_1(self) -> None:
        """Test that from_env parses LLAMA_CPP_RESPONSE_FORMAT_JSON=1."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_RESPONSE_FORMAT_JSON": "1",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertTrue(config.response_format_json)

    def test_config_from_env_with_yes(self) -> None:
        """Test that from_env parses LLAMA_CPP_RESPONSE_FORMAT_JSON=yes."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_RESPONSE_FORMAT_JSON": "yes",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertTrue(config.response_format_json)

    def test_config_from_env_with_false(self) -> None:
        """Test that from_env parses LLAMA_CPP_RESPONSE_FORMAT_JSON=false."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_RESPONSE_FORMAT_JSON": "false",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertFalse(config.response_format_json)

    def test_config_from_env_with_0(self) -> None:
        """Test that from_env parses LLAMA_CPP_RESPONSE_FORMAT_JSON=0."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_RESPONSE_FORMAT_JSON": "0",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertFalse(config.response_format_json)

    def test_config_from_env_with_empty(self) -> None:
        """Test that from_env parses empty LLAMA_CPP_RESPONSE_FORMAT_JSON as False."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_RESPONSE_FORMAT_JSON": "",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertFalse(config.response_format_json)

    def test_config_from_env_with_unknown_value_defaults_false(self) -> None:
        """Test that unknown values default to False for safety."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_RESPONSE_FORMAT_JSON": "maybe",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertFalse(config.response_format_json)


class TestAssessOmitResponseFormatByDefault(unittest.TestCase):
    """Test that assess() omits response_format by default."""

    def test_assess_omits_response_format_when_config_false(self) -> None:
        """Test that assess() omits response_format when config.response_format_json=False."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _CapturingSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            response_format_json=False,
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        # Don't pass response_format_json, rely on config default
        provider.assess("prompt", _dummy_payload(), validate_schema=False)
        self.assertNotIn("response_format", session.last_payload)

    def test_assess_uses_config_true_when_param_none(self) -> None:
        """Test that assess() uses config response_format_json when param is None."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _CapturingSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            response_format_json=True,
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        # Don't pass response_format_json - should use config default (True)
        provider.assess("prompt", _dummy_payload(), validate_schema=False)
        self.assertIn("response_format", session.last_payload)
        self.assertEqual(session.last_payload["response_format"], {"type": "json_object"})


class TestAssessExplicitResponseFormatJson(unittest.TestCase):
    """Test that explicit response_format_json=True still works."""

    def test_assess_with_explicit_true_includes_response_format(self) -> None:
        """Test that passing response_format_json=True includes response_format."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _CapturingSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            response_format_json=False,
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        # Explicitly pass response_format_json=True
        provider.assess(
            "prompt",
            _dummy_payload(),
            validate_schema=False,
            response_format_json=True,
        )
        self.assertIn("response_format", session.last_payload)
        self.assertEqual(session.last_payload["response_format"], {"type": "json_object"})

    def test_assess_with_explicit_false_omits_response_format(self) -> None:
        """Test that passing response_format_json=False explicitly omits response_format."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _CapturingSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            response_format_json=True,
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        # Explicitly pass response_format_json=False to override config
        provider.assess(
            "prompt",
            _dummy_payload(),
            validate_schema=False,
            response_format_json=False,
        )
        self.assertNotIn("response_format", session.last_payload)


class TestResponseFormatJsonPayloadIntegration(unittest.TestCase):
    """Integration tests for response_format_json in _build_payload."""

    def test_build_payload_without_response_format_json(self) -> None:
        """Test that response_format is omitted by default."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _CapturingSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        provider.assess("prompt", _dummy_payload(), validate_schema=False)
        self.assertNotIn("response_format", session.last_payload)

    def test_build_payload_with_response_format_json_true(self) -> None:
        """Test that response_format is included when response_format_json=True."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _CapturingSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        provider.assess(
            "prompt", _dummy_payload(), validate_schema=False, response_format_json=True
        )
        self.assertIn("response_format", session.last_payload)
        self.assertEqual(session.last_payload["response_format"], {"type": "json_object"})

    def test_response_format_and_max_tokens_together(self) -> None:
        """Test that both response_format and max_tokens can be used together."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _CapturingSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        provider.assess(
            "prompt",
            _dummy_payload(),
            validate_schema=False,
            max_tokens=768,
            response_format_json=True,
        )
        self.assertIn("response_format", session.last_payload)
        self.assertIn("max_tokens", session.last_payload)
        self.assertEqual(session.last_payload["max_tokens"], 768)
        self.assertEqual(session.last_payload["response_format"], {"type": "json_object"})


if __name__ == "__main__":
    unittest.main()
