"""Next-check queue and planner-availability serialization functions for the operator UI.

This module contains serializer functions for next-check queue and planner-availability payloads:
- Queue item serialization with Alertmanager and feedback adaptation provenance
- Queue cluster state and candidate accounting summaries
- Queue explanation (compound view combining cluster state and accounting)
- Planner availability state

Extracted from api.py to establish a clean separation of concerns.
These functions are re-exported from api.py for backward compatibility.

Ownership reminder:
    - Payload TypedDict classes live in api_payloads.py.
    - Serializer functions live here.
    - api.py is the public serialization surface.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from .api_payloads import (
    AlertmanagerProvenancePayload,
    FeedbackAdaptationProvenancePayload,
    NextCheckQueueCandidateAccountingPayload,
    NextCheckQueueClusterStatePayload,
    NextCheckQueueExplanationPayload,
    NextCheckQueueItemPayload,
    PlannerAvailabilityPayload,
)
from .model import (
    NextCheckQueueCandidateAccountingView,
    NextCheckQueueClusterStateView,
    NextCheckQueueExplanationView,
    NextCheckQueueItemView,
    PlannerAvailabilityView,
)


def _serialize_next_check_queue(
    queue: tuple[NextCheckQueueItemView, ...],
    promotions: Sequence[Mapping[str, object]] | None = None,
) -> list[NextCheckQueueItemPayload]:
    entries: list[NextCheckQueueItemPayload] = []
    for item in queue:
        # Build provenance dict if present
        provenance: AlertmanagerProvenancePayload | None = None
        if item.alertmanager_provenance is not None:
            provenance = {
                "matchedDimensions": list(item.alertmanager_provenance.matched_dimensions),
                "matchedValues": {k: list(v) for k, v in item.alertmanager_provenance.matched_values.items()},
                "appliedBonus": item.alertmanager_provenance.applied_bonus,
                "baseBonus": item.alertmanager_provenance.base_bonus,
            }
            if item.alertmanager_provenance.severity_summary:
                provenance["severitySummary"] = item.alertmanager_provenance.severity_summary
            if item.alertmanager_provenance.signal_status:
                provenance["signalStatus"] = item.alertmanager_provenance.signal_status

        # Build feedback adaptation provenance dict if present
        feedback_provenance: FeedbackAdaptationProvenancePayload | None = None
        if item.feedback_adaptation_provenance is not None:
            feedback_provenance = {
                "feedbackAdaptation": item.feedback_adaptation_provenance.feedback_adaptation,
                "adaptationReason": item.feedback_adaptation_provenance.adaptation_reason,
                "originalBonus": item.feedback_adaptation_provenance.original_bonus,
                "suppressedBonus": item.feedback_adaptation_provenance.suppressed_bonus,
                "penaltyApplied": item.feedback_adaptation_provenance.penalty_applied,
            }
            if item.feedback_adaptation_provenance.explanation is not None:
                feedback_provenance["explanation"] = item.feedback_adaptation_provenance.explanation
            if item.feedback_adaptation_provenance.feedback_summary is not None:
                fs = item.feedback_adaptation_provenance.feedback_summary
                feedback_provenance["feedbackSummary"] = {
                    "totalEntries": fs.total_entries,
                    "namespacesWithFeedback": list(fs.namespaces_with_feedback),
                    "clustersWithFeedback": list(fs.clusters_with_feedback),
                    "servicesWithFeedback": list(fs.services_with_feedback),
                }

        entry: NextCheckQueueItemPayload = {
            "candidateId": item.candidate_id,
            "candidateIndex": item.candidate_index,
            "description": item.description,
            "targetCluster": item.target_cluster,
            "priorityLabel": item.priority_label,
            "suggestedCommandFamily": item.suggested_command_family,
            "safeToAutomate": item.safe_to_automate,
            "requiresOperatorApproval": item.requires_operator_approval,
            "approvalState": item.approval_state,
            "executionState": item.execution_state,
            "outcomeStatus": item.outcome_status,
            "latestArtifactPath": item.latest_artifact_path,
            "sourceReason": item.source_reason,
            "sourceType": item.source_type,
            "expectedSignal": item.expected_signal,
            "normalizationReason": item.normalization_reason,
            "safetyReason": item.safety_reason,
            "approvalReason": item.approval_reason,
            "duplicateReason": item.duplicate_reason,
            "blockingReason": item.blocking_reason,
            "failureClass": item.failure_class,
            "failureSummary": item.failure_summary,
            "suggestedNextOperatorMove": item.suggested_next_operator_move,
            "resultClass": item.result_class,
            "resultSummary": item.result_summary,
            "targetContext": item.target_context,
            "commandPreview": item.command_preview,
            "planArtifactPath": item.plan_artifact_path,
            "queueStatus": item.queue_status,
            "workstream": item.workstream,
        }
        if provenance is not None:
            entry["alertmanagerProvenance"] = provenance
        if feedback_provenance is not None:
            entry["feedbackAdaptationProvenance"] = feedback_provenance
        entries.append(entry)
    if promotions:
        for promo_entry in promotions:
            if isinstance(entry, Mapping):
                entries.append(cast(NextCheckQueueItemPayload, dict(promo_entry)))
    return entries


def _serialize_queue_cluster_state(
    view: NextCheckQueueClusterStateView,
) -> NextCheckQueueClusterStatePayload:
    return {
        "degradedClusterCount": view.degraded_cluster_count,
        "degradedClusterLabels": list(view.degraded_cluster_labels),
        "deterministicNextCheckCount": view.deterministic_next_check_count,
        "deterministicClusterCount": view.deterministic_cluster_count,
        "drilldownReadyCount": view.drilldown_ready_count,
    }


def _serialize_queue_candidate_accounting(
    view: NextCheckQueueCandidateAccountingView,
) -> NextCheckQueueCandidateAccountingPayload:
    return {
        "generated": view.generated,
        "safe": view.safe,
        "approvalNeeded": view.approval_needed,
        "duplicate": view.duplicate,
        "completed": view.completed,
        "staleOrphaned": view.stale_orphaned,
        "orphanedApprovals": view.orphaned_approvals,
    }


def _serialize_queue_explanation(
    explanation: NextCheckQueueExplanationView | None,
) -> NextCheckQueueExplanationPayload | None:
    if not explanation:
        return None
    return {
        "status": explanation.status,
        "reason": explanation.reason,
        "hint": explanation.hint,
        "plannerArtifactPath": explanation.planner_artifact_path,
        "clusterState": _serialize_queue_cluster_state(explanation.cluster_state),
        "candidateAccounting": _serialize_queue_candidate_accounting(explanation.candidate_accounting),
        "deterministicNextChecksAvailable": explanation.deterministic_next_checks_available,
        "recommendedNextActions": list(explanation.recommended_next_actions),
    }


def _serialize_planner_availability(
    view: PlannerAvailabilityView | None,
) -> PlannerAvailabilityPayload | None:
    if not view:
        return None
    return {
        "status": view.status,
        "reason": view.reason,
        "hint": view.hint,
        "artifactPath": view.artifact_path,
        "nextActionHint": view.next_action_hint,
    }
