"""llama.cpp adapter implementation."""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..llm.base import LLMAssessmentInput
from ..llm.call_labels import build_llm_call_id
from ..llm.llamacpp_provider import (
    _REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS,
    DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT,
    DEFAULT_TIMEOUT_SECONDS,
    LlamaCppProvider,
    LlamaCppProviderConfig,
    LLMFailureMetadata,
    LLMResponseParseError,
    classify_llm_failure,
)
from ..llm.prompt_diagnostics import (
    PromptSection,
    build_full_prompt_diagnostics,
    build_prompt_diagnostics,
)
from .adapter import (
    ExternalAnalysisAdapter,
    ExternalAnalysisExecutionError,
    ExternalAnalysisRequest,
    _run_subprocess,
    register_external_analysis_adapter,
)
from .artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from .config import ExternalAnalysisAdapterConfig, ExternalAnalysisSettings
from .review_input import ReviewEnrichmentInput, build_review_enrichment_input
from .review_schema import ReviewEnrichmentPayload, ReviewEnrichmentPayloadError


class LlamaCppAdapter(ExternalAnalysisAdapter):
    name = "llamacpp"

    def __init__(self, command: Sequence[str] | None = None) -> None:
        self._use_http = False
        self._http_provider: LlamaCppProvider | None = None
        self._http_config_error: Exception | None = None
        default_command = ("llamacpp", "analysis")
        http_config: LlamaCppProviderConfig | None = None
        http_intent = False
        if command is None:
            try:
                http_config = LlamaCppProviderConfig.from_env()
                http_intent = True
            except RuntimeError:
                http_intent = False
            except (ValueError, TypeError) as exc:
                # REVIEWED: Intentional broad catch for provider config boundary.
                # Catches config-related value/type errors without leaking internal details.
                # Behavior: config error is stored and triggers HTTP path with failure artifact.
                http_intent = True
                self._http_config_error = exc
        if http_intent:
            self._use_http = True
            if http_config:
                self._http_provider = LlamaCppProvider(config=http_config)
            super().__init__(command=None)
            return
        if command is None:
            super().__init__(command=default_command)
        else:
            super().__init__(command=tuple(command) if command else None)

    def run(self, request: ExternalAnalysisRequest) -> ExternalAnalysisArtifact:
        if self._use_http:
            return self._run_http(request)
        if not self._command:
            artifact = ExternalAnalysisArtifact(
                tool_name=self.name,
                run_id=request.run_id,
                cluster_label=request.cluster_label,
                source_artifact=request.source_artifact,
                summary="Adapter is not configured",
                status=ExternalAnalysisStatus.SKIPPED,
                provider=self.name,
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
                "llama.cpp HTTP provider unavailable",
                ExternalAnalysisStatus.FAILED,
                error_summary="llama.cpp HTTP provider unavailable",
            )
        prompt, payload = self._prepare_provider_request(request)
        try:
            review_enrichment_max_tokens = (
                self._http_provider._config.max_tokens_review_enrichment
                if self._http_provider and self._http_provider._config
                else DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT
            )
            # Let provider config control response_format_json (defaults to False)
            assessment = self._http_provider.assess(
                prompt,
                payload,
                validate_schema=False,
                system_instructions=_REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS,
                max_tokens=review_enrichment_max_tokens,
            )
            parsed = ReviewEnrichmentPayload.from_dict(assessment)
            duration_ms = int((time.perf_counter() - start) * 1000)
            return self._build_success_artifact(request, assessment, parsed, duration_ms)
        except ReviewEnrichmentPayloadError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return self._build_failure_artifact(
                request,
                duration_ms,
                "Invalid review enrichment output",
                ExternalAnalysisStatus.FAILED,
                error_summary=str(exc),
            )
        except LLMResponseParseError as exc:
            # Structured output failure - capture diagnostics
            duration_ms = int((time.perf_counter() - start) * 1000)
            config = self._http_provider._config if self._http_provider else None
            timeout_value = config.timeout_seconds if config else DEFAULT_TIMEOUT_SECONDS
            # Build base failure metadata
            failure_class_value = (
                "llm_response_parse_error_length_capped"
                if exc.completion_stopped_by_length
                else "llm_response_invalid_json"
            )
            failure_metadata = LLMFailureMetadata(
                failure_class=failure_class_value,
                exception_type="LLMResponseParseError",
                timeout_seconds=timeout_value,
                elapsed_ms=duration_ms,
                endpoint=config.endpoint if config else None,
                summary=str(exc),
                **exc.to_diagnostics(),
            ).to_dict()
            # Include prompt diagnostics
            try:
                context_for_sections = build_review_enrichment_input(
                    Path(request.source_artifact) if request.source_artifact else Path("."),
                    request.run_id
                )
                sections = self._extract_prompt_sections(request, context_for_sections)
                prompt_diags = build_prompt_diagnostics(
                    provider="llamacpp",
                    operation="review-enrichment",
                    sections=sections,
                    actual_prompt_chars=len(prompt) if prompt else 0,
                    max_tokens=review_enrichment_max_tokens,
                    timeout_seconds=timeout_value,
                    elapsed_ms=duration_ms,
                    failure_class=failure_class_value,
                    exception_type="LLMResponseParseError",
                )
                failure_metadata["prompt_diagnostics"] = prompt_diags.to_dict()
            except (ValueError, TypeError, AttributeError):
                # REVIEWED: Non-fatal diagnostic capture fallback.
                # Silently skip if prompt diagnostics building fails - core LLM logic proceeds.
                pass
            # Build skip_reason that is bounded for logging
            skip_reason_bounded = self._bound_skip_reason(str(exc))
            return self._build_failure_artifact(
                request,
                duration_ms,
                skip_reason_bounded["summary"],
                ExternalAnalysisStatus.SKIPPED,
                skip_reason=str(exc),  # Full reason stays in artifact
                failure_metadata=failure_metadata,
            )
        except ValueError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            skip_reason_bounded = self._bound_skip_reason(str(exc))
            return self._build_failure_artifact(
                request,
                duration_ms,
                skip_reason_bounded["summary"],
                ExternalAnalysisStatus.SKIPPED,
                skip_reason=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            # REVIEWED: Intentional catch-all for LLM provider failure boundary.
            # Catches provider/client/network errors not covered by specific handlers.
            # All such failures produce structured failure artifacts with metadata.
            duration_ms = int((time.perf_counter() - start) * 1000)
            # Classify the failure for structured metadata
            failure_class, exc_type = classify_llm_failure(exc)
            config = self._http_provider._config if self._http_provider else None
            timeout_value = config.timeout_seconds if config else DEFAULT_TIMEOUT_SECONDS

            # Build prompt diagnostics for failure metadata
            # Always include exact full_prompt measurement from the actual prompt sent to LLM
            actual_prompt_chars = len(prompt) if prompt else 0
            try:
                context_for_sections = build_review_enrichment_input(
                    Path(request.source_artifact) if request.source_artifact else Path("."),
                    request.run_id
                )
                sections = self._extract_prompt_sections(request, context_for_sections)
                prompt_diags = build_prompt_diagnostics(
                    provider="llamacpp",
                    operation="review-enrichment",
                    sections=sections,
                    actual_prompt_chars=actual_prompt_chars,
                    timeout_seconds=timeout_value,
                    endpoint=config.endpoint if config else None,
                    elapsed_ms=duration_ms,
                    failure_class=failure_class.value,
                    exception_type=exc_type,
                )
            except (ValueError, TypeError, AttributeError, OSError):
                # REVIEWED: Non-fatal diagnostic fallback.
                # Build full prompt diagnostics when named section extraction fails.
                prompt_diags = build_full_prompt_diagnostics(
                    provider="llamacpp",
                    operation="review-enrichment",
                    actual_prompt=prompt if prompt else "",
                    timeout_seconds=timeout_value,
                    elapsed_ms=duration_ms,
                    failure_class=failure_class.value,
                    exception_type=exc_type,
                )

            # Build deterministic call ID for review-enrichment operation
            call_id = build_llm_call_id(request.run_id, "review-enrichment", self.name)
            failure_metadata = LLMFailureMetadata(
                failure_class=failure_class.value,
                exception_type=exc_type,
                timeout_seconds=timeout_value,
                elapsed_ms=duration_ms,
                endpoint=config.endpoint if config else None,
                summary=str(exc),
            ).to_dict()
            # Include llm_* fields and prompt diagnostics in failure metadata
            failure_metadata["llm_call"] = True
            failure_metadata["llm_call_id"] = call_id
            failure_metadata["llm_provider"] = self.name
            failure_metadata["llm_operation"] = "review-enrichment"
            failure_metadata["prompt_diagnostics"] = prompt_diags.to_dict()
            return self._build_failure_artifact(
                request,
                duration_ms,
                str(exc),
                ExternalAnalysisStatus.FAILED,
                error_summary=str(exc),
                failure_metadata=failure_metadata,
            )

    @staticmethod
    def _bound_skip_reason(reason: str, max_length: int = 240) -> dict[str, Any]:
        """Bound skip_reason for artifact summary, preserving full reason in artifact.skip_reason.

        Returns a dict with:
        - summary: short bounded one-line summary (for artifact summary field)
        - skip_reason_class: invalid_json | schema_error | skipped | unknown
        - skip_reason: optional bounded to max_length chars (for logging, not artifact)
        """
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

    def _prepare_provider_request(
        self, request: ExternalAnalysisRequest
    ) -> tuple[str, LLMAssessmentInput]:
        if not request.source_artifact:
            raise ValueError("Review artifact path is required for review enrichment")
        review_path = Path(request.source_artifact)
        context = build_review_enrichment_input(review_path, request.run_id)
        prompt = self._build_prompt(request, context)
        payload = self._build_payload_from_context(request, context)
        return prompt, payload

    def _extract_prompt_sections(
        self, request: ExternalAnalysisRequest, context: ReviewEnrichmentInput
    ) -> list[PromptSection]:
        """Extract named sections from the prompt for diagnostics.

        NOTE: Named sections are best-effort and may not exactly match the
        actual prompt due to JSON formatting, whitespace, and structure
        differences. The actual_prompt_chars field in PromptDiagnostics
        is the authoritative measurement.

        This method identifies natural sections in the review enrichment prompt.
        If section extraction would be invasive, it falls back to a single
        'full_prompt' section.

        Named sections include:
        - system_instructions: The instruction to produce JSON
        - review_artifact: The review JSON content
        - alertmanager_context: Alertmanager compact data when available
        - drilldown_evidence: Drilldown artifacts for selected items
        - assessment_evidence: Assessment artifacts for selected items
        - missing_context: Notes about missing artifacts
        - kubectl_guidance: Instructions for nextChecks format
        """
        sections: list[PromptSection] = []

        # Section 1: Request header/instructions
        sections.append(PromptSection(
            name="request_header",
            text=f"LLM external analysis request\nrun_id={request.run_id}\ncluster_label={request.cluster_label}",
        ))

        # Section 2: Output format instruction
        sections.append(PromptSection(
            name="output_schema",
            text="Produce a concise JSON advisory payload that includes summary, triageOrder/triage_order, "
                 "topConcerns/top_concerns, evidenceGaps/evidence_gaps, nextChecks/next_checks, and "
                 "focusNotes/focus_notes. Use arrays of non-empty strings for the list entries and highlight "
                 "missing data explicitly.",
        ))

        # Section 3: Review artifact
        sections.append(PromptSection(
            name="review_artifact",
            text=json.dumps(context.review, indent=2),
        ))

        # Section 4: Alertmanager context
        alertmanager_text = json.dumps({
            "available": context.alertmanager_context.available,
            "source": context.alertmanager_context.source,
            "status": context.alertmanager_context.status,
            "compact": context.alertmanager_context.compact,
        }, indent=2)
        sections.append(PromptSection(
            name="alertmanager_context",
            text=alertmanager_text,
        ))

        # Section 5: Drilldown and assessment evidence for selections
        if context.selections:
            selection_parts: list[str] = []
            for selection in context.selections:
                label = selection.label or selection.context or "<unknown>"
                selection_parts.append(f"Selected drilldown: {label} ({selection.context})")
                selection_parts.append(json.dumps(selection.entry, indent=2))
                if selection.drilldown:
                    selection_parts.append("Drilldown artifact:")
                    selection_parts.append(json.dumps(selection.drilldown, indent=2))
                else:
                    selection_parts.append(f"Drilldown artifact unavailable for {label}.")
                if selection.assessment:
                    selection_parts.append("Assessment artifact:")
                    selection_parts.append(json.dumps(selection.assessment, indent=2))
                else:
                    selection_parts.append(f"Assessment artifact unavailable for {label}.")
                if selection.snapshot:
                    selection_parts.append("Referenced snapshot:")
                    selection_parts.append(json.dumps(selection.snapshot, indent=2))
                elif selection.snapshot_path:
                    selection_parts.append(
                        f"Snapshot referenced at {selection.snapshot_path} is unavailable."
                    )
            sections.append(PromptSection(
                name="drilldown_evidence",
                text="\n".join(selection_parts),
            ))
        else:
            sections.append(PromptSection(
                name="drilldown_evidence",
                text="No drilldown was selected for this review.",
            ))

        # Section 6: Missing context notes
        missing_parts: list[str] = []
        if context.missing_drilldowns:
            missing_parts.append(
                "Missing drilldown artifacts: " + ", ".join(context.missing_drilldowns)
            )
        if context.missing_assessments:
            missing_parts.append(
                "Missing assessments: " + ", ".join(context.missing_assessments)
            )
        if context.missing_snapshots:
            missing_parts.append(
                "Missing snapshots: " + ", ".join(context.missing_snapshots)
            )
        if missing_parts:
            sections.append(PromptSection(
                name="missing_context",
                text="\n".join(missing_parts),
            ))

        # Section 7: Interpretation guidance
        sections.append(PromptSection(
            name="interpretation_guidance",
            text="Interpret the inputs conservatively and focus on actionable next checks and missing evidence.",
        ))

        # Section 8: kubectl command guidance
        kubectl_guidance = (
            "CRITICAL for nextChecks: each entry MUST be an explicit kubectl command in one of these formats:\n"
            "  - 'kubectl describe <resource> -n <namespace>'\n"
            "  - 'kubectl logs <pod> -n <namespace>'\n"
            "  - 'kubectl get <resource> -n <namespace>'\n"
            "  - 'kubectl get crd --context <cluster>'\n"
            "  - 'kubectl top <resource> -n <namespace>' (if metrics-server available)\n"
            "REQUIREMENTS:\n"
            "  - Every nextChecks entry must START with one of: kubectl describe, kubectl logs, kubectl get, kubectl top\n"
            "  - Each command must target exactly ONE cluster (use --context flag)\n"
            "  - NEVER use phrases like: validate, review, check status, confirm, investigate, verify, plan upgrade\n"
            "  - NEVER suggest 'all clusters', 'across clusters', or multi-cluster commands\n"
            "  - NEVER suggest mutations: do not include apply, patch, scale, edit, upgrade, delete, restart, rollout\n"
            "Examples of CORRECT nextChecks:\n"
            "  - 'kubectl describe pod -n default myapp-abc123 --context cluster1'\n"
            "  - 'kubectl logs deployment/myapp -n production --context admin@prod'\n"
            "  - 'kubectl get crd --context cluster2'\n"
            "Examples of WRONG nextChecks (will be rejected by planner):\n"
            "  - 'Validate image pull secrets in cluster1' (has 'validate')\n"
            "  - 'Check all clusters for CRDs' (has 'all clusters')\n"
            "  - 'Verify cluster2 version and upgrade to v1.33' (has 'upgrade')"
        )
        sections.append(PromptSection(
            name="kubectl_guidance",
            text=kubectl_guidance,
        ))

        return sections

    def _build_prompt(
        self, request: ExternalAnalysisRequest, context: ReviewEnrichmentInput
    ) -> str:
        prompt_parts: list[str] = [
            f"LLM external analysis request\nrun_id={request.run_id}\ncluster_label={request.cluster_label}",
            (
                "Produce a concise JSON advisory payload that includes summary, triageOrder/triage_order, "
                "topConcerns/top_concerns, evidenceGaps/evidence_gaps, nextChecks/next_checks, and "
                "focusNotes/focus_notes. Use arrays of non-empty strings for the list entries and highlight "
                "missing data explicitly."
            ),
            "Review artifact:",
            json.dumps(context.review, indent=2),
        ]
        # Inject Alertmanager compact context when available
        if context.alertmanager_context.available:
            prompt_parts.append("Alertmanager operational context:")
            prompt_parts.append(json.dumps({
                "available": True,
                "source": context.alertmanager_context.source,
                "status": context.alertmanager_context.status,
                "compact": context.alertmanager_context.compact,
            }, indent=2))
        else:
            prompt_parts.append("Alertmanager operational context:")
            prompt_parts.append(json.dumps({
                "available": False,
                "source": context.alertmanager_context.source,
                "status": context.alertmanager_context.status,
                "compact": None,
            }, indent=2))
        if context.selections:
            for selection in context.selections:
                label = selection.label or selection.context or "<unknown>"
                prompt_parts.append(f"Selected drilldown: {label} ({selection.context})")
                prompt_parts.append(json.dumps(selection.entry, indent=2))
                if selection.drilldown:
                    prompt_parts.append("Drilldown artifact:")
                    prompt_parts.append(json.dumps(selection.drilldown, indent=2))
                else:
                    prompt_parts.append(f"Drilldown artifact unavailable for {label}.")
                if selection.assessment:
                    prompt_parts.append("Assessment artifact:")
                    prompt_parts.append(json.dumps(selection.assessment, indent=2))
                else:
                    prompt_parts.append(f"Assessment artifact unavailable for {label}.")
                if selection.snapshot:
                    prompt_parts.append("Referenced snapshot:")
                    prompt_parts.append(json.dumps(selection.snapshot, indent=2))
                elif selection.snapshot_path:
                    prompt_parts.append(
                        f"Snapshot referenced at {selection.snapshot_path} is unavailable."
                    )
        else:
            prompt_parts.append("No drilldown was selected for this review.")
        missing_notes: list[str] = []
        if context.missing_drilldowns:
            missing_notes.append(
                "Missing drilldown artifacts: " + ", ".join(context.missing_drilldowns)
            )
        if context.missing_assessments:
            missing_notes.append(
                "Missing assessments: " + ", ".join(context.missing_assessments)
            )
        if context.missing_snapshots:
            missing_notes.append(
                "Missing snapshots: " + ", ".join(context.missing_snapshots)
            )
        if missing_notes:
            prompt_parts.append("Missing context details:")
            prompt_parts.extend(missing_notes)
        prompt_parts.append(
            "Interpret the inputs conservatively and focus on actionable next checks and missing evidence."
        )
        prompt_parts.append(
            "CRITICAL for nextChecks: each entry MUST be an explicit kubectl command in one of these formats:\n"
            "  - 'kubectl describe <resource> -n <namespace>'\n"
            "  - 'kubectl logs <pod> -n <namespace>'\n"
            "  - 'kubectl get <resource> -n <namespace>'\n"
            "  - 'kubectl get crd --context <cluster>'\n"
            "  - 'kubectl top <resource> -n <namespace>' (if metrics-server available)\n"
            "REQUIREMENTS:\n"
            "  - Every nextChecks entry must START with one of: kubectl describe, kubectl logs, kubectl get, kubectl top\n"
            "  - Each command must target exactly ONE cluster (use --context flag)\n"
            "  - NEVER use phrases like: validate, review, check status, confirm, investigate, verify, plan upgrade\n"
            "  - NEVER suggest 'all clusters', 'across clusters', or multi-cluster commands\n"
            "  - NEVER suggest mutations: do not include apply, patch, scale, edit, upgrade, delete, restart, rollout\n"
            "Examples of CORRECT nextChecks:\n"
            "  - 'kubectl describe pod -n default myapp-abc123 --context cluster1'\n"
            "  - 'kubectl logs deployment/myapp -n production --context admin@prod'\n"
            "  - 'kubectl get crd --context cluster2'\n"
            "Examples of WRONG nextChecks (will be rejected by planner):\n"
            "  - 'Validate image pull secrets in cluster1' (has 'validate')\n"
            "  - 'Check all clusters for CRDs' (has 'all clusters')\n"
            "  - 'Verify cluster2 version and upgrade to v1.33' (has 'upgrade')"
        )
        return "\n".join(prompt_parts)

    def _build_payload_from_context(
        self, request: ExternalAnalysisRequest, context: ReviewEnrichmentInput
    ) -> LLMAssessmentInput:
        secondary_snapshot = {
            "selections": [dict(selection.entry) for selection in context.selections]
        }
        comparison_entries: list[dict[str, Any]] = []
        for selection in context.selections:
            comparison_entries.append(
                {
                    "label": selection.label,
                    "context": selection.context,
                    "selection": dict(selection.entry),
                    "drilldown_path": selection.drilldown_path,
                    "drilldown": selection.drilldown,
                    "assessment_path": selection.assessment_path,
                    "assessment": selection.assessment,
                    "snapshot_path": selection.snapshot_path,
                    "snapshot": selection.snapshot,
                }
            )
        comparison: dict[str, Any] = {
            "review_run_id": context.review.get("run_id"),
            "review_version": context.review.get("review_version"),
            "selected_drilldowns": comparison_entries,
            "missing_context": {
                "drilldowns": list(context.missing_drilldowns),
                "assessments": list(context.missing_assessments),
                "snapshots": list(context.missing_snapshots),
            },
        }
        collection_statuses: dict[str, dict[str, Any]] = {
            "review": self._extract_status(context.review),
            "drilldowns": {
                "loaded": [selection.label for selection in context.selections if selection.drilldown],
                "missing": list(context.missing_drilldowns),
            },
            "assessments": {
                "loaded": [selection.label for selection in context.selections if selection.assessment],
                "missing": list(context.missing_assessments),
            },
            "snapshots": {
                "loaded": [selection.label for selection in context.selections if selection.snapshot],
                "missing": list(context.missing_snapshots),
            },
        }
        return LLMAssessmentInput(
            primary_snapshot=context.review,
            secondary_snapshot=secondary_snapshot,
            comparison=comparison,
            comparison_metadata={
                "run_id": request.run_id,
                "cluster_label": request.cluster_label,
                "review_run_id": context.review.get("run_id"),
                "alertmanager_context": {
                    "available": context.alertmanager_context.available,
                    "source": context.alertmanager_context.source,
                    "compact": context.alertmanager_context.compact,
                    "status": context.alertmanager_context.status,
                },
            },
            collection_statuses=collection_statuses,
        )

    def _extract_status(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        status = snapshot.get("status")
        return status if isinstance(status, dict) else {}

    def _build_success_artifact(
        self,
        request: ExternalAnalysisRequest,
        payload: dict[str, Any],
        parsed: ReviewEnrichmentPayload,
        duration_ms: int,
    ) -> ExternalAnalysisArtifact:
        summary = parsed.summary
        if not summary:
            if parsed.top_concerns:
                summary = parsed.top_concerns[0]
            elif parsed.next_checks:
                summary = parsed.next_checks[0]
            else:
                summary = "Review enrichment insight"
        return ExternalAnalysisArtifact(
            tool_name=self.name,
            run_id=request.run_id,
            cluster_label=request.cluster_label,
            source_artifact=request.source_artifact,
            summary=summary,
            findings=parsed.top_concerns,
            suggested_next_checks=parsed.next_checks,
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output=None,
            provider=self.name,
            duration_ms=duration_ms,
            payload=payload,
            interpretation=payload if parsed.alertmanager_evidence_references else None,
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
        return ExternalAnalysisArtifact(
            tool_name=self.name,
            run_id=request.run_id,
            cluster_label=request.cluster_label,
            source_artifact=request.source_artifact,
            summary=summary,
            findings=(),
            suggested_next_checks=(),
            status=status,
            raw_output=None,
            provider=self.name,
            duration_ms=duration_ms,
            payload=None,
            error_summary=error_summary,
            skip_reason=skip_reason,
            failure_metadata=failure_metadata,
        )


@register_external_analysis_adapter("llamacpp")
def _build_llamacpp_adapter(
    config: ExternalAnalysisAdapterConfig,
    settings: ExternalAnalysisSettings,
) -> ExternalAnalysisAdapter:
    return LlamaCppAdapter(command=config.command)
