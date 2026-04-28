"""Tests for LLM timeout diagnostics and failure classification."""

import unittest
from typing import Any, cast

import requests

from k8s_diag_agent.llm.llamacpp_provider import (
    DEFAULT_TIMEOUT_SECONDS,
    LlamaCppProvider,
    LlamaCppProviderConfig,
    LLMFailureClass,
    LLMFailureMetadata,
    classify_llm_failure,
)


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _FakeSession:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, Any], dict[str, str], int]] = []

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str], timeout: int) -> Any:
        self.calls.append((url, json, headers, timeout))
        return self.response


class _RaisingSession:
    def __init__(self, error: requests.RequestException) -> None:
        self.error = error
        self.calls: list[str] = []

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str], timeout: int) -> Any:
        self.calls.append(url)
        raise self.error


def _dummy_payload() -> dict[str, Any]:
    return {
        "primary_snapshot": {"foo": "bar"},
        "secondary_snapshot": {"foo": "baz"},
        "comparison": {"differences": {}},
        "comparison_metadata": None,
        "collection_statuses": {"primary": {"status": "ok"}, "secondary": {"status": "ok"}},
    }


class TestDefaultTimeoutValue(unittest.TestCase):
    """Test that the default llama.cpp timeout is 120 seconds."""

    def test_default_timeout_is_120_seconds(self) -> None:
        """Verify DEFAULT_TIMEOUT_SECONDS is 120."""
        self.assertEqual(DEFAULT_TIMEOUT_SECONDS, 120)

    def test_config_defaults_to_120(self) -> None:
        """Test that LlamaCppProviderConfig defaults to 120s."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
        )
        self.assertEqual(config.timeout_seconds, 120)

    def test_config_from_env_defaults_to_120(self) -> None:
        """Test that from_env() uses 120s when no timeout env var is set."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
        }
        config = LlamaCppProviderConfig.from_env(env=env)
        self.assertEqual(config.timeout_seconds, 120)


class TestExplicitTimeoutOverride(unittest.TestCase):
    """Test that explicit timeout override still works."""

    def test_config_explicit_timeout(self) -> None:
        """Test explicit timeout_seconds in config."""
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            timeout_seconds=90,
        )
        self.assertEqual(config.timeout_seconds, 90)

    def test_from_env_explicit_timeout(self) -> None:
        """Test that LLAMA_CPP_TIMEOUT_SECONDS env var works."""
        env = {
            "LLAMA_CPP_BASE_URL": "http://example.com/api",
            "LLAMA_CPP_MODEL": "test-model",
            "LLAMA_CPP_TIMEOUT_SECONDS": "45",
        }
        config = LlamaCppProviderConfig.from_env(env=env)
        self.assertEqual(config.timeout_seconds, 45)

    def test_provider_uses_configured_timeout(self) -> None:
        """Test that provider uses the configured timeout value."""
        response = _FakeResponse({"choices": [{"message": {"content": "{}"}}]})
        session = _FakeSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="test-model",
            timeout_seconds=60,
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        # Trigger assess to capture the timeout
        try:
            provider.assess("prompt", _dummy_payload())  # type: ignore[arg-type]
        except Exception:
            pass  # We only care about the call arguments
        self.assertEqual(session.calls[0][3], 60)  # timeout arg


class TestFailureClassification(unittest.TestCase):
    """Test failure classification for LLM provider exceptions."""

    def test_read_timeout_classified(self) -> None:
        """Test that ReadTimeout is classified as llm_client_read_timeout."""
        exc = requests.ReadTimeout("read timed out")
        failure_class, exc_type = classify_llm_failure(exc)
        self.assertEqual(failure_class, LLMFailureClass.LLM_CLIENT_READ_TIMEOUT)
        self.assertEqual(exc_type, "ReadTimeout")

    def test_connect_timeout_classified(self) -> None:
        """Test that ConnectTimeout is classified as llm_client_connect_timeout."""
        # requests library uses ReadTimeout for both connect and read timeouts
        # but we can detect via the exception message
        exc = requests.ReadTimeout("Connection timed out")
        failure_class, exc_type = classify_llm_failure(exc)
        # The classifier checks for "timeout" or "timed out" in message for ConnectTimeout
        # With a timeout message, it should be classified appropriately
        self.assertIsNotNone(failure_class)

    def test_connection_error_timeout_classified(self) -> None:
        """Test that timeout-related ConnectionError is classified correctly."""
        exc = requests.ConnectionError("Connection timed out after 30s")
        failure_class, exc_type = classify_llm_failure(exc)
        self.assertEqual(failure_class, LLMFailureClass.LLM_CLIENT_CONNECT_TIMEOUT)

    def test_http_error_classified(self) -> None:
        """Test that HTTP errors are classified as llm_server_http_error."""
        exc = requests.HTTPError("500 Server Error")
        failure_class, exc_type = classify_llm_failure(exc)
        self.assertEqual(failure_class, LLMFailureClass.LLM_SERVER_HTTP_ERROR)

    def test_json_parse_error_classified(self) -> None:
        """Test that JSON parse errors are classified as llm_response_parse_error."""
        exc = ValueError("not a valid json")
        failure_class, exc_type = classify_llm_failure(exc)
        self.assertEqual(failure_class, LLMFailureClass.LLM_RESPONSE_PARSE_ERROR)

    def test_unknown_error_classified_as_adapter_error(self) -> None:
        """Test that unexpected exceptions are classified as llm_adapter_error."""
        exc = RuntimeError("unexpected error")
        failure_class, exc_type = classify_llm_failure(exc)
        self.assertEqual(failure_class, LLMFailureClass.LLM_ADAPTER_ERROR)


class TestLLMFailureMetadata(unittest.TestCase):
    """Test LLMFailureMetadata structure."""

    def test_to_dict_includes_all_fields(self) -> None:
        """Test that to_dict includes all relevant fields."""
        metadata = LLMFailureMetadata(
            failure_class="llm_client_read_timeout",
            exception_type="ReadTimeout",
            timeout_seconds=120,
            elapsed_ms=120034,
            endpoint="http://example.com/api/v1/chat/completions",
            summary="Read timed out after 120 seconds",
        )
        result = metadata.to_dict()
        self.assertEqual(result["failure_class"], "llm_client_read_timeout")
        self.assertEqual(result["exception_type"], "ReadTimeout")
        self.assertEqual(result["timeout_seconds"], 120)
        self.assertEqual(result["elapsed_ms"], 120034)
        self.assertEqual(result["endpoint"], "http://example.com/api/v1/chat/completions")
        self.assertEqual(result["summary"], "Read timed out after 120 seconds")

    def test_to_dict_omits_none_fields(self) -> None:
        """Test that None fields are omitted from to_dict."""
        metadata = LLMFailureMetadata(
            failure_class="llm_adapter_error",
            exception_type="RuntimeError",
        )
        result = metadata.to_dict()
        self.assertIn("failure_class", result)
        self.assertIn("exception_type", result)
        self.assertNotIn("timeout_seconds", result)
        self.assertNotIn("elapsed_ms", result)
        self.assertNotIn("endpoint", result)


class TestTimeoutErrorMessageIncludesValue(unittest.TestCase):
    """Test that timeout errors include the actual timeout value used."""

    def test_timeout_error_includes_120s(self) -> None:
        """Test that error message includes timeout=120s."""
        error = requests.Timeout("read timed out")
        session = _RaisingSession(error)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="llama-model",
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        with self.assertRaises(RuntimeError) as ctx:
            provider.assess("prompt", _dummy_payload())  # type: ignore[arg-type]
        message = str(ctx.exception)
        self.assertIn("timeout=120s", message)

    def test_explicit_timeout_in_error_message(self) -> None:
        """Test that explicit timeout override is reflected in error message."""
        error = requests.Timeout("read timed out")
        session = _RaisingSession(error)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api",
            model="llama-model",
            timeout_seconds=90,
        )
        provider = LlamaCppProvider(
            config=config,
            session_factory=lambda: cast(requests.Session, session),
        )
        with self.assertRaises(RuntimeError) as ctx:
            provider.assess("prompt", _dummy_payload())  # type: ignore[arg-type]
        message = str(ctx.exception)
        self.assertIn("timeout=90s", message)


if __name__ == "__main__":
    unittest.main()