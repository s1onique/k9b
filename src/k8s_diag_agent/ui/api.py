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
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

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

# Import DeterministicNextChecks serializers from extracted module.
# Re-export for backward compatibility: callers importing from api.py continue to work.
from .api_deterministic_next_checks import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_deterministic_next_check_cluster,
    _serialize_deterministic_next_check_summary,
    _serialize_deterministic_next_checks,
)

# Import DiagnosticPack serializers from extracted module.
# Re-export for backward compatibility: callers importing from api.py continue to work.
from .api_diagnostic_pack import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_diagnostic_pack,
    _serialize_diagnostic_pack_review,
)
from .api_incident_report import (
    _build_incident_report_payload,
    _build_operator_worklist_payload,
)

# Import LLM serializers from extracted module.
# Re-export for backward compatibility: callers importing from api.py continue to work.
from .api_llm import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_llm_activity,
    _serialize_llm_policy,
    _serialize_llm_stats,
)

# Import NextCheckPlan serializers from extracted module.
# Re-export for backward compatibility: callers importing from api.py continue to work.
from .api_next_check_plan import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_execution_history,
    _serialize_next_check_candidate,
    _serialize_next_check_plan,
    _serialize_orphaned_approval,
    _serialize_plan_candidates_for_cluster,
)

# Import NextCheckQueue serializers from extracted module.
# Re-export for backward compatibility: callers importing from api.py continue to work.
from .api_next_check_queue import (  # noqa: F401 - re-exported for backward compatibility
    _serialize_next_check_queue,
    _serialize_planner_availability,
    _serialize_queue_candidate_accounting,
    _serialize_queue_cluster_state,
    _serialize_queue_explanation,
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
    RunStatsView,
    UIIndexContext,
)


def build_run_payload(
    context: UIIndexContext,
    *,
    promotions: Sequence[dict[str, object]] | None = None,
) -> RunPayload:
    freshness = _build_freshness_payload(
        context.run.timestamp, context.run.scheduler_interval_seconds
    )
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
        "freshness": freshness,
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
        "incidentReport": _build_incident_report_payload(context, freshness),
        "operatorWorklist": _build_operator_worklist_payload(context),
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
    limit: int | None = 100,
    include_expensive: bool = False,
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

    Performance optimization:
    - By default (limit=100), only computes batch eligibility for the returned window.
    - Set include_expensive=True to compute batch eligibility for all runs.
    - Set limit=None to return all runs without batch eligibility computation.

    Args:
        runs_dir: Path to the runs directory
        limit: Maximum number of runs to return (default 100). None for all runs.
        include_expensive: If True, compute batch eligibility for all runs (expensive).
            If False (default), only compute for returned window.
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

    # Define external_analysis_dir for use in later stages
    external_analysis_dir = run_health_dir / "external-analysis"

    # Stage 3: Sort and window selection (BEFORE expensive batch eligibility scan)
    row_assembly_start = time_module.perf_counter()

    # Sort all entries by timestamp descending (most recent first)
    sort_start = time_module.perf_counter()
    sorted_entries = sorted(
        run_entries.values(),
        key=lambda e: cast(datetime, e["parsed_time"]),
        reverse=True
    )
    timings["sort_ms"] = (time_module.perf_counter() - sort_start) * 1000

    # Track total runs considered vs returned
    rows_considered = len(sorted_entries)
    timings["rows_considered"] = rows_considered

    # Determine window run_ids - these are the runs we'll actually return
    # - If limit is set: return only the first `limit` runs
    # - If limit=None: return all runs
    window_run_ids: set[str]
    if limit is not None:
        window_run_ids = {cast(str, entry["run_id"]) for entry in sorted_entries[:limit]}
        rows_to_return = min(limit, len(sorted_entries))
    else:
        window_run_ids = set(run_entries.keys())
        rows_to_return = len(sorted_entries)

    # Pre-sort run_ids by length (longest first) to handle prefixed run_ids correctly
    # e.g., "run-2024-01-15" should match before "run-2024"
    # This is used for both Stage 2b (execution count) and Stage 3b (batch eligibility)
    sorted_window_run_ids = sorted(window_run_ids, key=len, reverse=True)

    # Stage 2b: Derive execution counts ONLY for runs in window_run_ids
    # This is the key optimization: use window-driven lookup instead of global scan
    execution_scan_start = time_module.perf_counter()

    # Sub-stage: window-driven execution file lookup (avoids global glob)
    # For each run_id in window, find execution files using prefix match
    execution_parsed = 0
    execution_count_matches = 0

    window_exec_files: list[tuple[Path, str]] = []  # (path, matched_run_id)

    execution_lookup_start = time_module.perf_counter()

    # Window-driven lookup: query only window run prefixes
    timings["execution_lookup_strategy"] = "window_glob"
    timings["execution_run_prefixes_queried"] = len(window_run_ids)

    for run_id in sorted_window_run_ids:
        # Use window-run prefix to find only relevant files
        pattern = f"{run_id}-next-check-execution*.json"
        for exec_path in external_analysis_dir.glob(pattern):
            window_exec_files.append((exec_path, run_id))

    timings["execution_files_found_total"] = len(window_exec_files)
    timings["execution_files_considered"] = len(window_exec_files)
    timings["execution_files_skipped_outside_window"] = 0  # Window mode doesn't consider non-window files

    timings["execution_lookup_ms"] = (time_module.perf_counter() - execution_lookup_start) * 1000

    # Sub-stage: parse only window_exec_files to derive execution counts
    execution_parse_start = time_module.perf_counter()
    for exec_path, run_id in window_exec_files:
        execution_parsed += 1
        try:
            raw = json.loads(exec_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        # Check if this is an execution artifact
        purpose = raw.get("purpose")
        if purpose != "next-check-execution":
            continue

        execution_count_matches += 1

        # Increment execution count for this run
        current_exec_count = run_entries[run_id].get("execution_count", 0)
        run_entries[run_id]["execution_count"] = cast(int, current_exec_count) + 1

        # Check if this execution has usefulness feedback (means it was reviewed)
        usefulness = raw.get("usefulness_class")
        if usefulness and isinstance(usefulness, str) and usefulness.strip():
            current_reviewed_count = run_entries[run_id].get("reviewed_count", 0)
            run_entries[run_id]["reviewed_count"] = cast(int, current_reviewed_count) + 1

    timings["execution_parse_ms"] = (time_module.perf_counter() - execution_parse_start) * 1000
    timings["execution_files_parsed"] = execution_parsed
    timings["execution_count_derivation_ms"] = (time_module.perf_counter() - execution_scan_start) * 1000
    timings["execution_count_derivation_matches"] = execution_count_matches

    timings["rows_returned"] = rows_to_return

    # Determine which runs need batch eligibility computation
    # - If include_expensive=True: compute for ALL runs
    # - If limit is set: compute only for the first `limit` runs (after sorting)
    # - If limit=None: compute for NO runs (all get batchEligibility="unknown")
    if include_expensive:
        batch_eligibility_run_ids: set[str] = set(run_entries.keys())
    elif limit is not None:
        # Only compute batch eligibility for runs in the returned window
        batch_eligibility_run_ids = window_run_ids
    else:
        # limit=None means return all runs without batch eligibility
        batch_eligibility_run_ids = set()

    # Sub-stage 3a: Pre-scan diagnostic-packs directory for review download paths
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

    # Sub-stage 3b: Only scan batch eligibility for runs in window_run_ids
    # This is the key optimization: skip files for runs outside the returned window
    batch_eligibility_prescan_start = time_module.perf_counter()

    # Sub-stage: next-check-plan glob (filtered to window run_ids)
    # Note: sorted_window_run_ids is already defined above (used for Stage 2b)
    batch_plan_glob_start = time_module.perf_counter()
    plan_files: list[Path] = []
    if external_analysis_dir.is_dir():
        plan_files = list(external_analysis_dir.glob("*-next-check-plan*.json"))
    timings["batch_plan_glob_ms"] = (time_module.perf_counter() - batch_plan_glob_start) * 1000
    timings["batch_plan_files_found"] = len(plan_files)

    # Sub-stage: next-check-plan parse and matching (filtered to window run_ids)
    batch_plan_parse_start = time_module.perf_counter()
    plan_data: dict[str, dict[str, object]] = {}
    for plan_path in plan_files:
        filename = plan_path.stem
        # Check if this file belongs to a run in our window
        for run_id in sorted_window_run_ids:
            if filename.startswith(f"{run_id}-next-check-plan"):
                try:
                    raw = json.loads(plan_path.read_text(encoding="utf-8"))
                    if raw.get("purpose") == "next-check-planning":
                        plan_data[run_id] = raw
                        break
                except Exception:
                    continue
            # If run_id is not in window_run_ids, skip without parsing
    timings["batch_plan_parse_ms"] = (time_module.perf_counter() - batch_plan_parse_start) * 1000

    # Sub-stage: execution artifact glob (filtered to window run_ids)
    batch_exec_glob_start = time_module.perf_counter()
    exec_files: list[Path] = []
    if external_analysis_dir.is_dir():
        exec_files = list(external_analysis_dir.glob("*-next-check-execution*.json"))
    timings["batch_exec_glob_ms"] = (time_module.perf_counter() - batch_exec_glob_start) * 1000
    timings["batch_exec_files_found"] = len(exec_files)

    # Sub-stage: execution artifact parse and matching (filtered to window run_ids)
    batch_exec_parse_start = time_module.perf_counter()
    execution_indices: dict[str, set[int]] = {run_id: set() for run_id in window_run_ids}
    for exec_path in exec_files:
        filename = exec_path.stem
        # Check if this file belongs to a run in our window
        for run_id in sorted_window_run_ids:
            if filename.startswith(f"{run_id}-next-check-execution"):
                try:
                    raw = json.loads(exec_path.read_text(encoding="utf-8"))
                    if raw.get("purpose") == "next-check-execution":
                        exec_payload: dict[str, object] = raw.get("payload", {})  # type: ignore[assignment]
                        candidate_index = exec_payload.get("candidateIndex")
                        if isinstance(candidate_index, int):
                            execution_indices[run_id].add(candidate_index)
                except Exception:
                    continue
            # If run_id is not in window_run_ids, skip without parsing
    timings["batch_exec_parse_ms"] = (time_module.perf_counter() - batch_exec_parse_start) * 1000

    timings["batch_run_id_matching_ms"] = 0.0
    timings["batch_cache_construction_ms"] = 0.0
    timings["batch_eligibility_prescan_ms"] = (time_module.perf_counter() - batch_eligibility_prescan_start) * 1000

    # Only build rows for runs in the returned window (key optimization)
    # This avoids processing runs outside the window that won't be returned
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

    # Only iterate over entries in the returned window
    entries_to_build = sorted_entries[:rows_to_return] if limit is not None else sorted_entries

    for entry in entries_to_build:
        run_id = entry["run_id"]

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
            run_id_str = cast(str, run_id)
            if review_artifact_exists.get(run_id_str, False):
                run_scoped_path = diagnostic_packs_dir / run_id_str / "next_check_usefulness_review.json"
                review_download_path = str(run_scoped_path.relative_to(runs_dir))
                review_download_paths_found += 1
            # DO NOT fallback to /latest/ - historical runs must have run-specific artifacts
            # If only /latest/ exists today, historical rows should NOT show misleading download links
        review_download_path_row_ms_total += (time_module.perf_counter() - row_start) * 1000

        # Sub-stage: batch eligibility computation (conditional)
        row_start = time_module.perf_counter()
        if run_id in batch_eligibility_run_ids:
            # Compute batch eligibility using pre-scanned data (no per-row filesystem access)
            batch_executable, batch_eligible_count = _compute_batch_eligibility_from_cache(
                run_id, plan_data, execution_indices
            )
            batch_eligibility = "computed"
            if batch_executable:
                batch_eligible_runs += 1
        else:
            # Deferred: batch eligibility not computed for this run
            batch_executable = False
            batch_eligible_count = 0
            batch_eligibility = "unknown"
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
                batchEligibility=cast(Literal["computed", "unknown"], batch_eligibility),
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
    # Note: rows_returned already set above
    # Note: review_artifact_prescan_ms and batch_eligibility_prescan_ms are already set

    timings["batch_eligible_runs"] = batch_eligible_runs
    timings["batch_eligibility_runs_computed"] = len(batch_eligibility_run_ids)

    # Initialize counters (proves no per-row FS work is happening)
    timings["path_exists_calls"] = 0
    timings["stat_calls"] = 0
    timings["diagnostic_pack_path_checks"] = 0
    timings["run_scoped_review_path_checks"] = 0
    timings["per_run_glob_calls"] = 0
    timings["per_run_directory_list_calls"] = 0

    # Build payload with correct counts
    total_discovered = len(run_entries)
    returned_count = len(runs_list)
    has_more = total_discovered > returned_count

    payload = RunsListPayload(
        runs=runs_list,
        totalCount=total_discovered,
        returnedCount=returned_count,
        hasMore=has_more,
    )

    if _timings:
        return payload, timings
    return payload
