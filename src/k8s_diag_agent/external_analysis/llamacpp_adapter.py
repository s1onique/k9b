"""llama.cpp adapter implementation."""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..llm.base import LLMAssessmentInput
from ..llm.llamacpp_provider import LlamaCppProvider, LlamaCppProviderConfig
from .adapter import (
    ExternalAnalysisAdapter,
    ExternalAnalysisExecutionError,
    ExternalAnalysisRequest,
    _run_subprocess,
    register_external_analysis_adapter,
)
from .artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from .config import ExternalAnalysisAdapterConfig
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
            except Exception as exc:
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
            assessment = self._http_provider.assess(
                prompt, payload, validate_schema=False
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
        except ValueError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return self._build_failure_artifact(
                request,
                duration_ms,
                str(exc),
                ExternalAnalysisStatus.SKIPPED,
                skip_reason=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.perf_counter() - start) * 1000)
            return self._build_failure_artifact(
                request,
                duration_ms,
                str(exc),
                ExternalAnalysisStatus.FAILED,
                error_summary=str(exc),
            )

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
            "Interpret the inputs conservatively and describe any missing data when providing hypotheses and next evidence."
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
        )



@register_external_analysis_adapter("llamacpp")
def _build_llamacpp_adapter(config: ExternalAnalysisAdapterConfig) -> ExternalAnalysisAdapter:
    return LlamaCppAdapter(command=config.command)
