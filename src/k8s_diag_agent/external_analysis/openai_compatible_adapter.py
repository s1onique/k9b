"""OpenAI-compatible adapter implementation."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..llm.base import LLMAssessmentInput
from ..llm.openai_compatible_provider import (
    OpenAICompatibleProviderConfig,
)
from ..llm.prompt_diagnostics import (
    PromptSection,
)
from .adapter import (
    ExternalAnalysisAdapter,
    ExternalAnalysisExecutionError,
    ExternalAnalysisRequest,
    _run_subprocess,
    normalize_adapter_name,
    register_external_analysis_adapter,
)
from .artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from .config import ExternalAnalysisAdapterConfig, ExternalAnalysisSettings
from .openai_compatible_adapter_config import (
    DEFAULT_COMMAND,
    init_http_provider,
)
from .openai_compatible_adapter_diagnostics import (
    extract_prompt_sections,
)
from .openai_compatible_adapter_http import run_http_assessment

# Re-export payload/artifact builders extracted to sibling module
from .openai_compatible_adapter_payloads import (
    build_failure_artifact,
    build_payload_from_context,
    build_success_artifact,
    extract_status,
)
from .openai_compatible_adapter_prompt import (
    compose_review_enrichment_prompt,
)
from .review_input import ReviewEnrichmentInput, build_review_enrichment_input
from .review_schema import ReviewEnrichmentPayload


@dataclass(frozen=True)
class ExternalAnalysisPreflightResult:
    """Result of an external analysis provider preflight check.

    This dataclass captures the result of validating whether an LLM provider
    is properly configured and ready for use. It includes operator-grade
    messages for troubleshooting configuration issues.
    """

    ok: bool
    provider_requested: str
    provider_normalized: str
    model: str | None = None
    base_url: str | None = None
    reason: str | None = None
    operator_message: str | None = None

    @property
    def legacy_provider_used(self) -> bool:
        """True if the legacy 'llamacpp' name was used instead of canonical 'openai_compatible'."""
        return self.provider_normalized != self.provider_requested


class OpenAICompatibleAdapter(ExternalAnalysisAdapter):
    """OpenAI-compatible adapter for LLM-based review enrichment.
    
    This adapter communicates with any server exposing an OpenAI-compatible
    chat completions API (HTTP POST to /v1/chat/completions).
    
    It does NOT require llama.cpp specifically; any compatible server
    (vLLM, Ollama, LM Studio, etc.) works with this adapter.
    """
    name = "openai_compatible"

    def __init__(self, command: Sequence[str] | None = None, http_only: bool = False) -> None:
        """Initialize the OpenAI-compatible adapter.

        Args:
            command: Explicit command to execute. If None, attempts HTTP provider config.
            http_only: When True, never fall back to CLI even if HTTP config is missing.
                      This is set to True for the canonical openai_compatible adapter to
                      ensure HTTP-only behavior (no subprocess binary execution).
        """
        use_http, http_provider, config_error = init_http_provider(command, http_only)
        self._use_http = use_http
        self._http_provider = http_provider
        self._http_config_error = config_error
        self._http_only = http_only

        if use_http:
            super().__init__(command=None)
        elif not http_only:
            super().__init__(command=tuple(command) if command is not None else DEFAULT_COMMAND)

    def preflight_check(self, provider_requested: str | None = None) -> ExternalAnalysisPreflightResult:
        """Check if the adapter is properly configured and ready for external analysis.

        Delegates to _openai_compatible_adapter_preflight.py for message construction.
        """
        from . import openai_compatible_adapter_preflight as preflight

        requested = provider_requested or self.name
        provider_normalized = normalize_adapter_name(requested)

        # Case 1: command-based adapter
        if not self._use_http and self._command:
            return ExternalAnalysisPreflightResult(
                ok=True,
                provider_requested=requested,
                provider_normalized=provider_normalized,
                operator_message=(
                    f"External analysis adapter '{provider_normalized}' is configured for "
                    f"command-based execution (not HTTP)."
                ),
            )

        # Case 2: config error
        if self._http_config_error:
            reason, operator_message = preflight.parse_config_error_reason(str(self._http_config_error))
            return ExternalAnalysisPreflightResult(
                ok=False,
                provider_requested=requested,
                provider_normalized=provider_normalized,
                reason=reason,
                operator_message=operator_message,
            )

        # Case 3: HTTP intent but no provider
        if self._use_http and not self._http_provider:
            return ExternalAnalysisPreflightResult(
                ok=False,
                provider_requested=requested,
                provider_normalized=provider_normalized,
                reason="provider_unavailable",
                operator_message=preflight.build_provider_unavailable_message(),
            )

        # Case 4: provider available
        if self._http_provider and self._http_provider._config:
            config = self._http_provider._config
            return ExternalAnalysisPreflightResult(
                ok=True,
                provider_requested=requested,
                provider_normalized=provider_normalized,
                model=config.model,
                base_url=config.base_url,
                operator_message=preflight.build_success_message(config.base_url, config.model),
            )

        # Case 5: try loading config
        if self._use_http:
            try:
                config = OpenAICompatibleProviderConfig.from_env()
                return ExternalAnalysisPreflightResult(
                    ok=True,
                    provider_requested=requested,
                    provider_normalized=provider_normalized,
                    model=config.model,
                    base_url=config.base_url,
                    operator_message=preflight.build_success_message(config.base_url, config.model),
                )
            except RuntimeError as exc:
                return ExternalAnalysisPreflightResult(
                    ok=False,
                    provider_requested=requested,
                    provider_normalized=provider_normalized,
                    reason="missing_config",
                    operator_message=str(exc),
                )

        # Fallback
        return ExternalAnalysisPreflightResult(
            ok=False,
            provider_requested=requested,
            provider_normalized=provider_normalized,
            reason="unknown",
            operator_message="External analysis adapter state is ambiguous.",
        )

    def run(self, request: ExternalAnalysisRequest) -> ExternalAnalysisArtifact:
        if self._use_http:
            return self._run_http(request)
        if not self._command:
            # No command configured and not HTTP mode - this is a misconfiguration
            artifact = ExternalAnalysisArtifact(
                tool_name=self.name,
                run_id=request.run_id,
                cluster_label=request.cluster_label,
                source_artifact=request.source_artifact,
                summary="Adapter is not configured",
                status=ExternalAnalysisStatus.SKIPPED,
                provider=self.name,
                skip_reason="No command configured and HTTP provider not available",
            )
            return artifact

        invocation = list(self._command)
        if request.source_artifact:
            invocation.append(request.source_artifact)
        else:
            invocation.extend(["--cluster", request.cluster_label])

        start = time.perf_counter()
        try:
            raw_output = _run_subprocess(invocation)
            duration_ms = int((time.perf_counter() - start) * 1000)
            summary = raw_output.splitlines()[0] if raw_output else "analysis completed"
            artifact = ExternalAnalysisArtifact(
                tool_name=self.name,
                run_id=request.run_id,
                cluster_label=request.cluster_label,
                source_artifact=request.source_artifact,
                summary=summary,
                findings=(),
                suggested_next_checks=(),
                status=ExternalAnalysisStatus.SUCCESS,
                raw_output=raw_output,
                provider=self.name,
                duration_ms=duration_ms,
            )
            return artifact
        except ExternalAnalysisExecutionError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            artifact = ExternalAnalysisArtifact(
                tool_name=self.name,
                run_id=request.run_id,
                cluster_label=request.cluster_label,
                source_artifact=request.source_artifact,
                summary=str(exc),
                findings=(),
                suggested_next_checks=(),
                status=ExternalAnalysisStatus.FAILED,
                raw_output=str(exc),
                provider=self.name,
                duration_ms=duration_ms,
            )
            return artifact

    def _run_http(self, request: ExternalAnalysisRequest) -> ExternalAnalysisArtifact:
        """Run HTTP-based LLM assessment, delegating to extracted helpers."""
        start = time.perf_counter()
        if self._http_config_error:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return self._build_failure_artifact(
                request,
                duration_ms,
                str(self._http_config_error),
                ExternalAnalysisStatus.FAILED,
                error_summary=str(self._http_config_error),
            )
        if not self._http_provider:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return self._build_failure_artifact(
                request,
                duration_ms,
                "OpenAI-compatible HTTP provider unavailable",
                ExternalAnalysisStatus.FAILED,
                error_summary="OpenAI-compatible HTTP provider unavailable",
            )
        return run_http_assessment(
            self.name, request, self._http_provider, self._prepare_provider_request
        )

    def _prepare_provider_request(
        self, request: ExternalAnalysisRequest
    ) -> tuple[str, LLMAssessmentInput, dict[str, str] | None]:
        if not request.source_artifact:
            raise ValueError("Review artifact path is required for review enrichment")
        review_path = Path(request.source_artifact)
        context = build_review_enrichment_input(review_path, request.run_id)
        prompt, alias_mapping = self._build_prompt(request, context)
        payload = self._build_payload_from_context(request, context)
        return prompt, payload, alias_mapping

    def _extract_prompt_sections(
        self, request: ExternalAnalysisRequest, context: ReviewEnrichmentInput
    ) -> list[PromptSection]:
        return extract_prompt_sections(request, context)

    def _build_prompt(
        self, request: ExternalAnalysisRequest, context: ReviewEnrichmentInput
    ) -> tuple[str, dict[str, str] | None]:
        return compose_review_enrichment_prompt(
            request.run_id, request.cluster_label, context
        )

    def _build_payload_from_context(
        self, request: ExternalAnalysisRequest, context: ReviewEnrichmentInput
    ) -> LLMAssessmentInput:
        return build_payload_from_context(request, context)

    def _extract_status(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return extract_status(snapshot)

    def _build_success_artifact(
        self,
        request: ExternalAnalysisRequest,
        payload: dict[str, Any],
        parsed: ReviewEnrichmentPayload,
        duration_ms: int,
        alias_mapping: dict[str, str] | None = None,
    ) -> ExternalAnalysisArtifact:
        return build_success_artifact(
            self.name, request, payload, parsed, duration_ms, alias_mapping
        )

    def _build_failure_artifact(
        self,
        request: ExternalAnalysisRequest,
        duration_ms: int,
        summary: str,
        status: ExternalAnalysisStatus,
        *,
        error_summary: str | None = None,
        skip_reason: str | None = None,
        failure_metadata: dict[str, object] | None = None,
    ) -> ExternalAnalysisArtifact:
        return build_failure_artifact(
            self.name, request, duration_ms, summary, status,
            error_summary=error_summary, skip_reason=skip_reason,
            failure_metadata=failure_metadata,
        )


@register_external_analysis_adapter("openai_compatible")
def _build_openai_compatible_adapter(
    config: ExternalAnalysisAdapterConfig,
    settings: ExternalAnalysisSettings,
) -> ExternalAnalysisAdapter:
    """Build adapter registered under canonical 'openai_compatible' name.

    This is the primary adapter registration during Phase 2 of the
    llamacpp → openai_compatible rename epic.

    The openai_compatible adapter is HTTP-only: it will NOT fall back to
    subprocess llamacpp binary execution. If HTTP config is missing, the
    preflight check will fail with explicit missing_base_url/missing_model
    reason codes.
    """
    return OpenAICompatibleAdapter(command=config.command, http_only=True)


@register_external_analysis_adapter("llamacpp")
def _build_legacy_llamacpp_adapter(
    config: ExternalAnalysisAdapterConfig,
    settings: ExternalAnalysisSettings,
) -> ExternalAnalysisAdapter:
    """Build adapter registered under legacy 'llamacpp' name.

    This alias ensures backward compatibility during the migration period.
    The legacy llamacpp adapter may fall back to subprocess execution if
    HTTP config is not available (for backward compatibility with existing
    deployments that have a local llamacpp binary).
    """
    return OpenAICompatibleAdapter(command=config.command)
