"""Tests for structured output hardening in llama.cpp provider.

Tests cover:
- response_format_json parameter in _build_payload
- LLMResponseParseError carries structured diagnostics
- finish_reason extraction from LLM response
- completion_stopped_by_length detection
- failure metadata includes structured output diagnostics
"""
import unittest
from typing import Any, cast

import requests

from k8s_diag_agent.llm.llamacpp_provider import (
    LlamaCppProvider,
    LlamaCppProviderConfig,
    LLMFailureMetadata,
    LLMResponseParseError,
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


class TestResponseFormatJsonPayload(unittest.TestCase):
    """Test that response_format_json parameter is included in request payload."""

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
        provider.assess("prompt", _dummy_payload(), validate_schema=False)  # type: ignore[arg-type]
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
            "prompt", _dummy_payload(), validate_schema=False, response_format_json=True  # type: ignore[arg-type]
        )
        self.assertIn("response_format", session.last_payload)
        self.assertEqual(
            session.last_payload["response_format"], {"type": "json_object"}
        )

    def test_build_payload_with_response_format_json_false(self) -> None:
        """Test that response_format is omitted when response_format_json=False."""
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
            "prompt", _dummy_payload(), validate_schema=False, response_format_json=False  # type: ignore[arg-type]
        )
        self.assertNotIn("response_format", session.last_payload)

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
            _dummy_payload(),  # type: ignore[arg-type]
            validate_schema=False,
            max_tokens=768,
            response_format_json=True,
        )
        self.assertIn("response_format", session.last_payload)
        self.assertIn("max_tokens", session.last_payload)
        self.assertEqual(session.last_payload["max_tokens"], 768)
        self.assertEqual(
            session.last_payload["response_format"], {"type": "json_object"}
        )


class TestLLMResponseParseError(unittest.TestCase):
    """Test LLMResponseParseError exception and its diagnostics."""

    def test_error_carrying_finish_reason(self) -> None:
        """Test that LLMResponseParseError carries finish_reason."""
        exc = LLMResponseParseError(
            "invalid JSON",
            finish_reason="length",
            response_content_chars=1000,
        )
        self.assertEqual(exc.finish_reason, "length")
        self.assertEqual(exc.response_content_chars, 1000)

    def test_error_completion_stopped_by_length(self) -> None:
        """Test that completion_stopped_by_length is captured."""
        exc = LLMResponseParseError(
            "invalid JSON",
            finish_reason="length",
            completion_stopped_by_length=True,
        )
        self.assertTrue(exc.completion_stopped_by_length)

    def test_to_diagnostics(self) -> None:
        """Test that to_diagnostics returns correct dict."""
        exc = LLMResponseParseError(
            "invalid JSON",
            finish_reason="length",
            response_content_chars=1500,
            response_content_prefix="some Thai text ฉาก",
            completion_stopped_by_length=True,
            max_tokens=768,
        )
        diags = exc.to_diagnostics()
        self.assertEqual(diags["finish_reason"], "length")
        self.assertEqual(diags["response_content_chars"], 1500)
        self.assertEqual(diags["response_content_prefix"], "some Thai text ฉาก")
        self.assertTrue(diags["completion_stopped_by_length"])
        self.assertEqual(diags["max_tokens"], 768)

    def test_to_diagnostics_with_none_values(self) -> None:
        """Test that to_diagnostics handles None values correctly."""
        exc = LLMResponseParseError("invalid JSON")
        diags = exc.to_diagnostics()
        self.assertIsNone(diags["finish_reason"])
        self.assertIsNone(diags["response_content_chars"])

    def test_to_diagnostics_includes_max_tokens(self) -> None:
        """Test that to_diagnostics includes max_tokens."""
        exc = LLMResponseParseError("invalid JSON", max_tokens=1200)
        diags = exc.to_diagnostics()
        self.assertEqual(diags["max_tokens"], 1200)

    def test_to_diagnostics_completion_stopped_by_length_true(self) -> None:
        """Test that completion_stopped_by_length is True when finish_reason is length."""
        exc = LLMResponseParseError(
            "invalid JSON",
            finish_reason="length",
            completion_stopped_by_length=True,
        )
        self.assertTrue(exc.completion_stopped_by_length)
        diags = exc.to_diagnostics()
        self.assertTrue(diags["completion_stopped_by_length"])


class TestExtractResponseDiagnostics(unittest.TestCase):
    """Test extraction of response diagnostics from LLM response."""

    def test_extract_finish_reason(self) -> None:
        """Test that finish_reason is extracted from response."""
        data = {
            "choices": [
                {
                    "message": {"content": "{}"},
                    "finish_reason": "stop",
                }
            ]
        }
        diags = LlamaCppProvider._extract_response_diagnostics(data)
        self.assertEqual(diags["finish_reason"], "stop")

    def test_extract_finish_reason_length(self) -> None:
        """Test that finish_reason=length is extracted correctly."""
        data = {
            "choices": [
                {
                    "message": {"content": "incomplete..."},
                    "finish_reason": "length",
                }
            ]
        }
        diags = LlamaCppProvider._extract_response_diagnostics(data)
        self.assertEqual(diags["finish_reason"], "length")

    def test_extract_content_chars(self) -> None:
        """Test that response content char count is extracted."""
        data = {
            "choices": [
                {
                    "message": {"content": "short text"},
                    "finish_reason": "stop",
                }
            ]
        }
        diags = LlamaCppProvider._extract_response_diagnostics(data)
        self.assertEqual(diags["response_content_chars"], 10)

    def test_extract_content_prefix(self) -> None:
        """Test that response content prefix is extracted."""
        data = {
            "choices": [
                {
                    "message": {"content": "ฉากฉากฉาก" * 100},
                    "finish_reason": "length",
                }
            ]
        }
        diags = LlamaCppProvider._extract_response_diagnostics(data)
        self.assertIn("response_content_chars", diags)
        self.assertEqual(diags["response_content_chars"], len("ฉากฉากฉาก" * 100))

    def test_extract_content_prefix_bounded(self) -> None:
        """Test that content prefix is bounded to max_prefix_len."""
        long_content = "x" * 1000
        data = {
            "choices": [
                {
                    "message": {"content": long_content},
                    "finish_reason": "stop",
                }
            ]
        }
        diags = LlamaCppProvider._extract_response_diagnostics(data, max_prefix_len=50)
        self.assertEqual(len(diags.get("response_content_prefix", "")), 50)

    def test_missing_choices_handled_gracefully(self) -> None:
        """Test that missing choices doesn't raise."""
        data = {"model": "test"}
        diags = LlamaCppProvider._extract_response_diagnostics(data)
        self.assertEqual(diags, {})

    def test_empty_choices_handled_gracefully(self) -> None:
        """Test that empty choices doesn't raise."""
        data: dict[str, object] = {"choices": []}
        diags = LlamaCppProvider._extract_response_diagnostics(data)
        self.assertEqual(diags, {})


class TestLLMFailureMetadataStructuredOutput(unittest.TestCase):
    """Test LLMFailureMetadata includes structured output fields."""

    def test_failure_metadata_with_finish_reason(self) -> None:
        """Test that failure_metadata includes finish_reason."""
        meta = LLMFailureMetadata(
            failure_class="llm_response_invalid_json",
            exception_type="LLMResponseParseError",
            finish_reason="length",
        )
        result = meta.to_dict()
        self.assertEqual(result["finish_reason"], "length")

    def test_failure_metadata_with_response_content_chars(self) -> None:
        """Test that failure_metadata includes response_content_chars."""
        meta = LLMFailureMetadata(
            failure_class="llm_response_invalid_json",
            exception_type="LLMResponseParseError",
            response_content_chars=1500,
        )
        result = meta.to_dict()
        self.assertEqual(result["response_content_chars"], 1500)

    def test_failure_metadata_with_response_content_prefix(self) -> None:
        """Test that failure_metadata includes response_content_prefix."""
        meta = LLMFailureMetadata(
            failure_class="llm_response_invalid_json",
            exception_type="LLMResponseParseError",
            response_content_prefix="ฉากฉาก",
        )
        result = meta.to_dict()
        self.assertEqual(result["response_content_prefix"], "ฉากฉาก")

    def test_failure_metadata_with_completion_stopped_by_length(self) -> None:
        """Test that failure_metadata includes completion_stopped_by_length."""
        meta = LLMFailureMetadata(
            failure_class="llm_response_invalid_json",
            exception_type="LLMResponseParseError",
            completion_stopped_by_length=True,
        )
        result = meta.to_dict()
        self.assertTrue(result["completion_stopped_by_length"])

    def test_failure_metadata_with_max_tokens(self) -> None:
        """Test that failure_metadata includes max_tokens."""
        meta = LLMFailureMetadata(
            failure_class="llm_response_invalid_json",
            exception_type="LLMResponseParseError",
            max_tokens=768,
        )
        result = meta.to_dict()
        self.assertEqual(result["max_tokens"], 768)

    def test_failure_metadata_with_provider_and_operation(self) -> None:
        """Test that failure_metadata includes provider and operation."""
        meta = LLMFailureMetadata(
            failure_class="llm_response_invalid_json",
            exception_type="LLMResponseParseError",
            provider="llamacpp",
            operation="review-enrichment",
        )
        result = meta.to_dict()
        self.assertEqual(result["provider"], "llamacpp")
        self.assertEqual(result["operation"], "review-enrichment")

    def test_failure_metadata_complete_structured_output(self) -> None:
        """Test complete structured output metadata."""
        meta = LLMFailureMetadata(
            failure_class="llm_response_invalid_json",
            exception_type="LLMResponseParseError",
            elapsed_ms=22650,
            endpoint="http://example.com/v1/chat/completions",
            summary="invalid JSON",
            finish_reason="length",
            response_content_chars=2000,
            response_content_prefix="ฉากฉากฉาก",
            completion_stopped_by_length=True,
            max_tokens=1200,
            provider="llamacpp",
            operation="review-enrichment",
        )
        result = meta.to_dict()
        self.assertEqual(result["failure_class"], "llm_response_invalid_json")
        self.assertEqual(result["elapsed_ms"], 22650)
        self.assertEqual(result["finish_reason"], "length")
        self.assertEqual(result["response_content_chars"], 2000)
        self.assertTrue(result["completion_stopped_by_length"])
        self.assertEqual(result["max_tokens"], 1200)
        self.assertEqual(result["provider"], "llamacpp")
        self.assertEqual(result["operation"], "review-enrichment")

    def test_failure_metadata_length_capped_class(self) -> None:
        """Test that length-capped failure uses correct failure class."""
        meta = LLMFailureMetadata(
            failure_class="llm_response_parse_error_length_capped",
            exception_type="LLMResponseParseError",
            finish_reason="length",
            completion_stopped_by_length=True,
            max_tokens=1200,
        )
        result = meta.to_dict()
        self.assertEqual(result["failure_class"], "llm_response_parse_error_length_capped")
        self.assertTrue(result["completion_stopped_by_length"])
        self.assertEqual(result["finish_reason"], "length")


if __name__ == "__main__":
    unittest.main()
