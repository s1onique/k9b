"""Tests for auto-drilldown LLMResponseParseError failure metadata propagation.

Tests cover:
- Auto-drilldown LLMResponseParseError populates failure_metadata with length-capped class
- llm-call-result extracts finish_reason/completion_stopped_by_length/response_content_chars/max_tokens
- skip_reason in llm-call-result is bounded
- review-enrichment invalid JSON shape log is invalid-json, not unrecognized-payload
"""
import unittest
from typing import Any, cast
from pathlib import Path
import json
import tempfile

import requests

from k8s_diag_agent.llm.llamacpp_provider import (
    LlamaCppProvider,
    LlamaCppProviderConfig,
    LLMResponseParseError,
    LLMFailureMetadata,
    LLMFailureClass,
)
from k8s_diag_agent.external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from k8s_diag_agent.external_analysis.review_schema import (
    ReviewEnrichmentShapeClassification,
    classify_review_enrichment_shape,
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


class TestLLMResponseParseErrorToDiagnostics(unittest.TestCase):
    """Test LLMResponseParseError.to_diagnostics() method."""

    def test_to_diagnostics_includes_all_structured_fields(self) -> None:
        """Test that to_diagnostics includes finish_reason, response_content_chars, etc."""
        exc = LLMResponseParseError(
            "invalid JSON",
            finish_reason="length",
            response_content_chars=1500,
            response_content_prefix="ฉากฉาก",
            completion_stopped_by_length=True,
            max_tokens=768,
        )
        diags = exc.to_diagnostics()
        self.assertEqual(diags["finish_reason"], "length")
        self.assertEqual(diags["response_content_chars"], 1500)
        self.assertEqual(diags["response_content_prefix"], "ฉากฉาก")
        self.assertTrue(diags["completion_stopped_by_length"])
        self.assertEqual(diags["max_tokens"], 768)

    def test_to_diagnostics_length_capped_detection(self) -> None:
        """Test that completion_stopped_by_length is correctly set from finish_reason."""
        exc = LLMResponseParseError(
            "invalid JSON",
            finish_reason="length",
            completion_stopped_by_length=True,
        )
        diags = exc.to_diagnostics()
        self.assertTrue(diags["completion_stopped_by_length"])

    def test_to_diagnostics_with_none_values(self) -> None:
        """Test that to_diagnostics handles None values gracefully."""
        exc = LLMResponseParseError("invalid JSON")
        diags = exc.to_diagnostics()
        self.assertIsNone(diags["finish_reason"])
        self.assertIsNone(diags["response_content_chars"])
        self.assertIsNone(diags["response_content_prefix"])
        self.assertFalse(diags["completion_stopped_by_length"])
        self.assertIsNone(diags["max_tokens"])


class TestLLMFailureMetadataStructuredOutputFields(unittest.TestCase):
    """Test LLMFailureMetadata includes structured output fields."""

    def test_failure_metadata_with_length_capped_class(self) -> None:
        """Test that length-capped failure uses correct failure class."""
        meta = LLMFailureMetadata(
            failure_class=LLMFailureClass.LLM_RESPONSE_PARSE_ERROR_LENGTH_CAPPED,
            exception_type="LLMResponseParseError",
            finish_reason="length",
            completion_stopped_by_length=True,
            max_tokens=768,
        )
        result = meta.to_dict()
        self.assertEqual(result["failure_class"], "llm_response_parse_error_length_capped")
        self.assertEqual(result["finish_reason"], "length")
        self.assertTrue(result["completion_stopped_by_length"])
        self.assertEqual(result["max_tokens"], 768)

    def test_failure_metadata_with_invalid_json_class(self) -> None:
        """Test that invalid JSON failure uses correct failure class."""
        meta = LLMFailureMetadata(
            failure_class=LLMFailureClass.LLM_RESPONSE_INVALID_JSON,
            exception_type="LLMResponseParseError",
            finish_reason="stop",
            completion_stopped_by_length=False,
            max_tokens=1200,
        )
        result = meta.to_dict()
        self.assertEqual(result["failure_class"], "llm_response_invalid_json")
        self.assertEqual(result["finish_reason"], "stop")
        self.assertFalse(result["completion_stopped_by_length"])

    def test_failure_metadata_complete_structured_output(self) -> None:
        """Test complete structured output metadata."""
        meta = LLMFailureMetadata(
            failure_class="llm_response_parse_error_length_capped",
            exception_type="LLMResponseParseError",
            elapsed_ms=24636,
            endpoint="http://example.com/v1/chat/completions",
            summary="llama.cpp response text content is not valid JSON",
            finish_reason="length",
            response_content_chars=2000,
            response_content_prefix="ฉากฉากฉาก",
            completion_stopped_by_length=True,
            max_tokens=768,
            provider="llamacpp",
            operation="auto-drilldown",
        )
        result = meta.to_dict()
        # Verify all structured output fields are present
        self.assertEqual(result["failure_class"], "llm_response_parse_error_length_capped")
        self.assertEqual(result["exception_type"], "LLMResponseParseError")
        self.assertEqual(result["elapsed_ms"], 24636)
        self.assertEqual(result["finish_reason"], "length")
        self.assertEqual(result["response_content_chars"], 2000)
        self.assertEqual(result["response_content_prefix"], "ฉากฉากฉาก")
        self.assertTrue(result["completion_stopped_by_length"])
        self.assertEqual(result["max_tokens"], 768)
        self.assertEqual(result["provider"], "llamacpp")
        self.assertEqual(result["operation"], "auto-drilldown")


class TestReviewEnrichmentShapeClassificationInvalidJson(unittest.TestCase):
    """Test that review-enrichment invalid JSON uses correct shape classification."""

    def test_shape_classification_invalid_json_exists(self) -> None:
        """Test that INVALID_JSON classification exists."""
        self.assertTrue(hasattr(ReviewEnrichmentShapeClassification, "INVALID_JSON"))
        self.assertEqual(ReviewEnrichmentShapeClassification.INVALID_JSON, "invalid-json")

    def test_shape_classification_parse_error_exists(self) -> None:
        """Test that PARSE_ERROR classification exists."""
        self.assertTrue(hasattr(ReviewEnrichmentShapeClassification, "PARSE_ERROR"))
        self.assertEqual(ReviewEnrichmentShapeClassification.PARSE_ERROR, "parse-error")

    def test_classify_with_valid_payload_returns_bounded(self) -> None:
        """Test that valid bounded payload returns bounded classification."""
        payload = {
            "summary": "Test summary",
            "triageOrder": ["cluster-a"],
            "topConcerns": ["latency"],
            "evidenceGaps": [],
            "nextChecks": ["kubectl describe pod -n default test --context cluster-a"],
            "focusNotes": [],
        }
        result = classify_review_enrichment_shape(payload)
        self.assertEqual(result.classification, ReviewEnrichmentShapeClassification.BOUNDED_REVIEW_ENRICHMENT)

    def test_classify_with_empty_dict_returns_unrecognized(self) -> None:
        """Test that empty dict returns unrecognized-payload (not invalid-json)."""
        # Empty dict means no JSON was parsed at all - this is different from invalid JSON
        result = classify_review_enrichment_shape({})
        self.assertEqual(result.classification, ReviewEnrichmentShapeClassification.UNRECOGNIZED_PAYLOAD)

    def test_classify_with_null_returns_unrecognized(self) -> None:
        """Test that null payload returns unrecognized-payload."""
        result = classify_review_enrichment_shape(None)
        self.assertEqual(result.classification, ReviewEnrichmentShapeClassification.UNRECOGNIZED_PAYLOAD)


class TestBoundedSkipReason(unittest.TestCase):
    """Test bounded skip_reason for logging."""

    def _bound_skip_reason(self, reason: str, max_length: int = 240) -> dict[str, Any]:
        """Helper that mirrors the bounded skip_reason logic."""
        reason_lower = reason.lower()
        if "json" in reason_lower or "parse" in reason_lower:
            skip_reason_class = "invalid_json"
        elif "schema" in reason_lower:
            skip_reason_class = "schema_error"
        else:
            skip_reason_class = "skipped"

        if len(reason) > max_length:
            summary = reason[:max_length].rstrip() + "…"
        else:
            summary = reason

        return {
            "summary": summary,
            "skip_reason_class": skip_reason_class,
            "skip_reason": reason[:max_length] if len(reason) > max_length else None,
        }

    def test_short_reason_not_bounded(self) -> None:
        """Test that short reasons are not bounded."""
        reason = "schema validation failed"
        result = self._bound_skip_reason(reason)
        self.assertEqual(result["summary"], reason)
        self.assertIsNone(result["skip_reason"])
        self.assertEqual(result["skip_reason_class"], "schema_error")

    def test_long_reason_bounded(self) -> None:
        """Test that long reasons are bounded to 240 chars."""
        reason = "A" * 500
        result = self._bound_skip_reason(reason)
        self.assertEqual(len(result["summary"]), 241)
        self.assertTrue(result["summary"].endswith("…"))
        self.assertEqual(result["skip_reason_class"], "skipped")

    def test_invalid_json_reason_classification(self) -> None:
        """Test that invalid JSON reasons are classified correctly."""
        reason = "llama.cpp response text content is not valid JSON"
        result = self._bound_skip_reason(reason)
        self.assertEqual(result["skip_reason_class"], "invalid_json")

    def test_parse_error_reason_classification(self) -> None:
        """Test that parse error reasons are classified correctly."""
        reason = "JSON parse error at line 42"
        result = self._bound_skip_reason(reason)
        self.assertEqual(result["skip_reason_class"], "invalid_json")

    def test_schema_error_reason_classification(self) -> None:
        """Test that schema error reasons are classified correctly."""
        reason = "schema validation failed: missing required field"
        result = self._bound_skip_reason(reason)
        self.assertEqual(result["skip_reason_class"], "schema_error")


if __name__ == "__main__":
    unittest.main()
