"""Tests for max_tokens completion budget and wrapped exception classification."""
import unittest
from typing import Any, cast

import requests

from k8s_diag_agent.llm.llamacpp_provider import (
    DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN,
    DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT,
    LlamaCppProvider,
    LlamaCppProviderConfig,
    LLMFailureClass,
    classify_llm_failure,
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


class TestMaxTokensDefaults(unittest.TestCase):
    """Test max_tokens defaults are correct."""

    def test_auto_drilldown_default_is_768(self) -> None:
        """Verify DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN is 768."""
        self.assertEqual(DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN, 768)

    def test_review_enrichment_default_is_1200(self) -> None:
        """Verify DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT is 1200."""
        self.assertEqual(DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT, 1200)


class TestLlamaCppProviderMaxTokens(unittest.TestCase):
    """Test that LlamaCppProvider includes max_tokens in request payload."""

    def test_assess_without_max_tokens(self) -> None:
        """Test that assess without max_tokens omits it from payload."""
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
        provider.assess("prompt", _dummy_payload(), validate_schema=False)  # type: ignore
        self.assertNotIn("max_tokens", session.last_payload)

    def test_assess_with_max_tokens(self) -> None:
        """Test that assess with max_tokens includes it in payload."""
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
        provider.assess("prompt", _dummy_payload(), max_tokens=768, validate_schema=False)  # type: ignore
        self.assertIn("max_tokens", session.last_payload)
        self.assertEqual(session.last_payload["max_tokens"], 768)

    def test_assess_auto_drilldown_value(self) -> None:
        """Test that auto-drilldown calls use 768 max_tokens."""
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
        provider.assess("prompt", _dummy_payload(), max_tokens=DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN, validate_schema=False)
        self.assertEqual(session.last_payload["max_tokens"], DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN)
        self.assertEqual(session.last_payload["max_tokens"], 768)

    def test_assess_review_enrichment_value(self) -> None:
        """Test that review-enrichment calls use 1200 max_tokens."""
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
        provider.assess("prompt", _dummy_payload(), max_tokens=DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT, validate_schema=False)
        self.assertEqual(session.last_payload["max_tokens"], DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT)
        self.assertEqual(session.last_payload["max_tokens"], 1200)


class TestMaxTokensConfig(unittest.TestCase):
    """Test max_tokens config parsing from environment."""

    def test_config_defaults(self) -> None:
        """Test that config has correct defaults for max_tokens."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
        )
        self.assertEqual(config.max_tokens_auto_drilldown, DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN)
        self.assertEqual(config.max_tokens_review_enrichment, DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT)

    def test_config_from_env_with_max_tokens(self) -> None:
        """Test that from_env parses max_tokens from environment."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_MAX_TOKENS_AUTO_DRILLDOWN": "512",
            "LLAMA_CPP_MAX_TOKENS_REVIEW_ENRICHMENT": "1000",
        }
        config = LlamaCppProviderConfig.from_env(env=env)
        self.assertEqual(config.max_tokens_auto_drilldown, 512)
        self.assertEqual(config.max_tokens_review_enrichment, 1000)

    def test_config_from_env_invalid_max_tokens(self) -> None:
        """Test that invalid max_tokens values fall back to defaults."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_MAX_TOKENS_AUTO_DRILLDOWN": "invalid",
        }
        config = LlamaCppProviderConfig.from_env(env=env)
        # Should fall back to default
        self.assertEqual(config.max_tokens_auto_drilldown, DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN)

    def test_config_from_env_negative_max_tokens(self) -> None:
        """Test that negative max_tokens values fall back to defaults."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_MAX_TOKENS_REVIEW_ENRICHMENT": "-100",
        }
        config = LlamaCppProviderConfig.from_env(env=env)
        # Should fall back to default
        self.assertEqual(config.max_tokens_review_enrichment, DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT)


class TestMaxTokensForOperation(unittest.TestCase):
    """Test max_tokens_for_operation helper method."""

    def test_returns_auto_drilldown_value(self) -> None:
        """Test that max_tokens_for_operation returns auto-drilldown value."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            max_tokens_auto_drilldown=512,
        )
        provider = LlamaCppProvider(config=config)
        self.assertEqual(provider.max_tokens_for_operation("auto-drilldown"), 512)

    def test_returns_review_enrichment_value(self) -> None:
        """Test that max_tokens_for_operation returns review-enrichment value."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            max_tokens_review_enrichment=1000,
        )
        provider = LlamaCppProvider(config=config)
        self.assertEqual(provider.max_tokens_for_operation("review-enrichment"), 1000)

    def test_returns_none_for_unknown_operation(self) -> None:
        """Test that max_tokens_for_operation returns None for unknown operation."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
        )
        provider = LlamaCppProvider(config=config)
        self.assertIsNone(provider.max_tokens_for_operation("unknown"))

    def test_config_value_used_not_constant(self) -> None:
        """Test that config value is used, not hardcoded constant."""
        custom_value = 1024
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            max_tokens_auto_drilldown=custom_value,
        )
        provider = LlamaCppProvider(config=config)
        result = provider.max_tokens_for_operation("auto-drilldown")
        self.assertEqual(result, custom_value)
        self.assertNotEqual(result, DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN)


class TestWrappedTimeoutClassification(unittest.TestCase):
    """Test that wrapped exceptions are classified correctly."""

    def test_runtime_error_wrapping_read_timeout(self) -> None:
        """Test that RuntimeError wrapping ReadTimeout is classified as read timeout."""
        # Simulate what llama.cpp provider does: catch requests.ReadTimeout and raise RuntimeError from it
        original_exc = requests.ReadTimeout("read timed out. (read timeout=120)")
        wrapped_exc = RuntimeError(
            "llama.cpp request failed: Endpoint http://example.com/api/v1/chat/completions "
            "(LLAMA_CPP_BASE_URL=http://example.com/api); ReadTimeout: read timed out. "
            "(read timeout=120); timeout=120s"
        )
        # Manually chain: wrapped_exc.__cause__ = original_exc
        wrapped_exc.__cause__ = original_exc

        failure_class, exc_type = classify_llm_failure(wrapped_exc)

        self.assertEqual(failure_class, LLMFailureClass.LLM_CLIENT_READ_TIMEOUT)
        self.assertEqual(exc_type, "ReadTimeout")

    def test_runtime_error_wrapping_connect_timeout(self) -> None:
        """Test that RuntimeError wrapping ConnectTimeout is classified as connect timeout."""
        original_exc = requests.ConnectTimeout("Connection timed out")
        wrapped_exc = RuntimeError(
            "llama.cpp request failed: Endpoint http://example.com/api/v1/chat/completions; "
            "ConnectTimeout: Connection timed out; timeout=120s"
        )
        wrapped_exc.__cause__ = original_exc

        failure_class, exc_type = classify_llm_failure(wrapped_exc)

        self.assertEqual(failure_class, LLMFailureClass.LLM_CLIENT_CONNECT_TIMEOUT)
        self.assertEqual(exc_type, "ConnectTimeout")

    def test_runtime_error_with_timeout_in_message(self) -> None:
        """Test that RuntimeError with timeout in message is classified correctly."""
        exc = RuntimeError(
            "llama.cpp request failed: Endpoint http://example.com/api/v1/chat/completions; "
            "ReadTimeout: read timed out. (read timeout=120); timeout=120s"
        )
        # No __cause__, but check if message-based fallback works
        failure_class, exc_type = classify_llm_failure(exc)

        self.assertEqual(failure_class, LLMFailureClass.LLM_CLIENT_READ_TIMEOUT)
        self.assertEqual(exc_type, "RuntimeError")

    def test_direct_read_timeout(self) -> None:
        """Test that direct ReadTimeout is classified correctly."""
        exc = requests.ReadTimeout("read timed out")
        failure_class, exc_type = classify_llm_failure(exc)

        self.assertEqual(failure_class, LLMFailureClass.LLM_CLIENT_READ_TIMEOUT)
        self.assertEqual(exc_type, "ReadTimeout")

    def test_direct_runtime_error_no_timeout(self) -> None:
        """Test that RuntimeError without timeout indicators is classified as adapter error."""
        exc = RuntimeError("Unexpected error")
        failure_class, exc_type = classify_llm_failure(exc)

        self.assertEqual(failure_class, LLMFailureClass.LLM_ADAPTER_ERROR)
        self.assertEqual(exc_type, "RuntimeError")


class TestExceptionContextClassification(unittest.TestCase):
    """Test that exceptions in __context__ are properly classified."""

    def test_runtime_error_with_read_timeout_in_context(self) -> None:
        """Test that RuntimeError with ReadTimeout in __context__ is classified correctly.

        The failure_class should be llm_client_read_timeout (from the context),
        and exc_type should be ReadTimeout (preserving the inner exception type).
        """
        original_exc = requests.ReadTimeout("read timed out")
        wrapped_exc = RuntimeError(
            "llama.cpp request failed: some error"
        )
        # __context__ is set implicitly when raising from within except block
        wrapped_exc.__context__ = original_exc

        failure_class, exc_type = classify_llm_failure(wrapped_exc)

        self.assertEqual(failure_class, LLMFailureClass.LLM_CLIENT_READ_TIMEOUT)
        self.assertEqual(exc_type, "ReadTimeout")


class TestCyclicExceptionClassification(unittest.TestCase):
    """Test that cyclic exception chains are handled defensively."""

    def test_cyclic_exception_does_not_infinite_loop(self) -> None:
        """Test that cyclic exceptions are handled without infinite recursion."""
        # Create a cyclic exception chain: A -> B -> A
        exc_a = RuntimeError("Error A")
        exc_b = RuntimeError("Error B")
        exc_a.__cause__ = exc_b
        exc_b.__cause__ = exc_a

        # Should not raise and should return adapter error (cycle protection)
        failure_class, exc_type = classify_llm_failure(exc_a)

        self.assertEqual(failure_class, LLMFailureClass.LLM_ADAPTER_ERROR)
        self.assertEqual(exc_type, "RuntimeError")

    def test_deep_exception_chain_with_cycle_protection(self) -> None:
        """Test that deep exception chains respect cycle protection."""
        # Create a chain with a cycle at the end: A -> B -> C -> B
        exc_a = RuntimeError("Error A")
        exc_b = RuntimeError("Error B")
        exc_c = RuntimeError("Error C")
        exc_a.__cause__ = exc_b
        exc_b.__cause__ = exc_c
        exc_c.__cause__ = exc_b  # cycle back to B

        failure_class, exc_type = classify_llm_failure(exc_a)

        # Should handle gracefully due to cycle protection
        self.assertEqual(failure_class, LLMFailureClass.LLM_ADAPTER_ERROR)


if __name__ == "__main__":
    unittest.main()
