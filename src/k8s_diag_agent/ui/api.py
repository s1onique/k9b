"""Read-model payload builders for the operator UI."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import NotRequired, TypedDict, cast

from ..health.freshness import freshness_status
from .model import (
    AssessmentHypothesisView,
    AssessmentNextCheckView,
    AssessmentView,
    AutoDrilldownInterpretationView,
    ClusterView,
    DeterministicNextCheckClusterView,
    DeterministicNextCheckSummaryView,
    DeterministicNextChecksView,
    DiagnosticPackReviewView,
    DiagnosticPackView,
    DrilldownAvailabilityView,
    DrilldownCoverageEntry,
    FindingsView,
    LLMActivityView,
    LLMPolicyView,
    LLMStatsView,
    NextCheckCandidateView,
    NextCheckExecutionHistoryEntryView,
    NextCheckOrphanedApprovalView,
    NextCheckPlanView,
    NextCheckQueueCandidateAccountingView,
    NextCheckQueueClusterStateView,
    NextCheckQueueExplanationView,
    NextCheckQueueItemView,
    NotificationView,
    PlannerAvailabilityView,
    ProposalView,
    ProviderExecutionBranchView,
    ProviderExecutionView,
    RecommendedActionView,
    ReviewEnrichmentStatusView,
    ReviewEnrichmentView,
    RunStatsView,
    UIIndexContext,
)


class ArtifactLink(TypedDict):
    label: str
    path: str


class ProblemSummary(TypedDict):
    title: str
    detail: str


class NextCheckExecutionHistoryEntry(TypedDict, total=False):
    timestamp: str
    clusterLabel: str | None
    candidateDescription: str | None
    commandFamily: str | None
    status: str
    durationMs: int | None
    artifactPath: str | None
    timedOut: bool | None
    stdoutTruncated: bool | None
    stderrTruncated: bool | None
    outputBytesCaptured: int | None
    failureClass: str | None
    failureSummary: str | None
    suggestedNextOperatorMove: str | None
    resultClass: str | None
    resultSummary: str | None


class FreshnessPayload(TypedDict, total=False):
    ageSeconds: int | None
    expectedIntervalSeconds: int | None
    status: str | None


class RunPayload(TypedDict):
    runId: str
    label: str
    timestamp: str
    collectorVersion: str
    clusterCount: int
    drilldownCount: int
    proposalCount: int
    externalAnalysisCount: int
    notificationCount: int
    artifacts: list[ArtifactLink]
    runStats: RunStatsPayload
    llmStats: LLMStatsPayload
    historicalLlmStats: LLMStatsPayload | None
    llmActivity: LLMActivityPayload
    llmPolicy: LLMPolicyPayload | None
    reviewEnrichment: ReviewEnrichmentPayload | None
    reviewEnrichmentStatus: ReviewEnrichmentStatusPayload | None
    providerExecution: ProviderExecutionPayload | None
    nextCheckExecutionHistory: list[NextCheckExecutionHistoryEntry]
    freshness: FreshnessPayload | None
    nextCheckPlan: NextCheckPlanPayload | None
    nextCheckQueue: list[NextCheckQueueItemPayload]
    nextCheckQueueExplanation: NextCheckQueueExplanationPayload | None
    deterministicNextChecks: DeterministicNextChecksPayload | None
    plannerAvailability: PlannerAvailabilityPayload | None
    diagnosticPackReview: DiagnosticPackReviewPayload | None
    diagnosticPack: DiagnosticPackPayload | None


class RunStatsPayload(TypedDict):
    lastRunDurationSeconds: int | None
    totalRuns: int
    p50RunDurationSeconds: int | None
    p95RunDurationSeconds: int | None
    p99RunDurationSeconds: int | None


class LLMProviderEntry(TypedDict):
    provider: str
    calls: int
    failedCalls: int


class LLMStatsPayload(TypedDict):
    totalCalls: int
    successfulCalls: int
    failedCalls: int
    lastCallTimestamp: str | None
    p50LatencyMs: int | None
    p95LatencyMs: int | None
    p99LatencyMs: int | None
    providerBreakdown: list[LLMProviderEntry]
    scope: str


class AutoDrilldownPolicyPayload(TypedDict):
    enabled: bool
    provider: str
    maxPerRun: int
    usedThisRun: int
    successfulThisRun: int
    failedThisRun: int
    skippedThisRun: int
    budgetExhausted: bool | None


class LLMPolicyPayload(TypedDict):
    autoDrilldown: AutoDrilldownPolicyPayload


class LLMActivityEntryPayload(TypedDict, total=False):
    timestamp: str | None
    runId: str | None
    runLabel: str | None
    clusterLabel: str | None
    toolName: str | None
    provider: str | None
    purpose: str | None
    status: str | None
    latencyMs: int | None
    artifactPath: str | None
    summary: str | None
    errorSummary: str | None
    skipReason: str | None


class LLMActivitySummaryPayload(TypedDict):
    retainedEntries: int


class LLMActivityPayload(TypedDict):
    entries: list[LLMActivityEntryPayload]
    summary: LLMActivitySummaryPayload


class ReviewEnrichmentPayload(TypedDict, total=False):
    status: str
    provider: str | None
    timestamp: str | None
    summary: str | None
    triageOrder: list[str]
    topConcerns: list[str]
    evidenceGaps: list[str]
    nextChecks: list[str]
    focusNotes: list[str]
    artifactPath: str | None
    errorSummary: str | None
    skipReason: str | None


class NextCheckCandidatePayload(TypedDict, total=False):
    description: str
    targetCluster: str | None
    sourceReason: str | None
    expectedSignal: str | None
    suggestedCommandFamily: str | None
    safeToAutomate: bool
    requiresOperatorApproval: bool
    riskLevel: str
    estimatedCost: str
    confidence: str
    priorityLabel: str | None
    gatingReason: str | None
    duplicateOfExistingEvidence: bool
    duplicateEvidenceDescription: str | None
    normalizationReason: str | None
    safetyReason: str | None
    approvalReason: str | None
    duplicateReason: str | None
    blockingReason: str | None
    approvalStatus: str | None
    approvalArtifactPath: str | None
    approvalTimestamp: str | None
    approvalState: str | None
    executionState: str | None
    outcomeStatus: str | None
    latestArtifactPath: str | None
    latestTimestamp: str | None
    candidateId: str | None
    candidateIndex: int | None
    targetContext: str | None
    commandPreview: str | None


class NextCheckQueueItemPayload(TypedDict, total=False):
    candidateId: str | None
    candidateIndex: int | None
    description: str
    targetCluster: str | None
    priorityLabel: str | None
    suggestedCommandFamily: str | None
    safeToAutomate: bool
    requiresOperatorApproval: bool
    approvalState: str | None
    executionState: str | None
    outcomeStatus: str | None
    latestArtifactPath: str | None
    queueStatus: str
    sourceReason: str | None
    expectedSignal: str | None
    normalizationReason: str | None
    safetyReason: str | None
    approvalReason: str | None
    duplicateReason: str | None
    blockingReason: str | None
    targetContext: str | None
    commandPreview: str | None
    planArtifactPath: str | None
    sourceType: str | None
    failureClass: str | None
    failureSummary: str | None
    suggestedNextOperatorMove: str | None
    resultClass: str | None
    resultSummary: str | None


class NextCheckQueueCandidateAccountingPayload(TypedDict):
    generated: int
    safe: int
    approvalNeeded: int
    duplicate: int
    completed: int
    staleOrphaned: int
    orphanedApprovals: int


class NextCheckQueueClusterStatePayload(TypedDict):
    degradedClusterCount: int
    degradedClusterLabels: list[str]
    deterministicNextCheckCount: int
    deterministicClusterCount: int
    drilldownReadyCount: int


class NextCheckQueueExplanationPayload(TypedDict, total=False):
    status: str
    reason: str | None
    hint: str | None
    plannerArtifactPath: str | None
    clusterState: NextCheckQueueClusterStatePayload
    candidateAccounting: NextCheckQueueCandidateAccountingPayload
    deterministicNextChecksAvailable: bool
    recommendedNextActions: list[str]


class DeterministicNextCheckSummaryPayload(TypedDict):
    description: str
    owner: str
    method: str
    evidenceNeeded: list[str]
    workstream: str
    urgency: str
    isPrimaryTriage: bool
    whyNow: str
    priorityScore: NotRequired[int | None]


class DeterministicNextCheckClusterPayload(TypedDict):
    label: str
    context: str
    topProblem: str | None
    deterministicNextCheckCount: int
    deterministicNextCheckSummaries: list[DeterministicNextCheckSummaryPayload]
    drilldownAvailable: bool
    assessmentArtifactPath: str | None
    drilldownArtifactPath: str | None


class DeterministicNextChecksPayload(TypedDict):
    clusterCount: int
    totalNextCheckCount: int
    clusters: list[DeterministicNextCheckClusterPayload]


class NextCheckOrphanedApprovalPayload(TypedDict, total=False):
    approvalStatus: str | None
    candidateId: str | None
    candidateIndex: int | None
    candidateDescription: str | None
    targetCluster: str | None
    planArtifactPath: str | None
    approvalArtifactPath: str | None
    approvalTimestamp: str | None


class NextCheckOutcomeCountPayload(TypedDict):
    status: str
    count: int


class NextCheckPlanPayload(TypedDict, total=False):
    status: str
    summary: str | None
    artifactPath: str | None
    reviewPath: str | None
    enrichmentArtifactPath: str | None
    candidateCount: int
    candidates: list[NextCheckCandidatePayload]
    orphanedApprovals: list[NextCheckOrphanedApprovalPayload]
    outcomeCounts: list[NextCheckOutcomeCountPayload]
    orphanedApprovalCount: int


class PlannerAvailabilityPayload(TypedDict, total=False):
    status: str
    reason: str | None
    hint: str | None
    artifactPath: str | None
    nextActionHint: str | None


class ReviewEnrichmentStatusPayload(TypedDict, total=False):
    status: str
    reason: str | None
    provider: str | None
    policyEnabled: bool
    providerConfigured: bool
    adapterAvailable: bool | None
    runEnabled: bool | None
    runProvider: str | None


class DiagnosticPackReviewCandidatePayload(TypedDict, total=False):
    providerReview: dict[str, object] | None


class DiagnosticPackReviewPayload(TypedDict, total=False):
    timestamp: str | None
    summary: str | None
    majorDisagreements: list[str]
    missingChecks: list[str]
    rankingIssues: list[str]
    genericChecks: list[str]
    recommendedNextActions: list[str]
    driftMisprioritized: bool
    confidence: str | None
    providerStatus: str | None
    providerSummary: str | None
    providerErrorSummary: str | None
    providerSkipReason: str | None
    providerReview: dict[str, object] | None
    artifactPath: str | None


class DiagnosticPackPayload(TypedDict, total=False):
    path: str | None
    timestamp: str | None
    label: str | None
    reviewBundlePath: str | None
    reviewInput14bPath: str | None


class ProviderExecutionBranchPayload(TypedDict, total=False):
    enabled: bool | None
    provider: str | None
    maxPerRun: int | None
    eligible: int | None
    attempted: int
    succeeded: int
    failed: int
    skipped: int
    unattempted: int | None
    budgetLimited: int | None
    notes: str | None


class ProviderExecutionPayload(TypedDict, total=False):
    autoDrilldown: ProviderExecutionBranchPayload
    reviewEnrichment: ProviderExecutionBranchPayload


class RatingCount(TypedDict):
    rating: str
    count: int


class StatusCount(TypedDict):
    status: str
    count: int


class FleetStatusPayload(TypedDict):
    ratingCounts: list[RatingCount]
    degradedClusters: list[str]


class ClusterSummaryPayload(TypedDict):
    label: str
    context: str
    clusterClass: str
    clusterRole: str
    baselineCohort: str
    controlPlaneVersion: str
    healthRating: str
    warnings: int
    nonRunningPods: int
    latestRunTimestamp: str
    topTriggerReason: str | None
    drilldownAvailable: bool
    drilldownTimestamp: str | None
    missingEvidence: list[str]


class ProposalSummaryPayload(TypedDict):
    pending: int
    total: int
    statusCounts: list[StatusCount]


class FleetPayload(TypedDict):
    runId: str
    runLabel: str
    lastRunTimestamp: str
    topProblem: ProblemSummary
    fleetStatus: FleetStatusPayload
    clusters: list[ClusterSummaryPayload]
    proposalSummary: ProposalSummaryPayload


class LifecycleEntry(TypedDict):
    status: str
    timestamp: str
    note: str | None


class ProposalEntry(TypedDict):
    proposalId: str
    target: str
    status: str
    confidence: str
    rationale: str
    expectedBenefit: str
    sourceRunId: str
    latestNote: str | None
    lifecycle: list[LifecycleEntry]
    artifacts: list[ArtifactLink]


class ProposalsPayload(TypedDict):
    statusSummary: list[StatusCount]
    proposals: list[ProposalEntry]


class NotificationDetail(TypedDict):
    label: str
    value: str


class NotificationEntry(TypedDict):
    kind: str
    summary: str
    timestamp: str
    runId: str | None
    clusterLabel: str | None
    context: str | None
    details: list[NotificationDetail]
    artifactPath: str | None


class NotificationsPayload(TypedDict):
    notifications: list[NotificationEntry]


class DrilldownCoveragePayload(TypedDict):
    label: str
    context: str
    available: bool
    timestamp: str | None
    artifactPath: str | None


class DrilldownInterpretationPayload(TypedDict, total=False):
    adapter: str
    status: str
    summary: str | None
    timestamp: str
    artifactPath: str | None
    provider: str | None
    durationMs: int | None
    payload: dict[str, object] | None
    errorSummary: str | None
    skipReason: str | None


class DrilldownSummaryPayload(TypedDict):
    totalClusters: int
    available: int
    missing: int
    missingClusters: list[str]


class FindingEntry(TypedDict):
    label: str | None
    context: str | None
    triggerReasons: list[str]
    warningEvents: int
    nonRunningPods: int
    summaryEntries: list[NotificationDetail]
    patternDetails: list[NotificationDetail]
    rolloutStatus: list[str]
    artifactPath: str | None


class HypothesisEntry(TypedDict):
    description: str
    confidence: str
    probableLayer: str
    falsifier: str


class NextCheckEntry(TypedDict):
    description: str
    owner: str
    method: str
    evidenceNeeded: list[str]


class RecommendedActionPayload(TypedDict):
    actionType: str
    description: str
    references: list[str]
    safetyLevel: str


class AssessmentSummaryPayload(TypedDict, total=False):
    healthRating: str
    missingEvidence: list[str]
    probableLayer: str | None
    overallConfidence: str | None
    artifactPath: str | None
    snapshotPath: str | None


class ClusterDetailPayload(TypedDict):
    selectedClusterLabel: str | None
    selectedClusterContext: str | None
    assessment: AssessmentSummaryPayload | None
    findings: list[FindingEntry]
    hypotheses: list[HypothesisEntry]
    nextChecks: list[NextCheckEntry]
    recommendedAction: RecommendedActionPayload | None
    drilldownAvailability: DrilldownSummaryPayload
    drilldownCoverage: list[DrilldownCoveragePayload]
    relatedProposals: list[ProposalEntry]
    relatedNotifications: list[NotificationEntry]
    artifacts: list[ArtifactLink]
    autoInterpretation: DrilldownInterpretationPayload | None
    nextCheckPlan: list[NextCheckCandidatePayload]
    topProblem: ProblemSummary


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
            context.run.next_check_queue, promotions
        ),
        "nextCheckQueueExplanation": _serialize_queue_explanation(
            context.run.next_check_queue_explanation
        ),
        "deterministicNextChecks": _serialize_deterministic_next_checks(
            context.run.deterministic_next_checks
        ),
        "plannerAvailability": _serialize_planner_availability(context.run.planner_availability),
        "diagnosticPackReview": _serialize_diagnostic_pack_review(context.run.diagnostic_pack_review),
        "diagnosticPack": _serialize_diagnostic_pack(context.run.diagnostic_pack),
        "nextCheckExecutionHistory": _serialize_execution_history(
            context.run.next_check_execution_history
        ),
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


def build_cluster_detail_payload(
    context: UIIndexContext, *, cluster_label: str | None = None
) -> ClusterDetailPayload:
    assessment = context.latest_assessment
    findings = context.latest_findings
    label = cluster_label or (assessment.cluster_label if assessment else findings.label if findings else None)
    cluster_context = (
        assessment.context
        if assessment and assessment.context != "-"
        else findings.context
        if findings
        else None
    )
    artifacts = _collect_run_artifacts(context)
    interpretation_view = (
        context.auto_drilldown_interpretations.get(label) if label else None
    )
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


def _serialize_plan_candidates_for_cluster(
    label: str | None, plan: NextCheckPlanView | None
) -> list[NextCheckCandidatePayload]:
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


def _build_freshness_payload(
    timestamp_value: str | None,
    expected_interval_seconds: int | None,
    *,
    now: datetime | None = None,
) -> FreshnessPayload | None:
    if not timestamp_value:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp_value)
    except ValueError:
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


def _serialize_llm_stats(stats: LLMStatsView) -> LLMStatsPayload:
    return {
        "totalCalls": stats.total_calls,
        "successfulCalls": stats.successful_calls,
        "failedCalls": stats.failed_calls,
        "lastCallTimestamp": stats.last_call_timestamp,
        "p50LatencyMs": stats.p50_latency_ms,
        "p95LatencyMs": stats.p95_latency_ms,
        "p99LatencyMs": stats.p99_latency_ms,
        "providerBreakdown": [
            {
                "provider": entry.provider,
                "calls": entry.calls,
                "failedCalls": entry.failed_calls,
            }
            for entry in stats.provider_breakdown
        ],
        "scope": stats.scope,
    }


def _serialize_llm_activity(activity: LLMActivityView) -> LLMActivityPayload:
    return {
        "entries": [
            {
                "timestamp": entry.timestamp,
                "runId": entry.run_id,
                "runLabel": entry.run_label,
                "clusterLabel": entry.cluster_label,
                "toolName": entry.tool_name,
                "provider": entry.provider,
                "purpose": entry.purpose,
                "status": entry.status,
                "latencyMs": entry.latency_ms,
                "artifactPath": entry.artifact_path,
                "summary": entry.summary,
                "errorSummary": entry.error_summary,
                "skipReason": entry.skip_reason,
            }
            for entry in activity.entries
        ],
        "summary": {"retainedEntries": activity.summary.retained_entries},
    }


def _serialize_llm_policy(policy: LLMPolicyView | None) -> LLMPolicyPayload | None:
    if not policy or not policy.auto_drilldown:
        return None
    auto = policy.auto_drilldown
    return {
        "autoDrilldown": {
            "enabled": auto.enabled,
            "provider": auto.provider,
            "maxPerRun": auto.max_per_run,
            "usedThisRun": auto.used_this_run,
            "successfulThisRun": auto.successful_this_run,
            "failedThisRun": auto.failed_this_run,
            "skippedThisRun": auto.skipped_this_run,
            "budgetExhausted": auto.budget_exhausted,
        }
    }


def _build_problem_summary(context: UIIndexContext) -> ProblemSummary:
    findings = context.latest_findings
    if findings and findings.trigger_reasons:
        detail = " · ".join(findings.trigger_reasons)
        return {"title": "Trigger reasons", "detail": detail}
    assessment = context.latest_assessment
    if assessment and assessment.findings:
        first = assessment.findings[0]
        return {"title": "Assessment finding", "detail": first.description}
    return {"title": "Fleet status", "detail": "Awaiting fresh evidence"}


def _serialize_cluster(cluster: ClusterView) -> ClusterSummaryPayload:
    return {
        "label": cluster.label,
        "context": cluster.context,
        "clusterClass": cluster.cluster_class,
        "clusterRole": cluster.cluster_role,
        "baselineCohort": cluster.baseline_cohort,
        "controlPlaneVersion": cluster.control_plane_version,
        "healthRating": cluster.health_rating,
        "warnings": cluster.warnings,
        "nonRunningPods": cluster.non_running_pods,
        "latestRunTimestamp": cluster.latest_run_timestamp,
        "topTriggerReason": cluster.top_trigger_reason,
        "drilldownAvailable": cluster.drilldown_available,
        "drilldownTimestamp": cluster.drilldown_timestamp,
        "missingEvidence": list(cluster.missing_evidence),
    }


def _serialize_rating_counts(entries: tuple[tuple[str, int], ...]) -> list[RatingCount]:
    return [{"rating": rating, "count": count} for rating, count in entries]


def _serialize_status_counts(entries: tuple[tuple[str, int], ...]) -> list[StatusCount]:
    return [{"status": status, "count": count} for status, count in entries]


def _build_proposal_summary(context: UIIndexContext) -> ProposalSummaryPayload:
    counts = {status.lower(): count for status, count in context.proposal_status_summary.status_counts}
    total = sum(count for count in counts.values())
    return {
        "pending": counts.get("pending", 0),
        "total": total,
        "statusCounts": _serialize_status_counts(context.proposal_status_summary.status_counts),
    }


def _serialize_proposal(proposal: ProposalView) -> ProposalEntry:
    artifacts: list[ArtifactLink] = []
    if proposal.artifact_path:
        artifacts.append({"label": "Proposal JSON", "path": proposal.artifact_path})
    if proposal.review_path:
        artifacts.append({"label": "Review JSON", "path": proposal.review_path})
    return {
        "proposalId": proposal.proposal_id,
        "target": proposal.target,
        "status": proposal.status,
        "confidence": proposal.confidence,
        "rationale": proposal.rationale,
        "expectedBenefit": proposal.expected_benefit,
        "sourceRunId": proposal.source_run_id,
        "latestNote": proposal.latest_note,
        "lifecycle": [
            {"status": status, "timestamp": timestamp, "note": note}
            for status, timestamp, note in proposal.lifecycle_history
        ],
        "artifacts": artifacts,
    }


def _serialize_notification(entry: NotificationView) -> NotificationEntry:
    return {
        "kind": entry.kind,
        "summary": entry.summary,
        "timestamp": entry.timestamp,
        "runId": entry.run_id,
        "clusterLabel": entry.cluster_label,
        "context": entry.context,
        "details": [{"label": label, "value": value} for label, value in entry.details],
        "artifactPath": entry.artifact_path,
    }


def _serialize_drilldown_summary(availability: DrilldownAvailabilityView) -> DrilldownSummaryPayload:
    return {
        "totalClusters": availability.total_clusters,
        "available": availability.available,
        "missing": availability.missing,
        "missingClusters": list(availability.missing_clusters),
    }


def _serialize_drilldown(entry: DrilldownCoverageEntry) -> DrilldownCoveragePayload:
    return {
        "label": entry.label,
        "context": entry.context,
        "available": entry.available,
        "timestamp": entry.timestamp,
        "artifactPath": entry.artifact_path,
    }


def _serialize_findings(findings: FindingsView | None) -> FindingEntry:
    if findings is None:
        return {
            "label": None,
            "context": None,
            "triggerReasons": [],
            "warningEvents": 0,
            "nonRunningPods": 0,
            "summaryEntries": [],
            "patternDetails": [],
            "rolloutStatus": [],
            "artifactPath": None,
        }
    return {
        "label": findings.label,
        "context": findings.context,
        "triggerReasons": list(findings.trigger_reasons),
        "warningEvents": findings.warning_events,
        "nonRunningPods": findings.non_running_pods,
        "summaryEntries": [{"label": label, "value": value} for label, value in findings.summary],
        "patternDetails": [{"label": label, "value": value} for label, value in findings.pattern_details],
        "rolloutStatus": list(findings.rollout_status),
        "artifactPath": findings.artifact_path,
    }


def _serialize_hypothesis(hypothesis: AssessmentHypothesisView) -> HypothesisEntry:
    return {
        "description": hypothesis.description,
        "confidence": hypothesis.confidence,
        "probableLayer": hypothesis.probable_layer,
        "falsifier": hypothesis.what_would_falsify,
    }


def _serialize_next_check(check: AssessmentNextCheckView) -> NextCheckEntry:
    return {
        "description": check.description,
        "owner": check.owner,
        "method": check.method,
        "evidenceNeeded": list(check.evidence_needed),
    }


def _serialize_recommended_action(action: RecommendedActionView | None) -> RecommendedActionPayload | None:
    if not action:
        return None
    return {
        "actionType": action.action_type,
        "description": action.description,
        "references": list(action.references),
        "safetyLevel": action.safety_level,
    }


def _serialize_assessment_summary(assessment: AssessmentView | None) -> AssessmentSummaryPayload | None:
    if not assessment:
        return None
    return {
        "healthRating": assessment.health_rating,
        "missingEvidence": list(assessment.missing_evidence),
        "probableLayer": assessment.probable_layer,
        "overallConfidence": assessment.overall_confidence,
        "artifactPath": assessment.artifact_path,
        "snapshotPath": assessment.snapshot_path,
    }


def _serialize_auto_interpretation(
    interpretation: AutoDrilldownInterpretationView | None
) -> DrilldownInterpretationPayload | None:
    if not interpretation:
        return None
    payload = dict(interpretation.payload) if interpretation.payload else None
    return {
        "adapter": interpretation.adapter,
        "status": interpretation.status,
        "summary": interpretation.summary,
        "timestamp": interpretation.timestamp,
        "artifactPath": interpretation.artifact_path,
        "provider": interpretation.provider,
        "durationMs": interpretation.duration_ms,
        "payload": payload,
        "errorSummary": interpretation.error_summary,
        "skipReason": interpretation.skip_reason,
    }


def _serialize_review_enrichment(view: ReviewEnrichmentView | None) -> ReviewEnrichmentPayload | None:
    if not view:
        return None
    return {
        "status": view.status,
        "provider": view.provider,
        "timestamp": view.timestamp,
        "summary": view.summary,
        "triageOrder": list(view.triage_order),
        "topConcerns": list(view.top_concerns),
        "evidenceGaps": list(view.evidence_gaps),
        "nextChecks": list(view.next_checks),
        "focusNotes": list(view.focus_notes),
        "artifactPath": view.artifact_path,
        "errorSummary": view.error_summary,
        "skipReason": view.skip_reason,
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
        "orphanedApprovals": [
            _serialize_orphaned_approval(entry) for entry in view.orphaned_approvals
        ],
        "outcomeCounts": [
            {"status": entry.status, "count": entry.count} for entry in view.outcome_counts
        ],
        "orphanedApprovalCount": view.orphaned_approval_count,
    }


def _serialize_next_check_queue(
    queue: tuple[NextCheckQueueItemView, ...],
    promotions: Sequence[Mapping[str, object]] | None = None,
) -> list[NextCheckQueueItemPayload]:
    entries: list[NextCheckQueueItemPayload] = [
            {
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
        }
        for item in queue
    ]
    if promotions:
        for entry in promotions:
            if isinstance(entry, Mapping):
                entries.append(cast(NextCheckQueueItemPayload, dict(entry)))
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
        "candidateAccounting": _serialize_queue_candidate_accounting(
            explanation.candidate_accounting
        ),
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
        "deterministicNextCheckSummaries": [
            _serialize_deterministic_next_check_summary(entry)
            for entry in view.deterministic_next_check_summaries
        ],
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
        "clusters": [
            _serialize_deterministic_next_check_cluster(entry) for entry in view.clusters
        ],
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


def _serialize_diagnostic_pack_review(
    view: DiagnosticPackReviewView | None,
) -> DiagnosticPackReviewPayload | None:
    if not view:
        return None
    return {
        "timestamp": view.timestamp,
        "summary": view.summary,
        "majorDisagreements": list(view.major_disagreements),
        "missingChecks": list(view.missing_checks),
        "rankingIssues": list(view.ranking_issues),
        "genericChecks": list(view.generic_checks),
        "recommendedNextActions": list(view.recommended_next_actions),
        "driftMisprioritized": view.drift_misprioritized,
        "confidence": view.confidence,
        "providerStatus": view.provider_status,
        "providerSummary": view.provider_summary,
        "providerErrorSummary": view.provider_error_summary,
        "providerSkipReason": view.provider_skip_reason,
        "providerReview": dict(view.provider_review) if view.provider_review else None,
        "artifactPath": view.artifact_path,
    }


def _serialize_diagnostic_pack(view: DiagnosticPackView | None) -> DiagnosticPackPayload | None:
    if not view:
        return None
    return {
        "path": view.path,
        "timestamp": view.timestamp,
        "label": view.label,
        "reviewBundlePath": view.review_bundle_path,
        "reviewInput14bPath": view.review_input_14b_path,
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
    return [
        {
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
            "failureClass": entry.failure_class,
            "failureSummary": entry.failure_summary,
            "suggestedNextOperatorMove": entry.suggested_next_operator_move,
            "resultClass": entry.result_class,
            "resultSummary": entry.result_summary,
        }
        for entry in entries
    ]


def _serialize_next_check_candidate(view: NextCheckCandidateView) -> NextCheckCandidatePayload:
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
    return payload


def _serialize_review_enrichment_status(
    view: ReviewEnrichmentStatusView | None,
) -> ReviewEnrichmentStatusPayload | None:
    if not view:
        return None
    return {
        "status": view.status,
        "reason": view.reason,
        "provider": view.provider,
        "policyEnabled": view.policy_enabled,
        "providerConfigured": view.provider_configured,
        "adapterAvailable": view.adapter_available,
        "runEnabled": view.run_enabled,
        "runProvider": view.run_provider,
    }


def _serialize_provider_execution(view: ProviderExecutionView | None) -> ProviderExecutionPayload | None:
    if not view:
        return None
    payload: ProviderExecutionPayload = {}
    if view.auto_drilldown:
        payload["autoDrilldown"] = _serialize_provider_execution_branch(view.auto_drilldown)
    if view.review_enrichment:
        payload["reviewEnrichment"] = _serialize_provider_execution_branch(
            view.review_enrichment
        )
    return payload or None


def _serialize_provider_execution_branch(
    branch: ProviderExecutionBranchView,
) -> ProviderExecutionBranchPayload:
    return {
        "enabled": branch.enabled,
        "provider": branch.provider,
        "maxPerRun": branch.max_per_run,
        "eligible": branch.eligible,
        "attempted": branch.attempted,
        "succeeded": branch.succeeded,
        "failed": branch.failed,
        "skipped": branch.skipped,
        "unattempted": branch.unattempted,
        "budgetLimited": branch.budget_limited,
        "notes": branch.notes,
    }


def _filter_related_proposals(label: str | None, proposals: tuple[ProposalView, ...]) -> list[ProposalEntry]:
    if label:
        matching = [p for p in proposals if label in p.target or label in (p.latest_note or "")]
        if matching:
            return [_serialize_proposal(p) for p in matching[:3]]
    return [_serialize_proposal(p) for p in proposals[:3]]


def _filter_related_notifications(label: str | None, notifications: tuple[NotificationView, ...]) -> list[NotificationEntry]:
    if label:
        matching = [n for n in notifications if n.cluster_label == label]
        if matching:
            return [_serialize_notification(entry) for entry in matching[:3]]
    return [_serialize_notification(entry) for entry in notifications[:3]]
