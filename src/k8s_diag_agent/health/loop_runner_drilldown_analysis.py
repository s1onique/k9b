"""Auto-drilldown analysis orchestration seam extracted from HealthLoopRunner.

This module provides the `run_auto_drilldown_analysis` helper which encapsulates
the logic for running LLM-based auto-drilldown analysis on drilldown artifacts.
Preserves behavior exactly - no schema or artifact contract changes.

These helpers are pure functions with no runner logic. They delegate to
drilldown_assessor for LLM calls and handle artifact writing, logging, and
failure metadata assembly.

These helpers do NOT import loop.py or HealthLoopRunner.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ..external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
    write_external_analysis_artifact,
)
from ..external_analysis.config import AutoDrilldownPolicy
from ..llm.call_labels import build_llm_call_id
from ..llm.drilldown_prompts import build_drilldown_prompt
from ..llm.llamacpp_provider import LLMResponseParseError, classify_llm_failure
from .drilldown import DrilldownArtifact
from .drilldown_assessor import assess_drilldown_artifact, build_drilldown_prompt_diagnostics, resolve_drilldown_max_tokens
from .loop_failure_metadata import extract_failure_metadata_field

# Type alias for log event callback to avoid hard coupling to runner
LogEventFn = Callable[..., None]


def _is_openai_compatible_provider(provider_name: str) -> bool:
    """Check if provider name resolves to the OpenAI-compatible provider.

    This handles both canonical (openai_compatible) and legacy (llamacpp)
    provider names during the migration period.
    """
    from ..llm.provider import LEGACY_LLAMACPP_PROVIDER_NAME, OPENAI_COMPATIBLE_PROVIDER_NAME

    return provider_name in (OPENAI_COMPATIBLE_PROVIDER_NAME, LEGACY_LLAMACPP_PROVIDER_NAME)


def run_auto_drilldown_analysis(
    *,
    drilldowns: list[DrilldownArtifact],
    directories: dict[str, Path],
    run_id: str,
    run_label: str,
    auto_drilldown_policy: AutoDrilldownPolicy,
    provider_name: str,
    log_event_fn: LogEventFn | None = None,
) -> list[ExternalAnalysisArtifact]:
    """Run LLM auto-drilldown analysis on drilldown artifacts.

    Preserves exact behavior from HealthLoopRunner._run_auto_drilldown_analysis():
    1. Check policy enabled, max_per_run, and drilldowns non-empty
    2. For each drilldown (up to max_per_run):
       a. Build prompt and measure character count
       b. Log LLM call start with diagnostics
       c. Call assess_drilldown_artifact() to run LLM
       d. On success: extract findings, next_checks, summary from assessment
       e. On LLMResponseParseError: build failure metadata and diagnostics
       f. On ValueError (schema validation): set SKIPPED status
       g. On other exceptions: classify failure, build diagnostics
       h. Write artifact with status, payload, failure_metadata
       i. Log result with severity based on status
    3. Return all artifacts

    Args:
        drilldowns: List of drilldown artifacts to analyze.
        directories: Dict with 'external_analysis' path for artifact writing.
        run_id: Current run identifier (used for artifact naming).
        run_label: Human-readable run label (used for artifact metadata).
        auto_drilldown_policy: Policy controlling auto-drilldown behavior.
        provider_name: LLM provider name (e.g., "llamacpp", "openai_compatible").
        log_event_fn: Optional callback for logging events.

    Returns:
        List of ExternalAnalysisArtifact objects created.
    """
    policy = auto_drilldown_policy
    if not policy.enabled or policy.max_per_run <= 0 or not drilldowns:
        return []

    artifacts: list[ExternalAnalysisArtifact] = []
    attempts = 0

    for drilldown in drilldowns:
        if attempts >= policy.max_per_run:
            break
        attempts += 1

        artifact_path = directories["external_analysis"] / (
            f"{run_id}-{drilldown.label}-auto-{provider_name}.json"
        )
        start = time.perf_counter()
        status = ExternalAnalysisStatus.FAILED
        summary: str | None = None
        findings: tuple[str, ...] = ()
        next_checks: tuple[str, ...] = ()
        payload: dict[str, object] | None = None
        error_summary: str | None = None
        skip_reason: str | None = None
        failure_metadata: dict[str, object] | None = None

        # Build actual prompt first for exact measurement.
        # Note: assess_drilldown_artifact() also builds the prompt internally.
        # Since build_drilldown_prompt() is deterministic, the measured chars
        # should match the actual prompt sent to the LLM.
        actual_prompt = build_drilldown_prompt(drilldown)
        actual_prompt_chars = len(actual_prompt) if actual_prompt else 0

        # Build deterministic call ID for start log
        start_call_id = build_llm_call_id(run_id, "auto-drilldown", provider_name, cluster_label=drilldown.label)

        # Resolve max_tokens for llama.cpp provider
        start_max_tokens: int | None = None
        if _is_openai_compatible_provider(provider_name):
            start_max_tokens = resolve_drilldown_max_tokens(provider_name)

        # Log LLM call start
        if log_event_fn:
            log_event_fn(
                "llm-call",
                "INFO",
                "LLM call started",
                llm_call=True,
                llm_call_id=start_call_id,
                llm_provider=provider_name,
                llm_operation="auto-drilldown",
                llm_phase="start",
                run_id=run_id,
                run_label=run_label,
                cluster_label=drilldown.label,
                max_tokens=start_max_tokens,
                timeout_seconds=None,
                actual_prompt_chars=actual_prompt_chars,
            )

        try:
            # max_tokens will be resolved by assess_drilldown_artifact using provider config
            assessment = assess_drilldown_artifact(drilldown, provider_name=provider_name)
            payload = assessment.to_dict()
            summary = assessment.recommended_action.description if assessment.recommended_action else (
                assessment.hypotheses[0].description if assessment.hypotheses else "Auto drilldown interpretation"
            )
            findings = tuple(entry.description for entry in assessment.findings)
            next_checks = tuple(entry.description for entry in assessment.next_evidence_to_collect)
            status = ExternalAnalysisStatus.SUCCESS
        except ValueError as exc:
            # LLMResponseParseError is a ValueError subclass: handle it with structured failure metadata
            if isinstance(exc, LLMResponseParseError):
                status = ExternalAnalysisStatus.FAILED
                summary = str(exc)
                error_summary = str(exc)
                payload = None
                skip_reason = None
                elapsed_ms = int((time.perf_counter() - start) * 1000)

                # Determine failure class based on length cap
                if exc.completion_stopped_by_length is True:
                    failure_class_value = "llm_completion_truncated"
                else:
                    failure_class_value = "llm_response_parse_error"

                # Build structured top-level failure metadata
                exc_diags = exc.to_diagnostics()
                max_toks: int | None = None
                if _is_openai_compatible_provider(provider_name):
                    max_toks = resolve_drilldown_max_tokens(provider_name)

                prompt_diags = build_drilldown_prompt_diagnostics(
                    drilldown,
                    provider_name=provider_name,
                    actual_prompt_chars=actual_prompt_chars,
                    max_tokens=max_toks,
                    elapsed_ms=elapsed_ms,
                    failure_class=failure_class_value,
                    exception_type="LLMResponseParseError",
                )
                llm_call_id_val = build_llm_call_id(run_id, "auto-drilldown", provider_name, cluster_label=drilldown.label)
                failure_metadata = {
                    "failure_class": failure_class_value,
                    "exception_type": "LLMResponseParseError",
                    "finish_reason": exc_diags.get("finish_reason"),
                    "completion_stopped_by_length": exc_diags.get("completion_stopped_by_length"),
                    "response_content_chars": exc_diags.get("response_content_chars"),
                    "response_content_prefix": exc_diags.get("response_content_prefix"),
                    "max_tokens": exc_diags.get("max_tokens"),
                    "provider": provider_name,
                    "operation": "auto-drilldown",
                    "llm_call_id": llm_call_id_val,
                    "llm_call": True,
                    "prompt_diagnostics": prompt_diags,
                }

                if log_event_fn:
                    log_event_fn(
                        "llm-prompt-diagnostics",
                        "ERROR",
                        "Auto-drilldown LLM call failed",
                        llm_call=True,
                        llm_call_id=llm_call_id_val,
                        llm_provider=provider_name,
                        llm_operation="auto-drilldown",
                        llm_phase="diagnostics",
                        operation=prompt_diags.get("operation"),
                        provider=prompt_diags.get("provider"),
                        prompt_chars=prompt_diags.get("prompt_chars"),
                        prompt_tokens_estimate=prompt_diags.get("prompt_tokens_estimate"),
                        actual_prompt_chars=prompt_diags.get("actual_prompt_chars"),
                        actual_prompt_tokens_estimate=prompt_diags.get("actual_prompt_tokens_estimate"),
                        section_coverage_ratio=prompt_diags.get("section_coverage_ratio"),
                        prompt_section_count=prompt_diags.get("prompt_section_count"),
                        top_prompt_sections=[s.get("name") for s in prompt_diags.get("top_prompt_sections", [])],
                        elapsed_ms=elapsed_ms,
                        failure_class=failure_class_value,
                        exception_type="LLMResponseParseError",
                    )
            else:
                # Non-LLM ValueError (including schema validation): preserve SKIPPED behavior
                # but set explicit failure metadata for observability
                status = ExternalAnalysisStatus.SKIPPED
                summary = str(exc)
                skip_reason = str(exc)
                error_summary = None
                payload = None
                failure_metadata = {
                    "failure_class": "llm_response_schema_validation_error",
                    "exception_type": "ValueError",
                    "provider": provider_name,
                    "operation": "auto-drilldown",
                    "llm_call_id": build_llm_call_id(run_id, "auto-drilldown", provider_name, cluster_label=drilldown.label),
                    "llm_call": True,
                    "max_tokens": start_max_tokens,
                    "actual_prompt_chars": actual_prompt_chars,
                }

        # REVIEWED: LLM call boundary in auto-drilldown.
        # assess_drilldown_artifact() calls the provider and may raise exceptions from:
        # - provider network/HTTP errors (requests.RequestException, httpx.HTTPError, etc.)
        # - LLM parsing errors (ValueError subclasses, already handled above)
        # - unexpected provider SDK errors
        # Non-fatal fallback: FAILED status with failure_metadata (when available).
        # No credential exposure: failure_metadata uses bounded field extraction, not raw response.
        except Exception as exc:
            status = ExternalAnalysisStatus.FAILED
            summary = str(exc)
            error_summary = str(exc)
            payload = None

            # Build prompt diagnostics for failure logging and artifact
            failure_metadata = None
            elapsed_ms = int((time.perf_counter() - start) * 1000)

            try:
                # Classify the exception properly - check __cause__ and __context__ for wrapped exceptions
                classified_failure_class, classified_exc_type = classify_llm_failure(exc)

                # Resolve max_tokens for diagnostics using the drilldown_assessor helper
                diagnostic_max_tokens: int | None = None
                if _is_openai_compatible_provider(provider_name):
                    diagnostic_max_tokens = resolve_drilldown_max_tokens(provider_name)

                prompt_diags = build_drilldown_prompt_diagnostics(
                    drilldown,
                    provider_name=provider_name,
                    actual_prompt_chars=actual_prompt_chars,
                    max_tokens=diagnostic_max_tokens,
                    elapsed_ms=elapsed_ms,
                    failure_class=classified_failure_class.value,
                    exception_type=classified_exc_type,
                )

                # Build deterministic call ID for correlation across logs and artifacts
                call_id = build_llm_call_id(run_id, "auto-drilldown", provider_name, cluster_label=drilldown.label)

                # Log structured diagnostics for failure observability
                if log_event_fn:
                    log_event_fn(
                        "llm-prompt-diagnostics",
                        "ERROR",
                        "Auto-drilldown LLM call failed",
                        llm_call=True,
                        llm_call_id=call_id,
                        llm_provider=provider_name,
                        llm_operation="auto-drilldown",
                        llm_phase="diagnostics",
                        operation=prompt_diags.get("operation"),
                        provider=prompt_diags.get("provider"),
                        prompt_chars=prompt_diags.get("prompt_chars"),
                        prompt_tokens_estimate=prompt_diags.get("prompt_tokens_estimate"),
                        actual_prompt_chars=prompt_diags.get("actual_prompt_chars"),
                        actual_prompt_tokens_estimate=prompt_diags.get("actual_prompt_tokens_estimate"),
                        section_coverage_ratio=prompt_diags.get("section_coverage_ratio"),
                        prompt_section_count=prompt_diags.get("prompt_section_count"),
                        top_prompt_sections=[s.get("name") for s in prompt_diags.get("top_prompt_sections", [])],
                        elapsed_ms=elapsed_ms,
                        failure_class=classified_failure_class.value,
                        exception_type=classified_exc_type,
                    )

                failure_metadata = {"prompt_diagnostics": prompt_diags}

            # REVIEWED: internal diagnostics extraction boundary.
            # Narrowed to TypeError/AttributeError/KeyError/ValueError: these are
            # the expected exceptions when accessing dict fields or calling helpers
            # during prompt diagnostics extraction. Non-fatal fallback: no diagnostics.
            except (TypeError, AttributeError, KeyError, ValueError):
                failure_metadata = None

        duration_ms = int((time.perf_counter() - start) * 1000)

        artifact = ExternalAnalysisArtifact(
            tool_name="llm-autodrilldown",
            run_id=run_id,
            cluster_label=drilldown.label,
            run_label=run_label,
            source_artifact=drilldown.artifact_path,
            summary=summary,
            findings=findings,
            suggested_next_checks=next_checks,
            status=status,
            raw_output=None,
            timestamp=datetime.now(UTC),
            artifact_path=str(artifact_path),
            provider=provider_name,
            duration_ms=duration_ms,
            purpose=ExternalAnalysisPurpose.AUTO_DRILLDOWN,
            payload=payload,
            error_summary=error_summary,
            skip_reason=skip_reason,
            failure_metadata=failure_metadata,
        )

        write_external_analysis_artifact(artifact_path, artifact)

        severity = (
            "INFO" if status == ExternalAnalysisStatus.SUCCESS
            else "WARNING" if status == ExternalAnalysisStatus.SKIPPED
            else "ERROR"
        )

        # Build status-appropriate log message
        _interp_label = (
            "Auto drilldown interpretation failed" if status == ExternalAnalysisStatus.FAILED
            else "Auto drilldown interpretation skipped" if status == ExternalAnalysisStatus.SKIPPED
            else "Auto drilldown interpretation recorded"
        )

        if log_event_fn:
            log_event_fn(
                "external-analysis",
                severity,
                _interp_label,
                tool=provider_name,
                cluster_label=drilldown.label,
                status=status.value,
                artifact_path=str(artifact_path),
                error_summary=error_summary,
                duration_ms=duration_ms,
                event="auto-drilldown",
            )

        # Log LLM call result with deterministic call ID for correlation
        result_call_id = build_llm_call_id(run_id, "auto-drilldown", provider_name, cluster_label=drilldown.label)

        # Extract failure details from failure_metadata if available (check top-level and nested prompt_diagnostics)
        result_failure_class = extract_failure_metadata_field(failure_metadata, "failure_class")
        result_exception_type = extract_failure_metadata_field(failure_metadata, "exception_type")
        result_skip_reason: str | None = None
        if failure_metadata:
            nested_diags = failure_metadata.get("prompt_diagnostics")
            if isinstance(nested_diags, dict):
                result_skip_reason = str(nested_diags.get("skip_reason")) if nested_diags.get("skip_reason") else None
        if status == ExternalAnalysisStatus.SKIPPED and skip_reason:
            result_skip_reason = skip_reason

        # Resolve max_tokens for openai-compatible provider
        result_max_tokens: int | None = None
        if _is_openai_compatible_provider(provider_name):
            result_max_tokens = resolve_drilldown_max_tokens(provider_name)

        if log_event_fn:
            log_event_fn(
                "llm-call",
                severity,
                (
                    "LLM call completed" if status == ExternalAnalysisStatus.SUCCESS
                    else ("LLM call skipped" if status == ExternalAnalysisStatus.SKIPPED else "LLM call failed")
                ),
                llm_call=True,
                llm_call_id=result_call_id,
                llm_provider=provider_name,
                llm_operation="auto-drilldown",
                llm_phase="result",
                run_id=run_id,
                run_label=run_label,
                cluster_label=drilldown.label,
                status=status.value,
                duration_ms=duration_ms,
                artifact_path=str(artifact_path),
                max_tokens=result_max_tokens,
                failure_class=result_failure_class,
                exception_type=result_exception_type,
                finish_reason=extract_failure_metadata_field(failure_metadata, "finish_reason"),
                completion_stopped_by_length=extract_failure_metadata_field(
                    failure_metadata,
                    "completion_stopped_by_length",
                ),
                skip_reason=result_skip_reason,
            )

        artifacts.append(artifact)

        # Stop on SKIPPED if there's a skip reason (per original behavior)
        if status == ExternalAnalysisStatus.SKIPPED and skip_reason:
            break

    return artifacts
