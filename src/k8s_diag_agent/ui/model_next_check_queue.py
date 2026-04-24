"""View models for next-check queue UI layer (UI model module).

This module contains queue-specific view model dataclasses and builders extracted from model.py.
It exists to enable incremental modularization without changing behavior.

Dependency direction: model_next_check_queue.py -> model_primitives.py, model_alertmanager.py, model_feedback.py
model.py imports from model_next_check_queue.py for re-export compatibility.

The new module does NOT import from ui_planner_queue, keeping the queue UI layer independent
of the planner domain logic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
    _coerce_sequence,
    _coerce_str,
)


@dataclass(frozen=True)
class NextCheckQueueItemView:
    """View model for a single item in the next-check execution queue."""
    candidate_id: str | None
    candidate_index: int | None
    description: str
    target_cluster: str | None
    priority_label: str | None
    suggested_command_family: str | None
    safe_to_automate: bool
    requires_operator_approval: bool
    approval_state: str | None
    execution_state: str | None
    outcome_status: str | None
    latest_artifact_path: str | None
    queue_status: str
    source_reason: str | None
    source_type: str | None
    expected_signal: str | None
    normalization_reason: str | None
    safety_reason: str | None
    approval_reason: str | None
    duplicate_reason: str | None
    blocking_reason: str | None
    target_context: str | None
    command_preview: str | None
    plan_artifact_path: str | None
    failure_class: str | None = None
    failure_summary: str | None = None
    suggested_next_operator_move: str | None = None
    result_class: str | None = None
    result_summary: str | None = None
    workstream: str | None = None
    # Alertmanager provenance snapshot from ranking phase
    alertmanager_provenance: AlertmanagerProvenanceView | None = None
    # Feedback adaptation provenance from operator corrections
    feedback_adaptation_provenance: FeedbackAdaptationProvenanceView | None = None


@dataclass(frozen=True)
class NextCheckQueueCandidateAccountingView:
    """View model for queue candidate accounting statistics."""
    generated: int
    safe: int
    approval_needed: int
    duplicate: int
    completed: int
    stale_orphaned: int
    orphaned_approvals: int


@dataclass(frozen=True)
class NextCheckQueueClusterStateView:
    """View model for cluster state summary within queue context."""
    degraded_cluster_count: int
    degraded_cluster_labels: tuple[str, ...]
    deterministic_next_check_count: int
    deterministic_cluster_count: int
    drilldown_ready_count: int


@dataclass(frozen=True)
class NextCheckQueueExplanationView:
    """View model for the queue explanation/status with recommended actions."""
    status: str
    reason: str | None
    hint: str | None
    planner_artifact_path: str | None
    cluster_state: NextCheckQueueClusterStateView
    candidate_accounting: NextCheckQueueCandidateAccountingView
    deterministic_next_checks_available: bool
    recommended_next_actions: tuple[str, ...]


def _build_queue_item_view(
    raw: Mapping[str, object],
) -> NextCheckQueueItemView:
    """Build NextCheckQueueItemView from raw JSON data (queue item entry).
    
    Handles both camelCase keys (from planner artifacts) and snake_case variants
    for Alertmanager/feedback provenance fields.
    """
    # Build Alertmanager provenance from queue item
    provenance_raw = raw.get("alertmanagerProvenance") or raw.get("alertmanager_provenance")
    provenance = _build_alertmanager_provenance_view(provenance_raw)
    
    # Build feedback adaptation provenance
    feedback_provenance_raw = raw.get("feedbackAdaptationProvenance") or raw.get("feedback_adaptation_provenance")
    feedback_provenance = _build_feedback_adaptation_provenance_view(feedback_provenance_raw)
    
    return NextCheckQueueItemView(
        candidate_id=_coerce_optional_str(raw.get("candidateId")),
        candidate_index=_coerce_optional_int(raw.get("candidateIndex")),
        description=_coerce_str(raw.get("description")),
        target_cluster=_coerce_optional_str(raw.get("targetCluster")),
        priority_label=_coerce_optional_str(raw.get("priorityLabel")),
        suggested_command_family=_coerce_optional_str(raw.get("suggestedCommandFamily")),
        safe_to_automate=bool(raw.get("safeToAutomate")),
        requires_operator_approval=bool(raw.get("requiresOperatorApproval")),
        approval_state=_coerce_optional_str(raw.get("approvalState")),
        execution_state=_coerce_optional_str(raw.get("executionState")),
        outcome_status=_coerce_optional_str(raw.get("outcomeStatus")),
        latest_artifact_path=_coerce_optional_str(raw.get("latestArtifactPath")),
        queue_status=_coerce_str(raw.get("queueStatus")),
        source_reason=_coerce_optional_str(raw.get("sourceReason")),
        source_type=_coerce_optional_str(raw.get("sourceType")),
        expected_signal=_coerce_optional_str(raw.get("expectedSignal")),
        normalization_reason=_coerce_optional_str(raw.get("normalizationReason")),
        safety_reason=_coerce_optional_str(raw.get("safetyReason")),
        approval_reason=_coerce_optional_str(raw.get("approvalReason")),
        duplicate_reason=_coerce_optional_str(raw.get("duplicateReason")),
        blocking_reason=_coerce_optional_str(raw.get("blockingReason")),
        target_context=_coerce_optional_str(raw.get("targetContext")),
        command_preview=_coerce_optional_str(raw.get("commandPreview")),
        plan_artifact_path=_coerce_optional_str(raw.get("planArtifactPath")),
        failure_class=_coerce_optional_str(raw.get("failureClass")),
        failure_summary=_coerce_optional_str(raw.get("failureSummary")),
        suggested_next_operator_move=_coerce_optional_str(raw.get("suggestedNextOperatorMove")),
        result_class=_coerce_optional_str(raw.get("resultClass")),
        result_summary=_coerce_optional_str(raw.get("resultSummary")),
        workstream=_coerce_optional_str(raw.get("workstream")),
        alertmanager_provenance=provenance,
        feedback_adaptation_provenance=feedback_provenance,
    )


def _build_next_check_queue_view(
    raw: object | None,
) -> tuple[NextCheckQueueItemView, ...]:
    """Build tuple of NextCheckQueueItemView from raw JSON data (next_check_queue field).
    
    Returns empty tuple for non-Sequence input to preserve queue ordering semantics.
    Silently skips non-Mapping entries to handle malformed data gracefully.
    """
    if not isinstance(raw, Sequence):
        return ()
    entries: list[NextCheckQueueItemView] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        entries.append(_build_queue_item_view(entry))
    return tuple(entries)


def _build_queue_cluster_state_view(
    raw: object | None,
) -> NextCheckQueueClusterStateView:
    """Build NextCheckQueueClusterStateView from raw JSON data (clusterState field).
    
    Returns default/empty state for non-Mapping input.
    """
    if not isinstance(raw, Mapping):
        return NextCheckQueueClusterStateView(
            degraded_cluster_count=0,
            degraded_cluster_labels=(),
            deterministic_next_check_count=0,
            deterministic_cluster_count=0,
            drilldown_ready_count=0,
        )
    return NextCheckQueueClusterStateView(
        degraded_cluster_count=_coerce_int(raw.get("degradedClusterCount")),
        degraded_cluster_labels=_coerce_sequence(raw.get("degradedClusterLabels")),
        deterministic_next_check_count=_coerce_int(raw.get("deterministicNextCheckCount")),
        deterministic_cluster_count=_coerce_int(raw.get("deterministicClusterCount")),
        drilldown_ready_count=_coerce_int(raw.get("drilldownReadyCount")),
    )


def _build_queue_candidate_accounting_view(
    raw: object | None,
) -> NextCheckQueueCandidateAccountingView:
    """Build NextCheckQueueCandidateAccountingView from raw JSON data (candidateAccounting field).
    
    Returns default/empty accounting for non-Mapping input.
    """
    if not isinstance(raw, Mapping):
        return NextCheckQueueCandidateAccountingView(
            generated=0,
            safe=0,
            approval_needed=0,
            duplicate=0,
            completed=0,
            stale_orphaned=0,
            orphaned_approvals=0,
        )
    return NextCheckQueueCandidateAccountingView(
        generated=_coerce_int(raw.get("generated")),
        safe=_coerce_int(raw.get("safe")),
        approval_needed=_coerce_int(raw.get("approvalNeeded")),
        duplicate=_coerce_int(raw.get("duplicate")),
        completed=_coerce_int(raw.get("completed")),
        stale_orphaned=_coerce_int(raw.get("staleOrphaned")),
        orphaned_approvals=_coerce_int(raw.get("orphanedApprovals")),
    )


def _build_queue_explanation_view(
    raw: object | None,
) -> NextCheckQueueExplanationView | None:
    """Build NextCheckQueueExplanationView from raw JSON data (next_check_queue_explanation field).
    
    Returns None for non-Mapping input to signal missing explanation.
    Filters recommended actions to non-empty strings only.
    """
    if not isinstance(raw, Mapping):
        return None
    recommended_actions_raw = raw.get("recommendedNextActions") or ()
    recommended_actions = tuple(
        str(entry) for entry in recommended_actions_raw if isinstance(entry, str) and entry.strip()
    )
    return NextCheckQueueExplanationView(
        status=_coerce_str(raw.get("status")),
        reason=_coerce_optional_str(raw.get("reason")),
        hint=_coerce_optional_str(raw.get("hint")),
        planner_artifact_path=_coerce_optional_str(raw.get("plannerArtifactPath")),
        cluster_state=_build_queue_cluster_state_view(raw.get("clusterState")),
        candidate_accounting=_build_queue_candidate_accounting_view(raw.get("candidateAccounting")),
        deterministic_next_checks_available=bool(raw.get("deterministicNextChecksAvailable")),
        recommended_next_actions=recommended_actions,
    )
