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

from typing import Literal, NotRequired, TypedDict

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
    "AdaptationEffect",
    "FeedbackAdaptationProvenancePayload",
    "StalenessClass",
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
    "ClaimType",
    "IncidentReportFactPayload",
    "IncidentReportDerivedPayload",
    "IncidentReportInferencePayload",
    "IncidentReportRecommendationPayload",
    "IncidentReportUnknownPayload",
    "IncidentReportPayload",
    "OperatorWorklistItemPayload",
    "OperatorWorklistPayload",
    # Cross-cluster comparison findings
    "CrossClusterFindingPayload",
    "VmalertDiscoveryContextPayload",
    "VmalertSourceSummaryPayload",
    # vmalert rule state
    "VmalertRuleStatePayload",
    "VmalertRuleStateAlertPayload",
    "VmalertRuleStateRuleGroupPayload",
    "VmalertRuleStateFetchErrorPayload",
    "RunPayload",
    # Re-exported from api_payloads_runs for backward compatibility
    "BatchExecutionSummary",  # noqa: F401 - re-exported
    "RunsListEntry",  # noqa: F401 - re-exported
    "RunsListPayload",  # noqa: F401 - re-exported
    "RunsListTimings",  # noqa: F401 - re-exported
]

# === Runs-list contracts moved to api_payloads_runs.py ===
from .api_payloads_runs import (  # noqa: F401 - re-exported for backward compatibility
    BatchExecutionSummary,
    RunsListEntry,
    RunsListPayload,
    RunsListTimings,
)


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


# Adaptation effect taxonomy for feedback provenance
# These describe what changed in the diagnosis or worklist because of execution feedback
AdaptationEffect = Literal[
    "hypothesis_strengthened",
    "hypothesis_weakened",
    "unknown_resolved",
    "recommendation_promoted",
    "recommendation_deprioritized",
    "no_material_change",
]


# Staleness class taxonomy for temporal context
# Derivation rules:
# - fresh: < 5 minutes since first recommendation
# - aging: 5-30 minutes since first recommendation
# - stale: > 30 minutes since first recommendation
# - unknown: timing data insufficient
StalenessClass = Literal["fresh", "aging", "stale", "unknown"]


class FeedbackAdaptationProvenancePayload(TypedDict, total=False):
    """Payload for feedback adaptation provenance data on next-check candidates/queue items.

    Surfaces what execution feedback changed in the diagnosis and operator worklist,
    so operators can understand how completed checks affected the system's current
    understanding and next recommendations.

    Adaptation effects are derived-only (stateless) from execution results and
    usefulness feedback. They do not introduce new persistence; they are projections
    from existing execution history and usefulness feedback artifacts.

    Contract invariants:
    - adaptationEffect is present when feedbackAdaptation is True
    - adaptationSummary is concise and operator-readable
    - no_material_change is used for noisy/inconclusive executions
    - adaptation does not overclaim causality from execution feedback
    """

    feedbackAdaptation: bool
    adaptationReason: str | None
    adaptationEffect: AdaptationEffect | None
    adaptationSummary: str | None  # Concise operator-readable description of what changed
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


class VmalertSourcePayload(TypedDict, total=False):
    """Payload for a single vmalert source."""

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


class VmalertSourcesPayload(TypedDict, total=False):
    """Payload for the full vmalert source inventory."""

    sources: list[VmalertSourcePayload]
    total_count: int
    source_count: int
    discovered_count: int
    discovered_but_unverified_count: int
    auto_tracked_count: int
    manual_count: int
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


# Constrained claim type literal for incident report taxonomy
ClaimType = Literal["observed", "derived", "hypothesis", "recommendation", "unknown"]


class IncidentReportFactPayload(TypedDict, total=False):
    """A deterministic, evidence-backed fact in the incident report.

    Corresponds to the "observed" claim type: direct telemetry signals backed
    by source artifact provenance.
    """

    claimType: ClaimType  # Always "observed"
    statement: str
    sourceArtifactRefs: list[ArtifactLink]
    confidence: str


class IncidentReportDerivedPayload(TypedDict, total=False):
    """A deterministic derived conclusion in the incident report.

    Corresponds to the "derived" claim type: conclusions from evidence fields
    that are deterministic but require interpretation (e.g., "degraded health
    based on warning threshold"). Originates from assessment/drilldown
    deterministic fields.
    """

    claimType: ClaimType  # Always "derived"
    statement: str
    sourceFields: list[str]  # Deterministic fields that produced this claim
    sourceArtifactRefs: list[ArtifactLink]
    confidence: str


class IncidentReportInferencePayload(TypedDict, total=False):
    """A reasoned inference in the incident report, explicitly labeled.

    Corresponds to the "hypothesis" claim type: plausible causes that still
    require confirmation. Cannot contain root-cause language without explicit
    basis. Provider-assisted content (review enrichment) also uses this type.
    """

    claimType: ClaimType  # Always "hypothesis"
    statement: str
    basis: list[str]
    confidence: str
    sourceArtifactRefs: list[ArtifactLink]


class IncidentReportRecommendationPayload(TypedDict, total=False):
    """An operator action recommendation in the incident report.

    Corresponds to the "recommendation" claim type: safe, low-disruption
    action suggestions. Separated from findings to prevent mixing observation
    and prescription. Must include safety level.
    """

    claimType: ClaimType  # Always "recommendation"
    statement: str
    safetyLevel: str
    sourceArtifactRefs: list[ArtifactLink]


# Ownership confidence levels for missing-evidence items
EvidenceOwnershipConfidence = Literal["high", "medium", "low", "unknown"]


class IncidentReportUnknownPayload(TypedDict, total=False):
    """An explicitly acknowledged unknown or missing-evidence item.

    Corresponds to the "unknown" claim type: data gaps and missing evidence
    that must NOT be rendered as confident prose or omitted silently.

    Ownership fields (evidenceOwner, routingHint, ownershipConfidence) are
    derived-only from available signals: method, evidence_needed, probable_layer,
    existing owner field, workstream, and cluster-vs-fleet scope. When no signal
    is available, evidenceOwner remains "unknown" and routingHint is omitted.
    """

    claimType: ClaimType  # Always "unknown"
    statement: str
    whyMissing: str | None
    sourceArtifactRefs: list[ArtifactLink]
    # Ownership/routing context: which team likely owns collecting this signal
    # Derived from: method patterns, evidence_needed labels, probable_layer,
    # existing owner field, workstream, cross-cluster scope
    evidenceOwner: str | None  # platform | application | networking | storage | security | observability | unknown
    routingHint: str | None  # Concise operator-readable routing instruction
    ownershipConfidence: EvidenceOwnershipConfidence | None  # high | medium | low | unknown


class CrossClusterFindingPayload(TypedDict, total=False):
    """A cross-cluster finding from comparison trigger artifacts.

    Cross-cluster findings represent fleet-level drift patterns that involve
    multiple clusters. They are distinct from per-cluster observations and
    provide visibility into drift that individual cluster assessments may miss.

    Taxonomy mapping:
    - observed: deterministic drift signals (e.g., helm release diff count)
    - hypothesis: speculative explanations of why drift exists
    - unknown: missing fleet context
    """

    # Identity
    primaryCluster: str
    secondaryCluster: str

    # Drift summary - counts per category
    # e.g., {"helm_releases": 2, "crds": 0, "metadata": 1}
    driftCounts: dict[str, int]

    # Comparison intent classification
    intent: str

    # Trigger reasons - deterministic signals that fired the comparison
    triggerReasons: list[str]

    # Provenance
    artifactPath: str | None
    timestamp: str | None

    # Cross-cluster recommendations (fleet-aware next checks)
    recommendedNextChecks: list[str]


class VmalertDiscoveryContextPayload(TypedDict, total=False):
    """vmalert discovery context in the incident report.

    Provides operator-visible context about discovered vmalert sources.
    This is a read-only, non-invasive integration: no live scraping or actions.

    Contract invariants:
    - source_count: total sources (0 = quiet, not an error)
    - discovered_count: sources in discovered state
    - discovered_but_unverified_count: sources discovered but not yet verified
    - sources: list of discovered sources with key fields for context
    - All missing/unverified states are non-fatal and do not degrade diagnostics
    """

    source_count: int
    discovered_count: int
    discovered_but_unverified_count: int
    sources: list[VmalertSourceSummaryPayload]


class VmalertSourceSummaryPayload(TypedDict, total=False):
    """Compact vmalert source summary for diagnostics context."""

    endpoint: str
    namespace: str | None
    name: str | None
    origin: str
    state: str
    display_provenance: str
    cluster_label: str | None


class VmalertRuleStateAlertPayload(TypedDict, total=False):
    """Payload for a single vmalert alert in rule state."""

    alertname: str
    state: str
    severity: str | None
    cluster_label: str | None
    namespace: str | None
    workload: str | None
    pod: str | None
    instance: str | None
    summary: str | None
    description: str | None
    active_at: str | None
    starts_at: str | None
    source_endpoint: str | None
    group_name: str | None
    rule_name: str | None


class VmalertRuleStateRuleGroupPayload(TypedDict, total=False):
    """Payload for a vmalert rule group in rule state."""

    name: str
    file: str | None
    interval: str | None
    rule_count: int
    firing_alert_count: int
    error_count: int


class VmalertRuleStateFetchErrorPayload(TypedDict, total=False):
    """Payload for a vmalert fetch error in rule state."""

    source_endpoint: str
    source_id: str | None
    status: str
    error: str


class VmalertRuleStatePayload(TypedDict, total=False):
    """Payload for vmalert rule state in run payload.

    Exposes collected vmalert alert/rule state as read-only diagnostic context.

    Contract invariants:
    - source_count: total sources attempted
    - fetched_source_count: sources successfully fetched
    - failed_source_count: sources that failed to fetch (non-fatal)
    - alert_count: total alerts across all sources
    - firing_alert_count: alerts in firing state
    - pending_alert_count: alerts in pending state
    - critical_firing_count: firing alerts with critical severity
    - alerts: list of alert signals
    - rule_groups: list of rule groups
    - fetch_errors: list of fetch errors (non-fatal diagnostic context)
    - Missing artifact returns None (not an error)
    """

    source_count: int
    fetched_source_count: int
    failed_source_count: int
    alert_count: int
    firing_alert_count: int
    pending_alert_count: int
    critical_firing_count: int
    rule_group_count: int
    fetch_error_count: int
    captured_at: str
    alerts: list[VmalertRuleStateAlertPayload]
    rule_groups: list[VmalertRuleStateRuleGroupPayload]
    fetch_errors: list[VmalertRuleStateFetchErrorPayload]


class VmalertRuleStateContextPayload(TypedDict, total=False):
    """Compact vmalert rule state context for the incident report.

    Provides operator-visible diagnostic context about vmalert firing/pending alerts.
    This is a read-only, non-invasive integration: no live scraping or actions.
    vmalertRuleState is sourced from the UI context (artifact-backed).

    Contract invariants:
    - source_count, fetched_source_count, failed_source_count: source status
    - alert_count, firing_alert_count, pending_alert_count: alert state counts
    - critical_firing_count: critical severity firing alerts
    - top_alertnames: most frequent firing alert names (up to 5)
    - severity_counts: firing alert counts per severity
    - affected_namespaces: namespaces with firing alerts
    - affected_workloads: workloads with firing alerts
    - fetch_error_count: non-fatal fetch errors
    - Missing artifact returns None (not an error)
    - Empty alerts means quiet zero-count state (not an error)
    - Pending alerts are visible but not escalated
    - Fetch failures are visible but non-fatal
    """

    source_count: int
    fetched_source_count: int
    failed_source_count: int
    alert_count: int
    firing_alert_count: int
    pending_alert_count: int
    critical_firing_count: int
    top_alertnames: list[str]
    severity_counts: list[tuple[str, int]]
    affected_namespaces: list[str]
    affected_workloads: list[str]
    fetch_error_count: int


class IncidentReportPayload(TypedDict, total=False):
    """Canonical incident report projection for a selected health run.

    Derived from existing artifacts. Not a new immutable source of truth.

    Canonical structured claims live in facts, derived, inferences,
    recommendations, and unknowns. recommendedActions is legacy display
    compatibility only.

    crossClusterFindings surfaces comparison-triggered fleet-level drift
    that individual cluster assessments may miss. These findings are
    clearly separated from per-cluster observations.

    vmalertDiscoveryContext provides operator-visible context about discovered
    vmalert sources for diagnostic awareness. This is read-only and non-invasive.
    """

    title: str
    status: str
    affectedScope: str | None
    impact: str | None
    evidenceSummary: str | None
    facts: list[IncidentReportFactPayload]
    derived: list[IncidentReportDerivedPayload]
    inferences: list[IncidentReportInferencePayload]
    recommendations: list[IncidentReportRecommendationPayload]
    unknowns: list[IncidentReportUnknownPayload]
    staleEvidenceWarnings: list[str]
    confidence: str | None
    freshness: FreshnessPayload | None
    recommendedActions: list[str]  # Legacy display compatibility only
    sourceArtifactRefs: list[ArtifactLink]
    # Cross-cluster findings from comparison triggers
    crossClusterFindings: list[CrossClusterFindingPayload] | None
    # vmalert discovery context for diagnostic awareness
    # Present when vmalert sources are available; None when no sources discovered
    vmalertDiscoveryContext: VmalertDiscoveryContextPayload | None
    # vmalert rule state context for firing/pending alert diagnostics
    # Present when vmalert rule state artifact exists; None when missing
    # Non-fatal: fetch errors and pending alerts are visible but not escalated
    vmalertRuleStateContext: VmalertRuleStateContextPayload | None


class OperatorWorklistItemPayload(TypedDict, total=False):
    """A single ranked, actionable item in the operator worklist.

    Unified projection derived from deterministic next checks, planner candidates,
    and execution history. This is a read-only projection; there is no new
    persistence layer.

    Contract invariants:
    - command is None for deterministic/advisory items (they have method, not executable cmd)
    - command is a concrete string for executable queue items
    - sourceArtifactRefs always uses real paths; no fabricated "unknown" references
    - itemState reflects the canonical state: advisory | approval-needed | approved |
      queued | executed | reviewed
    - provenance is preserved when items from multiple sources are deduplicated
    """

    # Identity and ranking
    id: str
    rank: int
    workstream: str | None

    # Content
    title: str
    description: str | None

    # Command semantics: None for deterministic/advisory, concrete string for executable
    # Consumers must NOT treat null command as a runnable string
    command: str | None

    # Target context
    targetCluster: str | None
    targetContext: str | None

    # Rationale
    reason: str | None
    expectedEvidence: str | None
    safetyNote: str | None

    # Explicit state (canonical itemState for UI consistency)
    # None for deterministic items, concrete state for queue items
    itemState: str | None  # advisory | approval-needed | approved | queued | executed | reviewed
    approvalState: str | None
    executionState: str | None
    feedbackState: str | None

    # Source provenance
    # sourceType distinguishes origin: deterministic | planner | promotion | execution
    sourceType: str | None

    # Deduplication provenance: when multiple sources contribute to one logical action,
    # mergedSources preserves all contributing origins for traceability
    mergedSources: list[str] | None

    # Artifact provenance: real paths only, no fabricated "unknown" refs
    sourceArtifactRefs: list[ArtifactLink]

    # Ranking rationale: concise, operator-readable explanation for why this item
    # has its current rank in the worklist. Derived from source signals and state.
    # Rationale is None when no ranking basis is determinable.
    rankingReason: str | None

    # Feedback adaptation provenance: surfaces what execution feedback changed
    # in the diagnosis and operator worklist. Present when feedback exists.
    # None for items without execution feedback.
    feedbackAdaptationProvenance: FeedbackAdaptationProvenancePayload | None

    # Temporal context: when timestamps are available from artifacts
    # firstRecommendedAt: earliest known timestamp tied to this logical recommendation
    #   - deterministic items: assessment/drilldown artifact timestamp
    #   - queue items: plan artifact timestamp or earliest candidate timestamp
    #   - None when no timing data is available
    firstRecommendedAt: str | None
    # lastStateChangedAt: most recent meaningful state transition timestamp
    #   - approval, execution, or review timestamp
    #   - None when no state change timestamp is available
    lastStateChangedAt: str | None
    # recommendationAgeSeconds: age in seconds from first recommendation to current run
    #   - Derived from firstRecommendedAt and run timestamp when both are known
    #   - None when timing data is insufficient
    recommendationAgeSeconds: int | None
    # stalenessClass: honest staleness category
    #   - fresh: < 5 minutes since first recommendation
    #   - aging: 5-30 minutes since first recommendation
    #   - stale: > 30 minutes since first recommendation
    #   - unknown: timing data insufficient
    stalenessClass: StalenessClass | None


class OperatorWorklistPayload(TypedDict, total=False):
    """Ranked operator worklist projection for a selected health run.

    Derived from deterministic next checks, planner candidates, and execution history.
    Not a new immutable source of truth.
    """

    items: list[OperatorWorklistItemPayload]
    totalItems: int
    completedItems: int
    pendingItems: int
    blockedItems: int


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
    vmalertSources: VmalertSourcesPayload | None
    vmalertRuleState: VmalertRuleStatePayload | None
    incidentReport: IncidentReportPayload | None
    operatorWorklist: OperatorWorklistPayload | None

