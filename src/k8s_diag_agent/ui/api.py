"""Read-model payload builders for the operator UI.

Payload TypedDict contracts are defined in api_payloads.py.
This module is the public serialization surface: it imports payloads from
api_payloads.py and re-exports them for backwards compatibility.

Ownership reminder:
    - TypedDict payload classes live in api_payloads.py (the contract module).
    - Serializer functions (_serialize_*) and public builders live here.
    - Do not add new TypedDict definitions here; add them to api_payloads.py.
    - Runs-list payload logic has been extracted to api_runs_payloads.py and helpers.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from ..datetime_utils import parse_iso_to_utc
from ..health.freshness import freshness_status

# Re-export all payload TypedDicts for backwards compatibility.
# Consumers should migrate to importing from ui.api_payloads directly,
# but existing imports from ui.api will continue to work.
from .api_alertmanager import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_alertmanager_compact,
    _serialize_alertmanager_source,
    _serialize_alertmanager_sources,
)
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
from .api_deterministic_next_checks import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_deterministic_next_check_cluster,
    _serialize_deterministic_next_check_summary,
    _serialize_deterministic_next_checks,
)
from .api_diagnostic_pack import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_diagnostic_pack,
    _serialize_diagnostic_pack_review,
)
from .api_incident_report import (
    _build_incident_report_payload,
    _build_operator_worklist_payload,
)
from .api_llm import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_llm_activity,
    _serialize_llm_policy,
    _serialize_llm_stats,
)
from .api_next_check_plan import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_execution_history,
    _serialize_next_check_candidate,
    _serialize_next_check_plan,
    _serialize_orphaned_approval,
    _serialize_plan_candidates_for_cluster,
)
from .api_next_check_queue import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_next_check_queue,
    _serialize_planner_availability,
    _serialize_queue_candidate_accounting,
    _serialize_queue_cluster_state,
    _serialize_queue_explanation,
)
from .api_payloads import (  # noqa: F401 - re-exported for backward compatibility
    AlertmanagerCompactPayload,
    AlertmanagerEvidenceReferencePayload,
    AlertmanagerProvenancePayload,
    AlertmanagerSourcePayload,
    AlertmanagerSourcesPayload,
    ArtifactLink,
    AssessmentSummaryPayload,
    BatchExecutionSummary,
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
    FeedbackSummaryPayload,
    FindingEntry,
    FleetPayload,
    FreshnessPayload,
    HypothesisEntry,
    IncidentReportFactPayload,
    IncidentReportInferencePayload,
    IncidentReportPayload,
    IncidentReportUnknownPayload,
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
    OperatorWorklistItemPayload,
    OperatorWorklistPayload,
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
from .api_provider_execution import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_provider_execution,
    _serialize_provider_execution_branch,
)
from .api_review_enrichment import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_review_enrichment,
    _serialize_review_enrichment_status,
)

# Import runs-list payload builders from extracted module.
# Re-export for backward compatibility: callers importing from api.py continue to work.
from .api_runs_payloads import (  # noqa: F401 - re-exported for backward compatibility
    _build_runs_list_from_index,
    _build_runs_list_review_streaming,
    _build_runs_list_super_fast,
    _build_runs_list_with_batch_eligibility_index,
    _compute_batch_eligibility,
    _extract_review_metadata_streaming,
    build_runs_list,
)
from .api_runs_payloads_batch import (  # noqa: F401 - re-exported for backward compatibility
    _compute_batch_eligibility_from_cache,
    _compute_execution_summary,
)
from .api_runs_payloads_index import (  # noqa: F401 - re-exported for backward compatibility
    _compute_execution_summary_indexed,
    _normalize_execution_indices_from_index,
)
from .api_runs_payloads_review import (  # noqa: F401 - re-exported for backward compatibility
    _derive_review_status,
)
from .api_vmalert import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_vmalert_rule_state,
    _serialize_vmalert_sources,
)
from .model import (
    RunStatsView,
    UIIndexContext,
)

logger = logging.getLogger(__name__)


def build_run_payload(
    context: UIIndexContext,
    *,
    promotions: Sequence[dict[str, object]] | None = None,
    health_root: Path | None = None,
) -> RunPayload:
    freshness = _build_freshness_payload(context.run.timestamp, context.run.scheduler_interval_seconds)
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
        "historicalLlmStats": (_serialize_llm_stats(context.run.historical_llm_stats) if context.run.historical_llm_stats else None),
        "llmActivity": _serialize_llm_activity(context.run.llm_activity),
        "llmPolicy": _serialize_llm_policy(context.run.llm_policy),
        "reviewEnrichment": _serialize_review_enrichment(context.run.review_enrichment),
        "reviewEnrichmentStatus": _serialize_review_enrichment_status(context.run.review_enrichment_status),
        "providerExecution": _serialize_provider_execution(context.run.provider_execution),
        "freshness": freshness,
        "nextCheckPlan": _serialize_next_check_plan(context.run.next_check_plan),
        "nextCheckQueue": _serialize_next_check_queue(
            context.run.next_check_queue,
            promotions,
        ),
        "nextCheckQueueExplanation": _serialize_queue_explanation(context.run.next_check_queue_explanation),
        "deterministicNextChecks": _serialize_deterministic_next_checks(context.run.deterministic_next_checks),
        "plannerAvailability": _serialize_planner_availability(context.run.planner_availability),
        "diagnosticPackReview": _serialize_diagnostic_pack_review(context.run.diagnostic_pack_review),
        "diagnosticPack": _serialize_diagnostic_pack(context.run.diagnostic_pack),
        "nextCheckExecutionHistory": _serialize_execution_history(context.run.next_check_execution_history),
        "alertmanagerCompact": _serialize_alertmanager_compact(context.alertmanager_compact),
        "alertmanagerSources": _serialize_alertmanager_sources(context.alertmanager_sources),
        "vmalertSources": _serialize_vmalert_sources(context.vmalert_sources),
        "vmalertRuleState": _serialize_vmalert_rule_state(context.vmalert_rule_state),
        "incidentReport": _build_incident_report_payload(context, freshness),
        "operatorWorklist": _build_operator_worklist_payload(context, health_root=health_root),
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

