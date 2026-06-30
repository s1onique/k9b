"""Payload and artifact builders for llamacpp adapter.

This module extracts the payload construction and artifact building responsibilities
from openai_compatible_adapter.py, providing focused helpers for:
- Building LLMAssessmentInput payloads from review enrichment context
- Constructing success and failure ExternalAnalysisArtifacts
"""

from __future__ import annotations

from typing import Any

from ..llm.base import LLMAssessmentInput
from ..security.kubectl_context import display_kube_cluster_label
from .adapter import ExternalAnalysisRequest
from .artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from .review_input import ReviewEnrichmentInput


def build_payload_from_context(
    request: ExternalAnalysisRequest, context: ReviewEnrichmentInput
) -> LLMAssessmentInput:
    """Build LLMAssessmentInput payload from review enrichment context.

    Constructs a structured payload containing:
    - primary_snapshot: the review artifact
    - secondary_snapshot: selection entries
    - comparison: selection details with drilldown/assessment/snapshot references
    - comparison_metadata: run context and alertmanager info
    - collection_statuses: loaded/missing counts for each artifact type
    """
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
        "review": extract_status(context.review),
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
            # Sanitize cluster_label to prevent internal markers like "in-cluster"
            # from appearing in LLM prompts as cluster names
            "cluster_label": display_kube_cluster_label(request.cluster_label),
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


def extract_status(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Extract status dict from snapshot, returning empty dict if not present."""
    status = snapshot.get("status")
    return status if isinstance(status, dict) else {}


def build_success_artifact(
    tool_name: str,
    request: ExternalAnalysisRequest,
    payload: dict[str, Any],
    parsed: Any,  # ReviewEnrichmentPayload
    duration_ms: int,
    alias_mapping: dict[str, str] | None = None,
) -> ExternalAnalysisArtifact:
    """Build success artifact from parsed review enrichment response.

    Uses parsed.top_concerns or parsed.next_checks as fallback summary
    if parsed.summary is empty.
    """
    summary = parsed.summary
    if not summary:
        if parsed.top_concerns:
            summary = parsed.top_concerns[0]
        elif parsed.next_checks:
            summary = parsed.next_checks[0]
        else:
            summary = "Review enrichment insight"
    return ExternalAnalysisArtifact(
        tool_name=tool_name,
        run_id=request.run_id,
        cluster_label=request.cluster_label,
        source_artifact=request.source_artifact,
        summary=summary,
        findings=parsed.top_concerns,
        suggested_next_checks=parsed.next_checks,
        status=ExternalAnalysisStatus.SUCCESS,
        raw_output=None,
        provider=tool_name,
        duration_ms=duration_ms,
        payload=payload,
        interpretation=payload if parsed.alertmanager_evidence_references else None,
        alias_mapping=alias_mapping,
    )


def build_failure_artifact(
    tool_name: str,
    request: ExternalAnalysisRequest,
    duration_ms: int,
    summary: str,
    status: ExternalAnalysisStatus,
    *,
    error_summary: str | None = None,
    skip_reason: str | None = None,
    failure_metadata: dict[str, object] | None = None,
) -> ExternalAnalysisArtifact:
    """Build failure artifact with appropriate status and metadata."""
    return ExternalAnalysisArtifact(
        tool_name=tool_name,
        run_id=request.run_id,
        cluster_label=request.cluster_label,
        source_artifact=request.source_artifact,
        summary=summary,
        findings=(),
        suggested_next_checks=(),
        status=status,
        raw_output=None,
        provider=tool_name,
        duration_ms=duration_ms,
        payload=None,
        error_summary=error_summary,
        skip_reason=skip_reason,
        failure_metadata=failure_metadata,
    )
