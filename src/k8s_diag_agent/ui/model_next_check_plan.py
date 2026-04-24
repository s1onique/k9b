"""View models for next-check plan/candidate UI layer (UI model module).

This module contains plan and candidate-specific view model dataclasses and builders
extracted from model.py. It exists to enable incremental modularization without
changing behavior.

Dependency direction:
- model_next_check_plan.py -> model_primitives.py, model_alertmanager.py, model_feedback.py
- model.py imports from model_next_check_plan.py for re-export compatibility.

NOTE: _build_next_check_candidate_view has a dependency on ui_planner_queue helpers
(_derive_priority_rationale, _derive_ranking_reason). To avoid circular imports,
this builder is NOT extracted to this module and remains in model.py.
The dependency graph:
- model.py imports from this module (model_next_check_plan)
- model.py also imports from ui_planner_queue
- model.py imports from model_alertmanager and model_feedback
- model_alertmanager and model_feedback do NOT import from model_next_check_plan
- If model_next_check_plan imports from ui_planner_queue, we risk:
  - model_next_check_plan imports ui_planner_queue
  - ui_planner_queue imports model_alertmanager/model_feedback (through ui_next_check_execution)
  - This would cause a cycle if model_next_check_plan is imported during module load

Since _build_next_check_candidate_view needs ui_planner_queue helpers AND those helpers
are already effectively part of the builder's dependency, the builder stays in model.py.
The dataclasses can be safely extracted since they have no dependencies on ui_planner_queue.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .model_alertmanager import (
    AlertmanagerProvenanceView,
    _build_alertmanager_provenance_view,
)
from .model_feedback import (
    FeedbackAdaptationProvenanceView,
    _build_feedback_adaptation_provenance_view,
)
from .model_primitives import (
    _coerce_int,
    _coerce_optional_int,
    _coerce_optional_str,
    _coerce_str,
)


@dataclass(frozen=True)
class NextCheckCandidateView:
    """View model for a single next-check candidate within a plan."""
    candidate_id: str | None
    priority_label: str | None
    description: str
    target_cluster: str | None
    source_reason: str | None
    expected_signal: str | None
    suggested_command_family: str | None
    safe_to_automate: bool
    requires_operator_approval: bool
    risk_level: str
    estimated_cost: str
    confidence: str
    gating_reason: str | None
    duplicate_of_existing_evidence: bool
    duplicate_evidence_description: str | None
    approval_status: str | None
    approval_artifact_path: str | None
    approval_timestamp: str | None
    candidate_index: int | None
    normalization_reason: str | None
    safety_reason: str | None
    approval_reason: str | None
    duplicate_reason: str | None
    blocking_reason: str | None
    approval_state: str | None
    execution_state: str | None
    outcome_status: str | None
    latest_artifact_path: str | None
    latest_timestamp: str | None
    priority_rationale: str | None
    ranking_reason: str | None
    # Alertmanager provenance snapshot from ranking phase
    alertmanager_provenance: AlertmanagerProvenanceView | None = None
    # Feedback adaptation provenance from operator corrections
    feedback_adaptation_provenance: FeedbackAdaptationProvenanceView | None = None


@dataclass(frozen=True)
class NextCheckOrphanedApprovalView:
    """View model for an orphaned approval record within a plan."""
    approval_status: str | None
    candidate_id: str | None
    candidate_index: int | None
    candidate_description: str | None
    target_cluster: str | None
    plan_artifact_path: str | None
    approval_artifact_path: str | None
    approval_timestamp: str | None


@dataclass(frozen=True)
class NextCheckOutcomeCountView:
    """View model for outcome count statistics within a plan."""
    status: str
    count: int


@dataclass(frozen=True)
class NextCheckPlanView:
    """View model for the complete next-check plan."""
    status: str
    summary: str | None
    artifact_path: str | None
    review_path: str | None
    enrichment_artifact_path: str | None
    candidate_count: int
    candidates: tuple[NextCheckCandidateView, ...]
    orphaned_approvals: tuple[NextCheckOrphanedApprovalView, ...]
    outcome_counts: tuple[NextCheckOutcomeCountView, ...]
    orphaned_approval_count: int


def _build_orphaned_approval_view(raw: Mapping[str, object]) -> NextCheckOrphanedApprovalView:
    """Build NextCheckOrphanedApprovalView from raw JSON data.

    Handles both camelCase keys (from planner artifacts) and snake_case variants.
    Returns a view with all fields None for non-Mapping input.
    """
    return NextCheckOrphanedApprovalView(
        approval_status=_coerce_optional_str(raw.get("approvalStatus")),
        candidate_id=_coerce_optional_str(raw.get("candidateId")),
        candidate_index=_coerce_optional_int(raw.get("candidateIndex")),
        candidate_description=_coerce_optional_str(raw.get("candidateDescription")),
        target_cluster=_coerce_optional_str(raw.get("targetCluster")),
        plan_artifact_path=_coerce_optional_str(raw.get("planArtifactPath")),
        approval_artifact_path=_coerce_optional_str(raw.get("approvalArtifactPath")),
        approval_timestamp=_coerce_optional_str(raw.get("approvalTimestamp")),
    )


def _build_outcome_count_view(raw: Mapping[str, object]) -> NextCheckOutcomeCountView:
    """Build NextCheckOutcomeCountView from raw JSON data.

    Returns a view with default values for non-Mapping input.
    """
    return NextCheckOutcomeCountView(
        status=_coerce_str(raw.get("status")),
        count=_coerce_int(raw.get("count")),
    )


def _build_next_check_plan_view(raw: object | None) -> NextCheckPlanView | None:
    """Build NextCheckPlanView from raw JSON data (next_check_plan field).

    Returns None for non-Mapping input to signal missing plan.
    Silently skips non-Mapping entries in candidates/orphaned/outcome lists.
    Handles both camelCase keys (from planner artifacts) and snake_case variants.
    """
    if not isinstance(raw, Mapping):
        return None
    candidates_raw = raw.get("candidates") or raw.get("candidates") or ()
    candidates = tuple(
        _build_next_check_candidate_view_from_plan(entry)
        for entry in candidates_raw
        if isinstance(entry, Mapping)
    )
    orphaned_raw = raw.get("orphanedApprovals") or raw.get("orphaned_approvals") or ()
    orphaned = tuple(
        _build_orphaned_approval_view(entry)
        for entry in orphaned_raw
        if isinstance(entry, Mapping)
    )
    outcome_counts_raw = raw.get("outcomeCounts") or raw.get("outcome_counts") or ()
    outcome_counts = tuple(
        _build_outcome_count_view(entry)
        for entry in outcome_counts_raw
        if isinstance(entry, Mapping)
    )
    orphaned_count = _coerce_int(raw.get("orphanedApprovalCount") or raw.get("orphaned_approval_count"))
    return NextCheckPlanView(
        status=_coerce_str(raw.get("status")),
        summary=_coerce_optional_str(raw.get("summary")),
        artifact_path=_coerce_optional_str(raw.get("artifactPath") or raw.get("artifact_path")),
        review_path=_coerce_optional_str(raw.get("reviewPath") or raw.get("review_path")),
        enrichment_artifact_path=_coerce_optional_str(
            raw.get("enrichmentArtifactPath") or raw.get("enrichment_artifact_path")
        ),
        candidate_count=_coerce_int(raw.get("candidateCount") or raw.get("candidate_count")),
        candidates=candidates,
        orphaned_approvals=orphaned,
        outcome_counts=outcome_counts,
        orphaned_approval_count=orphaned_count,
    )


def _build_next_check_candidate_view_from_plan(raw: Mapping[str, object]) -> NextCheckCandidateView:
    """Build NextCheckCandidateView from raw JSON data (candidate entry within plan).

    This is a simplified builder for use in plan views. It does NOT include
    priority_rationale or ranking_reason derivation (those require ui_planner_queue).
    The full builder with ranking reason/priority rationale remains in model.py.

    Handles both camelCase keys (from planner artifacts) and snake_case variants.
    """
    provenance_raw = raw.get("alertmanagerProvenance") or raw.get("alertmanager_provenance")
    provenance = _build_alertmanager_provenance_view(provenance_raw)
    feedback_provenance_raw = raw.get("feedbackAdaptationProvenance") or raw.get("feedback_adaptation_provenance")
    feedback_provenance = _build_feedback_adaptation_provenance_view(feedback_provenance_raw)

    return NextCheckCandidateView(
        alertmanager_provenance=provenance,
        feedback_adaptation_provenance=feedback_provenance,
        candidate_id=_coerce_optional_str(raw.get("candidateId")),
        description=_coerce_str(raw.get("description")),
        target_cluster=_coerce_optional_str(raw.get("targetCluster")),
        source_reason=_coerce_optional_str(raw.get("sourceReason")),
        expected_signal=_coerce_optional_str(raw.get("expectedSignal")),
        suggested_command_family=_coerce_optional_str(raw.get("suggestedCommandFamily")),
        safe_to_automate=bool(raw.get("safeToAutomate")),
        requires_operator_approval=bool(raw.get("requiresOperatorApproval")),
        risk_level=_coerce_str(raw.get("riskLevel")),
        estimated_cost=_coerce_str(raw.get("estimatedCost")),
        confidence=_coerce_str(raw.get("confidence")),
        gating_reason=_coerce_optional_str(raw.get("gatingReason")),
        duplicate_of_existing_evidence=bool(raw.get("duplicateOfExistingEvidence")),
        duplicate_evidence_description=_coerce_optional_str(
            raw.get("duplicateEvidenceDescription")
        ),
        approval_status=_coerce_optional_str(raw.get("approvalStatus")),
        approval_artifact_path=_coerce_optional_str(raw.get("approvalArtifactPath")),
        approval_timestamp=_coerce_optional_str(raw.get("approvalTimestamp")),
        candidate_index=_coerce_optional_int(raw.get("candidateIndex")),
        normalization_reason=_coerce_optional_str(raw.get("normalizationReason")),
        safety_reason=_coerce_optional_str(raw.get("safetyReason")),
        approval_reason=_coerce_optional_str(raw.get("approvalReason")),
        duplicate_reason=_coerce_optional_str(raw.get("duplicateReason")),
        blocking_reason=_coerce_optional_str(raw.get("blockingReason")),
        approval_state=_coerce_optional_str(raw.get("approvalState")),
        execution_state=_coerce_optional_str(raw.get("executionState")),
        outcome_status=_coerce_optional_str(raw.get("outcomeStatus")),
        latest_artifact_path=_coerce_optional_str(raw.get("latestArtifactPath")),
        latest_timestamp=_coerce_optional_str(raw.get("latestTimestamp")),
        priority_label=_coerce_optional_str(raw.get("priorityLabel")),
        priority_rationale=_coerce_optional_str(raw.get("priorityRationale")),
        ranking_reason=_coerce_optional_str(raw.get("rankingReason")),
    )
