"""Next-check plan, candidate, and execution serialization functions for the operator UI.

This module contains serializer functions for next-check plan and execution payloads:
- Next-check plan serialization
- Next-check candidate serialization with Alertmanager and feedback adaptation provenance
- Orphaned approval serialization
- Execution history serialization
- Plan candidates filtered by cluster

Extracted from api.py to establish a clean separation of concerns.
These functions are re-exported from api.py for backward compatibility.

Ownership reminder:
    - Payload TypedDict classes live in api_payloads.py.
    - Serializer functions live here.
    - api.py is the public serialization surface.
"""

from __future__ import annotations

from typing import cast

from .api_payloads import (
    AlertmanagerProvenancePayload,
    FeedbackAdaptationProvenancePayload,
    NextCheckCandidatePayload,
    NextCheckExecutionHistoryEntry,
    NextCheckOrphanedApprovalPayload,
    NextCheckPlanPayload,
)
from .model import (
    NextCheckCandidateView,
    NextCheckExecutionHistoryEntryView,
    NextCheckOrphanedApprovalView,
    NextCheckPlanView,
)


def _serialize_next_check_plan(view: NextCheckPlanView | None) -> NextCheckPlanPayload | None:
    if not view:
        return None
    return {
        "status": view.status,
        "summary": view.summary,
        "artifactPath": view.artifact_path,
        "reviewPath": view.review_path,
        "enrichmentArtifactPath": view.enrichment_artifact_path,
        "candidateCount": view.candidate_count,
        "candidates": [_serialize_next_check_candidate(entry) for entry in view.candidates],
        "orphanedApprovals": [_serialize_orphaned_approval(entry) for entry in view.orphaned_approvals],
        "outcomeCounts": [{"status": entry.status, "count": entry.count} for entry in view.outcome_counts],
        "orphanedApprovalCount": view.orphaned_approval_count,
    }


def _serialize_next_check_candidate(view: NextCheckCandidateView) -> NextCheckCandidatePayload:
    """Serialize next-check candidate view to payload dict."""
    # Build provenance dict if present
    provenance: AlertmanagerProvenancePayload | None = None
    if view.alertmanager_provenance is not None:
        provenance = {
            "matchedDimensions": list(view.alertmanager_provenance.matched_dimensions),
            "matchedValues": {k: list(v) for k, v in view.alertmanager_provenance.matched_values.items()},
            "appliedBonus": view.alertmanager_provenance.applied_bonus,
            "baseBonus": view.alertmanager_provenance.base_bonus,
        }
        if view.alertmanager_provenance.severity_summary:
            provenance["severitySummary"] = view.alertmanager_provenance.severity_summary
        if view.alertmanager_provenance.signal_status:
            provenance["signalStatus"] = view.alertmanager_provenance.signal_status

    # Build feedback adaptation provenance dict if present
    feedback_provenance: FeedbackAdaptationProvenancePayload | None = None
    if view.feedback_adaptation_provenance is not None:
        feedback_provenance = {
            "feedbackAdaptation": view.feedback_adaptation_provenance.feedback_adaptation,
            "adaptationReason": view.feedback_adaptation_provenance.adaptation_reason,
            "originalBonus": view.feedback_adaptation_provenance.original_bonus,
            "suppressedBonus": view.feedback_adaptation_provenance.suppressed_bonus,
            "penaltyApplied": view.feedback_adaptation_provenance.penalty_applied,
        }
        if view.feedback_adaptation_provenance.explanation is not None:
            feedback_provenance["explanation"] = view.feedback_adaptation_provenance.explanation
        if view.feedback_adaptation_provenance.feedback_summary is not None:
            fs = view.feedback_adaptation_provenance.feedback_summary
            feedback_provenance["feedbackSummary"] = {
                "totalEntries": fs.total_entries,
                "namespacesWithFeedback": list(fs.namespaces_with_feedback),
                "clustersWithFeedback": list(fs.clusters_with_feedback),
                "servicesWithFeedback": list(fs.services_with_feedback),
            }

    payload: NextCheckCandidatePayload = {
        "description": view.description,
        "targetCluster": view.target_cluster,
        "sourceReason": view.source_reason,
        "expectedSignal": view.expected_signal,
        "suggestedCommandFamily": view.suggested_command_family,
        "safeToAutomate": view.safe_to_automate,
        "requiresOperatorApproval": view.requires_operator_approval,
        "riskLevel": view.risk_level,
        "estimatedCost": view.estimated_cost,
        "confidence": view.confidence,
        "gatingReason": view.gating_reason,
        "duplicateOfExistingEvidence": view.duplicate_of_existing_evidence,
        "duplicateEvidenceDescription": view.duplicate_evidence_description,
        "normalizationReason": view.normalization_reason,
        "safetyReason": view.safety_reason,
        "approvalReason": view.approval_reason,
        "duplicateReason": view.duplicate_reason,
        "blockingReason": view.blocking_reason,
        "approvalState": view.approval_state,
        "executionState": view.execution_state,
        "outcomeStatus": view.outcome_status,
        "latestArtifactPath": view.latest_artifact_path,
        "latestTimestamp": view.latest_timestamp,
    }
    if view.candidate_id is not None:
        payload["candidateId"] = view.candidate_id
    if view.candidate_index is not None:
        payload["candidateIndex"] = view.candidate_index
    if view.priority_label is not None:
        payload["priorityLabel"] = view.priority_label
    if view.priority_rationale is not None:
        payload["priorityRationale"] = view.priority_rationale
    if view.ranking_reason is not None:
        payload["rankingReason"] = view.ranking_reason
    if provenance is not None:
        payload["alertmanagerProvenance"] = provenance
    if feedback_provenance is not None:
        payload["feedbackAdaptationProvenance"] = feedback_provenance
    return payload


def _serialize_orphaned_approval(view: NextCheckOrphanedApprovalView) -> NextCheckOrphanedApprovalPayload:
    payload: NextCheckOrphanedApprovalPayload = {
        "approvalStatus": view.approval_status,
        "candidateId": view.candidate_id,
        "candidateIndex": view.candidate_index,
        "candidateDescription": view.candidate_description,
        "targetCluster": view.target_cluster,
        "planArtifactPath": view.plan_artifact_path,
        "approvalArtifactPath": view.approval_artifact_path,
        "approvalTimestamp": view.approval_timestamp,
    }
    return payload


def _serialize_execution_history(entries: tuple[NextCheckExecutionHistoryEntryView, ...]) -> list[NextCheckExecutionHistoryEntry]:
    result: list[NextCheckExecutionHistoryEntry] = []
    for entry in entries:
        serialized: dict[str, object] = {
            "timestamp": entry.timestamp,
            "clusterLabel": entry.cluster_label,
            "candidateDescription": entry.candidate_description,
            "commandFamily": entry.command_family,
            "status": entry.status,
            "durationMs": entry.duration_ms,
            "artifactPath": entry.artifact_path,
            "timedOut": entry.timed_out,
            "stdoutTruncated": entry.stdout_truncated,
            "stderrTruncated": entry.stderr_truncated,
            "outputBytesCaptured": entry.output_bytes_captured,
            "packRefreshStatus": entry.pack_refresh_status,
            "packRefreshWarning": entry.pack_refresh_warning,
            "failureClass": entry.failure_class,
            "failureSummary": entry.failure_summary,
            "suggestedNextOperatorMove": entry.suggested_next_operator_move,
            "resultClass": entry.result_class,
            "resultSummary": entry.result_summary,
            "usefulnessClass": entry.usefulness_class,
            "usefulnessSummary": entry.usefulness_summary,
            # Provenance fields for traceability
            "candidateId": entry.candidate_id,
            "candidateIndex": entry.candidate_index,
            # Artifact identity for immutability traceability
            "artifactId": entry.artifact_id,
            # Usefulness review artifact identity fields
            "usefulnessArtifactId": entry.usefulness_artifact_id,
            "usefulnessArtifactPath": entry.usefulness_artifact_path,
            "usefulnessReviewedAt": entry.usefulness_reviewed_at,
        }
        # Include Alertmanager provenance if present
        if entry.alertmanager_provenance is not None:
            serialized["alertmanagerProvenance"] = entry.alertmanager_provenance
        # Include Alertmanager relevance judgment if present
        if entry.alertmanager_relevance is not None:
            serialized["alertmanagerRelevance"] = entry.alertmanager_relevance
        if entry.alertmanager_relevance_summary is not None:
            serialized["alertmanagerRelevanceSummary"] = entry.alertmanager_relevance_summary
        result.append(cast(NextCheckExecutionHistoryEntry, serialized))
    return result


def _serialize_plan_candidates_for_cluster(
    label: str | None, plan: NextCheckPlanView | None
) -> list[NextCheckCandidatePayload]:
    """Serialize next-check plan candidates filtered for a specific cluster."""
    if not plan:
        return []
    payloads: list[NextCheckCandidatePayload] = []
    for index, candidate in enumerate(plan.candidates):
        if label and candidate.target_cluster and candidate.target_cluster != label:
            continue
        payload = _serialize_next_check_candidate(candidate)
        payload["candidateIndex"] = index
        payloads.append(payload)
    return payloads
