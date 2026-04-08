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
class NextCheckCandidateView:
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


@dataclass(frozen=True)
class NextCheckPlanView:
    status: str
    summary: str | None
    artifact_path: str | None
    review_path: str | None
    enrichment_artifact_path: str | None
    candidate_count: int
    candidates: tuple[NextCheckCandidateView, ...]


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


def _build_next_check_plan_view(raw: object | None) -> NextCheckPlanView | None:
    if not isinstance(raw, Mapping):
        return None
    candidates_raw = raw.get("candidates") or ()
    candidates = tuple(
        _build_next_check_candidate_view(entry)
        for entry in candidates_raw
        if isinstance(entry, Mapping)
    )
    return NextCheckPlanView(
        status=_coerce_str(raw.get("status")),
        summary=_coerce_optional_str(raw.get("summary")),
        artifact_path=_coerce_optional_str(raw.get("artifactPath")),
        review_path=_coerce_optional_str(raw.get("reviewPath")),
        enrichment_artifact_path=_coerce_optional_str(raw.get("enrichmentArtifactPath")),
        candidate_count=_coerce_int(raw.get("candidateCount")),
        candidates=candidates,
    )


def _build_next_check_candidate_view(raw: Mapping[str, object]) -> NextCheckCandidateView:
    return NextCheckCandidateView(
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
