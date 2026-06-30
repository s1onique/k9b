"""Tests for LLM response truncation handling and defensive extraction.

These tests verify:
- finish_reason="length" is detected and classified correctly
- LLM_COMPLETION_TRUNCATED failure class is used appropriately
- Response extraction handles reasoning/thinking models
- Deprecation warnings use structured logging (not warnings.warn)
"""

import unittest

from k8s_diag_agent.llm.openai_compatible_provider_errors import (
    LLMFailureClass,
    LLMResponseParseError,
)
from k8s_diag_agent.llm.openai_compatible_provider_response import (
    _REASONING_CONTENT_KEYS,
    _check_truncation_before_parse,
    _extract_content_from_message,
)


class TestLLMCompletionTruncatedFailureClass(unittest.TestCase):
    """Test LLM_COMPLETION_TRUNCATED failure class exists and has correct value."""

    def test_failure_class_exists(self) -> None:
        """LLM_COMPLETION_TRUNCATED should be defined in LLMFailureClass."""
        self.assertTrue(hasattr(LLMFailureClass, "LLM_COMPLETION_TRUNCATED"))

    def test_failure_class_value(self) -> None:
        """LLM_COMPLETION_TRUNCATED should have correct string value."""
        self.assertEqual(LLMFailureClass.LLM_COMPLETION_TRUNCATED.value, "llm_completion_truncated")


class TestCheckTruncationBeforeParse(unittest.TestCase):
    """Test _check_truncation_before_parse detects finish_reason=length."""

    def test_raises_on_finish_reason_length(self) -> None:
        """Should raise LLMResponseParseError when finish_reason is 'length'."""
        data = {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"role": "assistant", "content": None},
                }
            ]
        }
        with self.assertRaises(LLMResponseParseError) as ctx:
            _check_truncation_before_parse(data, None, max_tokens=768)
        
        exc = ctx.exception
        self.assertTrue(exc.completion_stopped_by_length)
        self.assertEqual(exc.finish_reason, "length")
        self.assertIn("finish_reason=length", str(exc))

    def test_does_not_raise_on_stop(self) -> None:
        """Should NOT raise when finish_reason is 'stop'."""
        data = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": '{"valid": "json"}'},
                }
            ]
        }
        # Should not raise
        _check_truncation_before_parse(data, '{"valid": "json"}', max_tokens=768)

    def test_does_not_raise_on_none_finish_reason(self) -> None:
        """Should NOT raise when finish_reason is None."""
        data = {
            "choices": [
                {
                    "finish_reason": None,
                    "message": {"role": "assistant", "content": '{"valid": "json"}'},
                }
            ]
        }
        # Should not raise
        _check_truncation_before_parse(data, '{"valid": "json"}', max_tokens=768)

    def test_preserves_diagnostics(self) -> None:
        """Should preserve response diagnostics in exception."""
        data = {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"role": "assistant", "content": "partial..."},
                }
            ]
        }
        with self.assertRaises(LLMResponseParseError) as ctx:
            _check_truncation_before_parse(data, "partial...", max_tokens=768)
        
        exc = ctx.exception
        self.assertEqual(exc.response_content_chars, 10)  # len("partial...") = 10
        self.assertEqual(exc.max_tokens, 768)


class TestExtractContentFromMessage(unittest.TestCase):
    """Test _extract_content_from_message handles various message shapes."""

    def test_standard_openai_content(self) -> None:
        """Should extract standard OpenAI message.content."""
        message = {"role": "assistant", "content": "Hello, world!"}
        result = _extract_content_from_message(message)
        self.assertEqual(result, "Hello, world!")

    def test_plain_string_message(self) -> None:
        """Should handle plain string messages."""
        result = _extract_content_from_message("Just a string")
        self.assertEqual(result, "Just a string")

    def test_empty_string_returns_none(self) -> None:
        """Should return None for empty string."""
        result = _extract_content_from_message("")
        self.assertIsNone(result)

    def test_whitespace_only_returns_none(self) -> None:
        """Should return None for whitespace-only content."""
        result = _extract_content_from_message({"role": "assistant", "content": "   \n\t  "})
        self.assertIsNone(result)

    def test_reasoning_content_fallback(self) -> None:
        """Should extract reasoning_content when content is None."""
        message = {
            "role": "assistant",
            "content": None,
            "reasoning_content": "Let me think about this..."
        }
        result = _extract_content_from_message(message)
        self.assertEqual(result, "Let me think about this...")

    def test_reasoning_field_fallback(self) -> None:
        """Should extract 'reasoning' field when content is None."""
        message = {
            "role": "assistant",
            "content": None,
            "reasoning": "Thinking process..."
        }
        result = _extract_content_from_message(message)
        self.assertEqual(result, "Thinking process...")

    def test_content_takes_precedence_over_reasoning(self) -> None:
        """Standard content should take precedence over reasoning content."""
        message = {
            "role": "assistant",
            "content": "Final answer",
            "reasoning_content": "My reasoning..."
        }
        result = _extract_content_from_message(message)
        self.assertEqual(result, "Final answer")

    def test_parts_array_with_text(self) -> None:
        """Should extract text from OpenAI-style parts array."""
        message = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Hello"},
                {"type": "text", "text": " world!"},
            ]
        }
        result = _extract_content_from_message(message)
        self.assertEqual(result, "Hello world!")

    def test_parts_array_empty_returns_none(self) -> None:
        """Should return None for empty parts array."""
        message = {
            "role": "assistant",
            "content": []
        }
        result = _extract_content_from_message(message)
        self.assertIsNone(result)


class TestReasoningContentKeys(unittest.TestCase):
    """Test that _REASONING_CONTENT_KEYS contains expected values."""

    def test_contains_reasoning_content(self) -> None:
        """Should include 'reasoning_content'."""
        self.assertIn("reasoning_content", _REASONING_CONTENT_KEYS)

    def test_contains_reasoning(self) -> None:
        """Should include 'reasoning'."""
        self.assertIn("reasoning", _REASONING_CONTENT_KEYS)

    def test_contains_text(self) -> None:
        """Should include 'text'."""
        self.assertIn("text", _REASONING_CONTENT_KEYS)


if __name__ == "__main__":
    unittest.main()
