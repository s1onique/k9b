"""Review enrichment seam extracted from HealthLoopRunner.

This module contains the `run_review_enrichment` helper which encapsulates
the logic for running review enrichment via external analysis adapters.
Preserves behavior exactly - no schema or artifact contract changes.

This module does NOT import loop.py or HealthLoopRunner.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from ..external_analysis.adapter import ExternalAnalysisAdapter, ExternalAnalysisRequest
from ..external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
    write_external_analysis_artifact,
)
from ..external_analysis.config import ReviewEnrichmentPolicy
from ..external_analysis.review_schema import classify_review_enrichment_shape
from .loop_history import _safe_label

if TYPE_CHECKING:
    from ..external_analysis.adapter import PreflightResult

# Type alias for callbacks to avoid hard coupling to runner
LogEventFn = Callable[..., None]


def run_review_enrichment(
    *,
    review_path: Path | None,
    directories: dict[str, Path],
    review_enrichment_policy: ReviewEnrichmentPolicy,
    analysis_adapters: dict[str, ExternalAnalysisAdapter],
    run_id: str,
    run_label: str,
    log_event_fn: LogEventFn,
) -> ExternalAnalysisArtifact | None:
    """Run review enrichment via external analysis adapter.

    Preserves exact behavior from HealthLoopRunner._run_review_enrichment():
    1. Check policy enabled and review_path present
    2. Normalize provider name for adapter lookup
    3. Run preflight check if adapter supports it
    4. Call adapter.run() with ExternalAnalysisRequest
    5. Handle ValueError (unconfigured/missing) vs Exception (runtime) errors
    6. Classify payload shape for observability
    7. Log all events with consistent metadata
    8. Write artifact to disk

    Args:
        review_path: Path to the review input artifact.
        directories: Mapping of named directories for artifact output.
        review_enrichment_policy: Policy controlling review enrichment behavior.
        analysis_adapters: Dict mapping adapter names to adapter instances.
        run_id: Current run identifier.
        run_label: Human-readable run label.
        log_event_fn: Callback for logging events.

    Returns:
        The created enrichment artifact, or None if enrichment was disabled or skipped.
    """
    policy = review_enrichment_policy
    if not policy.enabled or not review_path:
        return None

    provider_requested = (policy.provider or "").strip()

    # Normalize provider name to canonical form for artifact naming and adapter lookup
    from ..external_analysis.adapter import normalize_adapter_name

    provider_normalized = normalize_adapter_name(provider_requested) if provider_requested else "review-enrichment"
    provider_segment = _safe_label(provider_normalized) if provider_normalized else "review-enrichment"
    artifact_path = directories["external_analysis"] / (f"{run_id}-review-enrichment-{provider_segment}.json")
    start = time.perf_counter()

    # Artifact to be returned (or written in case of failure)
    artifact: ExternalAnalysisArtifact | None = None

    try:
        if not provider_requested:
            raise ValueError("No review enrichment provider configured")

        # Use normalized name first for adapter lookup, then requested as fallback
        adapter: ExternalAnalysisAdapter | None = (
            analysis_adapters.get(provider_normalized)
            or analysis_adapters.get(provider_normalized.lower())
            or analysis_adapters.get(provider_requested)
            or analysis_adapters.get(provider_requested.lower())
        )
        if not adapter:
            raise ValueError(f"Adapter '{provider_requested}' (normalized: '{provider_normalized}') is not registered for review enrichment")

        # Run preflight check to validate provider configuration before execution
        # Pass the originally requested provider name so preflight can report it accurately
        preflight_result: PreflightResult | None = None
        if hasattr(adapter, "preflight_check"):
            try:
                preflight_result = adapter.preflight_check(provider_requested=provider_requested)
            except TypeError:
                # Fallback for adapters that don't accept provider_requested parameter
                preflight_result = adapter.preflight_check()
            if not preflight_result.ok:
                # Emit ERROR log for provider misconfiguration
                log_event_fn(
                    "review-enrichment",
                    "ERROR",
                    "Review enrichment preflight check failed",
                    run_label=run_label,
                    run_id=run_id,
                    provider_requested=preflight_result.provider_requested,
                    provider_normalized=preflight_result.provider_normalized,
                    reason=preflight_result.reason or "unknown",
                    operator_message=preflight_result.operator_message or "Provider configuration check failed",
                    artifact_path=str(artifact_path),
                    status="failed",
                    event="review-enrichment-preflight-failed",
                )
                # Build failure artifact with provider metadata
                duration_ms = int((time.perf_counter() - start) * 1000)
                failure_metadata: dict[str, object] = {
                    "preflight_failed": True,
                    "provider_requested": preflight_result.provider_requested,
                    "provider_normalized": preflight_result.provider_normalized,
                    "reason": preflight_result.reason or "unknown",
                    "operator_message": preflight_result.operator_message or "Provider configuration check failed",
                }
                artifact = ExternalAnalysisArtifact(
                    tool_name=adapter.name,
                    run_id=run_id,
                    cluster_label=run_label,
                    run_label=run_label,
                    source_artifact=str(review_path),
                    summary=f"Provider preflight failed: {preflight_result.reason or 'configuration error'}",
                    findings=(),
                    suggested_next_checks=(),
                    status=ExternalAnalysisStatus.FAILED,
                    raw_output=None,
                    timestamp=datetime.now(UTC),
                    artifact_path=str(artifact_path),
                    provider=preflight_result.provider_normalized,
                    duration_ms=duration_ms,
                    purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
                    error_summary=preflight_result.operator_message,
                    failure_metadata=failure_metadata,
                )
                write_external_analysis_artifact(artifact_path, artifact)
                # Log final result with preflight failure info
                log_event_fn(
                    "review-enrichment",
                    "ERROR",
                    "Review enrichment failed",
                    run_label=run_label,
                    run_id=run_id,
                    provider_requested=preflight_result.provider_requested,
                    provider_normalized=preflight_result.provider_normalized,
                    provider_legacy_alias_used=preflight_result.legacy_provider_used,
                    artifact_path=str(artifact_path),
                    status="failed",
                    elapsed_ms=duration_ms,
                    event="review-enrichment-result",
                )
                return artifact

        request = ExternalAnalysisRequest(
            run_id=run_id,
            cluster_label=run_label,
            source_artifact=str(review_path),
        )
        artifact = adapter.run(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        artifact = replace(
            artifact,
            run_id=run_id,
            artifact_path=str(artifact_path),
            provider=provider_normalized,
            duration_ms=duration_ms,
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
        )

    except ValueError as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        # Distinguish between unconfigured (SKIPPED) and misconfigured (FAILED).
        # - "no provider configured": operator did not set a provider → SKIP (intent to skip)
        # - "adapter not registered": provider set but adapter missing → SKIP (graceful degradation)
        # - "missing base_url" / "invalid config": provider set with structural problem → FAIL
        exc_str = str(exc)
        is_unconfigured = not provider_requested or "No review enrichment provider configured" in exc_str
        is_adapter_missing = "is not registered for review enrichment" in exc_str
        artifact_status = ExternalAnalysisStatus.SKIPPED if (is_unconfigured or is_adapter_missing) else ExternalAnalysisStatus.FAILED
        artifact = ExternalAnalysisArtifact(
            tool_name=provider_requested or "review-enrichment",
            run_id=run_id,
            cluster_label=run_label,
            run_label=run_label,
            source_artifact=str(review_path),
            summary=str(exc),
            status=artifact_status,
            timestamp=datetime.now(UTC),
            artifact_path=str(artifact_path),
            provider=provider_normalized if provider_requested else None,
            duration_ms=duration_ms,
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            skip_reason=str(exc) if (is_unconfigured or is_adapter_missing) else None,
            error_summary=str(exc) if not (is_unconfigured or is_adapter_missing) else None,
        )
    # REVIEWED: review enrichment LLM call boundary.
    # adapter.run() calls the provider and may raise exceptions from:
    # - provider network/HTTP errors (requests.RequestException, httpx.HTTPError, etc.)
    # - LLM parsing errors (ValueError subclasses, already handled above)
    # - unexpected provider SDK errors
    # Non-fatal fallback: FAILED status with bounded error_summary (str(exc)).
    # No credential exposure: error_summary is the exception message only.
    except Exception as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        artifact = ExternalAnalysisArtifact(
            tool_name=provider_requested or "review-enrichment",
            run_id=run_id,
            cluster_label=run_label,
            run_label=run_label,
            source_artifact=str(review_path),
            summary=str(exc),
            status=ExternalAnalysisStatus.FAILED,
            timestamp=datetime.now(UTC),
            artifact_path=str(artifact_path),
            provider=provider_normalized if provider_requested else None,
            duration_ms=duration_ms,
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            error_summary=str(exc),
        )

    # Write artifact to disk
    write_external_analysis_artifact(artifact_path, artifact)

    severity = "INFO" if artifact.status == ExternalAnalysisStatus.SUCCESS else "WARNING" if artifact.status == ExternalAnalysisStatus.SKIPPED else "ERROR"
    message = "Review enrichment recorded" if artifact.status == ExternalAnalysisStatus.SUCCESS else "Review enrichment skipped" if artifact.status == ExternalAnalysisStatus.SKIPPED else "Review enrichment failed"

    # Extract nextChecks from the enrichment payload for structured logging
    next_checks_count = 0
    enrichment_payload = artifact.payload if isinstance(artifact.payload, dict) else {}
    if enrichment_payload:
        next_checks = enrichment_payload.get("nextChecks") or enrichment_payload.get("next_checks")
        if isinstance(next_checks, list):
            next_checks_count = len(next_checks)

    # Classify the payload shape for observability
    # If the artifact was skipped due to invalid JSON/parse error, use invalid-json classification
    # instead of unrecognized-payload to avoid misleading diagnostics
    # Truncation (completion_stopped_by_length) is classified as TRUNCATED_JSON
    if artifact.status in (ExternalAnalysisStatus.SKIPPED, ExternalAnalysisStatus.FAILED) and artifact.failure_metadata:
        failure_meta = cast(dict[str, Any], artifact.failure_metadata)
        failure_class = str(failure_meta.get("failure_class", ""))
        failure_class_normalized = failure_class.lower()
        exception_type = str(failure_meta.get("exception_type", ""))
        completion_stopped = failure_meta.get("completion_stopped_by_length") is True
        
        if "llm_completion_truncated" in failure_class_normalized or completion_stopped:
            # Truncation: provider output was cut off by max_tokens limit
            from ..external_analysis.review_schema import ReviewEnrichmentShapeAnalysis, ReviewEnrichmentShapeClassification

            shape_analysis = ReviewEnrichmentShapeAnalysis(
                classification=ReviewEnrichmentShapeClassification.TRUNCATED_JSON,
                reason=f"LLM response truncated (max tokens exceeded): finish_reason={failure_meta.get('finish_reason')}",
                raw_payload_keys=(),
                summary_present=False,
                triage_order_count=0,
                top_concerns_count=0,
                evidence_gaps_count=0,
                next_checks_count=0,
                focus_notes_count=0,
            )
        elif "llm_response_parse_error" in failure_class_normalized or "llmresponseparseerror" in exception_type.lower():
            # Non-truncated parse error: genuinely malformed JSON
            from ..external_analysis.review_schema import ReviewEnrichmentShapeAnalysis, ReviewEnrichmentShapeClassification

            shape_analysis = ReviewEnrichmentShapeAnalysis(
                classification=ReviewEnrichmentShapeClassification.INVALID_JSON,
                reason="LLM response parse error - invalid JSON (not truncated)",
                raw_payload_keys=(),
                summary_present=False,
                triage_order_count=0,
                top_concerns_count=0,
                evidence_gaps_count=0,
                next_checks_count=0,
                focus_notes_count=0,
            )
        else:
            shape_analysis = classify_review_enrichment_shape(enrichment_payload)
    else:
        shape_analysis = classify_review_enrichment_shape(enrichment_payload)

    # Emit shape classification log
    log_event_fn(
        "review-enrichment",
        "INFO",
        f"Review enrichment payload shape: {shape_analysis.classification.value}",
        run_label=run_label,
        run_id=run_id,
        provider=provider_normalized if provider_requested else "unspecified",
        artifact_path=str(artifact_path),
        status=artifact.status.value,
        shape_classification=shape_analysis.classification.value,
        reason=shape_analysis.reason,
        raw_payload_keys=list(shape_analysis.raw_payload_keys)[:10],
        summary_present=shape_analysis.summary_present,
        triage_order_count=shape_analysis.triage_order_count,
        top_concerns_count=shape_analysis.top_concerns_count,
        evidence_gaps_count=shape_analysis.evidence_gaps_count,
        next_checks_count=shape_analysis.next_checks_count,
        focus_notes_count=shape_analysis.focus_notes_count,
        event="review-enrichment-shape",
    )

    # Build error_summary or skip_reason for structured logging
    error_summary = artifact.error_summary
    skip_reason = artifact.skip_reason

    # Extract reason/operator_message from artifact failure_metadata for ERROR logging
    reason: str | None = None
    operator_message: str | None = None
    if artifact.status == ExternalAnalysisStatus.FAILED and artifact.failure_metadata:
        failure_meta = cast(dict[str, Any], artifact.failure_metadata)
        reason = str(failure_meta.get("reason")) if failure_meta.get("reason") else None
        operator_message = str(failure_meta.get("operator_message")) if failure_meta.get("operator_message") else None

    # Additional failure metadata for failed status
    log_kwargs: dict[str, Any] = {
        "run_label": run_label,
        "run_id": run_id,
        "provider": provider_normalized if provider_requested else "unspecified",
        "artifact_path": str(artifact_path),
        "status": artifact.status.value,
        "next_checks_count": next_checks_count,
        "error_summary": error_summary,
        "skip_reason": skip_reason,
        "event": "review-enrichment-result",
    }
    # Include failure metadata for FAILED status if available
    if artifact.status == ExternalAnalysisStatus.FAILED:
        if artifact.duration_ms is not None:
            log_kwargs["elapsed_ms"] = artifact.duration_ms
        if reason:
            log_kwargs["reason"] = reason
        if operator_message:
            log_kwargs["operator_message"] = operator_message
    log_event_fn(
        "review-enrichment",
        severity,
        message,
        **log_kwargs,
    )
    return artifact
