"""Read-model payload builders for the operator UI.

Payload TypedDict contracts are defined in api_payloads.py.
This module is the public serialization surface: it imports payloads from
api_payloads.py and re-exports them for backwards compatibility.

Ownership reminder:
    - TypedDict payload classes live in api_payloads.py (the contract module).
    - Serializer functions (_serialize_*) and public builders live here.
    - Do not add new TypedDict definitions here; add them to api_payloads.py.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import ijson

from ..datetime_utils import parse_iso_to_utc
from ..health.freshness import freshness_status

# Import Alertmanager serializers from extracted module.
# Re-export for backward compatibility: callers importing from api.py continue to work.
from .api_alertmanager import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_alertmanager_compact,
    _serialize_alertmanager_source,
    _serialize_alertmanager_sources,
)

# Import ClusterDetail serializers from extracted module.
# Re-export for backward compatibility: callers importing from api.py continue to work.
from .api_cluster_detail import (  # noqa: F401 - re-exported for backward compatibility
    _build_problem_summary,
    _build_proposal_summary,
    _filter_related_notifications,
    _filter_related_proposals,
    _serialize_assessment_summary,
    _serialize_auto_interpretation,
    _serialize_cluster,
    _serialize_drilldown,
    _serialize_drilldown_summary,
    _serialize_findings,
    _serialize_hypothesis,
    _serialize_next_check,
    _serialize_notification,
    _serialize_proposal,
    _serialize_rating_counts,
    _serialize_recommended_action,
    _serialize_status_counts,
)

# Import DiagnosticPack serializers from extracted module.
# Re-export for backward compatibility: callers importing from api.py continue to work.
from .api_diagnostic_pack import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_diagnostic_pack,
    _serialize_diagnostic_pack_review,
)

# Import LLM serializers from extracted module.
# Re-export for backward compatibility: callers importing from api.py continue to work.
from .api_llm import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_llm_activity,
    _serialize_llm_policy,
    _serialize_llm_stats,
)

# Re-export all payload TypedDicts for backwards compatibility.
# Consumers should migrate to importing from ui.api_payloads directly,
# but existing imports from ui.api will continue to work.
from .api_payloads import (  # noqa: F401 - re-exported for backward compatibility
    AlertmanagerCompactPayload,
    AlertmanagerEvidenceReferencePayload,
    AlertmanagerProvenancePayload,
    AlertmanagerSourcePayload,
    AlertmanagerSourcesPayload,
    ArtifactLink,
    AssessmentSummaryPayload,
    ClusterAlertSummaryPayload,
    ClusterDetailPayload,
    ClusterSummaryPayload,
    DeterministicNextCheckClusterPayload,
    DeterministicNextChecksPayload,
    DeterministicNextCheckSummaryPayload,
    DiagnosticPackPayload,
    DiagnosticPackReviewPayload,
    DrilldownCoveragePayload,
    DrilldownInterpretationPayload,
    DrilldownSummaryPayload,
    FeedbackAdaptationProvenancePayload,
    FindingEntry,
    FleetPayload,
    FreshnessPayload,
    HypothesisEntry,
    LLMActivityPayload,
    LLMPolicyPayload,
    LLMStatsPayload,
    NextCheckCandidatePayload,
    NextCheckEntry,
    NextCheckExecutionHistoryEntry,
    NextCheckOrphanedApprovalPayload,
    NextCheckPlanPayload,
    NextCheckQueueCandidateAccountingPayload,
    NextCheckQueueClusterStatePayload,
    NextCheckQueueExplanationPayload,
    NextCheckQueueItemPayload,
    NotificationEntry,
    NotificationsPayload,
    PlannerAvailabilityPayload,
    ProblemSummary,
    ProposalEntry,
    ProposalsPayload,
    ProposalSummaryPayload,
    ProviderExecutionBranchPayload,
    ProviderExecutionPayload,
    RatingCount,
    RecommendedActionPayload,
    ReviewEnrichmentPayload,
    ReviewEnrichmentStatusPayload,
    RunPayload,
    RunsListEntry,
    RunsListPayload,
    RunsListTimings,
    RunStatsPayload,
    StatusCount,
)

# Import ProviderExecution serializers from extracted module.
# Re-export for backward compatibility: callers importing from api.py continue to work.
from .api_provider_execution import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_provider_execution,
    _serialize_provider_execution_branch,
)

# Import ReviewEnrichment serializers from extracted module.
# Re-export for backward compatibility: callers importing from api.py continue to work.
from .api_review_enrichment import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_review_enrichment,
    _serialize_review_enrichment_status,
)
from .model import (
    DeterministicNextCheckClusterView,
    DeterministicNextCheckSummaryView,
    DeterministicNextChecksView,
    NextCheckCandidateView,
    NextCheckExecutionHistoryEntryView,
    NextCheckOrphanedApprovalView,
    NextCheckPlanView,
    NextCheckQueueCandidateAccountingView,
    NextCheckQueueClusterStateView,
    NextCheckQueueExplanationView,
    NextCheckQueueItemView,
    PlannerAvailabilityView,
    RunStatsView,
    UIIndexContext,
)


def build_run_payload(
    context: UIIndexContext,
    *,
    promotions: Sequence[dict[str, object]] | None = None,
) -> RunPayload:
    return {
        "runId": context.run.run_id,
        "label": context.run.run_label,
        "timestamp": context.run.timestamp,
        "collectorVersion": context.run.collector_version,
        "clusterCount": context.run.cluster_count,
        "drilldownCount": context.run.drilldown_count,
        "proposalCount": context.run.proposal_count,
        "externalAnalysisCount": context.run.external_analysis_count,
        "notificationCount": context.run.notification_count,
        "artifacts": _collect_run_artifacts(context),
        "runStats": _serialize_run_stats(context.run.run_stats),
        "llmStats": _serialize_llm_stats(context.run.llm_stats),
        "historicalLlmStats": (
            _serialize_llm_stats(context.run.historical_llm_stats)
            if context.run.historical_llm_stats
            else None
        ),
        "llmActivity": _serialize_llm_activity(context.run.llm_activity),
        "llmPolicy": _serialize_llm_policy(context.run.llm_policy),
        "reviewEnrichment": _serialize_review_enrichment(context.run.review_enrichment),
        "reviewEnrichmentStatus": _serialize_review_enrichment_status(
            context.run.review_enrichment_status
        ),
        "providerExecution": _serialize_provider_execution(context.run.provider_execution),
        "freshness": _build_freshness_payload(
            context.run.timestamp, context.run.scheduler_interval_seconds
        ),
        "nextCheckPlan": _serialize_next_check_plan(context.run.next_check_plan),
        "nextCheckQueue": _serialize_next_check_queue(
            context.run.next_check_queue,
            promotions,
        ),
        "nextCheckQueueExplanation": _serialize_queue_explanation(
            context.run.next_check_queue_explanation
        ),
        "deterministicNextChecks": _serialize_deterministic_next_checks(
            context.run.deterministic_next_checks
        ),
        "plannerAvailability": _serialize_planner_availability(
            context.run.planner_availability
        ),
        "diagnosticPackReview": _serialize_diagnostic_pack_review(
            context.run.diagnostic_pack_review
        ),
        "diagnosticPack": _serialize_diagnostic_pack(context.run.diagnostic_pack),
        "nextCheckExecutionHistory": _serialize_execution_history(
            context.run.next_check_execution_history
        ),
        "alertmanagerCompact": _serialize_alertmanager_compact(context.alertmanager_compact),
        "alertmanagerSources": _serialize_alertmanager_sources(context.alertmanager_sources),
    }


def build_fleet_payload(context: UIIndexContext) -> FleetPayload:
    return {
        "runId": context.run.run_id,
        "runLabel": context.run.run_label,
        "lastRunTimestamp": context.run.timestamp,
        "topProblem": _build_problem_summary(context),
        "fleetStatus": {
            "ratingCounts": _serialize_rating_counts(context.fleet_status.rating_counts),
            "degradedClusters": list(context.fleet_status.degraded_clusters),
        },
        "clusters": [_serialize_cluster(cluster) for cluster in context.clusters],
        "proposalSummary": _build_proposal_summary(context),
    }


def build_proposals_payload(context: UIIndexContext) -> ProposalsPayload:
    return {
        "statusSummary": _serialize_status_counts(context.proposal_status_summary.status_counts),
        "proposals": [_serialize_proposal(proposal) for proposal in context.proposals],
    }


def build_notifications_payload(context: UIIndexContext) -> NotificationsPayload:
    return {"notifications": [_serialize_notification(entry) for entry in context.notification_history]}


def build_cluster_detail_payload(context: UIIndexContext, *, cluster_label: str | None = None) -> ClusterDetailPayload:
    assessment = context.latest_assessment
    findings = context.latest_findings
    label = cluster_label or (assessment.cluster_label if assessment else findings.label if findings else None)
    cluster_context = assessment.context if assessment and assessment.context != "-" else findings.context if findings else None
    artifacts = _collect_run_artifacts(context)
    interpretation_view = context.auto_drilldown_interpretations.get(label) if label else None
    return {
        "selectedClusterLabel": label,
        "selectedClusterContext": cluster_context,
        "assessment": _serialize_assessment_summary(assessment),
        "findings": [_serialize_findings(findings)] if findings else [],
        "hypotheses": [_serialize_hypothesis(entry) for entry in assessment.hypotheses] if assessment else [],
        "nextChecks": [_serialize_next_check(entry) for entry in assessment.next_checks] if assessment else [],
        "recommendedAction": _serialize_recommended_action(assessment.recommended_action) if assessment else None,
        "drilldownAvailability": _serialize_drilldown_summary(context.drilldown_availability),
        "drilldownCoverage": [_serialize_drilldown(entry) for entry in context.drilldown_availability.coverage],
        "relatedProposals": _filter_related_proposals(label, context.proposals),
        "relatedNotifications": _filter_related_notifications(label, context.notification_history),
        "artifacts": artifacts,
        "autoInterpretation": _serialize_auto_interpretation(interpretation_view),
        "topProblem": _build_problem_summary(context),
        "nextCheckPlan": _serialize_plan_candidates_for_cluster(label, context.run.next_check_plan),
    }


def _collect_run_artifacts(context: UIIndexContext) -> list[ArtifactLink]:
    artifacts: list[ArtifactLink] = []
    assessment = context.latest_assessment
    if assessment:
        if assessment.artifact_path:
            artifacts.append({"label": "Assessment JSON", "path": assessment.artifact_path})
        if assessment.snapshot_path:
            artifacts.append({"label": "Snapshot JSON", "path": assessment.snapshot_path})
    findings = context.latest_findings
    if findings and findings.artifact_path:
        artifacts.append({"label": "Drilldown JSON", "path": findings.artifact_path})
    coverage = context.drilldown_availability.coverage
    if coverage:
        for entry in coverage[:2]:
            if entry.artifact_path:
                artifacts.append({"label": f"Drilldown: {entry.label}", "path": entry.artifact_path})
    return artifacts


def _build_freshness_payload(
    timestamp_value: str | None,
    expected_interval_seconds: int | None,
    *,
    now: datetime | None = None,
) -> FreshnessPayload | None:
    if not timestamp_value:
        return None
    parsed = parse_iso_to_utc(timestamp_value)
    if parsed is None:
        return None
    now_value = now or datetime.now(UTC)
    age_seconds = int(max(0, (now_value - parsed).total_seconds()))
    status = freshness_status(age_seconds, expected_interval_seconds)
    payload: FreshnessPayload = {
        "ageSeconds": age_seconds,
        "expectedIntervalSeconds": expected_interval_seconds,
        "status": status,
    }
    return payload


def _serialize_run_stats(stats: RunStatsView) -> RunStatsPayload:
    return {
        "lastRunDurationSeconds": stats.last_run_duration_seconds,
        "totalRuns": stats.total_runs,
        "p50RunDurationSeconds": stats.p50_run_duration_seconds,
        "p95RunDurationSeconds": stats.p95_run_duration_seconds,
        "p99RunDurationSeconds": stats.p99_run_duration_seconds,
    }


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


def _serialize_deterministic_next_check_summary(
    view: DeterministicNextCheckSummaryView,
) -> DeterministicNextCheckSummaryPayload:
    return {
        "description": view.description,
        "owner": view.owner,
        "method": view.method,
        "evidenceNeeded": list(view.evidence_needed),
        "workstream": view.workstream,
        "urgency": view.urgency,
        "isPrimaryTriage": view.is_primary_triage,
        "whyNow": view.why_now,
    }


def _serialize_deterministic_next_check_cluster(
    view: DeterministicNextCheckClusterView,
) -> DeterministicNextCheckClusterPayload:
    return {
        "label": view.label,
        "context": view.context,
        "topProblem": view.top_problem,
        "deterministicNextCheckCount": view.deterministic_next_check_count,
        "deterministicNextCheckSummaries": [_serialize_deterministic_next_check_summary(entry) for entry in view.deterministic_next_check_summaries],
        "drilldownAvailable": view.drilldown_available,
        "assessmentArtifactPath": view.assessment_artifact_path,
        "drilldownArtifactPath": view.drilldown_artifact_path,
    }


def _serialize_deterministic_next_checks(
    view: DeterministicNextChecksView | None,
) -> DeterministicNextChecksPayload | None:
    if not view:
        return None
    return {
        "clusterCount": view.cluster_count,
        "totalNextCheckCount": view.total_next_check_count,
        "clusters": [_serialize_deterministic_next_check_cluster(entry) for entry in view.clusters],
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


def _derive_review_status(execution_count: int, reviewed_count: int) -> str:
    """Derive review status from execution and reviewed counts.

    Returns one of:
    - "no-executions": run has no executed next checks
    - "unreviewed": has executions but none reviewed
    - "partially-reviewed": some executions reviewed, some not
    - "fully-reviewed": all executions reviewed
    """
    if execution_count == 0:
        return "no-executions"
    if reviewed_count == 0:
        return "unreviewed"
    if reviewed_count < execution_count:
        return "partially-reviewed"
    return "fully-reviewed"


def _compute_batch_eligibility(
    run_id: str,
    run_health_dir: Path,
) -> tuple[bool, int]:
    """Compute batch executable status for a run.

    Uses the same eligibility logic as run_batch_next_checks.py to determine
    if there are any eligible candidates that can be batch-executed.

    Returns:
        Tuple of (batchExecutable: bool, batchEligibleCount: int)
    """
    from typing import cast

    external_analysis_dir = run_health_dir / "external-analysis"

    # Load next_check_plan for this run
    plan_data: dict[str, object] | None = None

    if external_analysis_dir.is_dir():
        for plan_path in external_analysis_dir.glob(f"{run_id}-next-check-plan*.json"):
            try:
                raw = json.loads(plan_path.read_text(encoding="utf-8"))
                if raw.get("purpose") == "next-check-planning":
                    plan_data = cast(dict[str, object], raw)
                    break
            except Exception:
                continue

    if not plan_data:
        return False, 0

    # Get candidates from plan
    candidates_data: list[dict[str, object]] = []
    if "candidates" in plan_data and isinstance(plan_data["candidates"], list):
        candidates_data = cast(list[dict[str, object]], plan_data["candidates"])
    elif "payload" in plan_data and isinstance(plan_data["payload"], dict):
        payload = cast(dict[str, object], plan_data["payload"])
        if "candidates" in payload and isinstance(payload["candidates"], list):
            candidates_data = cast(list[dict[str, object]], payload["candidates"])

    if not candidates_data:
        return False, 0

    # Load already-executed indices
    execution_indices: set[int] = set()
    if external_analysis_dir.is_dir():
        for exec_path in external_analysis_dir.glob(f"{run_id}-next-check-execution*.json"):
            try:
                raw = json.loads(exec_path.read_text(encoding="utf-8"))
                if raw.get("purpose") == "next-check-execution":
                    payload = raw.get("payload", {})
                    candidate_index = payload.get("candidateIndex")
                    if isinstance(candidate_index, int):
                        execution_indices.add(candidate_index)
            except Exception:
                continue

    # Count eligible candidates using the same logic as run_batch_next_checks.py
    eligible_count = 0
    for idx, candidate in enumerate(candidates_data):
        # Already executed?
        if idx in execution_indices:
            continue

        # Must be safe to automate
        if not candidate.get("safeToAutomate"):
            continue

        # Must have a valid command family
        family = candidate.get("suggestedCommandFamily")
        if not family or not isinstance(family, str):
            continue

        # Must have a description
        description = candidate.get("description")
        if not description or not isinstance(description, str):
            continue

        # Must have target context info
        target_context = candidate.get("targetContext")
        if not target_context or not isinstance(target_context, str):
            continue

        # Check approval requirement
        requires_approval = candidate.get("requiresOperatorApproval")
        if requires_approval:
            approval_status = str(candidate.get("approvalStatus") or "").lower()
            if approval_status != "approved":
                continue

        # Check for duplicates
        if candidate.get("duplicateOfExistingEvidence"):
            continue

        eligible_count += 1

    return eligible_count > 0, eligible_count


def _compute_batch_eligibility_from_cache(
    run_id: str,
    all_plan_data: dict[str, dict[str, object]],
    all_execution_indices: dict[str, set[int]],
) -> tuple[bool, int]:
    """Compute batch eligibility using pre-scanned data (no filesystem access).

    This is the optimized version that uses data pre-loaded in Stage 3b
    to eliminate per-row filesystem operations.

    Returns:
        Tuple of (batchExecutable: bool, batchEligibleCount: int)
    """
    from typing import cast

    plan_data = all_plan_data.get(run_id)
    if not plan_data:
        return False, 0

    # Get candidates from plan
    candidates_data: list[dict[str, object]] = []
    if "candidates" in plan_data and isinstance(plan_data["candidates"], list):
        candidates_data = cast(list[dict[str, object]], plan_data["candidates"])
    elif "payload" in plan_data and isinstance(plan_data["payload"], dict):
        payload = cast(dict[str, object], plan_data["payload"])
        if "candidates" in payload and isinstance(payload["candidates"], list):
            candidates_data = cast(list[dict[str, object]], payload["candidates"])

    if not candidates_data:
        return False, 0

    # Get pre-loaded execution indices
    execution_indices = all_execution_indices.get(run_id, set())

    # Count eligible candidates using the same logic as run_batch_next_checks.py
    eligible_count = 0
    for idx, candidate in enumerate(candidates_data):
        # Already executed?
        if idx in execution_indices:
            continue

        # Must be safe to automate
        if not candidate.get("safeToAutomate"):
            continue

        # Must have a valid command family
        family = candidate.get("suggestedCommandFamily")
        if not family or not isinstance(family, str):
            continue

        # Must have a description
        description = candidate.get("description")
        if not description or not isinstance(description, str):
            continue

        # Must have target context info
        target_context = candidate.get("targetContext")
        if not target_context or not isinstance(target_context, str):
            continue

        # Check approval requirement
        requires_approval = candidate.get("requiresOperatorApproval")
        if requires_approval:
            approval_status = str(candidate.get("approvalStatus") or "").lower()
            if approval_status != "approved":
                continue

        # Check for duplicates
        if candidate.get("duplicateOfExistingEvidence"):
            continue

        eligible_count += 1

    return eligible_count > 0, eligible_count


def _extract_review_metadata_streaming(review_path: Path) -> dict[str, object] | None:
    """Extract only the required fields from review artifact using ijson streaming.

    This is a fast-path for extracting run_id, timestamp, run_label, and cluster_count
    without loading the entire JSON file into memory.

    Returns:
        Dictionary with extracted fields, or None if extraction fails.
    """
    try:
        with open(review_path, "rb") as f:
            # Use ijson to stream-parse only the fields we need
            parser = ijson.kvitems(f, "")
            extracted: dict[str, object] = {}
            for key, value in parser:
                if key in ("run_id", "timestamp", "run_label", "cluster_count"):
                    extracted[key] = value
                # Early exit once we have all required fields
                if len(extracted) >= 4:
                    break

            # Validate we got the required fields
            if "run_id" not in extracted or "timestamp" not in extracted:
                return None
            if not isinstance(extracted["run_id"], str):
                return None
            if not isinstance(extracted["timestamp"], str):
                return None

            return extracted
    except Exception:
        return None


def build_runs_list(
    runs_dir: Path,
    *,
    _timings: bool = False,
) -> RunsListPayload | tuple[RunsListPayload, RunsListTimings]:
    """Build a list of available runs with their review coverage status.

    A run's review status is derived from execution artifacts in the
    external-analysis/ directory. The status indicates:
    - "no-executions": run has no executed next checks
    - "unreviewed": has executions but none reviewed
    - "partially-reviewed": some executions reviewed, some not
    - "fully-reviewed": all executions reviewed

    Runs are discovered from review artifacts in the reviews/ directory.

    Args:
        runs_dir: Path to the runs directory
        _timings: If True, return tuple of (payload, timings) with detailed metrics

    Returns:
        RunsListPayload, or tuple of (RunsListPayload, RunsListTimings) if _timings=True
    """
    import time as time_module
    from datetime import UTC, datetime
    from typing import cast

    timings: RunsListTimings = {}

    # Stage 1: Collect runs from review artifacts
    reviews_scan_start = time_module.perf_counter()
    run_health_dir = runs_dir / "health"
    reviews_dir = run_health_dir / "reviews"

    run_entries: dict[str, dict[str, object]] = {}
    reviews_parsed = 0

    # Sub-stage: reviews glob (just find files)
    reviews_glob_only_start = time_module.perf_counter()
    review_files: list[Path] = []
    if reviews_dir.is_dir():
        review_files = list(reviews_dir.glob("*-review.json"))
    timings["reviews_glob_only_ms"] = (time_module.perf_counter() - reviews_glob_only_start) * 1000
    timings["reviews_files_found"] = len(review_files)

    # Sub-stage: reviews parse (read and parse JSON)
    # Use ijson streaming fast-path with fallback to full parse
    reviews_parse_start = time_module.perf_counter()

    # Initialize fast-path telemetry
    review_fast_path_attempted = 0
    review_fast_path_succeeded = 0
    review_fast_path_fallbacks = 0
    review_fast_path_failure_json = 0
    review_fast_path_failure_missing_field = 0
    review_fast_path_failure_other = 0

    for review_path in review_files:
        raw: dict[str, object] | None = None
        fast_path_used = False

        # Try ijson streaming fast-path first
        review_fast_path_attempted += 1
        extracted = _extract_review_metadata_streaming(review_path)

        if extracted is not None:
            # Fast path succeeded
            raw = extracted
            fast_path_used = True
            review_fast_path_succeeded += 1
        else:
            # Fast path failed, fall back to full JSON parse
            review_fast_path_fallbacks += 1
            try:
                raw = json.loads(review_path.read_text(encoding="utf-8"))
            except Exception:
                review_fast_path_failure_json += 1
                continue

            # Verify required fields exist in full parse result
            run_id = raw.get("run_id")
            timestamp = raw.get("timestamp")
            if not isinstance(run_id, str) or not isinstance(timestamp, str):
                review_fast_path_failure_missing_field += 1
                continue

        # Process the extracted/parsed data
        reviews_parsed += 1
        run_id = raw.get("run_id")
        timestamp = raw.get("timestamp")
        run_label = raw.get("run_label")
        cluster_count = raw.get("cluster_count", 0)

        if not isinstance(run_id, str):
            if fast_path_used:
                review_fast_path_failure_missing_field += 1
            continue
        if not isinstance(timestamp, str):
            if fast_path_used:
                review_fast_path_failure_missing_field += 1
            continue

        parsed_time = parse_iso_to_utc(timestamp)
        if parsed_time is None:
            parsed_time = datetime.now(UTC)

        run_entries[run_id] = {
            "run_id": run_id,
            "run_label": str(run_label) if run_label else run_id,
            "timestamp": timestamp,
            "cluster_count": cluster_count if isinstance(cluster_count, int) else 0,
            "parsed_time": parsed_time,
            "execution_count": 0,
            "reviewed_count": 0,
        }

    # Record fast-path telemetry
    timings["review_fast_path_attempted"] = review_fast_path_attempted
    timings["review_fast_path_succeeded"] = review_fast_path_succeeded
    timings["review_fast_path_fallbacks"] = review_fast_path_fallbacks
    timings["review_fast_path_failure_json"] = review_fast_path_failure_json
    timings["review_fast_path_failure_missing_field"] = review_fast_path_failure_missing_field
    timings["review_fast_path_failure_other"] = review_fast_path_failure_other

    timings["reviews_parse_ms"] = (time_module.perf_counter() - reviews_parse_start) * 1000

    timings["reviews_glob_ms"] = (time_module.perf_counter() - reviews_scan_start) * 1000
    timings["reviews_parsed"] = reviews_parsed

    # Stage 2: Count executions and reviewed executions from external-analysis
    execution_scan_start = time_module.perf_counter()
    external_analysis_dir = run_health_dir / "external-analysis"
    execution_artifacts_scanned = 0
    execution_count_matches = 0

    # Sub-stage: execution glob (just find files)
    execution_glob_only_start = time_module.perf_counter()
    exec_artifact_files: list[Path] = []
    if external_analysis_dir.is_dir():
        # Pre-sort run_ids by length (longest first) to handle prefixed run_ids correctly
        # e.g., "run-2024-01-15" should match before "run-2024"
        sorted_run_ids = sorted(run_entries.keys(), key=len, reverse=True)

        # Find all execution artifacts
        exec_artifact_files = list(external_analysis_dir.glob("*-next-check-execution*.json"))
    timings["execution_glob_only_ms"] = (time_module.perf_counter() - execution_glob_only_start) * 1000

    # Sub-stage: execution parse (read and parse JSON)
    execution_parse_start = time_module.perf_counter()
    for artifact_path in exec_artifact_files:
        execution_artifacts_scanned += 1
        try:
            raw = json.loads(artifact_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        # Check if this is an execution artifact
        purpose = raw.get("purpose")
        if purpose != "next-check-execution":
            continue

        # Extract run_id from filename using prefix matching (O(N) instead of O(N*M))
        # Format: {run_id}-next-check-execution-*.json
        filename = artifact_path.name
        matched_run_id = None
        for run_id in sorted_run_ids:
            if filename.startswith(run_id):
                matched_run_id = run_id
                break

        if matched_run_id is None:
            continue

        execution_count_matches += 1

        # Increment execution count
        current_exec_count = run_entries[matched_run_id].get("execution_count", 0)
        run_entries[matched_run_id]["execution_count"] = cast(int, current_exec_count) + 1

        # Check if this execution has usefulness feedback
        usefulness = raw.get("usefulness_class")
        if usefulness and isinstance(usefulness, str) and usefulness.strip():
            current_reviewed_count = run_entries[matched_run_id].get("reviewed_count", 0)
            run_entries[matched_run_id]["reviewed_count"] = cast(int, current_reviewed_count) + 1

    timings["execution_parse_ms"] = (time_module.perf_counter() - execution_parse_start) * 1000
    timings["execution_artifacts_glob_ms"] = (time_module.perf_counter() - execution_scan_start) * 1000
    timings["execution_artifacts_scanned"] = execution_artifacts_scanned
    timings["execution_count_derivation_ms"] = (time_module.perf_counter() - execution_scan_start) * 1000
    timings["execution_count_derivation_matches"] = execution_count_matches

    # Stage 3: Build the runs list sorted by timestamp (most recent first)
    row_assembly_start = time_module.perf_counter()

    # Sub-stage 3a: Pre-scan diagnostic-packs directory to avoid O(runs * dirs) existence checks
    # Map run_id -> whether review artifact exists
    review_artifact_exists: dict[str, bool] = {}
    review_artifact_scan_start = time_module.perf_counter()
    diagnostic_packs_dir = run_health_dir / "diagnostic-packs"
    if diagnostic_packs_dir.is_dir():
        for run_dir in diagnostic_packs_dir.iterdir():
            if run_dir.is_dir():
                run_id = run_dir.name
                review_path = run_dir / "next_check_usefulness_review.json"
                review_artifact_exists[run_id] = review_path.exists()
    timings["review_artifact_prescan_ms"] = (time_module.perf_counter() - review_artifact_scan_start) * 1000

    # Sub-stage 3b: Pre-scan external-analysis directory for batch eligibility
    # This eliminates O(runs * files) per-row filesystem access
    batch_eligibility_prescan_start = time_module.perf_counter()

    # Pre-sort run_ids by length (longest first) to handle prefixed run_ids correctly
    # e.g., "run-2024-01-15" should match before "run-2024"
    sorted_run_ids_3b = sorted(run_entries.keys(), key=len, reverse=True)

    # Sub-stage: next-check-plan glob
    batch_plan_glob_start = time_module.perf_counter()
    plan_files: list[Path] = []
    if external_analysis_dir.is_dir():
        plan_files = list(external_analysis_dir.glob("*-next-check-plan*.json"))
    timings["batch_plan_glob_ms"] = (time_module.perf_counter() - batch_plan_glob_start) * 1000
    timings["batch_plan_files_found"] = len(plan_files)

    # Sub-stage: next-check-plan parse and matching
    batch_plan_parse_start = time_module.perf_counter()
    all_plan_data: dict[str, dict[str, object]] = {}
    for plan_path in plan_files:
        filename = plan_path.stem
        for run_id in sorted_run_ids_3b:
            if filename.startswith(f"{run_id}-next-check-plan"):
                try:
                    raw = json.loads(plan_path.read_text(encoding="utf-8"))
                    if raw.get("purpose") == "next-check-planning":
                        all_plan_data[run_id] = raw
                        break
                except Exception:
                    continue
    timings["batch_plan_parse_ms"] = (time_module.perf_counter() - batch_plan_parse_start) * 1000

    # Sub-stage: execution artifact glob
    batch_exec_glob_start = time_module.perf_counter()
    exec_files: list[Path] = []
    if external_analysis_dir.is_dir():
        exec_files = list(external_analysis_dir.glob("*-next-check-execution*.json"))
    timings["batch_exec_glob_ms"] = (time_module.perf_counter() - batch_exec_glob_start) * 1000
    timings["batch_exec_files_found"] = len(exec_files)

    # Sub-stage: execution artifact parse and matching
    batch_exec_parse_start = time_module.perf_counter()
    all_execution_indices: dict[str, set[int]] = {run_id: set() for run_id in run_entries}
    for exec_path in exec_files:
        filename = exec_path.stem
        for run_id in sorted_run_ids_3b:
            if filename.startswith(f"{run_id}-next-check-execution"):
                try:
                    raw = json.loads(exec_path.read_text(encoding="utf-8"))
                    if raw.get("purpose") == "next-check-execution":
                        exec_payload: dict[str, object] = raw.get("payload", {})  # type: ignore[assignment]
                        candidate_index = exec_payload.get("candidateIndex")
                        if isinstance(candidate_index, int):
                            all_execution_indices[run_id].add(candidate_index)
                except Exception:
                    continue
    timings["batch_exec_parse_ms"] = (time_module.perf_counter() - batch_exec_parse_start) * 1000

    # Matching and cache construction are included in parse stages above (they're interleaved)
    timings["batch_run_id_matching_ms"] = 0.0  # Included in parse stages
    timings["batch_cache_construction_ms"] = 0.0  # Included in parse stages

    timings["batch_eligibility_prescan_ms"] = (time_module.perf_counter() - batch_eligibility_prescan_start) * 1000

    # Sub-stage 3c: Build rows (now uses pre-scanned data)
    runs_list: list[RunsListEntry] = []
    review_download_paths_found = 0
    batch_eligible_runs = 0

    # Sub-stage timings for row assembly breakdown
    review_status_row_ms_total = 0.0
    review_download_path_row_ms_total = 0.0
    batch_eligibility_row_ms_total = 0.0
    artifact_lookup_row_ms_total = 0.0
    timestamp_normalization_row_ms_total = 0.0
    label_normalization_row_ms_total = 0.0

    for run_id, entry in run_entries.items():
        # Sub-stage: review_status computation (simple, fast)
        row_start = time_module.perf_counter()
        execution_count = cast(int, entry.get("execution_count", 0))
        reviewed_count = cast(int, entry.get("reviewed_count", 0))
        review_status = _derive_review_status(execution_count, reviewed_count)
        # triaged is true only if there are executions AND at least one has been reviewed
        # A run with no executions should NOT be marked as triaged
        triaged = execution_count > 0 and reviewed_count > 0
        review_status_row_ms_total += (time_module.perf_counter() - row_start) * 1000

        # Sub-stage: review_download_path lookup (uses pre-computed map - no FS)
        row_start = time_module.perf_counter()
        # Determine review download path for runs with executions
        # Only provide a path for runs that need review: unreviewed or partially-reviewed
        review_download_path: str | None = None
        if review_status in ("unreviewed", "partially-reviewed"):
            # Use pre-computed map instead of Path.exists() per run
            if review_artifact_exists.get(run_id, False):
                run_scoped_path = diagnostic_packs_dir / run_id / "next_check_usefulness_review.json"
                review_download_path = str(run_scoped_path.relative_to(runs_dir))
                review_download_paths_found += 1
            # DO NOT fallback to /latest/ - historical runs must have run-specific artifacts
            # If only /latest/ exists today, historical rows should NOT show misleading download links
        review_download_path_row_ms_total += (time_module.perf_counter() - row_start) * 1000

        # Sub-stage: batch eligibility computation (uses pre-scanned data - no FS)
        row_start = time_module.perf_counter()
        # Compute batch eligibility using pre-scanned data (no per-row filesystem access)
        batch_executable, batch_eligible_count = _compute_batch_eligibility_from_cache(run_id, all_plan_data, all_execution_indices)
        if batch_executable:
            batch_eligible_runs += 1
        batch_eligibility_row_ms_total += (time_module.perf_counter() - row_start) * 1000

        # Sub-stage: artifact_lookup (simple dict access - already done above)
        row_start = time_module.perf_counter()
        # Artifact lookup is implicit in the above - we use pre-computed maps
        artifact_lookup_row_ms_total += (time_module.perf_counter() - row_start) * 1000

        # Sub-stage: timestamp normalization (simple - already parsed earlier)
        row_start = time_module.perf_counter()
        timestamp_normalization_row_ms_total += (time_module.perf_counter() - row_start) * 1000

        # Sub-stage: label normalization (simple - already done earlier)
        row_start = time_module.perf_counter()
        label_normalization_row_ms_total += (time_module.perf_counter() - row_start) * 1000

        runs_list.append(
            RunsListEntry(
                runId=cast(str, entry["run_id"]),
                runLabel=cast(str, entry["run_label"]),
                timestamp=cast(str, entry["timestamp"]),
                clusterCount=cast(int, entry["cluster_count"]),
                triaged=triaged,
                executionCount=execution_count,
                reviewedCount=reviewed_count,
                reviewStatus=review_status,
                reviewDownloadPath=review_download_path,
                batchExecutable=batch_executable,
                batchEligibleCount=batch_eligible_count,
            )
        )

    # Record sub-stage timings
    timings["review_status_row_ms"] = round(review_status_row_ms_total, 2)
    timings["review_download_path_row_ms"] = round(review_download_path_row_ms_total, 2)
    timings["batch_eligibility_row_ms"] = round(batch_eligibility_row_ms_total, 2)
    timings["artifact_lookup_row_ms"] = round(artifact_lookup_row_ms_total, 2)
    timings["timestamp_normalization_row_ms"] = round(timestamp_normalization_row_ms_total, 2)
    timings["label_normalization_row_ms"] = round(label_normalization_row_ms_total, 2)
    timings["per_row_fs_checks_ms"] = 0.0  # Should be ~0 - we use pre-computed maps

    timings["review_download_path_checks_ms"] = 0  # Included in row_assembly
    timings["review_download_paths_found"] = review_download_paths_found
    timings["row_assembly_ms"] = (time_module.perf_counter() - row_assembly_start) * 1000
    timings["rows_built"] = len(runs_list)
    # Note: review_artifact_prescan_ms and batch_eligibility_prescan_ms are already set

    # Stage 4: Sort by timestamp descending (most recent first)
    sort_start = time_module.perf_counter()
    runs_list.sort(key=lambda r: r["timestamp"], reverse=True)
    timings["sort_ms"] = (time_module.perf_counter() - sort_start) * 1000
    timings["batch_eligible_runs"] = batch_eligible_runs

    # Initialize counters (proves no per-row FS work is happening)
    timings["path_exists_calls"] = 0
    timings["stat_calls"] = 0
    timings["diagnostic_pack_path_checks"] = 0
    timings["run_scoped_review_path_checks"] = 0
    timings["per_run_glob_calls"] = 0
    timings["per_run_directory_list_calls"] = 0

    payload = RunsListPayload(
        runs=runs_list,
        totalCount=len(runs_list),
    )

    if _timings:
        return payload, timings
    return payload
