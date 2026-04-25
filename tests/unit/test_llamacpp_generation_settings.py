"""Tests for llama.cpp generation settings configuration.

Tests cover:
- LlamaCppProviderConfig defaults for generation settings
- LLAMA_CPP_TEMPERATURE parsing from environment
- LLAMA_CPP_TOP_P parsing from environment
- LLAMA_CPP_TOP_K parsing from environment
- LLAMA_CPP_REPEAT_PENALTY parsing from environment
- LLAMA_CPP_SEED parsing from environment
- LLAMA_CPP_STOP parsing from environment
- Payload includes generation settings
- response_format_json remains default false
- Existing max_tokens tests still pass
"""
import unittest
from typing import Any, cast

import requests

from k8s_diag_agent.llm.base import LLMAssessmentInput
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


def _dummy_payload() -> LLMAssessmentInput:
    """Create a minimal test payload."""
    return LLMAssessmentInput(
        primary_snapshot={"foo": "bar"},
        secondary_snapshot={"foo": "baz"},
        comparison={"differences": {}},
        comparison_metadata=None,
        collection_statuses={"primary": {"status": "ok"}, "secondary": {"status": "ok"}},
    )


class TestGenerationSettingsDefaults(unittest.TestCase):
    """Test generation settings defaults are correct."""

    def test_temperature_default_is_zero(self) -> None:
        """Verify default temperature is 0.0 for deterministic structured output."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
        )
        self.assertEqual(config.temperature, 0.0)

    def test_top_p_default_is_none(self) -> None:
        """Verify default top_p is None."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
        )
        self.assertIsNone(config.top_p)

    def test_top_k_default_is_none(self) -> None:
        """Verify default top_k is None."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
        )
        self.assertIsNone(config.top_k)

    def test_repeat_penalty_default_is_none(self) -> None:
        """Verify default repeat_penalty is None."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
        )
        self.assertIsNone(config.repeat_penalty)

    def test_seed_default_is_none(self) -> None:
        """Verify default seed is None."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
        )
        self.assertIsNone(config.seed)

    def test_stop_default_is_none(self) -> None:
        """Verify default stop is None."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
        )
        self.assertIsNone(config.stop)


class TestGenerationSettingsFromEnv(unittest.TestCase):
    """Test generation settings parsing from environment."""

    def test_config_from_env_with_temperature(self) -> None:
        """Test that from_env parses LLAMA_CPP_TEMPERATURE."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_TEMPERATURE": "0.1",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertEqual(config.temperature, 0.1)

    def test_config_from_env_with_temperature_zero(self) -> None:
        """Test that from_env parses temperature=0."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_TEMPERATURE": "0",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertEqual(config.temperature, 0.0)

    def test_config_from_env_with_temperature_empty_defaults_zero(self) -> None:
        """Test that empty temperature defaults to 0.0."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_TEMPERATURE": "",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertEqual(config.temperature, 0.0)

    def test_config_from_env_with_temperature_invalid_defaults_zero(self) -> None:
        """Test that invalid temperature defaults to 0.0."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_TEMPERATURE": "invalid",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertEqual(config.temperature, 0.0)

    def test_config_from_env_with_top_p(self) -> None:
        """Test that from_env parses LLAMA_CPP_TOP_P."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_TOP_P": "0.9",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertEqual(config.top_p, 0.9)

    def test_config_from_env_with_top_p_invalid_defaults_none(self) -> None:
        """Test that invalid top_p defaults to None."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_TOP_P": "invalid",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertIsNone(config.top_p)

    def test_config_from_env_with_top_p_out_of_range_defaults_none(self) -> None:
        """Test that out-of-range top_p defaults to None."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_TOP_P": "2.0",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertIsNone(config.top_p)

    def test_config_from_env_with_top_k(self) -> None:
        """Test that from_env parses LLAMA_CPP_TOP_K."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_TOP_K": "40",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertEqual(config.top_k, 40)

    def test_config_from_env_with_top_k_invalid_defaults_none(self) -> None:
        """Test that invalid top_k defaults to None."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_TOP_K": "invalid",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertIsNone(config.top_k)

    def test_config_from_env_with_top_k_zero_defaults_none(self) -> None:
        """Test that zero top_k defaults to None."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_TOP_K": "0",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertIsNone(config.top_k)

    def test_config_from_env_with_repeat_penalty(self) -> None:
        """Test that from_env parses LLAMA_CPP_REPEAT_PENALTY."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_REPEAT_PENALTY": "1.1",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertEqual(config.repeat_penalty, 1.1)

    def test_config_from_env_with_seed(self) -> None:
        """Test that from_env parses LLAMA_CPP_SEED."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_SEED": "42",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertEqual(config.seed, 42)

    def test_config_from_env_with_seed_invalid_defaults_none(self) -> None:
        """Test that invalid seed defaults to None."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_SEED": "invalid",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertIsNone(config.seed)

    def test_config_from_env_with_stop_single(self) -> None:
        """Test that from_env parses single LLAMA_CPP_STOP sequence."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_STOP": "TERMINATE",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertEqual(config.stop, ("TERMINATE",))

    def test_config_from_env_with_stop_multiple(self) -> None:
        """Test that from_env parses multiple LLAMA_CPP_STOP sequences."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_STOP": "TERMINATE,END,STOP",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertEqual(config.stop, ("TERMINATE", "END", "STOP"))

    def test_config_from_env_with_stop_empty_defaults_none(self) -> None:
        """Test that empty stop defaults to None."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_STOP": "",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertIsNone(config.stop)

    def test_config_from_env_all_generation_settings(self) -> None:
        """Test that from_env parses all generation settings together."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_TEMPERATURE": "0.05",
            "LLAMA_CPP_TOP_P": "0.95",
            "LLAMA_CPP_TOP_K": "20",
            "LLAMA_CPP_REPEAT_PENALTY": "1.05",
            "LLAMA_CPP_SEED": "12345",
            "LLAMA_CPP_STOP": "END,STOP",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertEqual(config.temperature, 0.05)
        self.assertEqual(config.top_p, 0.95)
        self.assertEqual(config.top_k, 20)
        self.assertEqual(config.repeat_penalty, 1.05)
        self.assertEqual(config.seed, 12345)
        self.assertEqual(config.stop, ("END", "STOP"))


class TestPayloadIncludesGenerationSettings(unittest.TestCase):
    """Test that payload includes generation settings from config."""

    def test_assess_includes_temperature_in_payload(self) -> None:
        """Test that assess includes temperature in payload."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _CapturingSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            temperature=0.1,
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        provider.assess("prompt", _dummy_payload(), validate_schema=False)
        self.assertIn("temperature", session.last_payload)
        self.assertEqual(session.last_payload["temperature"], 0.1)

    def test_assess_includes_top_p_in_payload(self) -> None:
        """Test that assess includes top_p in payload when configured."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _CapturingSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            top_p=0.9,
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        provider.assess("prompt", _dummy_payload(), validate_schema=False)
        self.assertIn("top_p", session.last_payload)
        self.assertEqual(session.last_payload["top_p"], 0.9)

    def test_assess_includes_top_k_in_payload(self) -> None:
        """Test that assess includes top_k in payload when configured."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _CapturingSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            top_k=40,
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        provider.assess("prompt", _dummy_payload(), validate_schema=False)
        self.assertIn("top_k", session.last_payload)
        self.assertEqual(session.last_payload["top_k"], 40)

    def test_assess_includes_repeat_penalty_in_payload(self) -> None:
        """Test that assess includes repeat_penalty in payload when configured."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _CapturingSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            repeat_penalty=1.1,
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        provider.assess("prompt", _dummy_payload(), validate_schema=False)
        self.assertIn("repeat_penalty", session.last_payload)
        self.assertEqual(session.last_payload["repeat_penalty"], 1.1)

    def test_assess_includes_seed_in_payload(self) -> None:
        """Test that assess includes seed in payload when configured."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _CapturingSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            seed=42,
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        provider.assess("prompt", _dummy_payload(), validate_schema=False)
        self.assertIn("seed", session.last_payload)
        self.assertEqual(session.last_payload["seed"], 42)

    def test_assess_includes_stop_in_payload(self) -> None:
        """Test that assess includes stop in payload when configured."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _CapturingSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            stop=("END", "STOP"),
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        provider.assess("prompt", _dummy_payload(), validate_schema=False)
        self.assertIn("stop", session.last_payload)
        self.assertEqual(session.last_payload["stop"], ["END", "STOP"])

    def test_assess_omits_temperature_when_none(self) -> None:
        """Test that assess omits temperature when it's None (not default 0.0)."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _CapturingSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            temperature=None,
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        provider.assess("prompt", _dummy_payload(), validate_schema=False)
        # Temperature is None, so should not be in payload
        self.assertNotIn("temperature", session.last_payload)

    def test_assess_includes_all_generation_settings(self) -> None:
        """Test that assess includes all configured generation settings."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _CapturingSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            temperature=0.05,
            top_p=0.95,
            top_k=20,
            repeat_penalty=1.05,
            seed=12345,
            stop=("END",),
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        provider.assess("prompt", _dummy_payload(), validate_schema=False)
        self.assertEqual(session.last_payload["temperature"], 0.05)
        self.assertEqual(session.last_payload["top_p"], 0.95)
        self.assertEqual(session.last_payload["top_k"], 20)
        self.assertEqual(session.last_payload["repeat_penalty"], 1.05)
        self.assertEqual(session.last_payload["seed"], 12345)
        self.assertEqual(session.last_payload["stop"], ["END"])


class TestResponseFormatJsonStillDefaultsFalse(unittest.TestCase):
    """Test that response_format_json still defaults to False."""

    def test_response_format_json_still_defaults_false(self) -> None:
        """Verify response_format_json still defaults to False."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
        )
        self.assertFalse(config.response_format_json)

    def test_response_format_json_from_env_true(self) -> None:
        """Verify response_format_json can still be set to True via env."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_RESPONSE_FORMAT_JSON": "true",
        }
        config = LlamaCppProviderConfig.from_env(env)
        self.assertTrue(config.response_format_json)


class TestGenerationSettingsProperty(unittest.TestCase):
    """Test generation_settings property returns correct dict."""

    def test_generation_settings_empty_when_all_none(self) -> None:
        """Test that generation_settings returns empty dict when all are None."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
        )
        # Only temperature has a non-None default (0.0)
        settings = config.generation_settings
        self.assertEqual(settings, {"temperature": 0.0})

    def test_generation_settings_includes_non_none_values(self) -> None:
        """Test that generation_settings includes all non-None values."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            temperature=0.05,
            top_p=0.9,
            top_k=40,
            repeat_penalty=1.1,
            seed=42,
            stop=("END",),
        )
        settings = config.generation_settings
        self.assertEqual(settings["temperature"], 0.05)
        self.assertEqual(settings["top_p"], 0.9)
        self.assertEqual(settings["top_k"], 40)
        self.assertEqual(settings["repeat_penalty"], 1.1)
        self.assertEqual(settings["seed"], 42)
        self.assertEqual(settings["stop_count"], 1)


if __name__ == "__main__":
    unittest.main()
