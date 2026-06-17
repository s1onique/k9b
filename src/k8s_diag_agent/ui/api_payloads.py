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

from typing import TypedDict

__all__ = [
    # Shared primitives (moved to api_payloads_primitives.py)
    "ArtifactLink",  # noqa: F401 - re-exported
    "ProblemSummary",  # noqa: F401 - re-exported
    # Incident read-model contracts (moved to api_payloads_incident_reads.py)
    "IncidentSignalPayload",  # noqa: F401 - re-exported
    "IncidentEvidenceLinkPayload",  # noqa: F401 - re-exported
    "IncidentReviewPacketPayload",  # noqa: F401 - re-exported
    "IncidentEventPayload",  # noqa: F401 - re-exported
    "IncidentSuggestedCheckPayload",  # noqa: F401 - re-exported
    "IncidentSummaryPayload",  # noqa: F401 - re-exported
    "IncidentDetailPayload",  # noqa: F401 - re-exported
    # Runs-list contracts (moved to api_payloads_runs.py)
    "BatchExecutionSummary",  # noqa: F401 - re-exported
    "RunsListEntry",  # noqa: F401 - re-exported
    "RunsListPayload",  # noqa: F401 - re-exported
    "RunsListTimings",  # noqa: F401 - re-exported
    # Next-check contracts (moved to api_payloads_next_checks.py)
    "NextCheckExecutionHistoryEntry",  # noqa: F401 - re-exported
    "AdaptationEffect",  # noqa: F401 - re-exported
    "StalenessClass",  # noqa: F401 - re-exported
    "FeedbackSummaryPayload",  # noqa: F401 - re-exported
    "FeedbackAdaptationProvenancePayload",  # noqa: F401 - re-exported
    "AlertmanagerProvenancePayload",  # noqa: F401 - re-exported
    "NextCheckCandidatePayload",  # noqa: F401 - re-exported
    "NextCheckQueueItemPayload",  # noqa: F401 - re-exported
    "NextCheckQueueCandidateAccountingPayload",  # noqa: F401 - re-exported
    "NextCheckQueueClusterStatePayload",  # noqa: F401 - re-exported
    "NextCheckQueueExplanationPayload",  # noqa: F401 - re-exported
    "DeterministicNextCheckSummaryPayload",  # noqa: F401 - re-exported
    "DeterministicNextCheckClusterPayload",  # noqa: F401 - re-exported
    "DeterministicNextChecksPayload",  # noqa: F401 - re-exported
    "NextCheckOrphanedApprovalPayload",  # noqa: F401 - re-exported
    "NextCheckOutcomeCountPayload",  # noqa: F401 - re-exported
    "NextCheckPlanPayload",  # noqa: F401 - re-exported
    "PlannerAvailabilityPayload",  # noqa: F401 - re-exported
    # Review/enrichment contracts (moved to api_payloads_review.py)
    "AlertmanagerEvidenceReferencePayload",  # noqa: F401 - re-exported
    "ReviewEnrichmentPayload",  # noqa: F401 - re-exported
    "ReviewEnrichmentStatusPayload",  # noqa: F401 - re-exported
    "DiagnosticPackReviewCandidatePayload",  # noqa: F401 - re-exported
    "DiagnosticPackReviewPayload",  # noqa: F401 - re-exported
    # Notification contracts (moved to api_payloads_notifications.py)
    "NotificationDetail",  # noqa: F401 - re-exported
    "NotificationEntry",  # noqa: F401 - re-exported
    "NotificationsPayload",  # noqa: F401 - re-exported
    # Fleet status contracts (moved to api_payloads_fleet.py)
    "FreshnessPayload",  # noqa: F401 - re-exported
    "RunStatsPayload",  # noqa: F401 - re-exported
    # LLM/provider activity contracts (moved to api_payloads_llm.py)
    "LLMActivityEntryPayload",  # noqa: F401 - re-exported
    "LLMActivityPayload",  # noqa: F401 - re-exported
    "LLMActivitySummaryPayload",  # noqa: F401 - re-exported
    "AutoDrilldownPolicyPayload",  # noqa: F401 - re-exported
    "LLMPolicyPayload",  # noqa: F401 - re-exported
    "LLMProviderEntry",  # noqa: F401 - re-exported
    "LLMStatsPayload",  # noqa: F401 - re-exported
    "ProviderExecutionBranchPayload",  # noqa: F401 - re-exported
    "ProviderExecutionPayload",  # noqa: F401 - re-exported
    # Diagnostic/drilldown contracts (moved to api_payloads_diagnostics.py)
    "DiagnosticPackPayload",  # noqa: F401 - re-exported
    "DrilldownCoveragePayload",  # noqa: F401 - re-exported
    "DrilldownInterpretationPayload",  # noqa: F401 - re-exported
    "DrilldownSummaryPayload",  # noqa: F401 - re-exported
    # Alertmanager contracts (moved to api_payloads_alertmanager.py)
    "ClusterAlertSummaryPayload",  # noqa: F401 - re-exported
    "AlertmanagerCompactPayload",  # noqa: F401 - re-exported
    "AlertmanagerSourcePayload",  # noqa: F401 - re-exported
    "AlertmanagerSourcesPayload",  # noqa: F401 - re-exported
    # Proposal/lifecycle contracts (moved to api_payloads_proposals.py)
    "RatingCount",  # noqa: F401 - re-exported
    "StatusCount",  # noqa: F401 - re-exported
    "ProposalSummaryPayload",  # noqa: F401 - re-exported
    "LifecycleEntry",  # noqa: F401 - re-exported
    "ProposalEntry",  # noqa: F401 - re-exported
    "ProposalsPayload",  # noqa: F401 - re-exported
    # Fleet status contracts (moved to api_payloads_fleet.py)
    "FleetStatusPayload",  # noqa: F401 - re-exported
    "ClusterSummaryPayload",  # noqa: F401 - re-exported
    "FleetPayload",  # noqa: F401 - re-exported
    # Incident report / operator worklist contracts (moved to api_payloads_incident.py)
    "FindingEntry",  # noqa: F401 - re-exported
    "HypothesisEntry",  # noqa: F401 - re-exported
    "NextCheckEntry",  # noqa: F401 - re-exported
    "RecommendedActionPayload",  # noqa: F401 - re-exported
    "AssessmentSummaryPayload",  # noqa: F401 - re-exported
    "ClusterDetailPayload",  # noqa: F401 - re-exported
    "ClaimType",  # noqa: F401 - re-exported
    "EvidenceOwnershipConfidence",  # noqa: F401 - re-exported
    "IncidentReportFactPayload",  # noqa: F401 - re-exported
    "IncidentReportDerivedPayload",  # noqa: F401 - re-exported
    "IncidentReportInferencePayload",  # noqa: F401 - re-exported
    "IncidentReportRecommendationPayload",  # noqa: F401 - re-exported
    "IncidentReportUnknownPayload",  # noqa: F401 - re-exported
    "DiagnosticExecutionEvidencePayload",  # noqa: F401 - re-exported
    "IncidentReportPayload",  # noqa: F401 - re-exported
    "OperatorWorklistItemPayload",  # noqa: F401 - re-exported
    "OperatorWorklistPayload",  # noqa: F401 - re-exported
    # Cross-cluster comparison findings (moved to api_payloads_incident.py)
    "CrossClusterFindingPayload",  # noqa: F401 - re-exported
    "VmalertDiscoveryContextPayload",  # noqa: F401 - re-exported
    "VmalertRuleStateContextPayload",  # noqa: F401 - re-exported
    "VmalertSourceSummaryPayload",  # noqa: F401 - re-exported
    # vmalert contracts (moved to api_payloads_vmalert.py)
    "VmalertRuleStatePayload",  # noqa: F401 - re-exported
    "VmalertRuleStateAlertPayload",  # noqa: F401 - re-exported
    "VmalertRuleStateRuleGroupPayload",  # noqa: F401 - re-exported
    "VmalertRuleStateFetchErrorPayload",  # noqa: F401 - re-exported
    "VmalertSourcePayload",  # noqa: F401 - re-exported
    "VmalertSourcesPayload",  # noqa: F401 - re-exported
    "RunPayload",
]

# === Re-exports for backward compatibility ===

# Incident read-model contracts (moved to api_payloads_incident_reads.py)
# Shared primitives (moved to api_payloads_primitives.py)
# Runs-list contracts (moved to api_payloads_runs.py)
# Next-check contracts (moved to api_payloads_next_checks.py)
from .api_payloads_alertmanager import (  # noqa: F401 - re-exported for backward compatibility
    AlertmanagerCompactPayload,
    AlertmanagerSourcePayload,
    AlertmanagerSourcesPayload,
    ClusterAlertSummaryPayload,
)
from .api_payloads_diagnostics import (  # noqa: F401 - re-exported for backward compatibility
    DiagnosticPackPayload,
    DrilldownCoveragePayload,
    DrilldownInterpretationPayload,
    DrilldownSummaryPayload,
)
from .api_payloads_fleet import (  # noqa: F401 - re-exported for backward compatibility
    ClusterSummaryPayload,
    FleetPayload,
    FleetStatusPayload,
    FreshnessPayload,
    RunStatsPayload,
)

# Incident report and operator worklist contracts (moved to api_payloads_incident.py)
from .api_payloads_incident import (  # noqa: F401 - re-exported for backward compatibility
    AssessmentSummaryPayload,
    ClaimType,
    ClusterDetailPayload,
    CrossClusterFindingPayload,
    DiagnosticExecutionEvidencePayload,
    EvidenceOwnershipConfidence,
    FindingEntry,
    HypothesisEntry,
    IncidentReportDerivedPayload,
    IncidentReportFactPayload,
    IncidentReportInferencePayload,
    IncidentReportPayload,
    IncidentReportRecommendationPayload,
    IncidentReportUnknownPayload,
    NextCheckEntry,
    OperatorWorklistItemPayload,
    OperatorWorklistPayload,
    RecommendedActionPayload,
    VmalertDiscoveryContextPayload,
    VmalertRuleStateContextPayload,
    VmalertSourceSummaryPayload,
)
from .api_payloads_incident_reads import (  # noqa: F401 - re-exported for backward compatibility
    IncidentDetailPayload,
    IncidentEventPayload,
    IncidentEvidenceLinkPayload,
    IncidentReviewPacketPayload,
    IncidentSignalPayload,
    IncidentSuggestedCheckPayload,
    IncidentSummaryPayload,
)
from .api_payloads_llm import (  # noqa: F401 - re-exported for backward compatibility
    AutoDrilldownPolicyPayload,
    LLMActivityEntryPayload,
    LLMActivityPayload,
    LLMActivitySummaryPayload,
    LLMPolicyPayload,
    LLMProviderEntry,
    LLMStatsPayload,
    ProviderExecutionBranchPayload,
    ProviderExecutionPayload,
)
from .api_payloads_next_checks import (  # noqa: F401 - re-exported for backward compatibility
    AdaptationEffect,
    AlertmanagerProvenancePayload,
    DeterministicNextCheckClusterPayload,
    DeterministicNextChecksPayload,
    DeterministicNextCheckSummaryPayload,
    FeedbackAdaptationProvenancePayload,
    FeedbackSummaryPayload,
    NextCheckCandidatePayload,
    NextCheckExecutionHistoryEntry,
    NextCheckOrphanedApprovalPayload,
    NextCheckOutcomeCountPayload,
    NextCheckPlanPayload,
    NextCheckQueueCandidateAccountingPayload,
    NextCheckQueueClusterStatePayload,
    NextCheckQueueExplanationPayload,
    NextCheckQueueItemPayload,
    PlannerAvailabilityPayload,
    StalenessClass,
)
from .api_payloads_notifications import (  # noqa: F401 - re-exported for backward compatibility
    NotificationDetail,
    NotificationEntry,
    NotificationsPayload,
)
from .api_payloads_primitives import (  # noqa: F401 - re-exported for backward compatibility
    ArtifactLink,
    ProblemSummary,
)
from .api_payloads_proposals import (  # noqa: F401 - re-exported for backward compatibility
    LifecycleEntry,
    ProposalEntry,
    ProposalsPayload,
    ProposalSummaryPayload,
    RatingCount,
    StatusCount,
)
from .api_payloads_review import (  # noqa: F401 - re-exported for backward compatibility
    AlertmanagerEvidenceReferencePayload,
    DiagnosticPackReviewCandidatePayload,
    DiagnosticPackReviewPayload,
    ReviewEnrichmentPayload,
    ReviewEnrichmentStatusPayload,
)
from .api_payloads_runs import (  # noqa: F401 - re-exported for backward compatibility
    BatchExecutionSummary,
    RunsListEntry,
    RunsListPayload,
    RunsListTimings,
)
from .api_payloads_vmalert import (  # noqa: F401 - re-exported for backward compatibility
    VmalertRuleStateAlertPayload,
    VmalertRuleStateFetchErrorPayload,
    VmalertRuleStatePayload,
    VmalertRuleStateRuleGroupPayload,
    VmalertSourcePayload,
    VmalertSourcesPayload,
)

# Fleet status contracts are re-exported from api_payloads_fleet.py
# (see imports above). The actual definitions live in that module.

# LLM/provider activity contracts are re-exported from api_payloads_llm.py
# (see imports above). The actual definitions live in that module.

# Diagnostic/drilldown contracts are re-exported from api_payloads_diagnostics.py
# (see imports above). The actual definitions live in that module.

# Alertmanager contracts are re-exported from api_payloads_alertmanager.py
# (see imports above). The actual definitions live in that module.

# vmalert contracts are re-exported from api_payloads_vmalert.py
# (see imports above). The actual definitions live in that module.

# Proposal/lifecycle contracts are re-exported from api_payloads_proposals.py
# (see imports above). The actual definitions live in that module.

# Incident report and operator worklist contracts are re-exported from api_payloads_incident.py
# (see imports above). The actual definitions live in that module.


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
