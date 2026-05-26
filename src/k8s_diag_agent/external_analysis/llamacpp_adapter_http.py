"""HTTP execution helpers for llamacpp adapter.

This module extracts the HTTP execution and failure handling from llamacpp_adapter.py,
providing focused helpers for:
- Running HTTP-based LLM assessments
- Building failure metadata with prompt diagnostics
- Handling parse errors and exceptions
"""

from __future__ import annotations

import time
from typing import Any

from ..llm.call_labels import build_llm_call_id
from ..llm.llamacpp_provider import (
    _REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS,
    DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT,
    DEFAULT_TIMEOUT_SECONDS,
    LLMFailureMetadata,
    LLMResponseParseError,
    classify_llm_failure,
)
from ..llm.prompt_diagnostics import (
    build_full_prompt_diagnostics,
    build_prompt_diagnostics,
)
from .adapter import ExternalAnalysisRequest
from .artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from .llamacpp_adapter_payloads import build_failure_artifact, build_success_artifact
from .review_schema import ReviewEnrichmentPayload, ReviewEnrichmentPayloadError


def build_llm_failure_metadata(
    exc: Exception,
    exc_type: str,
    duration_ms: int,
    timeout_value: int,
    endpoint: str | None,
    prompt: str,
    prompt_sections: list[Any] | None,
    review_enrichment_max_tokens: int,
) -> dict[str, Any]:
    """Build failure metadata for LLM parse errors with diagnostics."""
    failure_class_value = (
        "llm_response_parse_error_length_capped"
        if isinstance(exc, LLMResponseParseError) and exc.completion_stopped_by_length
        else "llm_response_invalid_json"
    )
    metadata = LLMFailureMetadata(
        failure_class=failure_class_value,
        exception_type=exc_type,
        timeout_seconds=timeout_value,
        elapsed_ms=duration_ms,
        endpoint=endpoint,
        summary=str(exc),
        **(exc.to_diagnostics() if isinstance(exc, LLMResponseParseError) else {}),
    ).to_dict()
    if prompt_sections:
        try:
            prompt_diags = build_prompt_diagnostics(
                provider="llamacpp",
                operation="review-enrichment",
                sections=prompt_sections,
                actual_prompt_chars=len(prompt) if prompt else 0,
                max_tokens=review_enrichment_max_tokens,
                timeout_seconds=timeout_value,
                elapsed_ms=duration_ms,
                failure_class=failure_class_value,
                exception_type=exc_type,
            )
            metadata["prompt_diagnostics"] = prompt_diags.to_dict()
        except (ValueError, TypeError, AttributeError):
            pass  # REVIEWED: Non-fatal
    return metadata


def build_generic_failure_metadata(
    exc: Exception,
    exc_type: str,
    duration_ms: int,
    timeout_value: int,
    endpoint: str | None,
    prompt: str,
    prompt_sections: list[Any] | None,
) -> dict[str, Any]:
    """Build failure metadata for generic exceptions."""
    failure_class, _ = classify_llm_failure(exc)
    actual_prompt_chars = len(prompt) if prompt else 0
    if prompt_sections:
        try:
            prompt_diags = build_prompt_diagnostics(
                provider="llamacpp",
                operation="review-enrichment",
                sections=prompt_sections,
                actual_prompt_chars=actual_prompt_chars,
                timeout_seconds=timeout_value,
                endpoint=endpoint,
                elapsed_ms=duration_ms,
                failure_class=failure_class.value,
                exception_type=exc_type,
            )
        except (ValueError, TypeError, AttributeError, OSError):
            prompt_diags = build_full_prompt_diagnostics(
                provider="llamacpp",
                operation="review-enrichment",
                actual_prompt=prompt if prompt else "",
                timeout_seconds=timeout_value,
                elapsed_ms=duration_ms,
                failure_class=failure_class.value,
                exception_type=exc_type,
            )
    else:
        prompt_diags = build_full_prompt_diagnostics(
            provider="llamacpp",
            operation="review-enrichment",
            actual_prompt=prompt if prompt else "",
            timeout_seconds=timeout_value,
            elapsed_ms=duration_ms,
            failure_class=failure_class.value,
            exception_type=exc_type,
        )
    call_id = ""  # Will be set by caller with run_id
    metadata = LLMFailureMetadata(
        failure_class=failure_class.value,
        exception_type=exc_type,
        timeout_seconds=timeout_value,
        elapsed_ms=duration_ms,
        endpoint=endpoint,
        summary=str(exc),
    ).to_dict()
    metadata["llm_call"] = True
    metadata["llm_call_id"] = call_id
    metadata["llm_provider"] = "llamacpp"
    metadata["llm_operation"] = "review-enrichment"
    metadata["prompt_diagnostics"] = prompt_diags.to_dict()
    return metadata


def run_http_assessment(
    adapter_name: str,
    request: ExternalAnalysisRequest,
    provider: Any,
    prepare_request_fn: Any,
) -> ExternalAnalysisArtifact:
    """Run HTTP-based LLM assessment with comprehensive error handling."""
    start = time.perf_counter()
    
    # Get config
    config = provider._config if provider and provider._config else None
    timeout_value = int(config.timeout_seconds) if config else int(DEFAULT_TIMEOUT_SECONDS)
    review_enrichment_max_tokens = (
        config.max_tokens_review_enrichment if config else DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT
    )
    
    prompt, payload, alias_mapping = prepare_request_fn(request)
    
    try:
        assessment = provider.assess(
            prompt,
            payload,
            validate_schema=False,
            system_instructions=_REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS,
            max_tokens=review_enrichment_max_tokens,
        )
        parsed = ReviewEnrichmentPayload.from_dict(assessment)
        duration_ms = int((time.perf_counter() - start) * 1000)
        
        # Build success artifact via helper (passes LLM response as payload)
        return build_success_artifact(
            adapter_name, request, assessment, parsed, duration_ms, alias_mapping
        )
    except ReviewEnrichmentPayloadError as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return build_failure_artifact(
            adapter_name, request, duration_ms, "Invalid review enrichment output",
            ExternalAnalysisStatus.FAILED, error_summary=str(exc),
        )
    except LLMResponseParseError as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        metadata = build_llm_failure_metadata(
            exc, "LLMResponseParseError", duration_ms, timeout_value,
            config.endpoint if config else None, prompt, None,
            review_enrichment_max_tokens,
        )
        return build_failure_artifact(
            adapter_name, request, duration_ms, str(exc)[:240],
            ExternalAnalysisStatus.SKIPPED, skip_reason=str(exc),
            failure_metadata=metadata,
        )
    except ValueError as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return build_failure_artifact(
            adapter_name, request, duration_ms, str(exc)[:240],
            ExternalAnalysisStatus.SKIPPED, skip_reason=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.perf_counter() - start) * 1000)
        failure_class, exc_type = classify_llm_failure(exc)
        metadata = build_generic_failure_metadata(
            exc, exc_type, duration_ms, timeout_value,
            config.endpoint if config else None, prompt, None,
        )
        # Add call_id now that we have run_id
        metadata["llm_call_id"] = build_llm_call_id(request.run_id, "review-enrichment", adapter_name)
        return build_failure_artifact(
            adapter_name, request, duration_ms, str(exc),
            ExternalAnalysisStatus.FAILED, error_summary=str(exc),
            failure_metadata=metadata,
        )
