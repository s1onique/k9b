"""Tests for LLM response truncation handling in review enrichment.

These tests verify that:
- finish_reason="length" is detected and classified as llm_completion_truncated
- The truncated failure class is propagated into the artifact failure_metadata
- The artifact has SKIPPED status with proper diagnostics
"""

import unittest

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisStatus,
)


class TestReviewEnrichmentTruncatedResponse(unittest.TestCase):
    """Test that truncated LLM responses are classified correctly."""

    def test_truncated_response_artifact_has_completion_truncated_failure_class(self) -> None:
        """Verify truncated response produces artifact with llm_completion_truncated failure_class."""
        from k8s_diag_agent.external_analysis.llamacpp_adapter_http import (
            build_llm_failure_metadata,
        )
        from k8s_diag_agent.llm.llamacpp_provider_errors import (
            LLMResponseParseError,
        )

        # Simulate the error that would be raised when LLM hits max_tokens
        truncated_error = LLMResponseParseError(
            "LLM response ended with finish_reason=length before producing parseable "
            "JSON. Increase max output tokens or disable reasoning/thinking for this provider.",
            finish_reason="length",
            response_content_chars=0,
            response_content_prefix=None,
            completion_stopped_by_length=True,
            max_tokens=1200,
        )

        # Build failure metadata as the HTTP adapter would
        metadata = build_llm_failure_metadata(
            exc=truncated_error,
            exc_type="LLMResponseParseError",
            duration_ms=500,
            timeout_value=120,
            endpoint="http://localhost:8080/v1/chat/completions",
            prompt="test prompt",
            prompt_sections=None,
            review_enrichment_max_tokens=1200,
        )

        # Verify the failure class is correct
        self.assertEqual(metadata["failure_class"], "llm_completion_truncated")
        self.assertEqual(metadata["finish_reason"], "length")
        self.assertEqual(metadata["completion_stopped_by_length"], True)
        self.assertEqual(metadata["max_tokens"], 1200)
        self.assertEqual(metadata["exception_type"], "LLMResponseParseError")

    def test_non_truncated_parse_error_has_invalid_json_failure_class(self) -> None:
        """Verify non-truncated parse errors get llm_response_invalid_json failure_class."""
        from k8s_diag_agent.external_analysis.llamacpp_adapter_http import (
            build_llm_failure_metadata,
        )
        from k8s_diag_agent.llm.llamacpp_provider_errors import (
            LLMResponseParseError,
        )

        # Simulate a parse error that's NOT due to truncation
        parse_error = LLMResponseParseError(
            "llama.cpp response text content is not valid JSON",
            finish_reason="stop",
            response_content_chars=100,
            response_content_prefix="not valid json",
            completion_stopped_by_length=False,
            max_tokens=1200,
        )

        metadata = build_llm_failure_metadata(
            exc=parse_error,
            exc_type="LLMResponseParseError",
            duration_ms=500,
            timeout_value=120,
            endpoint="http://localhost:8080/v1/chat/completions",
            prompt="test prompt",
            prompt_sections=None,
            review_enrichment_max_tokens=1200,
        )

        # Verify the failure class is invalid_json, not truncated
        self.assertEqual(metadata["failure_class"], "llm_response_invalid_json")
        self.assertEqual(metadata["completion_stopped_by_length"], False)

    def test_extract_assessment_raises_on_finish_reason_length(self) -> None:
        """Verify extract_assessment raises LLMResponseParseError when finish_reason is length."""
        from k8s_diag_agent.llm.llamacpp_provider_errors import (
            LLMResponseParseError,
        )
        from k8s_diag_agent.llm.llamacpp_provider_response import (
            _check_truncation_before_parse,
        )

        # Response with finish_reason="length" and None content
        truncated_response = {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"role": "assistant", "content": None},
                }
            ]
        }

        # Should raise LLMResponseParseError
        with self.assertRaises(LLMResponseParseError) as ctx:
            _check_truncation_before_parse(
                truncated_response, None, max_tokens=1200
            )

        exc = ctx.exception
        self.assertTrue(exc.completion_stopped_by_length)
        self.assertEqual(exc.finish_reason, "length")

    def test_extract_assessment_raises_when_content_is_truncated_json(self) -> None:
        """Verify extract_assessment raises LLMResponseParseError when JSON is truncated."""
        from k8s_diag_agent.llm.llamacpp_provider_errors import (
            LLMResponseParseError,
        )
        from k8s_diag_agent.llm.llamacpp_provider_response import (
            extract_assessment,
        )

        # Response with finish_reason="length" and truncated/incomplete JSON
        truncated_json_response = {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {
                        "role": "assistant",
                        "content": '{"incomplete": "json res',
                    },
                }
            ]
        }

        with self.assertRaises(LLMResponseParseError) as ctx:
            extract_assessment(truncated_json_response, max_tokens=1200)

        exc = ctx.exception
        self.assertTrue(exc.completion_stopped_by_length)
        self.assertEqual(exc.finish_reason, "length")

    def test_reasoning_model_response_handling(self) -> None:
        """Verify reasoning model responses with reasoning_content are handled correctly."""
        from k8s_diag_agent.llm.llamacpp_provider_response import (
            _extract_content_from_message,
        )

        # Reasoning model response (e.g., Qwen) with reasoning_content
        reasoning_response = {
            "role": "assistant",
            "content": None,
            "reasoning_content": "Let me analyze this step by step...",
        }

        # Should extract reasoning_content as fallback
        content = _extract_content_from_message(reasoning_response)
        self.assertEqual(content, "Let me analyze this step by step...")

    def test_reasoning_model_with_final_content(self) -> None:
        """Verify reasoning model with both reasoning and final content prefers final."""
        from k8s_diag_agent.llm.llamacpp_provider_response import (
            _extract_content_from_message,
        )

        # Reasoning model with both reasoning and final answer
        response_with_answer = {
            "role": "assistant",
            "content": '{"summary": "Final answer here"}',
            "reasoning_content": "My reasoning process...",
        }

        # Should extract the final content, not the reasoning
        content = _extract_content_from_message(response_with_answer)
        self.assertEqual(content, '{"summary": "Final answer here"}')


class TestTruncatedResponseIntegration(unittest.TestCase):
    """Integration-style tests for truncated response artifact generation."""

    def test_build_failure_artifact_includes_truncation_metadata(self) -> None:
        """Verify build_failure_artifact includes all truncation metadata fields."""
        from k8s_diag_agent.external_analysis.adapter import ExternalAnalysisRequest
        from k8s_diag_agent.external_analysis.llamacpp_adapter_payloads import (
            build_failure_artifact,
        )
        from k8s_diag_agent.llm.llamacpp_provider_errors import (
            LLMFailureMetadata,
        )

        # Build failure metadata with truncation info
        failure_metadata = LLMFailureMetadata(
            failure_class="llm_completion_truncated",
            exception_type="LLMResponseParseError",
            finish_reason="length",
            completion_stopped_by_length=True,
            max_tokens=1200,
            response_content_chars=0,
        ).to_dict()

        # Create a request
        request = ExternalAnalysisRequest(
            run_id="test-run-123",
            cluster_label="test-cluster",
            source_artifact="test-source.json",
        )

        # Build the failure artifact
        artifact = build_failure_artifact(
            tool_name="llamacpp",
            request=request,
            duration_ms=500,
            summary="LLM response truncated",
            status=ExternalAnalysisStatus.SKIPPED,
            skip_reason="LLM response ended with finish_reason=length",
            failure_metadata=failure_metadata,
        )

        # Verify artifact properties
        self.assertEqual(artifact.status, ExternalAnalysisStatus.SKIPPED)
        assert artifact.failure_metadata is not None
        self.assertEqual(
            artifact.failure_metadata["failure_class"], "llm_completion_truncated"
        )
        self.assertEqual(
            artifact.failure_metadata["completion_stopped_by_length"], True
        )
        self.assertEqual(artifact.failure_metadata["finish_reason"], "length")


if __name__ == "__main__":
    unittest.main()
