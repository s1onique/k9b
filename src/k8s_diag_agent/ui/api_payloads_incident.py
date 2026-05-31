"""TypedDict payload definitions for incident report and operator worklist contracts."""

from __future__ import annotations

from typing import Literal, TypedDict

from .api_payloads_diagnostics import DrilldownCoveragePayload, DrilldownInterpretationPayload, DrilldownSummaryPayload
from .api_payloads_fleet import FreshnessPayload
from .api_payloads_next_checks import (
    FeedbackAdaptationProvenancePayload,
    NextCheckCandidatePayload,
    StalenessClass,
)
from .api_payloads_notifications import NotificationDetail, NotificationEntry
from .api_payloads_primitives import ArtifactLink, ProblemSummary
from .api_payloads_proposals import ProposalEntry

__all__ = [
    "ClaimType",
    "EvidenceOwnershipConfidence",
    "FindingEntry",
    "HypothesisEntry",
    "NextCheckEntry",
    "RecommendedActionPayload",
    "AssessmentSummaryPayload",
    "ClusterDetailPayload",
    "CrossClusterFindingPayload",
    "VmalertDiscoveryContextPayload",
    "VmalertSourceSummaryPayload",
    "VmalertRuleStateContextPayload",
    "IncidentReportFactPayload",
    "IncidentReportDerivedPayload",
    "IncidentReportInferencePayload",
    "IncidentReportRecommendationPayload",
    "IncidentReportUnknownPayload",
    "IncidentReportPayload",
    "OperatorWorklistItemPayload",
    "OperatorWorklistPayload",
]

# Constrained claim type literal for incident report taxonomy
ClaimType = Literal["observed", "derived", "hypothesis", "recommendation", "unknown"]


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


# Ownership confidence levels for missing-evidence items
EvidenceOwnershipConfidence = Literal["high", "medium", "low", "unknown"]


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
