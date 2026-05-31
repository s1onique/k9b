"""TypedDict payload definitions for next-check plan, queue, and execution.

This module contains pure data contracts (TypedDict definitions) for next-check
management UI responses, including plan views, queue items, execution history,
and approval/mutation payloads.

Ownership:
    - All TypedDict payload classes defined here represent API response contracts.
    - JSON key names, optional vs required fields, and field types are frozen.
    - Serialization logic lives in api_next_check_*.py and related modules.

Extraction rationale:
    - Next-check contracts are self-contained with well-defined dependencies.
    - Extracting them establishes the next-check contract boundary.
    - Keeping next-check contracts in a dedicated module makes it easier to
      audit next-check API contracts without filtering through unrelated payloads.
    - Candidates, queue items, plan, and execution contracts share provenance
      types (AlertmanagerProvenancePayload, FeedbackAdaptationProvenancePayload)
      that are also next-check specific.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

__all__ = [
    # Execution history
    "NextCheckExecutionHistoryEntry",
    # Provenance types (shared across candidates, queue items)
    "AdaptationEffect",
    "StalenessClass",
    "AlertmanagerProvenancePayload",
    "FeedbackSummaryPayload",
    "FeedbackAdaptationProvenancePayload",
    # Candidate payload
    "NextCheckCandidatePayload",
    # Queue payloads
    "NextCheckQueueItemPayload",
    "NextCheckQueueCandidateAccountingPayload",
    "NextCheckQueueClusterStatePayload",
    "NextCheckQueueExplanationPayload",
    # Deterministic next-check payloads
    "DeterministicNextCheckSummaryPayload",
    "DeterministicNextCheckClusterPayload",
    "DeterministicNextChecksPayload",
    # Approval payloads
    "NextCheckOrphanedApprovalPayload",
    # Plan payloads
    "NextCheckOutcomeCountPayload",
    "NextCheckPlanPayload",
    # Planner availability
    "PlannerAvailabilityPayload",
]


# === Provenance types shared across next-check contracts ===

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


class FeedbackSummaryPayload(TypedDict):
    """Structured payload for feedback summary in provenance display."""

    totalEntries: int
    namespacesWithFeedback: list[str]
    clustersWithFeedback: list[str]
    servicesWithFeedback: list[str]


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


# === Execution history ===

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


# === Candidate payload ===

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


# === Queue payloads ===

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


# === Deterministic next-check payloads ===

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


# === Approval payloads ===

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


# === Plan payloads ===

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


# === Planner availability ===

class PlannerAvailabilityPayload(TypedDict, total=False):
    """Payload for planner availability state."""

    status: str
    reason: str | None
    hint: str | None
    artifactPath: str | None
    nextActionHint: str | None