"""Deterministic planner for provider suggested next checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from .alertmanager_feedback import (
    build_feedback_from_execution_artifacts,
)
from .next_check_incident_linkage import (
    IncidentLinkageContext,
    build_next_check_incident_linkage,
    enrich_next_check_candidate_dict,
    enrich_next_check_plan_dict,
)
from .next_check_planner_alertmanager import (
    AlertmanagerRankingSignal,
    _build_alertmanager_rationale,
    _compute_alertmanager_bonus,
    build_alertmanager_provenance,
    compute_alertmanager_match_bonus,
    extract_alertmanager_severity_weight,
)
from .next_check_planner_candidates import (
    NextCheckCandidate,
    build_candidates_from_enrichment,
)
from .next_check_planner_models import (
    MUTATION_KEYWORDS,  # noqa: F401 - re-exported for manual_next_check compatibility
    AlertmanagerRankingProvenance,
    ApprovalReason,
    BlockingReason,
    CommandFamily,
    CostEstimate,
    DuplicateReason,
    NormalizationReason,
    RiskLevel,
    SafetyReason,
    detect_command_family,
    detect_expected_signal,
)
from .next_check_planner_ranking import (
    _compute_candidate_sort_score,
    _is_early_incident_triage,
    _rank_candidates,
    rank_candidates,
)
from .result_digest import ExecutionResultDigest

if TYPE_CHECKING:
    pass

# Re-export for backward compatibility with modules that import from next_check_planner
__all__ = [
    "NextCheckCandidate",
    "NextCheckPlan",
    "AlertmanagerRankingSignal",
    "AlertmanagerRankingProvenance",
    "CommandFamily",
    "CostEstimate",
    "ApprovalReason",
    "BlockingReason",
    "DuplicateReason",
    "NormalizationReason",
    "RiskLevel",
    "SafetyReason",
    "MUTATION_KEYWORDS",
    "detect_command_family",
    "detect_expected_signal",
    "plan_next_checks",
    "build_candidates_from_enrichment",
    # Re-export ranking functions with underscore prefix for backward compat
    "_rank_candidates",
    "_compute_candidate_sort_score",
    "_compute_alertmanager_bonus",
    "_build_alertmanager_rationale",
    "_is_early_incident_triage",
    # Re-export public ranking helpers
    "build_alertmanager_provenance",
    "compute_alertmanager_match_bonus",
    "extract_alertmanager_severity_weight",
]


@dataclass(frozen=True)
class NextCheckPlan:
    run_id: str
    review_path: Path
    enrichment_artifact_path: str | None
    candidates: tuple[NextCheckCandidate, ...]
    linkage_context: IncidentLinkageContext | None = None
    # Upstream failure context when enrichment failed (e.g., truncation)
    # Includes source_enrichment_status, source_failure_class, source_error_summary,
    # source_finish_reason, and source_completion_stopped_by_length
    upstream_failure_context: dict[str, object] | None = None

    def to_payload(self) -> dict[str, object | None]:
        # Build base payload
        candidates_payload: list[dict[str, object]] = []
        for index, candidate in enumerate(self.candidates):
            candidate_dict = candidate.to_dict()
            candidate_dict.setdefault("candidateIndex", index)
            candidates_payload.append(candidate_dict)

        base_payload: dict[str, object | None] = {
            "review_path": str(self.review_path),
            "enrichment_artifact_path": self.enrichment_artifact_path,
            "candidates": candidates_payload,
        }

        # Include upstream failure context if enrichment failed
        if self.upstream_failure_context is not None:
            base_payload["upstream_failure_context"] = self.upstream_failure_context

        # Enrich with incident linkage fields if context is available
        if self.linkage_context is not None:
            linkage_result = build_next_check_incident_linkage(self.linkage_context)
            if linkage_result:
                plan_linkage, candidate_linkage = linkage_result
                # Enrich plan-level payload with linkage fields
                base_payload = enrich_next_check_plan_dict(base_payload, plan_linkage)
                # Enrich each candidate with linkage fields
                enriched_candidates: list[dict[str, object]] = []
                for candidate_dict in candidates_payload:
                    enriched = enrich_next_check_candidate_dict(candidate_dict, candidate_linkage)
                    enriched_candidates.append(enriched)
                base_payload["candidates"] = enriched_candidates

        return base_payload


def plan_next_checks(
    review_path: Path,
    run_id: str,
    enrichment_artifact: ExternalAnalysisArtifact,
    execution_artifacts: tuple[ExternalAnalysisArtifact, ...] | None = None,
    linkage_context: IncidentLinkageContext | None = None,
) -> NextCheckPlan | None:
    """Plan next checks from enrichment artifact.
    
    Delegates candidate construction to build_candidates_from_enrichment
    in next_check_planner_candidates module, then applies ranking policy
    including Alertmanager-influenced bonus and CRD demotion.
    
    If execution_artifacts are provided, their digests are passed to
    candidate building for provenance and contextual reasoning.
    
    If linkage_context is provided, the resulting plan will include
    incident linkage fields in its payload.
    
    If the enrichment artifact has FAILED status (e.g., due to truncation),
    the plan will be returned with empty candidates but include upstream
    failure context in the payload for observability.
    """
    # Build execution context digests from execution artifacts
    # These digests are passed explicitly to candidate building
    execution_digests: tuple[ExecutionResultDigest, ...] = ()
    if execution_artifacts:
        from .review_input import build_execution_context
        execution_digests = build_execution_context(execution_artifacts)
    
    # Build candidates with explicit execution context
    # No module-level state is used - execution context is passed directly
    raw_candidates = build_candidates_from_enrichment(
        str(review_path),
        run_id,
        enrichment_artifact,
        execution_context=execution_digests,
    )
    
    # If enrichment failed (e.g., truncation), return plan with upstream failure context
    if enrichment_artifact.status == ExternalAnalysisStatus.FAILED:
        # Extract upstream failure context for observability
        failure_meta = enrichment_artifact.failure_metadata or {}
        # Normalize failure_class for matching (case-insensitive)
        failure_class_raw = failure_meta.get("failure_class", "unknown")
        failure_class_normalized = str(failure_class_raw).lower()
        
        upstream_failure_info: dict[str, object] = {
            "source_enrichment_status": "failed",
            "source_failure_class": failure_class_raw,  # Preserve original case
            "source_failure_class_normalized": failure_class_normalized,
            "source_status": "failed",
            "source_error_summary": enrichment_artifact.error_summary or enrichment_artifact.skip_reason or "unknown",
        }
        # Include finish_reason if available for truncation diagnostics
        if failure_meta.get("finish_reason"):
            upstream_failure_info["source_finish_reason"] = failure_meta.get("finish_reason")
        if failure_meta.get("completion_stopped_by_length"):
            upstream_failure_info["source_completion_stopped_by_length"] = True
        
        # Return plan with empty candidates and upstream failure context attached
        return NextCheckPlan(
            run_id=run_id,
            review_path=review_path,
            enrichment_artifact_path=enrichment_artifact.artifact_path,
            candidates=(),
            linkage_context=linkage_context,
            upstream_failure_context=upstream_failure_info,
        )
    
    if not raw_candidates:
        return None
    
    # Extract context for ranking policy adjustments
    # The enrichment artifact carries workstream/review_stage from the original assessment
    workstream = enrichment_artifact.workstream
    review_stage = enrichment_artifact.review_stage
    
    # Extract Alertmanager ranking signal from run-scoped context
    # No live Alertmanager fetch is performed - only run-scoped compact artifact is used
    from .review_input import build_review_enrichment_input
    alertmanager_signal: AlertmanagerRankingSignal | None = None
    try:
        context = build_review_enrichment_input(review_path, run_id)
        if context.alertmanager_context is not None:
            alertmanager_signal = AlertmanagerRankingSignal.from_alertmanager_context(
                context.alertmanager_context
            )
    except (OSError, ValueError, KeyError):
        # Non-fatal - ranking proceeds without Alertmanager signal
        pass
    
    # Build run-scoped Alertmanager feedback from execution artifacts
    # This enables run-scoped learning: operator marking Alertmanager relevance as
    # not_relevant/noisy suppresses similar Alertmanager-driven candidates
    alertmanager_feedback = None
    if execution_artifacts:
        alertmanager_feedback = build_feedback_from_execution_artifacts(execution_artifacts)
    
    sorted_candidates = rank_candidates(raw_candidates, workstream, review_stage, alertmanager_signal, alertmanager_feedback)
    return NextCheckPlan(
        run_id=run_id,
        review_path=review_path,
        enrichment_artifact_path=enrichment_artifact.artifact_path,
        candidates=sorted_candidates,
        linkage_context=linkage_context,
    )
