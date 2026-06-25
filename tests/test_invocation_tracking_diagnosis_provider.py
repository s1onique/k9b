"""Tests for InvocationTrackingDiagnosisProvider wrapper.

These tests verify the invocation tracking wrapper that wraps the production
provider to track when complete() is called.
"""

from __future__ import annotations

from k8s_diag_agent.collect.diagnosis_provider_runtime import (
    InvocationTrackingDiagnosisProvider,
)


class MockInnerProvider:
    """Mock inner provider for testing."""

    def __init__(self, response: str = "mock response") -> None:
        self._response = response
        self._call_count = 0
        self._last_prompt: str | None = None

    def complete(self, prompt: str) -> str:
        self._call_count += 1
        self._last_prompt = prompt
        return self._response

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def last_prompt(self) -> str | None:
        return self._last_prompt


class TestInvocationTrackingDiagnosisProvider:
    """Tests for InvocationTrackingDiagnosisProvider wrapper."""

    def test_invocation_attempted_false_before_complete(self) -> None:
        """invocation_attempted is False before complete() is called."""
        inner = MockInnerProvider()
        wrapper = InvocationTrackingDiagnosisProvider(inner)

        assert wrapper.invocation_attempted is False

    def test_complete_calls_inner_complete(self) -> None:
        """complete() calls inner.complete() with the same prompt."""
        inner = MockInnerProvider(response="test response")
        wrapper = InvocationTrackingDiagnosisProvider(inner)

        result = wrapper.complete("test prompt")

        assert result == "test response"
        assert inner.call_count == 1
        assert inner.last_prompt == "test prompt"

    def test_invocation_attempted_true_after_complete(self) -> None:
        """invocation_attempted is True after complete() is called."""
        inner = MockInnerProvider()
        wrapper = InvocationTrackingDiagnosisProvider(inner)

        assert wrapper.invocation_attempted is False
        wrapper.complete("test")
        assert wrapper.invocation_attempted is True

    def test_multiple_complete_calls(self) -> None:
        """Multiple complete() calls work correctly."""
        inner = MockInnerProvider()
        wrapper = InvocationTrackingDiagnosisProvider(inner)

        wrapper.complete("prompt 1")
        wrapper.complete("prompt 2")
        wrapper.complete("prompt 3")

        assert inner.call_count == 3
        assert inner.last_prompt == "prompt 3"
        assert wrapper.invocation_attempted is True

    def test_wrapper_passes_through_response(self) -> None:
        """Wrapper returns the exact response from inner provider."""
        expected_response = '{"hypothesis": "test", "confidence": 0.95}'
        inner = MockInnerProvider(response=expected_response)
        wrapper = InvocationTrackingDiagnosisProvider(inner)

        result = wrapper.complete("diagnose this")

        assert result == expected_response
