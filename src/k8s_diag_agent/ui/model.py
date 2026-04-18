"""View model helpers for the operator UI."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import SupportsInt, cast


@dataclass(frozen=True)
class RunView:
    run_id: str
    run_label: str
    timestamp: str
    collector_version: str
    cluster_count: int
    drilldown_count: int
    proposal_count: int
    external_analysis_count: int
    notification_count: int
    scheduler_interval_seconds: int | None
    run_stats: RunStatsView
    llm_stats: LLMStatsView
    historical_llm_stats: LLMStatsView | None
    llm_activity: LLMActivityView
    llm_policy: LLMPolicyView | None
    review_enrichment: ReviewEnrichmentView | None
    review_enrichment_status: ReviewEnrichmentStatusView | None
    provider_execution: ProviderExecutionView | None
    next_check_plan: NextCheckPlanView | None
    planner_availability: PlannerAvailabilityView | None
    next_check_execution_history: tuple[NextCheckExecutionHistoryEntryView, ...]
    next_check_queue: tuple[NextCheckQueueItemView, ...]
    next_check_queue_explanation: NextCheckQueueExplanationView | None
    deterministic_next_checks: DeterministicNextChecksView | None
    diagnostic_pack_review: DiagnosticPackReviewView | None
    diagnostic_pack: DiagnosticPackView | None


@dataclass(frozen=True)
class RunStatsView:
    last_run_duration_seconds: int | None = None
    total_runs: int = 0
    p50_run_duration_seconds: int | None = None
    p95_run_duration_seconds: int | None = None
    p99_run_duration_seconds: int | None = None


@dataclass(frozen=True)
class ProviderBreakdownEntry:
    provider: str
    calls: int
    failed_calls: int


@dataclass(frozen=True)
class LLMStatsView:
    total_calls: int
    successful_calls: int
    failed_calls: int
    last_call_timestamp: str | None
    p50_latency_ms: int | None
    p95_latency_ms: int | None
    p99_latency_ms: int | None
    provider_breakdown: tuple[ProviderBreakdownEntry, ...]
    scope: str = "current_run"


@dataclass(frozen=True)
class LLMActivityEntryView:
    timestamp: str | None
    run_id: str | None
    run_label: str | None
    cluster_label: str | None
    tool_name: str | None
    provider: str | None
    purpose: str | None
    status: str | None
    latency_ms: int | None
    artifact_path: str | None
    summary: str | None
    error_summary: str | None
    skip_reason: str | None


@dataclass(frozen=True)
class LLMActivitySummaryView:
    retained_entries: int


@dataclass(frozen=True)
class LLMActivityView:
    entries: tuple[LLMActivityEntryView, ...]
    summary: LLMActivitySummaryView


@dataclass(frozen=True)
class PlannerAvailabilityView:
    status: str
    reason: str | None
    hint: str | None
    artifact_path: str | None
    next_action_hint: str | None


@dataclass(frozen=True)
class AutoDrilldownPolicyView:
    enabled: bool
    provider: str
    max_per_run: int
    used_this_run: int
    successful_this_run: int
    failed_this_run: int
    skipped_this_run: int
    budget_exhausted: bool | None


@dataclass(frozen=True)
class LLMPolicyView:
    auto_drilldown: AutoDrilldownPolicyView | None


@dataclass(frozen=True)
class ProviderExecutionBranchView:
    enabled: bool | None
    eligible: int | None
    provider: str | None
    max_per_run: int | None
    attempted: int
    succeeded: int
    failed: int
    skipped: int
    unattempted: int | None
    budget_limited: int | None
    notes: str | None


@dataclass(frozen=True)
class ProviderExecutionView:
    auto_drilldown: ProviderExecutionBranchView | None
    review_enrichment: ProviderExecutionBranchView | None


@dataclass(frozen=True)
class ClusterView:
    label: str
    context: str
    cluster_class: str
    cluster_role: str
    baseline_cohort: str
    node_count: int
    control_plane_version: str
    health_rating: str
    warnings: int
    non_running_pods: int
    baseline_policy_path: str
    missing_evidence: tuple[str, ...]
    latest_run_timestamp: str
    top_trigger_reason: str | None
    drilldown_available: bool
    drilldown_timestamp: str | None
    snapshot_path: str | None
    assessment_path: str | None
    drilldown_path: str | None


@dataclass(frozen=True)
class ProposalView:
    proposal_id: str
    target: str
    status: str
    confidence: str
    rationale: str
    expected_benefit: str
    source_run_id: str
    latest_note: str | None
    artifact_path: str | None
    review_path: str | None
    lifecycle_history: tuple[tuple[str, str, str | None], ...]


@dataclass(frozen=True)
class DrilldownCoverageEntry:
    label: str
    context: str
    available: bool
    timestamp: str | None
    artifact_path: str | None


@dataclass(frozen=True)
class DrilldownAvailabilityView:
    total_clusters: int
    available: int
    missing: int
    missing_clusters: tuple[str, ...]
    coverage: tuple[DrilldownCoverageEntry, ...]


@dataclass(frozen=True)
class NotificationView:
    kind: str
    summary: str
    timestamp: str
    run_id: str | None
    cluster_label: str | None
    context: str | None
    details: tuple[tuple[str, str], ...]
    artifact_path: str | None


@dataclass(frozen=True)
class ExternalAnalysisView:
    tool_name: str
    cluster_label: str | None
    status: str
    summary: str | None
    findings: tuple[str, ...]
    suggested_next_checks: tuple[str, ...]
    timestamp: str
    artifact_path: str | None


@dataclass(frozen=True)
class AutoDrilldownInterpretationView:
    adapter: str
    status: str
    summary: str | None
    timestamp: str
    artifact_path: str | None
    provider: str | None
    duration_ms: int | None
    payload: Mapping[str, object] | None
    error_summary: str | None
    skip_reason: str | None


@dataclass(frozen=True)
class ReviewEnrichmentStatusView:
    status: str
    reason: str | None
    provider: str | None
    policy_enabled: bool
    provider_configured: bool
    adapter_available: bool | None
    run_enabled: bool | None = None
    run_provider: str | None = None


@dataclass(frozen=True)
class ReviewEnrichmentView:
    status: str
    provider: str | None
    timestamp: str | None
    summary: str | None
    triage_order: tuple[str, ...]
    top_concerns: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    next_checks: tuple[str, ...]
    focus_notes: tuple[str, ...]
    artifact_path: str | None
    error_summary: str | None
    skip_reason: str | None


@dataclass(frozen=True)
class DiagnosticPackReviewView:
    timestamp: str | None
    summary: str | None
    major_disagreements: tuple[str, ...]
    missing_checks: tuple[str, ...]
    ranking_issues: tuple[str, ...]
    generic_checks: tuple[str, ...]
    recommended_next_actions: tuple[str, ...]
    drift_misprioritized: bool
    confidence: str | None
    provider_status: str | None
    provider_summary: str | None
    provider_error_summary: str | None
    provider_skip_reason: str | None
    provider_review: Mapping[str, object] | None
    artifact_path: str | None


@dataclass(frozen=True)
class DiagnosticPackView:
    path: str | None
    timestamp: str | None
    label: str | None
    review_bundle_path: str | None
    review_input_14b_path: str | None


@dataclass(frozen=True)
class AlertmanagerCompactView:
    """View model for Alertmanager compact context - run-scoped snapshot of alerts."""
    status: str
    alert_count: int
    severity_counts: tuple[tuple[str, int], ...]
    state_counts: tuple[tuple[str, int], ...]
    top_alert_names: tuple[str, ...]
    affected_namespaces: tuple[str, ...]
    affected_clusters: tuple[str, ...]
    affected_services: tuple[str, ...]
    truncated: bool
    captured_at: str


@dataclass(frozen=True)
class AlertmanagerProvenanceView:
    matched_dimensions: tuple[str, ...]
    matched_values: dict[str, tuple[str, ...]]
    applied_bonus: int
    base_bonus: int = 0
    severity_summary: dict[str, int] | None = None
    signal_status: str | None = None


@dataclass(frozen=True)
class AlertmanagerSourceView:
    """View model for a single Alertmanager source in the inventory."""
    source_id: str
    endpoint: str
    namespace: str | None
    name: str | None
    origin: str  # origin enum value as string
    state: str  # state enum value as string
    discovered_at: str | None
    verified_at: str | None
    last_check: str | None
    last_error: str | None
    verified_version: str | None
    confidence_hints: tuple[str, ...]
    # Deduplication provenance: all origins that contributed to this source
    merged_provenances: tuple[str, ...]  # list of origin enum values
    # Human-readable provenance for UI tooltip
    display_provenance: str  # e.g., "Alertmanager CRD, Prometheus Config, Service Heuristic"
    # Computed UI fields
    is_manual: bool
    is_tracking: bool  # auto-tracked or manual
    can_disable: bool  # can be disabled from auto-tracking
    can_promote: bool  # can be promoted to manual
    display_origin: str  # human-readable origin
    display_state: str  # human-readable state with color hint
    provenance_summary: str  # short provenance string for UI


@dataclass(frozen=True)
class AlertmanagerSourcesView:
    """View model for the full Alertmanager source inventory."""
    sources: tuple[AlertmanagerSourceView, ...]
    total_count: int
    tracked_count: int  # auto-tracked + manual
    manual_count: int
    degraded_count: int
    missing_count: int
    discovery_timestamp: str | None
    cluster_context: str | None


@dataclass(frozen=True)
class NextCheckCandidateView:
    candidate_id: str | None
    priority_label: str | None
    description: str
    target_cluster: str | None
    source_reason: str | None
    expected_signal: str | None
    suggested_command_family: str | None
    safe_to_automate: bool
    requires_operator_approval: bool
    risk_level: str
    estimated_cost: str
    confidence: str
    gating_reason: str | None
    duplicate_of_existing_evidence: bool
    duplicate_evidence_description: str | None
    approval_status: str | None
    approval_artifact_path: str | None
    approval_timestamp: str | None
    candidate_index: int | None
    normalization_reason: str | None
    safety_reason: str | None
    approval_reason: str | None
    duplicate_reason: str | None
    blocking_reason: str | None
    approval_state: str | None
    execution_state: str | None
    outcome_status: str | None
    latest_artifact_path: str | None
    latest_timestamp: str | None
    priority_rationale: str | None
    ranking_reason: str | None
    alertmanager_provenance: AlertmanagerProvenanceView | None = None


@dataclass(frozen=True)
class NextCheckOrphanedApprovalView:
    approval_status: str | None
    candidate_id: str | None
    candidate_index: int | None
    candidate_description: str | None
    target_cluster: str | None
    plan_artifact_path: str | None
    approval_artifact_path: str | None
    approval_timestamp: str | None


@dataclass(frozen=True)
class NextCheckOutcomeCountView:
    status: str
    count: int


@dataclass(frozen=True)
class NextCheckPlanView:
    status: str
    summary: str | None
    artifact_path: str | None
    review_path: str | None
    enrichment_artifact_path: str | None
    candidate_count: int
    candidates: tuple[NextCheckCandidateView, ...]
    orphaned_approvals: tuple[NextCheckOrphanedApprovalView, ...]
    outcome_counts: tuple[NextCheckOutcomeCountView, ...]
    orphaned_approval_count: int


@dataclass(frozen=True)
class NextCheckExecutionHistoryEntryView:
    timestamp: str
    cluster_label: str | None
    candidate_description: str | None
    command_family: str | None
    status: str
    duration_ms: int | None
    artifact_path: str | None
    timed_out: bool | None
    stdout_truncated: bool | None
    stderr_truncated: bool | None
    output_bytes_captured: int | None
    pack_refresh_status: str | None = None
    pack_refresh_warning: str | None = None
    failure_class: str | None = None
    failure_summary: str | None = None
    suggested_next_operator_move: str | None = None
    result_class: str | None = None
    result_summary: str | None = None
    usefulness_class: str | None = None
    usefulness_summary: str | None = None
    # Provenance fields for traceability
    candidate_id: str | None = None
    candidate_index: int | None = None


@dataclass(frozen=True)
class NextCheckQueueItemView:
    candidate_id: str | None
    candidate_index: int | None
    description: str
    target_cluster: str | None
    priority_label: str | None
    suggested_command_family: str | None
    safe_to_automate: bool
    requires_operator_approval: bool
    approval_state: str | None
    execution_state: str | None
    outcome_status: str | None
    latest_artifact_path: str | None
    queue_status: str
    source_reason: str | None
    source_type: str | None
    expected_signal: str | None
    normalization_reason: str | None
    safety_reason: str | None
    approval_reason: str | None
    duplicate_reason: str | None
    blocking_reason: str | None
    target_context: str | None
    command_preview: str | None
    plan_artifact_path: str | None
    failure_class: str | None = None
    failure_summary: str | None = None
    suggested_next_operator_move: str | None = None
    result_class: str | None = None
    result_summary: str | None = None
    workstream: str | None = None
    alertmanager_provenance: AlertmanagerProvenanceView | None = None


@dataclass(frozen=True)
class NextCheckQueueCandidateAccountingView:
    generated: int
    safe: int
    approval_needed: int
    duplicate: int
    completed: int
    stale_orphaned: int
    orphaned_approvals: int


@dataclass(frozen=True)
class NextCheckQueueClusterStateView:
    degraded_cluster_count: int
    degraded_cluster_labels: tuple[str, ...]
    deterministic_next_check_count: int
    deterministic_cluster_count: int
    drilldown_ready_count: int


@dataclass(frozen=True)
class NextCheckQueueExplanationView:
    status: str
    reason: str | None
    hint: str | None
    planner_artifact_path: str | None
    cluster_state: NextCheckQueueClusterStateView
    candidate_accounting: NextCheckQueueCandidateAccountingView
    deterministic_next_checks_available: bool
    recommended_next_actions: tuple[str, ...]


@dataclass(frozen=True)
class DeterministicNextCheckSummaryView:
    description: str
    owner: str
    method: str
    evidence_needed: tuple[str, ...]
    workstream: str
    urgency: str
    is_primary_triage: bool
    why_now: str
    priority_score: int | None = None


@dataclass(frozen=True)
class DeterministicNextCheckClusterView:
    label: str
    context: str
    top_problem: str | None
    deterministic_next_check_count: int
    deterministic_next_check_summaries: tuple[DeterministicNextCheckSummaryView, ...]
    drilldown_available: bool
    assessment_artifact_path: str | None
    drilldown_artifact_path: str | None


@dataclass(frozen=True)
class DeterministicNextChecksView:
    cluster_count: int
    total_next_check_count: int
    clusters: tuple[DeterministicNextCheckClusterView, ...]


@dataclass(frozen=True)
class ExternalAnalysisSummary:
    count: int
    status_counts: tuple[tuple[str, int], ...]
    artifacts: tuple[ExternalAnalysisView, ...]


@dataclass(frozen=True)
class FindingsView:
    label: str | None
    context: str | None
    trigger_reasons: tuple[str, ...]
    warning_events: int
    non_running_pods: int
    summary: tuple[tuple[str, str], ...]
    rollout_status: tuple[str, ...]
    pattern_details: tuple[tuple[str, str], ...]
    artifact_path: str | None = None


@dataclass(frozen=True)
class AssessmentFindingView:
    description: str
    layer: str
    supporting_signals: tuple[str, ...]


@dataclass(frozen=True)
class AssessmentHypothesisView:
    description: str
    confidence: str
    probable_layer: str
    what_would_falsify: str


@dataclass(frozen=True)
class AssessmentNextCheckView:
    description: str
    owner: str
    method: str
    evidence_needed: tuple[str, ...]


@dataclass(frozen=True)
class RecommendedActionView:
    action_type: str
    description: str
    references: tuple[str, ...]
    safety_level: str


@dataclass(frozen=True)
class AssessmentView:
    cluster_label: str
    context: str
    timestamp: str
    health_rating: str
    missing_evidence: tuple[str, ...]
    findings: tuple[AssessmentFindingView, ...]
    hypotheses: tuple[AssessmentHypothesisView, ...]
    next_checks: tuple[AssessmentNextCheckView, ...]
    recommended_action: RecommendedActionView | None
    probable_layer: str | None
    overall_confidence: str | None
    artifact_path: str | None
    snapshot_path: str | None


@dataclass(frozen=True)
class FleetStatusSummary:
    rating_counts: tuple[tuple[str, int], ...]
    degraded_clusters: tuple[str, ...]


@dataclass(frozen=True)
class ProposalStatusSummary:
    status_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class UIIndexContext:
    run: RunView
    clusters: tuple[ClusterView, ...]
    proposals: tuple[ProposalView, ...]
    latest_findings: FindingsView | None
    latest_assessment: AssessmentView | None
    fleet_status: FleetStatusSummary
    proposal_status_summary: ProposalStatusSummary
    drilldown_availability: DrilldownAvailabilityView
    notification_history: tuple[NotificationView, ...]
    external_analysis: ExternalAnalysisSummary
    auto_drilldown_interpretations: Mapping[str, AutoDrilldownInterpretationView]
    llm_activity: LLMActivityView
    review_enrichment: ReviewEnrichmentView | None
    review_enrichment_status: ReviewEnrichmentStatusView | None
    provider_execution: ProviderExecutionView | None
    next_check_plan: NextCheckPlanView | None
    planner_availability: PlannerAvailabilityView | None
    diagnostic_pack: DiagnosticPackView | None
    next_check_queue: tuple[NextCheckQueueItemView, ...]
    alertmanager_compact: AlertmanagerCompactView | None
    alertmanager_sources: AlertmanagerSourcesView | None


def load_ui_index(directory: Path) -> Mapping[str, object]:
    path = directory / "ui-index.json"
    text = path.read_text(encoding="utf-8")
    return cast(Mapping[str, object], json.loads(text))


def build_ui_context(index: Mapping[str, object]) -> UIIndexContext:
    run_data = index.get("run") or {}
    llm_activity = _build_llm_activity(run_data.get("llm_activity"))
    review_enrichment = _build_review_enrichment_view(run_data.get("review_enrichment"))
    review_enrichment_status = _build_review_enrichment_status_view(
        run_data.get("review_enrichment_status")
    )
    next_check_plan = _build_next_check_plan_view(run_data.get("next_check_plan"))
    planner_availability = _build_planner_availability_view(run_data.get("planner_availability"))
    queue_explanation = _build_queue_explanation_view(run_data.get("next_check_queue_explanation"))
    run = RunView(
        run_id=_coerce_str(run_data.get("run_id")),
        run_label=_coerce_str(run_data.get("run_label")),
        timestamp=_coerce_str(run_data.get("timestamp")),
        collector_version=_coerce_str(run_data.get("collector_version")),
        cluster_count=_coerce_int(run_data.get("cluster_count")),
        drilldown_count=_coerce_int(run_data.get("drilldown_count")),
        proposal_count=_coerce_int(run_data.get("proposal_count")),
        external_analysis_count=_coerce_int(run_data.get("external_analysis_count")),
        notification_count=_coerce_int(run_data.get("notification_count")),
        scheduler_interval_seconds=_coerce_optional_int(run_data.get("scheduler_interval_seconds")),
        run_stats=_build_run_stats_view(index.get("run_stats")),
        llm_stats=_build_llm_stats_view(run_data.get("llm_stats")),
        historical_llm_stats=_build_optional_llm_stats_view(run_data.get("historical_llm_stats")),
        llm_activity=llm_activity,
        llm_policy=_build_llm_policy_view(run_data.get("llm_policy")),
        review_enrichment=review_enrichment,
        review_enrichment_status=review_enrichment_status,
        provider_execution=_build_provider_execution_view(run_data.get("provider_execution")),
        next_check_plan=next_check_plan,
        planner_availability=planner_availability,
        next_check_execution_history=_build_execution_history_view(
            run_data.get("next_check_execution_history")
        ),
        next_check_queue=_build_next_check_queue_view(run_data.get("next_check_queue")),
        next_check_queue_explanation=queue_explanation,
        deterministic_next_checks=_build_deterministic_next_checks_view(
            run_data.get("deterministic_next_checks")
        ),
        diagnostic_pack_review=_build_diagnostic_pack_review_view(
            run_data.get("diagnostic_pack_review")
        ),
        diagnostic_pack=_build_diagnostic_pack_view(run_data.get("diagnostic_pack")),
    )
    raw_clusters = index.get("clusters")
    if not isinstance(raw_clusters, Sequence):
        raw_clusters = ()
    clusters = tuple(
        _build_cluster_view(cluster)
        for cluster in sorted(
            (entry for entry in raw_clusters if isinstance(entry, Mapping)),
            key=lambda item: _coerce_str(item.get("label")),
        )
    )
    proposals = tuple(_build_proposal_view(proposal) for proposal in index.get("proposals") or [])
    latest_findings = _build_findings(index.get("latest_drilldown"))
    latest_assessment = _build_assessment_view(index.get("latest_assessment"))
    fleet_status = _build_fleet_status(index.get("fleet_status"))
    proposal_status_summary = _build_proposal_status_summary(index.get("proposal_status_summary"))
    drilldown_availability = _build_drilldown_availability(index.get("drilldown_availability"))
    notification_history = _build_notification_history(index.get("notification_history"))
    external_analysis = _build_external_analysis(index.get("external_analysis"))
    auto_drilldown_interpretations = _build_auto_drilldown_interpretations(
        index.get("auto_drilldown_interpretations")
    )
    alertmanager_compact = _build_alertmanager_compact_view(run_data.get("alertmanager_compact"))
    alertmanager_sources = _build_alertmanager_sources_view(run_data.get("alertmanager_sources"))
    return UIIndexContext(
        run=run,
        clusters=clusters,
        proposals=proposals,
        latest_findings=latest_findings,
        latest_assessment=latest_assessment,
        fleet_status=fleet_status,
        proposal_status_summary=proposal_status_summary,
        drilldown_availability=drilldown_availability,
        notification_history=notification_history,
        external_analysis=external_analysis,
        auto_drilldown_interpretations=auto_drilldown_interpretations,
        llm_activity=llm_activity,
        review_enrichment=review_enrichment,
        review_enrichment_status=review_enrichment_status,
        provider_execution=run.provider_execution,
        next_check_plan=run.next_check_plan,
        planner_availability=run.planner_availability,
        diagnostic_pack=run.diagnostic_pack,
        next_check_queue=run.next_check_queue,
        alertmanager_compact=alertmanager_compact,
        alertmanager_sources=alertmanager_sources,
    )


def _build_run_stats_view(raw: object | None) -> RunStatsView:
    if not isinstance(raw, Mapping):
        return RunStatsView()
    return RunStatsView(
        last_run_duration_seconds=_coerce_optional_int(raw.get("last_run_duration_seconds")),
        total_runs=_coerce_int(raw.get("total_runs")),
        p50_run_duration_seconds=_coerce_optional_int(raw.get("p50_run_duration_seconds")),
        p95_run_duration_seconds=_coerce_optional_int(raw.get("p95_run_duration_seconds")),
        p99_run_duration_seconds=_coerce_optional_int(raw.get("p99_run_duration_seconds")),
    )


def _build_llm_stats_view(raw: object | None) -> LLMStatsView:
    if not isinstance(raw, Mapping):
        return LLMStatsView(
            total_calls=0,
            successful_calls=0,
            failed_calls=0,
            last_call_timestamp=None,
            p50_latency_ms=None,
            p95_latency_ms=None,
            p99_latency_ms=None,
            provider_breakdown=(),
        )
    breakdown_raw = raw.get("providerBreakdown") or ()
    breakdown = tuple(
        ProviderBreakdownEntry(
            provider=_coerce_str(entry.get("provider")),
            calls=_coerce_int(entry.get("calls")),
            failed_calls=_coerce_int(entry.get("failedCalls")),
        )
        for entry in breakdown_raw
        if isinstance(entry, Mapping)
    )
    scope_value = _coerce_optional_str(raw.get("scope")) or "current_run"
    return LLMStatsView(
        total_calls=_coerce_int(raw.get("totalCalls")),
        successful_calls=_coerce_int(raw.get("successfulCalls")),
        failed_calls=_coerce_int(raw.get("failedCalls")),
        last_call_timestamp=_coerce_optional_str(raw.get("lastCallTimestamp")),
        p50_latency_ms=_coerce_optional_int(raw.get("p50LatencyMs")),
        p95_latency_ms=_coerce_optional_int(raw.get("p95LatencyMs")),
        p99_latency_ms=_coerce_optional_int(raw.get("p99LatencyMs")),
        provider_breakdown=breakdown,
        scope=scope_value,
    )


def _build_optional_llm_stats_view(raw: object | None) -> LLMStatsView | None:
    if not isinstance(raw, Mapping):
        return None
    return _build_llm_stats_view(raw)


def _build_cluster_view(cluster: Mapping[str, object]) -> ClusterView:
    artifacts = cluster.get("artifact_paths")
    snapshot = _coerce_optional_str(_value_from_mapping(artifacts, "snapshot"))
    assessment = _coerce_optional_str(_value_from_mapping(artifacts, "assessment"))
    drilldown = _coerce_optional_str(_value_from_mapping(artifacts, "drilldown"))
    return ClusterView(
        label=_coerce_str(cluster.get("label")),
        context=_coerce_str(cluster.get("context")),
        cluster_class=_coerce_str(cluster.get("cluster_class")),
        cluster_role=_coerce_str(cluster.get("cluster_role")),
        baseline_cohort=_coerce_str(cluster.get("baseline_cohort")),
        node_count=_coerce_int(cluster.get("node_count")),
        control_plane_version=_coerce_str(cluster.get("control_plane_version")),
        health_rating=_coerce_str(cluster.get("health_rating")),
        warnings=_coerce_int(cluster.get("warnings")),
        non_running_pods=_coerce_int(cluster.get("non_running_pods")),
        baseline_policy_path=_coerce_str(cluster.get("baseline_policy_path")),
        missing_evidence=_coerce_sequence(cluster.get("missing_evidence")),
        latest_run_timestamp=_coerce_str(cluster.get("latest_run_timestamp")),
        top_trigger_reason=_coerce_optional_str(cluster.get("top_trigger_reason")),
        drilldown_available=bool(cluster.get("drilldown_available")),
        drilldown_timestamp=_coerce_optional_str(cluster.get("drilldown_timestamp")),
        snapshot_path=snapshot,
        assessment_path=assessment,
        drilldown_path=drilldown,
    )


def _build_proposal_view(proposal: Mapping[str, object]) -> ProposalView:
    history = proposal.get("lifecycle_history") or []
    latest_entry = history[-1] if isinstance(history, Sequence) and history else None
    note = _coerce_str(latest_entry.get("note")) if latest_entry and isinstance(latest_entry, Mapping) and latest_entry.get("note") else None
    if note == "-":
        note = None
    lifecycle_history = _build_lifecycle_history(history)
    return ProposalView(
        proposal_id=_coerce_str(proposal.get("proposal_id")),
        target=_coerce_str(proposal.get("target")),
        status=_coerce_str(proposal.get("status")),
        confidence=_coerce_str(proposal.get("confidence")),
        rationale=_coerce_str(proposal.get("rationale")),
        expected_benefit=_coerce_str(proposal.get("expected_benefit")),
        source_run_id=_coerce_str(proposal.get("source_run_id")),
        latest_note=note,
        artifact_path=_coerce_optional_str(proposal.get("artifact_path")),
        review_path=_coerce_optional_str(proposal.get("review_artifact")),
        lifecycle_history=lifecycle_history,
    )


def _build_findings(raw: object | None) -> FindingsView | None:
    if not isinstance(raw, Mapping):
        return None
    return FindingsView(
        label=_coerce_optional_str(raw.get("label")),
        context=_coerce_optional_str(raw.get("context")),
        trigger_reasons=_coerce_sequence(raw.get("trigger_reasons")),
        warning_events=_coerce_int(raw.get("warning_events")),
        non_running_pods=_coerce_int(raw.get("non_running_pods")),
        summary=_serialize_map(raw.get("summary")),
        rollout_status=_coerce_sequence(raw.get("rollout_status")),
        pattern_details=_serialize_map(raw.get("pattern_details")),
        artifact_path=_coerce_optional_str(raw.get("artifact_path")),
    )


def _coerce_str(value: object | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_str_tuple(value: object | None) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(str(item) for item in value)
    if value is None:
        return ()
    return (str(value),)


def _coerce_int(value: object | None) -> int:
    if value is None:
        return 0
    if isinstance(value, SupportsInt):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _coerce_optional_int(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, SupportsInt):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _coerce_optional_bool(value: object | None) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in ("true", "1", "yes", "on"):
        return True
    if normalized in ("false", "0", "no", "off"):
        return False
    return None


def _coerce_sequence(value: object | None) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(str(item) for item in value)
    if value is None:
        return ()
    return (str(value),)


def _serialize_map(value: object | None) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, Mapping):
        return ()
    results: list[tuple[str, str]] = []
    for key, entry in value.items():
        results.append((str(key), _stringify(entry)))
    return tuple(results)


def _build_fleet_status(raw: object | None) -> FleetStatusSummary:
    if not isinstance(raw, Mapping):
        return FleetStatusSummary(rating_counts=(), degraded_clusters=())
    counts_raw = raw.get("rating_counts") or ()
    rating_counts = tuple(
        (_coerce_str(entry.get("rating")), _coerce_int(entry.get("count")))
        for entry in counts_raw
        if isinstance(entry, Mapping)
    )
    degraded = _coerce_sequence(raw.get("degraded_clusters"))
    return FleetStatusSummary(rating_counts=rating_counts, degraded_clusters=degraded)


def _build_proposal_status_summary(raw: object | None) -> ProposalStatusSummary:
    if not isinstance(raw, Mapping):
        return ProposalStatusSummary(status_counts=())
    counts_raw = raw.get("status_counts") or ()
    status_counts = tuple(
        (_coerce_str(entry.get("status")), _coerce_int(entry.get("count")))
        for entry in counts_raw
        if isinstance(entry, Mapping)
    )
    return ProposalStatusSummary(status_counts=status_counts)


def _build_lifecycle_history(raw: object | None) -> tuple[tuple[str, str, str | None], ...]:
    entries: list[tuple[str, str, str | None]] = []
    if not isinstance(raw, Sequence):
        return ()
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        status = _coerce_str(entry.get("status"))
        timestamp = _coerce_str(entry.get("timestamp"))
        note = _coerce_optional_str(entry.get("note"))
        if note == "-":
            note = None
        entries.append((status, timestamp, note))
    return tuple(entries)


def _value_from_mapping(mapping: object | None, key: str) -> object | None:
    if isinstance(mapping, Mapping):
        return mapping.get(key)
    return None


def _stringify(value: object | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def _build_drilldown_availability(raw: object | None) -> DrilldownAvailabilityView:
    if not isinstance(raw, Mapping):
        return DrilldownAvailabilityView(
            total_clusters=0,
            available=0,
            missing=0,
            missing_clusters=(),
            coverage=(),
        )
    coverage_raw = raw.get("coverage") or ()
    coverage = tuple(
        _build_drilldown_coverage(entry)
        for entry in coverage_raw
        if isinstance(entry, Mapping)
    )
    return DrilldownAvailabilityView(
        total_clusters=_coerce_int(raw.get("total_clusters")),
        available=_coerce_int(raw.get("available")),
        missing=_coerce_int(raw.get("missing")),
        missing_clusters=_coerce_sequence(raw.get("missing_clusters")),
        coverage=coverage,
    )


def _build_drilldown_coverage(raw: Mapping[str, object]) -> DrilldownCoverageEntry:
    return DrilldownCoverageEntry(
        label=_coerce_str(raw.get("label")),
        context=_coerce_str(raw.get("context")),
        available=bool(raw.get("available")),
        timestamp=_coerce_optional_str(raw.get("timestamp")),
        artifact_path=_coerce_optional_str(raw.get("artifact_path")),
    )


def _build_notification_history(raw: object | None) -> tuple[NotificationView, ...]:
    if not isinstance(raw, Sequence):
        return ()
    entries: list[NotificationView] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        entries.append(
            NotificationView(
                kind=_coerce_str(entry.get("kind")),
                summary=_coerce_str(entry.get("summary")),
                timestamp=_coerce_str(entry.get("timestamp")),
                run_id=_coerce_optional_str(entry.get("run_id")),
                cluster_label=_coerce_optional_str(entry.get("cluster_label")),
                context=_coerce_optional_str(entry.get("context")),
                details=_build_notification_details(entry.get("details")),
                artifact_path=_coerce_optional_str(entry.get("artifact_path")),
            )
        )
    return tuple(entries)


def _build_notification_details(raw: object | None) -> tuple[tuple[str, str], ...]:
    if not isinstance(raw, Sequence):
        return ()
    details: list[tuple[str, str]] = []
    for detail in raw:
        if not isinstance(detail, Mapping):
            continue
        label = _coerce_str(detail.get("label"))
        value = _coerce_str(detail.get("value"))
        details.append((label, value))
    return tuple(details)


def _build_external_analysis(raw: object | None) -> ExternalAnalysisSummary:
    if not isinstance(raw, Mapping):
        return ExternalAnalysisSummary(count=0, status_counts=(), artifacts=())
    status_counts_raw = raw.get("status_counts") or ()
    status_counts = tuple(
        (_coerce_str(entry.get("status")), _coerce_int(entry.get("count")))
        for entry in status_counts_raw
        if isinstance(entry, Mapping)
    )
    artifacts_raw = raw.get("artifacts") or ()
    artifacts = tuple(
        _build_external_analysis_view(entry)
        for entry in artifacts_raw
        if isinstance(entry, Mapping)
    )
    return ExternalAnalysisSummary(
        count=_coerce_int(raw.get("count")),
        status_counts=status_counts,
        artifacts=artifacts,
    )


def _build_llm_activity(raw: object | None) -> LLMActivityView:
    if not isinstance(raw, Mapping):
        return LLMActivityView(
            entries=(),
            summary=LLMActivitySummaryView(retained_entries=0),
        )
    entries_raw = raw.get("entries") or ()
    entries = tuple(
        _build_llm_activity_entry(entry)
        for entry in entries_raw
        if isinstance(entry, Mapping)
    )
    summary = _build_llm_activity_summary(raw.get("summary"))
    return LLMActivityView(entries=entries, summary=summary)


def _build_llm_policy_view(raw: object | None) -> LLMPolicyView | None:
    if not isinstance(raw, Mapping):
        return None
    return LLMPolicyView(auto_drilldown=_build_auto_drilldown_policy_view(raw.get("auto_drilldown")))


def _build_auto_drilldown_policy_view(raw: object | None) -> AutoDrilldownPolicyView | None:
    if not isinstance(raw, Mapping):
        return None
    return AutoDrilldownPolicyView(
        enabled=bool(raw.get("enabled")),
        provider=_coerce_str(raw.get("provider")),
        max_per_run=_coerce_int(raw.get("maxPerRun")),
        used_this_run=_coerce_int(raw.get("usedThisRun")),
        successful_this_run=_coerce_int(raw.get("successfulThisRun")),
        failed_this_run=_coerce_int(raw.get("failedThisRun")),
        skipped_this_run=_coerce_int(raw.get("skippedThisRun")),
        budget_exhausted=_coerce_optional_bool(raw.get("budgetExhausted")),
    )


def _build_provider_execution_view(raw: object | None) -> ProviderExecutionView | None:
    if not isinstance(raw, Mapping):
        return None
    return ProviderExecutionView(
        auto_drilldown=_build_execution_branch_view(raw.get("auto_drilldown")),
        review_enrichment=_build_execution_branch_view(raw.get("review_enrichment")),
    )


def _build_execution_branch_view(raw: object | None) -> ProviderExecutionBranchView | None:
    if not isinstance(raw, Mapping):
        return None
    return ProviderExecutionBranchView(
        enabled=_coerce_optional_bool(raw.get("enabled")),
        eligible=_coerce_optional_int(raw.get("eligible")),
        provider=_coerce_optional_str(raw.get("provider")),
        max_per_run=_coerce_optional_int(raw.get("maxPerRun")),
        attempted=_coerce_int(raw.get("attempted")),
        succeeded=_coerce_int(raw.get("succeeded")),
        failed=_coerce_int(raw.get("failed")),
        skipped=_coerce_int(raw.get("skipped")),
        unattempted=_coerce_optional_int(raw.get("unattempted")),
        budget_limited=_coerce_optional_int(raw.get("budgetLimited")),
        notes=_coerce_optional_str(raw.get("notes")),
    )


def _build_llm_activity_entry(raw: Mapping[str, object]) -> LLMActivityEntryView:
    return LLMActivityEntryView(
        timestamp=_coerce_optional_str(raw.get("timestamp")),
        run_id=_coerce_optional_str(raw.get("run_id")),
        run_label=_coerce_optional_str(raw.get("run_label")),
        cluster_label=_coerce_optional_str(raw.get("cluster_label")),
        tool_name=_coerce_optional_str(raw.get("tool_name")),
        provider=_coerce_optional_str(raw.get("provider")),
        purpose=_coerce_optional_str(raw.get("purpose")),
        status=_coerce_optional_str(raw.get("status")),
        latency_ms=_coerce_optional_int(raw.get("latency_ms")),
        artifact_path=_coerce_optional_str(raw.get("artifact_path")),
        summary=_coerce_optional_str(raw.get("summary")),
        error_summary=_coerce_optional_str(raw.get("error_summary")),
        skip_reason=_coerce_optional_str(raw.get("skip_reason")),
    )


def _build_llm_activity_summary(raw: object | None) -> LLMActivitySummaryView:
    if not isinstance(raw, Mapping):
        return LLMActivitySummaryView(retained_entries=0)
    return LLMActivitySummaryView(retained_entries=_coerce_int(raw.get("retained_entries")))


def _build_auto_drilldown_interpretations(
    raw: object | None,
) -> Mapping[str, AutoDrilldownInterpretationView]:
    if not isinstance(raw, Mapping):
        return {}
    interpretations: dict[str, AutoDrilldownInterpretationView] = {}
    for label, entry in raw.items():
        if not isinstance(label, str) or not isinstance(entry, Mapping):
            continue
        interpretations[label] = AutoDrilldownInterpretationView(
            adapter=_coerce_str(entry.get("adapter")),
            status=_coerce_str(entry.get("status")),
            summary=_coerce_optional_str(entry.get("summary")),
            timestamp=_coerce_str(entry.get("timestamp")),
            artifact_path=_coerce_optional_str(entry.get("artifact_path")),
            provider=_coerce_optional_str(entry.get("provider")),
            duration_ms=_coerce_optional_int(entry.get("duration_ms")),
            payload=entry.get("payload") if isinstance(entry.get("payload"), Mapping) else None,
            error_summary=_coerce_optional_str(entry.get("error_summary")),
            skip_reason=_coerce_optional_str(entry.get("skip_reason")),
        )
    return interpretations


def _build_review_enrichment_view(raw: object | None) -> ReviewEnrichmentView | None:
    if not isinstance(raw, Mapping):
        return None
    triage = raw.get("triageOrder") or raw.get("triage_order")
    concerns = raw.get("topConcerns") or raw.get("top_concerns")
    gaps = raw.get("evidenceGaps") or raw.get("evidence_gaps")
    checks = raw.get("nextChecks") or raw.get("next_checks")
    focus = raw.get("focusNotes") or raw.get("focus_notes")
    return ReviewEnrichmentView(
        status=_coerce_str(raw.get("status")),
        provider=_coerce_optional_str(raw.get("provider")),
        timestamp=_coerce_optional_str(raw.get("timestamp")),
        summary=_coerce_optional_str(raw.get("summary")),
        triage_order=_coerce_sequence(triage),
        top_concerns=_coerce_sequence(concerns),
        evidence_gaps=_coerce_sequence(gaps),
        next_checks=_coerce_sequence(checks),
        focus_notes=_coerce_sequence(focus),
        artifact_path=_coerce_optional_str(raw.get("artifactPath")),
        error_summary=_coerce_optional_str(raw.get("errorSummary")),
        skip_reason=_coerce_optional_str(raw.get("skipReason")),
    )


def _build_planner_availability_view(raw: object | None) -> PlannerAvailabilityView | None:
    if not isinstance(raw, Mapping):
        return None
    return PlannerAvailabilityView(
        status=_coerce_str(raw.get("status")),
        reason=_coerce_optional_str(raw.get("reason")),
        hint=_coerce_optional_str(raw.get("hint")),
        artifact_path=_coerce_optional_str(raw.get("artifactPath"))
        or _coerce_optional_str(raw.get("artifact_path")),
        next_action_hint=_coerce_optional_str(raw.get("nextActionHint"))
        or _coerce_optional_str(raw.get("next_action_hint")),
    )


def _build_diagnostic_pack_review_view(raw: object | None) -> DiagnosticPackReviewView | None:
    if not isinstance(raw, Mapping):
        return None
    major_disagreements = _coerce_sequence(raw.get("majorDisagreements") or raw.get("major_disagreements"))
    missing_checks = _coerce_sequence(raw.get("missingChecks") or raw.get("missing_checks"))
    ranking_issues = _coerce_sequence(raw.get("rankingIssues") or raw.get("ranking_issues"))
    generic_checks = _coerce_sequence(raw.get("genericChecks") or raw.get("generic_checks"))
    recommended_next_actions = _coerce_sequence(
        raw.get("recommendedNextActions") or raw.get("recommended_next_actions")
    )
    provider_review = raw.get("providerReview") or raw.get("provider_review")
    return DiagnosticPackReviewView(
        timestamp=_coerce_optional_str(raw.get("timestamp")),
        summary=_coerce_optional_str(raw.get("summary")),
        major_disagreements=major_disagreements,
        missing_checks=missing_checks,
        ranking_issues=ranking_issues,
        generic_checks=generic_checks,
        recommended_next_actions=recommended_next_actions,
        drift_misprioritized=bool(raw.get("driftMisprioritized") or raw.get("drift_misprioritized")),
        confidence=_coerce_optional_str(raw.get("confidence")),
        provider_status=_coerce_optional_str(raw.get("providerStatus") or raw.get("provider_status")),
        provider_summary=_coerce_optional_str(raw.get("providerSummary") or raw.get("provider_summary")),
        provider_error_summary=_coerce_optional_str(
            raw.get("providerErrorSummary") or raw.get("provider_error_summary")
        ),
        provider_skip_reason=_coerce_optional_str(
            raw.get("providerSkipReason") or raw.get("provider_skip_reason")
        ),
        provider_review=provider_review if isinstance(provider_review, Mapping) else None,
        artifact_path=_coerce_optional_str(raw.get("artifactPath") or raw.get("artifact_path")),
    )


def _build_next_check_plan_view(raw: object | None) -> NextCheckPlanView | None:
    if not isinstance(raw, Mapping):
        return None
    candidates_raw = raw.get("candidates") or ()
    candidates = tuple(
        _build_next_check_candidate_view(entry)
        for entry in candidates_raw
        if isinstance(entry, Mapping)
    )
    orphaned_raw = raw.get("orphanedApprovals") or ()
    orphaned = tuple(
        _build_orphaned_approval_view(entry)
        for entry in orphaned_raw
        if isinstance(entry, Mapping)
    )
    outcome_counts_raw = raw.get("outcomeCounts") or ()
    outcome_counts = tuple(
        _build_outcome_count_view(entry)
        for entry in outcome_counts_raw
        if isinstance(entry, Mapping)
    )
    orphaned_count = _coerce_int(raw.get("orphanedApprovalCount"))
    return NextCheckPlanView(
        status=_coerce_str(raw.get("status")),
        summary=_coerce_optional_str(raw.get("summary")),
        artifact_path=_coerce_optional_str(raw.get("artifactPath")),
        review_path=_coerce_optional_str(raw.get("reviewPath")),
        enrichment_artifact_path=_coerce_optional_str(raw.get("enrichmentArtifactPath")),
        candidate_count=_coerce_int(raw.get("candidateCount")),
        candidates=candidates,
        orphaned_approvals=orphaned,
        outcome_counts=outcome_counts,
        orphaned_approval_count=orphaned_count,
    )


def _build_execution_history_view(raw: object | None) -> tuple[NextCheckExecutionHistoryEntryView, ...]:
    if not isinstance(raw, Sequence):
        return ()
    entries: list[NextCheckExecutionHistoryEntryView] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        entries.append(
            NextCheckExecutionHistoryEntryView(
                timestamp=_coerce_str(entry.get("timestamp")),
                cluster_label=_coerce_optional_str(entry.get("clusterLabel")),
                candidate_description=_coerce_optional_str(entry.get("candidateDescription")),
                command_family=_coerce_optional_str(entry.get("commandFamily")),
                status=_coerce_str(entry.get("status")),
                duration_ms=_coerce_optional_int(entry.get("durationMs")),
                artifact_path=_coerce_optional_str(entry.get("artifactPath")),
                timed_out=_coerce_optional_bool(entry.get("timedOut")),
                stdout_truncated=_coerce_optional_bool(entry.get("stdoutTruncated")),
                stderr_truncated=_coerce_optional_bool(entry.get("stderrTruncated")),
                output_bytes_captured=_coerce_optional_int(entry.get("outputBytesCaptured")),
                pack_refresh_status=_coerce_optional_str(entry.get("packRefreshStatus")),
                pack_refresh_warning=_coerce_optional_str(entry.get("packRefreshWarning")),
                failure_class=_coerce_optional_str(entry.get("failureClass")),
                failure_summary=_coerce_optional_str(entry.get("failureSummary")),
                suggested_next_operator_move=_coerce_optional_str(entry.get("suggestedNextOperatorMove")),
                result_class=_coerce_optional_str(entry.get("resultClass")),
                result_summary=_coerce_optional_str(entry.get("resultSummary")),
                usefulness_class=_coerce_optional_str(entry.get("usefulnessClass")),
                usefulness_summary=_coerce_optional_str(entry.get("usefulnessSummary")),
                # Provenance fields for traceability
                candidate_id=_coerce_optional_str(entry.get("candidateId")),
                candidate_index=_coerce_optional_int(entry.get("candidateIndex")),
            )
        )
    return tuple(entries)


def _build_next_check_queue_view(raw: object | None) -> tuple[NextCheckQueueItemView, ...]:
    if not isinstance(raw, Sequence):
        return ()
    entries: list[NextCheckQueueItemView] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        provenance_raw = entry.get("alertmanagerProvenance") or entry.get("alertmanager_provenance")
        provenance = _build_alertmanager_provenance_view(provenance_raw)
        entries.append(
                NextCheckQueueItemView(
                    candidate_id=_coerce_optional_str(entry.get("candidateId")),
                    candidate_index=_coerce_optional_int(entry.get("candidateIndex")),
                    description=_coerce_str(entry.get("description")),
                    target_cluster=_coerce_optional_str(entry.get("targetCluster")),
                    priority_label=_coerce_optional_str(entry.get("priorityLabel")),
                    suggested_command_family=_coerce_optional_str(entry.get("suggestedCommandFamily")),
                    safe_to_automate=bool(entry.get("safeToAutomate")),
                    requires_operator_approval=bool(entry.get("requiresOperatorApproval")),
                    approval_state=_coerce_optional_str(entry.get("approvalState")),
                    execution_state=_coerce_optional_str(entry.get("executionState")),
                    outcome_status=_coerce_optional_str(entry.get("outcomeStatus")),
                    latest_artifact_path=_coerce_optional_str(entry.get("latestArtifactPath")),
                    source_reason=_coerce_optional_str(entry.get("sourceReason")),
                    source_type=_coerce_optional_str(entry.get("sourceType")),
                    expected_signal=_coerce_optional_str(entry.get("expectedSignal")),
                normalization_reason=_coerce_optional_str(entry.get("normalizationReason")),
                safety_reason=_coerce_optional_str(entry.get("safetyReason")),
                approval_reason=_coerce_optional_str(entry.get("approvalReason")),
                duplicate_reason=_coerce_optional_str(entry.get("duplicateReason")),
                blocking_reason=_coerce_optional_str(entry.get("blockingReason")),
                failure_class=_coerce_optional_str(entry.get("failureClass")),
                failure_summary=_coerce_optional_str(entry.get("failureSummary")),
                suggested_next_operator_move=_coerce_optional_str(entry.get("suggestedNextOperatorMove")),
                result_class=_coerce_optional_str(entry.get("resultClass")),
                result_summary=_coerce_optional_str(entry.get("resultSummary")),
                target_context=_coerce_optional_str(entry.get("targetContext")),
                command_preview=_coerce_optional_str(entry.get("commandPreview")),
                plan_artifact_path=_coerce_optional_str(entry.get("planArtifactPath")),
                queue_status=_coerce_str(entry.get("queueStatus")),
                workstream=_coerce_optional_str(entry.get("workstream")),
                alertmanager_provenance=provenance,
            )
        )
    return tuple(entries)


def _build_queue_cluster_state_view(raw: object | None) -> NextCheckQueueClusterStateView:
    if not isinstance(raw, Mapping):
        return NextCheckQueueClusterStateView(
            degraded_cluster_count=0,
            degraded_cluster_labels=(),
            deterministic_next_check_count=0,
            deterministic_cluster_count=0,
            drilldown_ready_count=0,
        )
    return NextCheckQueueClusterStateView(
        degraded_cluster_count=_coerce_int(raw.get("degradedClusterCount")),
        degraded_cluster_labels=_coerce_sequence(raw.get("degradedClusterLabels")),
        deterministic_next_check_count=_coerce_int(raw.get("deterministicNextCheckCount")),
        deterministic_cluster_count=_coerce_int(raw.get("deterministicClusterCount")),
        drilldown_ready_count=_coerce_int(raw.get("drilldownReadyCount")),
    )


def _build_queue_candidate_accounting_view(raw: object | None) -> NextCheckQueueCandidateAccountingView:
    if not isinstance(raw, Mapping):
        return NextCheckQueueCandidateAccountingView(
            generated=0,
            safe=0,
            approval_needed=0,
            duplicate=0,
            completed=0,
            stale_orphaned=0,
            orphaned_approvals=0,
        )
    return NextCheckQueueCandidateAccountingView(
        generated=_coerce_int(raw.get("generated")),
        safe=_coerce_int(raw.get("safe")),
        approval_needed=_coerce_int(raw.get("approvalNeeded")),
        duplicate=_coerce_int(raw.get("duplicate")),
        completed=_coerce_int(raw.get("completed")),
        stale_orphaned=_coerce_int(raw.get("staleOrphaned")),
        orphaned_approvals=_coerce_int(raw.get("orphanedApprovals")),
    )


def _build_queue_explanation_view(raw: object | None) -> NextCheckQueueExplanationView | None:
    if not isinstance(raw, Mapping):
        return None
    recommended_actions_raw = raw.get("recommendedNextActions") or ()
    recommended_actions = tuple(
        str(entry) for entry in recommended_actions_raw if isinstance(entry, str) and entry.strip()
    )
    return NextCheckQueueExplanationView(
        status=_coerce_str(raw.get("status")),
        reason=_coerce_optional_str(raw.get("reason")),
        hint=_coerce_optional_str(raw.get("hint")),
        planner_artifact_path=_coerce_optional_str(raw.get("plannerArtifactPath")),
        cluster_state=_build_queue_cluster_state_view(raw.get("clusterState")),
        candidate_accounting=_build_queue_candidate_accounting_view(raw.get("candidateAccounting")),
        deterministic_next_checks_available=bool(raw.get("deterministicNextChecksAvailable")),
        recommended_next_actions=recommended_actions,
    )


def _build_deterministic_next_checks_view(raw: object | None) -> DeterministicNextChecksView | None:
    if not isinstance(raw, Mapping):
        return None
    clusters_raw = raw.get("clusters") or ()
    clusters = tuple(
        _build_deterministic_next_check_cluster_view(entry)
        for entry in clusters_raw
        if isinstance(entry, Mapping)
    )
    return DeterministicNextChecksView(
        cluster_count=_coerce_int(raw.get("clusterCount")),
        total_next_check_count=_coerce_int(raw.get("totalNextCheckCount")),
        clusters=clusters,
    )


def _build_deterministic_next_check_cluster_view(raw: Mapping[str, object]) -> DeterministicNextCheckClusterView:
    summaries_raw = raw.get("deterministicNextCheckSummaries") or ()
    summaries = tuple(
        _build_deterministic_next_check_summary_view(entry)
        for entry in summaries_raw
        if isinstance(entry, Mapping)
    )
    return DeterministicNextCheckClusterView(
        label=_coerce_str(raw.get("label")),
        context=_coerce_str(raw.get("context")),
        top_problem=_coerce_optional_str(raw.get("topProblem")),
        deterministic_next_check_count=_coerce_int(raw.get("deterministicNextCheckCount")),
        deterministic_next_check_summaries=summaries,
        drilldown_available=bool(raw.get("drilldownAvailable")),
        assessment_artifact_path=_coerce_optional_str(raw.get("assessmentArtifactPath")),
        drilldown_artifact_path=_coerce_optional_str(raw.get("drilldownArtifactPath")),
    )


def _build_deterministic_next_check_summary_view(raw: Mapping[str, object]) -> DeterministicNextCheckSummaryView:
    return DeterministicNextCheckSummaryView(
        description=_coerce_str(raw.get("description")),
        owner=_coerce_str(raw.get("owner")),
        method=_coerce_str(raw.get("method")),
        evidence_needed=_coerce_sequence(raw.get("evidenceNeeded")),
        workstream=_coerce_str(raw.get("workstream")),
        urgency=_coerce_str(raw.get("urgency")),
        is_primary_triage=bool(raw.get("isPrimaryTriage")),
        why_now=_coerce_str(raw.get("whyNow")),
        priority_score=_coerce_optional_int(raw.get("priorityScore")),
    )


def _build_orphaned_approval_view(raw: Mapping[str, object]) -> NextCheckOrphanedApprovalView:
    return NextCheckOrphanedApprovalView(
        approval_status=_coerce_optional_str(raw.get("approvalStatus")),
        candidate_id=_coerce_optional_str(raw.get("candidateId")),
        candidate_index=_coerce_optional_int(raw.get("candidateIndex")),
        candidate_description=_coerce_optional_str(raw.get("candidateDescription")),
        target_cluster=_coerce_optional_str(raw.get("targetCluster")),
        plan_artifact_path=_coerce_optional_str(raw.get("planArtifactPath")),
        approval_artifact_path=_coerce_optional_str(raw.get("approvalArtifactPath")),
        approval_timestamp=_coerce_optional_str(raw.get("approvalTimestamp")),
    )


def _build_outcome_count_view(raw: Mapping[str, object]) -> NextCheckOutcomeCountView:
    return NextCheckOutcomeCountView(
        status=_coerce_str(raw.get("status")),
        count=_coerce_int(raw.get("count")),
    )


def _build_next_check_candidate_view(raw: Mapping[str, object]) -> NextCheckCandidateView:
    # Import here to avoid circular dependency at module level
    from ..health.ui import _derive_priority_rationale, _derive_ranking_reason

    provenance_raw = raw.get("alertmanagerProvenance") or raw.get("alertmanager_provenance")
    provenance = _build_alertmanager_provenance_view(provenance_raw)

    return NextCheckCandidateView(
        alertmanager_provenance=provenance,
        candidate_id=_coerce_optional_str(raw.get("candidateId")),
        description=_coerce_str(raw.get("description")),
        target_cluster=_coerce_optional_str(raw.get("targetCluster")),
        source_reason=_coerce_optional_str(raw.get("sourceReason")),
        expected_signal=_coerce_optional_str(raw.get("expectedSignal")),
        suggested_command_family=_coerce_optional_str(raw.get("suggestedCommandFamily")),
        safe_to_automate=bool(raw.get("safeToAutomate")),
        requires_operator_approval=bool(raw.get("requiresOperatorApproval")),
        risk_level=_coerce_str(raw.get("riskLevel")),
        estimated_cost=_coerce_str(raw.get("estimatedCost")),
        confidence=_coerce_str(raw.get("confidence")),
        gating_reason=_coerce_optional_str(raw.get("gatingReason")),
        duplicate_of_existing_evidence=bool(raw.get("duplicateOfExistingEvidence")),
        duplicate_evidence_description=_coerce_optional_str(
            raw.get("duplicateEvidenceDescription")
        ),
        approval_status=_coerce_optional_str(raw.get("approvalStatus")),
        approval_artifact_path=_coerce_optional_str(raw.get("approvalArtifactPath")),
        approval_timestamp=_coerce_optional_str(raw.get("approvalTimestamp")),
        candidate_index=_coerce_optional_int(raw.get("candidateIndex")),
        normalization_reason=_coerce_optional_str(raw.get("normalizationReason")),
        safety_reason=_coerce_optional_str(raw.get("safetyReason")),
        approval_reason=_coerce_optional_str(raw.get("approvalReason")),
        duplicate_reason=_coerce_optional_str(raw.get("duplicateReason")),
        blocking_reason=_coerce_optional_str(raw.get("blockingReason")),
        approval_state=_coerce_optional_str(raw.get("approvalState")),
        execution_state=_coerce_optional_str(raw.get("executionState")),
        outcome_status=_coerce_optional_str(raw.get("outcomeStatus")),
        latest_artifact_path=_coerce_optional_str(raw.get("latestArtifactPath")),
        latest_timestamp=_coerce_optional_str(raw.get("latestTimestamp")),
        priority_label=_coerce_optional_str(raw.get("priorityLabel")),
        priority_rationale=_derive_priority_rationale(raw),
        ranking_reason=_derive_ranking_reason(raw),
    )


def _build_review_enrichment_status_view(raw: object | None) -> ReviewEnrichmentStatusView | None:
    if not isinstance(raw, Mapping):
        return None
    return ReviewEnrichmentStatusView(
        status=_coerce_str(raw.get("status")),
        reason=_coerce_optional_str(raw.get("reason")),
        provider=_coerce_optional_str(raw.get("provider")),
        policy_enabled=bool(raw.get("policyEnabled")),
        provider_configured=bool(raw.get("providerConfigured")),
        adapter_available=_coerce_optional_bool(raw.get("adapterAvailable")),
        run_enabled=_coerce_optional_bool(raw.get("runEnabled")),
        run_provider=_coerce_optional_str(raw.get("runProvider")),
    )


def _build_external_analysis_view(raw: Mapping[str, object]) -> ExternalAnalysisView:
    return ExternalAnalysisView(
        tool_name=_coerce_str(raw.get("tool_name")),
        cluster_label=_coerce_optional_str(raw.get("cluster_label")),
        status=_coerce_str(raw.get("status")),
        summary=_coerce_optional_str(raw.get("summary")),
        findings=_coerce_sequence(raw.get("findings")),
        suggested_next_checks=_coerce_sequence(raw.get("suggested_next_checks")),
        timestamp=_coerce_str(raw.get("timestamp")),
        artifact_path=_coerce_optional_str(raw.get("artifact_path")),
    )


def _build_diagnostic_pack_view(raw: object | None) -> DiagnosticPackView | None:
    if not isinstance(raw, Mapping):
        return None
    return DiagnosticPackView(
        path=_coerce_optional_str(raw.get("path")),
        timestamp=_coerce_optional_str(raw.get("timestamp")),
        label=_coerce_optional_str(raw.get("label")),
        review_bundle_path=_coerce_optional_str(raw.get("review_bundle_path")),
        review_input_14b_path=_coerce_optional_str(raw.get("review_input_14b_path")),
    )


def _build_assessment_view(raw: object | None) -> AssessmentView | None:
    if not isinstance(raw, Mapping):
        return None
    return AssessmentView(
        cluster_label=_coerce_str(raw.get("cluster_label")),
        context=_coerce_str(raw.get("context")),
        timestamp=_coerce_str(raw.get("timestamp")),
        health_rating=_coerce_str(raw.get("health_rating")),
        missing_evidence=_coerce_sequence(raw.get("missing_evidence")),
        findings=_build_assessment_findings(raw.get("findings")),
        hypotheses=_build_assessment_hypotheses(raw.get("hypotheses")),
        next_checks=_build_assessment_next_checks(raw.get("next_evidence_to_collect")),
        recommended_action=_build_recommended_action(raw.get("recommended_action")),
        probable_layer=_coerce_optional_str(raw.get("probable_layer_of_origin")),
        overall_confidence=_coerce_optional_str(raw.get("overall_confidence")),
        artifact_path=_coerce_optional_str(raw.get("artifact_path")),
        snapshot_path=_coerce_optional_str(raw.get("snapshot_path")),
    )


def _build_assessment_findings(raw: object | None) -> tuple[AssessmentFindingView, ...]:
    if not isinstance(raw, Sequence):
        return ()
    entries: list[AssessmentFindingView] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        entries.append(
            AssessmentFindingView(
                description=_coerce_str(entry.get("description")),
                layer=_coerce_str(entry.get("layer")),
                supporting_signals=_coerce_sequence(entry.get("supporting_signals")),
            )
        )
    return tuple(entries)


def _build_assessment_hypotheses(raw: object | None) -> tuple[AssessmentHypothesisView, ...]:
    if not isinstance(raw, Sequence):
        return ()
    entries: list[AssessmentHypothesisView] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        entries.append(
            AssessmentHypothesisView(
                description=_coerce_str(entry.get("description")),
                confidence=_coerce_str(entry.get("confidence")),
                probable_layer=_coerce_str(entry.get("probable_layer")),
                what_would_falsify=_coerce_str(entry.get("what_would_falsify")),
            )
        )
    return tuple(entries)


def _build_assessment_next_checks(raw: object | None) -> tuple[AssessmentNextCheckView, ...]:
    if not isinstance(raw, Sequence):
        return ()
    entries: list[AssessmentNextCheckView] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        entries.append(
            AssessmentNextCheckView(
                description=_coerce_str(entry.get("description")),
                owner=_coerce_str(entry.get("owner")),
                method=_coerce_str(entry.get("method")),
                evidence_needed=_coerce_sequence(entry.get("evidence_needed")),
            )
        )
    return tuple(entries)


def _build_recommended_action(raw: object | None) -> RecommendedActionView | None:
    if not isinstance(raw, Mapping):
        return None
    return RecommendedActionView(
        action_type=_coerce_str(raw.get("type")),
        description=_coerce_str(raw.get("description")),
        references=_coerce_sequence(raw.get("references")),
        safety_level=_coerce_str(raw.get("safety_level")),
    )


def _build_alertmanager_provenance_view(raw: object | None) -> AlertmanagerProvenanceView | None:
    """Build AlertmanagerProvenanceView from raw JSON data (snake_case keys from planner)."""
    if not isinstance(raw, Mapping):
        return None
    matched_dimensions_raw = raw.get("matchedDimensions") or raw.get("matched_dimensions") or ()
    matched_dimensions: tuple[str, ...] = ()
    if isinstance(matched_dimensions_raw, Sequence) and not isinstance(matched_dimensions_raw, str | bytes):
        matched_dimensions = tuple(str(d) for d in matched_dimensions_raw)
    
    matched_values_raw = raw.get("matchedValues") or raw.get("matched_values") or {}
    matched_values: dict[str, tuple[str, ...]] = {}
    if isinstance(matched_values_raw, Mapping):
        for dim, vals in matched_values_raw.items():
            if isinstance(vals, Sequence) and not isinstance(vals, str | bytes):
                matched_values[str(dim)] = tuple(str(v) for v in vals)
            elif vals:
                matched_values[str(dim)] = (str(vals),)
    
    severity_summary_raw = raw.get("severitySummary") or raw.get("severity_summary")
    severity_summary: dict[str, int] | None = None
    if isinstance(severity_summary_raw, Mapping):
        severity_summary = {str(k): int(v) for k, v in severity_summary_raw.items()}
    
    return AlertmanagerProvenanceView(
        matched_dimensions=matched_dimensions,
        matched_values=matched_values,
        applied_bonus=_coerce_int(raw.get("appliedBonus") or raw.get("applied_bonus")),
        base_bonus=_coerce_int(raw.get("baseBonus") or raw.get("base_bonus") or 0),
        severity_summary=severity_summary,
        signal_status=_coerce_optional_str(raw.get("signalStatus") or raw.get("signal_status")),
    )


def _build_alertmanager_compact_view(raw: object | None) -> AlertmanagerCompactView | None:
    """Build AlertmanagerCompactView from raw JSON data."""
    if not isinstance(raw, Mapping):
        return None
    severity_raw = raw.get("severity_counts")
    severity_counts: tuple[tuple[str, int], ...] = ()
    if isinstance(severity_raw, Mapping):
        severity_counts = tuple(
            (str(k), int(v)) for k, v in severity_raw.items()
        )
    state_raw = raw.get("state_counts")
    state_counts: tuple[tuple[str, int], ...] = ()
    if isinstance(state_raw, Mapping):
        state_counts = tuple(
            (str(k), int(v)) for k, v in state_raw.items()
        )
    return AlertmanagerCompactView(
        status=_coerce_str(raw.get("status")),
        alert_count=_coerce_int(raw.get("alert_count")),
        severity_counts=severity_counts,
        state_counts=state_counts,
        top_alert_names=_coerce_str_tuple(raw.get("top_alert_names")),
        affected_namespaces=_coerce_str_tuple(raw.get("affected_namespaces")),
        affected_clusters=_coerce_str_tuple(raw.get("affected_clusters")),
        affected_services=_coerce_str_tuple(raw.get("affected_services")),
        truncated=bool(raw.get("truncated")),
        captured_at=_coerce_str(raw.get("captured_at")),
    )


# Human-readable labels for origin and state values
_ORIGIN_LABELS: dict[str, str] = {
    "manual": "Manual",
    "alertmanager-crd": "Alertmanager CRD",
    "prometheus-crd-config": "Prometheus Config",
    "service-heuristic": "Service Heuristic",
}

_STATE_LABELS: dict[str, str] = {
    "manual": "Manual",
    "auto-tracked": "Auto-tracked",
    "discovered": "Discovered",
    "degraded": "Degraded",
    "missing": "Missing",
}

_STATE_COLOR_HINTS: dict[str, str] = {
    "manual": "green",
    "auto-tracked": "green",
    "discovered": "yellow",
    "degraded": "red",
    "missing": "gray",
}


def _build_alertmanager_sources_view(raw: object | None) -> AlertmanagerSourcesView | None:
    """Build AlertmanagerSourcesView from raw JSON data (alertmanager_sources field).
    
    This function applies effective state overrides from operator actions
    (promote/disable) when computing UI fields like is_manual, is_tracking,
    can_disable, can_promote, and display_state.
    """
    if not isinstance(raw, Mapping):
        return None
    
    sources_raw = raw.get("sources") or ()
    sources: list[AlertmanagerSourceView] = []
    for src in sources_raw:
        if not isinstance(src, Mapping):
            continue
        origin = _coerce_str(src.get("origin", "service-heuristic"))
        state = _coerce_str(src.get("state", "discovered"))
        
        # Apply effective state from operator override (promote/disable)
        # This overrides the discovery-based state
        effective_state = _coerce_optional_str(src.get("effective_state"))
        if effective_state:
            state = effective_state
            # Promotion also changes the origin to "manual"
            if effective_state == "manual":
                origin = "manual"
        
        # Compute UI fields based on (possibly overridden) state and origin
        is_manual = origin == "manual"
        is_tracking = state in ("auto-tracked", "manual")
        # Sources with effective_state "disabled" cannot be disabled again
        # Sources that are already manual cannot be promoted
        can_disable = not is_manual and state == "auto-tracked"
        can_promote = not is_manual and state in ("auto-tracked", "discovered")
        display_origin = _ORIGIN_LABELS.get(origin, origin)
        display_state = _STATE_LABELS.get(state, state)
        
        # Build provenance summary from confidence_hints
        hints = _coerce_str_tuple(src.get("confidence_hints"))
        provenance_summary = "; ".join(hints) if hints else "-"
        
        # Build merged_provenances for deduplication display
        merged_provenances_raw = src.get("merged_provenances")
        if isinstance(merged_provenances_raw, Sequence) and not isinstance(merged_provenances_raw, str | bytes):
            merged_provenances = tuple(str(p) for p in merged_provenances_raw)
        else:
            merged_provenances = (origin,)
        
        # Build human-readable display_provenance
        display_provenance_raw = src.get("display_provenance")
        if display_provenance_raw:
            display_provenance = _coerce_str(display_provenance_raw)
        else:
            # Derive from merged_provenances if not explicitly set
            labels = [_ORIGIN_LABELS.get(p, p) for p in merged_provenances]
            display_provenance = ", ".join(labels) if labels else display_origin
        
        sources.append(AlertmanagerSourceView(
            source_id=_coerce_str(src.get("source_id")),
            endpoint=_coerce_str(src.get("endpoint")),
            namespace=_coerce_optional_str(src.get("namespace")),
            name=_coerce_optional_str(src.get("name")),
            origin=origin,
            state=state,
            discovered_at=_coerce_optional_str(src.get("discovered_at")),
            verified_at=_coerce_optional_str(src.get("verified_at")),
            last_check=_coerce_optional_str(src.get("last_check")),
            last_error=_coerce_optional_str(src.get("last_error")),
            verified_version=_coerce_optional_str(src.get("verified_version")),
            confidence_hints=hints,
            merged_provenances=merged_provenances,
            display_provenance=display_provenance,
            is_manual=is_manual,
            is_tracking=is_tracking,
            can_disable=can_disable,
            can_promote=can_promote,
            display_origin=display_origin,
            display_state=display_state,
            provenance_summary=provenance_summary,
        ))
    
    # Count by category
    manual_count = sum(1 for s in sources if s.is_manual)
    tracked_count = sum(1 for s in sources if s.is_tracking)
    degraded_count = sum(1 for s in sources if s.state == "degraded")
    missing_count = sum(1 for s in sources if s.state == "missing")
    
    return AlertmanagerSourcesView(
        sources=tuple(sources),
        total_count=len(sources),
        tracked_count=tracked_count,
        manual_count=manual_count,
        degraded_count=degraded_count,
        missing_count=missing_count,
        discovery_timestamp=_coerce_optional_str(raw.get("discovery_timestamp")),
        cluster_context=_coerce_optional_str(raw.get("cluster_context")),
    )
