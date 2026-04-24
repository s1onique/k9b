"""TypedDict payload definitions for the operator UI.

This module contains pure data contracts (TypedDict definitions) used by the API
serialization layer. These definitions are the canonical JSON key schemas for the
UI and must remain stable.

Ownership:
    - All TypedDict payload classes defined here represent API response contracts.
    - JSON key names, optional vs required fields, and field types are frozen.
    - Serialization logic lives in api.py (or future api_serialization.py).

Extraction rationale:
    - Pure payload definitions have minimal dependencies and no side effects.
    - Extracting them first establishes the contract boundary before any
      serializer refactoring.
    - Keeping payloads in a dedicated module makes it easier to audit API
      contracts without filtering through serializer functions.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict

__all__ = [
    "ArtifactLink",
    "ProblemSummary",
    "NextCheckExecutionHistoryEntry",
    "FreshnessPayload",
    "RunStatsPayload",
    "LLMProviderEntry",
    "LLMStatsPayload",
    "AutoDrilldownPolicyPayload",
    "LLMPolicyPayload",
    "LLMActivityEntryPayload",
    "LLMActivitySummaryPayload",
    "LLMActivityPayload",
    "AlertmanagerEvidenceReferencePayload",
    "ReviewEnrichmentPayload",
    "FeedbackSummaryPayload",
    "FeedbackAdaptationProvenancePayload",
    "AlertmanagerProvenancePayload",
    "NextCheckCandidatePayload",
    "NextCheckQueueItemPayload",
    "NextCheckQueueCandidateAccountingPayload",
    "NextCheckQueueClusterStatePayload",
    "NextCheckQueueExplanationPayload",
    "DeterministicNextCheckSummaryPayload",
    "DeterministicNextCheckClusterPayload",
    "DeterministicNextChecksPayload",
    "NextCheckOrphanedApprovalPayload",
    "NextCheckOutcomeCountPayload",
    "NextCheckPlanPayload",
    "PlannerAvailabilityPayload",
    "ReviewEnrichmentStatusPayload",
    "DiagnosticPackReviewCandidatePayload",
    "DiagnosticPackReviewPayload",
    "DiagnosticPackPayload",
    "ClusterAlertSummaryPayload",
    "AlertmanagerCompactPayload",
    "AlertmanagerSourcePayload",
    "AlertmanagerSourcesPayload",
    "ProviderExecutionBranchPayload",
    "ProviderExecutionPayload",
    "RatingCount",
    "StatusCount",
    "FleetStatusPayload",
    "ClusterSummaryPayload",
    "ProposalSummaryPayload",
    "FleetPayload",
    "LifecycleEntry",
    "ProposalEntry",
    "ProposalsPayload",
    "NotificationDetail",
    "NotificationEntry",
    "NotificationsPayload",
    "DrilldownCoveragePayload",
    "DrilldownInterpretationPayload",
    "DrilldownSummaryPayload",
    "FindingEntry",
    "HypothesisEntry",
    "NextCheckEntry",
    "RecommendedActionPayload",
    "AssessmentSummaryPayload",
    "ClusterDetailPayload",
    "RunPayload",
    "RunsListEntry",
    "RunsListPayload",
    "RunsListTimings",
]


class ArtifactLink(TypedDict):
    """Shared artifact link in a run or proposal."""

    label: str
    path: str


class ProblemSummary(TypedDict):
    """Top-problem summary shown in fleet and cluster detail views."""

    title: str
    detail: str


class NextCheckExecutionHistoryEntry(TypedDict, total=False):
    """Payload for a single next-check execution history entry."""

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
    packRefreshStatus: str | None
    packRefreshWarning: str | None
    failureClass: str | None
    failureSummary: str | None
    suggestedNextOperatorMove: str | None
    resultClass: str | None
    resultSummary: str | None
    usefulnessClass: str | None
    usefulnessSummary: str | None
    # Provenance fields for traceability
    candidateId: str | None
    candidateIndex: int | None
    # Alertmanager provenance and relevance judgment
    alertmanagerProvenance: dict[str, object] | None
    alertmanagerRelevance: str | None
    alertmanagerRelevanceSummary: str | None
    # Artifact identity for immutability traceability
    artifactId: str | None
    # Usefulness review artifact identity fields
    usefulnessArtifactId: str | None
    usefulnessArtifactPath: str | None
    usefulnessReviewedAt: str | None


class FreshnessPayload(TypedDict, total=False):
    """Payload for run freshness indicator."""

    ageSeconds: int | None
    expectedIntervalSeconds: int | None
    status: str | None


class RunStatsPayload(TypedDict):
    """Payload for run statistics."""

    lastRunDurationSeconds: int | None
    totalRuns: int
    p50RunDurationSeconds: int | None
    p95RunDurationSeconds: int | None
    p99RunDurationSeconds: int | None


class LLMProviderEntry(TypedDict):
    """Single provider breakdown entry in LLM stats."""

    provider: str
    calls: int
    failedCalls: int


class LLMStatsPayload(TypedDict):
    """Payload for LLM call statistics."""

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
    """Payload for auto-drilldown policy state."""

    enabled: bool
    provider: str
    maxPerRun: int
    usedThisRun: int
    successfulThisRun: int
    failedThisRun: int
    skippedThisRun: int
    budgetExhausted: bool | None


class LLMPolicyPayload(TypedDict):
    """Payload for LLM policy state."""

    autoDrilldown: AutoDrilldownPolicyPayload


class LLMActivityEntryPayload(TypedDict, total=False):
    """Single LLM activity log entry."""

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
    """Summary section of LLM activity payload."""

    retainedEntries: int


class LLMActivityPayload(TypedDict):
    """Payload for LLM activity log."""

    entries: list[LLMActivityEntryPayload]
    summary: LLMActivitySummaryPayload


class AlertmanagerEvidenceReferencePayload(TypedDict, total=False):
    """Payload for an Alertmanager evidence reference in review enrichment."""

    cluster: str
    matchedDimensions: list[str]
    reason: str
    usedFor: str


class ReviewEnrichmentPayload(TypedDict, total=False):
    """Payload for review enrichment data."""

    status: str
    provider: str | None
    timestamp: str | None
    summary: str | None
    triageOrder: list[str]
    topConcerns: list[str]
    evidenceGaps: list[str]
    nextChecks: list[str]
    focusNotes: list[str]
    alertmanagerEvidenceReferences: list[AlertmanagerEvidenceReferencePayload] | None
    artifactPath: str | None
    errorSummary: str | None
    skipReason: str | None


class FeedbackSummaryPayload(TypedDict):
    """Structured payload for feedback summary in provenance display."""

    totalEntries: int
    namespacesWithFeedback: list[str]
    clustersWithFeedback: list[str]
    servicesWithFeedback: list[str]


class FeedbackAdaptationProvenancePayload(TypedDict, total=False):
    """Payload for feedback adaptation provenance data on next-check candidates/queue items."""

    feedbackAdaptation: bool
    adaptationReason: str | None
    originalBonus: int
    suppressedBonus: int
    penaltyApplied: int
    explanation: str | None
    feedbackSummary: FeedbackSummaryPayload | None


class AlertmanagerProvenancePayload(TypedDict, total=False):
    """Payload for alertmanager provenance data on next-check candidates/queue items."""

    matchedDimensions: list[str]
    matchedValues: dict[str, list[str]]
    appliedBonus: int
    baseBonus: int
    severitySummary: dict[str, int] | None
    signalStatus: str | None


class NextCheckCandidatePayload(TypedDict, total=False):
    """Payload for a next-check candidate."""

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
    priorityRationale: str | None
    rankingReason: str | None

    alertmanagerProvenance: AlertmanagerProvenancePayload | None
    feedbackAdaptationProvenance: FeedbackAdaptationProvenancePayload | None


class NextCheckQueueItemPayload(TypedDict, total=False):
    """Payload for a next-check queue item."""

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
    workstream: str | None
    alertmanagerProvenance: AlertmanagerProvenancePayload | None
    feedbackAdaptationProvenance: FeedbackAdaptationProvenancePayload | None


class NextCheckQueueCandidateAccountingPayload(TypedDict):
    """Payload for queue candidate accounting summary."""

    generated: int
    safe: int
    approvalNeeded: int
    duplicate: int
    completed: int
    staleOrphaned: int
    orphanedApprovals: int


class NextCheckQueueClusterStatePayload(TypedDict):
    """Payload for queue cluster state snapshot."""

    degradedClusterCount: int
    degradedClusterLabels: list[str]
    deterministicNextCheckCount: int
    deterministicClusterCount: int
    drilldownReadyCount: int


class NextCheckQueueExplanationPayload(TypedDict, total=False):
    """Payload for queue explanation and planner availability context."""

    status: str
    reason: str | None
    hint: str | None
    plannerArtifactPath: str | None
    clusterState: NextCheckQueueClusterStatePayload
    candidateAccounting: NextCheckQueueCandidateAccountingPayload
    deterministicNextChecksAvailable: bool
    recommendedNextActions: list[str]


class DeterministicNextCheckSummaryPayload(TypedDict):
    """Payload for a single deterministic next-check summary."""

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
    """Payload for a cluster's deterministic next-check view."""

    label: str
    context: str
    topProblem: str | None
    deterministicNextCheckCount: int
    deterministicNextCheckSummaries: list[DeterministicNextCheckSummaryPayload]
    drilldownAvailable: bool
    assessmentArtifactPath: str | None
    drilldownArtifactPath: str | None


class DeterministicNextChecksPayload(TypedDict):
    """Payload for the full deterministic next-check view."""

    clusterCount: int
    totalNextCheckCount: int
    clusters: list[DeterministicNextCheckClusterPayload]


class NextCheckOrphanedApprovalPayload(TypedDict, total=False):
    """Payload for an orphaned next-check approval."""

    approvalStatus: str | None
    candidateId: str | None
    candidateIndex: int | None
    candidateDescription: str | None
    targetCluster: str | None
    planArtifactPath: str | None
    approvalArtifactPath: str | None
    approvalTimestamp: str | None


class NextCheckOutcomeCountPayload(TypedDict):
    """Payload for an outcome count bucket in the next-check plan."""

    status: str
    count: int


class NextCheckPlanPayload(TypedDict, total=False):
    """Payload for the next-check plan view."""

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
    """Payload for planner availability state."""

    status: str
    reason: str | None
    hint: str | None
    artifactPath: str | None
    nextActionHint: str | None


class ReviewEnrichmentStatusPayload(TypedDict, total=False):
    """Payload for review enrichment status."""

    status: str
    reason: str | None
    provider: str | None
    policyEnabled: bool
    providerConfigured: bool
    adapterAvailable: bool | None
    runEnabled: bool | None
    runProvider: str | None


class DiagnosticPackReviewCandidatePayload(TypedDict, total=False):
    """Payload for a single diagnostic-pack review candidate."""

    providerReview: dict[str, object] | None


class DiagnosticPackReviewPayload(TypedDict, total=False):
    """Payload for diagnostic-pack review summary."""

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
    """Payload for diagnostic pack metadata."""

    path: str | None
    timestamp: str | None
    label: str | None
    reviewBundlePath: str | None
    reviewInput14bPath: str | None
    # Semantic metadata: indicates whether reviewBundlePath/reviewInput14bPath point to
    # the mutable latest/ mirror (true) or immutable run-scoped artifacts (false).
    # Consumers should NOT treat isMirror=true paths as immutable references.
    isMirror: bool | None
    # Immutable source-of-truth reference: the pack ZIP path that corresponds to
    # the mirror paths when isMirror=true. Exposed so operators can reference
    # the exact immutable pack that generated the current mirror content.
    sourcePackPath: str | None


class ClusterAlertSummaryPayload(TypedDict, total=False):
    """Payload for per-cluster alert summary."""

    cluster: str
    alert_count: int
    severity_counts: dict[str, int]
    state_counts: dict[str, int]
    top_alert_names: list[str]
    affected_namespaces: list[str]
    affected_services: list[str]


class AlertmanagerCompactPayload(TypedDict, total=False):
    """Payload for the Alertmanager compact alert summary view."""

    status: str
    alert_count: int
    severity_counts: dict[str, int]
    state_counts: dict[str, int]
    top_alert_names: list[str]
    affected_namespaces: list[str]
    affected_clusters: list[str]
    affected_services: list[str]
    truncated: bool
    captured_at: str
    by_cluster: list[ClusterAlertSummaryPayload]


class AlertmanagerSourcePayload(TypedDict, total=False):
    """Payload for a single Alertmanager source."""

    source_id: str
    endpoint: str
    namespace: str | None
    name: str | None
    origin: str
    state: str
    discovered_at: str | None
    verified_at: str | None
    last_check: str | None
    last_error: str | None
    verified_version: str | None
    confidence_hints: list[str]
    # Deduplication provenance fields
    merged_provenances: list[str]  # all contributing origins
    display_provenance: str  # human-readable provenance string
    # Manual provenance: distinguishes operator-configured vs operator-promoted
    manual_source_mode: str | None  # operator-configured, operator-promoted, or not-present
    # Computed UI fields
    is_manual: bool
    is_tracking: bool
    can_disable: bool
    can_promote: bool
    display_origin: str
    display_state: str
    provenance_summary: str
    # Cluster association for per-cluster UI filtering
    cluster_label: str | None
    # Deterministic identity fields for historical/debug tracking
    canonicalEntityId: str | None
    cluster_uid: str | None
    object_uid: str | None


class AlertmanagerSourcesPayload(TypedDict, total=False):
    """Payload for the full Alertmanager source inventory."""

    sources: list[AlertmanagerSourcePayload]
    total_count: int
    tracked_count: int
    manual_count: int
    degraded_count: int
    missing_count: int
    discovery_timestamp: str | None
    cluster_context: str | None


class ProviderExecutionBranchPayload(TypedDict, total=False):
    """Payload for a single provider execution branch."""

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
    """Payload for provider execution branch summary."""

    autoDrilldown: ProviderExecutionBranchPayload
    reviewEnrichment: ProviderExecutionBranchPayload


class RatingCount(TypedDict):
    """A rating count bucket."""

    rating: str
    count: int


class StatusCount(TypedDict):
    """A status count bucket."""

    status: str
    count: int


class FleetStatusPayload(TypedDict):
    """Payload for fleet-level status summary."""

    ratingCounts: list[RatingCount]
    degradedClusters: list[str]


class ClusterSummaryPayload(TypedDict):
    """Payload for cluster summary in fleet view."""

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
    """Payload for proposal summary in fleet view."""

    pending: int
    total: int
    statusCounts: list[StatusCount]


class FleetPayload(TypedDict):
    """Payload for the fleet overview response."""

    runId: str
    runLabel: str
    lastRunTimestamp: str
    topProblem: ProblemSummary
    fleetStatus: FleetStatusPayload
    clusters: list[ClusterSummaryPayload]
    proposalSummary: ProposalSummaryPayload


class LifecycleEntry(TypedDict):
    """A single lifecycle status entry for a proposal."""

    status: str
    timestamp: str
    note: str | None


class ProposalEntry(TypedDict):
    """Payload for a single proposal entry."""

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
    # Immutable artifact identity (UUIDv7); None for legacy artifacts
    artifactId: str | None


class ProposalsPayload(TypedDict):
    """Payload for the proposals list response."""

    statusSummary: list[StatusCount]
    proposals: list[ProposalEntry]


class NotificationDetail(TypedDict):
    """A key-value detail pair in a notification."""

    label: str
    value: str


class NotificationEntry(TypedDict):
    """Payload for a single notification entry."""

    kind: str
    summary: str
    timestamp: str
    runId: str | None
    clusterLabel: str | None
    context: str | None
    details: list[NotificationDetail]
    artifactPath: str | None
    # Immutable artifact identity (UUIDv7); None for legacy artifacts
    artifactId: str | None


class NotificationsPayload(TypedDict):
    """Payload for the notifications list response."""

    notifications: list[NotificationEntry]


class DrilldownCoveragePayload(TypedDict):
    """Payload for drilldown coverage of a single cluster."""

    label: str
    context: str
    available: bool
    timestamp: str | None
    artifactPath: str | None


class DrilldownInterpretationPayload(TypedDict, total=False):
    """Payload for an auto-interpretation of drilldown data."""

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
    """Payload for drilldown availability summary."""

    totalClusters: int
    available: int
    missing: int
    missingClusters: list[str]


class FindingEntry(TypedDict):
    """Payload for a single findings entry."""

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
    """Payload for a single hypothesis entry."""

    description: str
    confidence: str
    probableLayer: str
    falsifier: str


class NextCheckEntry(TypedDict):
    """Payload for a single next-check entry in an assessment."""

    description: str
    owner: str
    method: str
    evidenceNeeded: list[str]


class RecommendedActionPayload(TypedDict):
    """Payload for a recommended action in an assessment."""

    actionType: str
    description: str
    references: list[str]
    safetyLevel: str


class AssessmentSummaryPayload(TypedDict, total=False):
    """Payload for assessment summary in cluster detail view."""

    healthRating: str
    missingEvidence: list[str]
    probableLayer: str | None
    overallConfidence: str | None
    artifactPath: str | None
    snapshotPath: str | None


class ClusterDetailPayload(TypedDict):
    """Payload for the cluster detail response."""

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


class RunPayload(TypedDict):
    """Payload for the top-level run/UI index response."""

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
    alertmanagerCompact: AlertmanagerCompactPayload | None
    alertmanagerSources: AlertmanagerSourcesPayload | None


class RunsListEntry(TypedDict):
    """Payload for a single entry in the runs list."""

    runId: str
    runLabel: str
    timestamp: str
    clusterCount: int
    triaged: bool
    executionCount: int
    reviewedCount: int
    reviewStatus: str
    reviewDownloadPath: str | None
    # Batch execution support for Recent runs
    batchExecutable: bool
    batchEligibleCount: int


class RunsListPayload(TypedDict):
    """Payload for the runs list response."""

    runs: list[RunsListEntry]
    totalCount: int


class RunsListTimings(TypedDict, total=False):
    """Timing metrics from build_runs_list()."""

    reviews_glob_ms: float
    reviews_parsed: int
    execution_artifacts_glob_ms: float
    execution_artifacts_scanned: int
    execution_count_derivation_ms: float
    execution_count_derivation_matches: int
    # Stage 1 sub-stages (breakdown of reviews_glob_ms)
    reviews_glob_only_ms: float
    reviews_files_found: int
    reviews_parse_ms: float
    # Fast path telemetry for ijson streaming
    review_fast_path_attempted: int
    review_fast_path_succeeded: int
    review_fast_path_fallbacks: int
    review_fast_path_failure_json: int
    review_fast_path_failure_missing_field: int
    review_fast_path_failure_other: int
    # Stage 2 sub-stages (breakdown of execution_artifacts_glob_ms)
    execution_glob_only_ms: float
    execution_parse_ms: float
    review_artifact_prescan_ms: float
    review_download_path_checks_ms: float
    review_download_paths_found: int
    batch_eligibility_prescan_ms: float
    # Stage 3b sub-stages (breakdown of batch_eligibility_prescan_ms)
    batch_plan_glob_ms: float
    batch_plan_parse_ms: float
    batch_plan_files_found: int
    batch_exec_glob_ms: float
    batch_exec_parse_ms: float
    batch_exec_files_found: int
    batch_run_id_matching_ms: float
    batch_cache_construction_ms: float
    batch_eligible_runs: int
    # Row assembly sub-stages (detailed breakdown of row_assembly_ms)
    review_status_row_ms: float
    review_download_path_row_ms: float
    batch_eligibility_row_ms: float
    artifact_lookup_row_ms: float
    timestamp_normalization_row_ms: float
    label_normalization_row_ms: float
    per_row_fs_checks_ms: float  # Should be ~0 if precomputed properly
    row_assembly_ms: float
    rows_built: int
    sort_ms: float
    # Per-row filesystem call counters (prove no per-row FS work)
    path_exists_calls: int
    stat_calls: int
    diagnostic_pack_path_checks: int
    run_scoped_review_path_checks: int
    per_run_glob_calls: int
    per_run_directory_list_calls: int
