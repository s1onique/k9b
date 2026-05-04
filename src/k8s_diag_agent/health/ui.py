"""Utilities that build a compact artifact index for UI consumers."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from ..datetime_utils import parse_iso_to_utc
from ..external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisPurpose
from ..external_analysis.config import (
    AutoDrilldownPolicy,
    ExternalAnalysisSettings,
    ReviewEnrichmentPolicy,
)
from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id
from .adaptation import HealthProposal
from .notifications import NotificationArtifact
from .ui_deterministic_next_checks import (
    _build_deterministic_next_checks_projection,
    _classify_deterministic_next_check,
)
from .ui_diagnostic_pack import (
    _serialize_alertmanager_compact,
    _serialize_alertmanager_sources,
    _serialize_diagnostic_pack,
    _serialize_diagnostic_pack_review,
)
from .ui_llm_stats import (
    _build_historical_llm_stats,
    _build_llm_policy,
    _build_llm_stats,
    _build_provider_execution,
    _collect_historical_external_analysis_entries,
    _percentile_value,
    _serialize_llm_activity,
)
from .ui_next_check_execution import (
    _build_next_check_execution_history,
    _classify_blocked_candidate,  # noqa: F401  # re-exported for tests
    _classify_execution_failure,  # noqa: F401  # re-exported for tests
    _classify_execution_success,  # noqa: F401  # re-exported for tests
)
from .ui_planner_queue import (
    _PLANNER_NEXT_ACTION_HINTS,  # noqa: F401  # re-exported for tests
    _PLANNER_STATUS_ENRICHMENT_FAILED,  # noqa: F401  # re-exported for tests
    _PLANNER_STATUS_ENRICHMENT_NOT_ATTEMPTED,  # noqa: F401  # re-exported for tests
    _PLANNER_STATUS_ENRICHMENT_SUCCESS_NO_CHECKS,  # noqa: F401  # re-exported for tests
    _PLANNER_STATUS_PLANNER_MISSING,  # noqa: F401  # re-exported for tests
    _PLANNER_STATUS_PLANNER_PRESENT,  # noqa: F401  # re-exported for tests
    _PLANNER_STATUS_POLICY_DISABLED,  # noqa: F401  # re-exported for tests
    _build_next_check_planner_availability,
    _build_next_check_queue,
    _build_next_check_queue_explanation,
    _derive_priority_rationale,  # noqa: F401  # re-exported for tests
    _serialize_next_check_plan,
)
from .ui_serialization import (
    _ANALYSIS_STATUS_ORDER,
    _serialize_cluster,
    _serialize_drilldown,
    _serialize_drilldown_availability,
    _serialize_fleet_status,
    _serialize_latest_assessment,
    _serialize_notification_history,
    _serialize_proposal,
    _serialize_proposal_status_summary,
    _stringify_notification_value,
)
from .ui_shared import _relative_path

logger = logging.getLogger(__name__)

# Re-export: required by test_health_ui.py
__all__ = ["_classify_deterministic_next_check"]

if TYPE_CHECKING:
    from .loop import DrilldownArtifact, HealthAssessmentArtifact, HealthSnapshotRecord


def _serialize_review_enrichment_policy(policy: ReviewEnrichmentPolicy) -> dict[str, object]:
    provider = (policy.provider or "").strip()
    return {
        "enabled": policy.enabled,
        "provider": provider or None,
    }


def _serialize_auto_drilldown_policy(policy: AutoDrilldownPolicy) -> dict[str, object]:
    provider = (policy.provider or "").strip()
    return {
        "enabled": policy.enabled,
        "provider": provider or None,
        "maxPerRun": policy.max_per_run,
    }


NotificationRecord = tuple[NotificationArtifact, Path]


def write_health_ui_index(
    output_dir: Path,
    run_id: str,
    run_label: str,
    collector_version: str,
    records: Sequence[HealthSnapshotRecord],
    assessments: Sequence[HealthAssessmentArtifact],
    drilldowns: Sequence[DrilldownArtifact],
    proposals: Sequence[HealthProposal],
    external_analysis: Sequence[ExternalAnalysisArtifact] = (),
    notifications: Sequence[NotificationRecord] = (),
    external_analysis_settings: ExternalAnalysisSettings | None = None,
    available_adapters: Iterable[str] | None = None,
    expected_scheduler_interval_seconds: int | None = None,
) -> Path:
    assessment_map = {artifact.label: artifact for artifact in assessments}
    drilldown_map = _latest_drilldown_map(drilldowns)
    clusters = [
        _serialize_cluster(record, assessment_map, drilldown_map, output_dir)
        for record in records
    ]
    deterministic_next_checks = _build_deterministic_next_checks_projection(
        clusters,
        assessment_map,
        drilldown_map,
        output_dir,
    )
    cluster_context_map = {record.target.label: record.target.context for record in records}
    drilldown_entries = [
        _serialize_drilldown(artifact, output_dir)
        for artifact in sorted(drilldowns, key=lambda item: item.timestamp, reverse=True)
    ]
    latest_drilldown = drilldown_entries[0] if drilldown_entries else None
    # Wire transitions_dir for current-state derivation from event artifacts
    transitions_dir = output_dir / "proposals" / "transitions"
    proposals_data = [_serialize_proposal(proposal, output_dir, transitions_dir) for proposal in proposals]
    drilldown_availability = _serialize_drilldown_availability(records, drilldown_map, output_dir)
    external_analysis_data = _serialize_external_analysis(external_analysis, output_dir)
    historical_entries = _collect_historical_external_analysis_entries(output_dir / "external-analysis")
    auto_drilldown_data = _serialize_auto_drilldown_interpretations(
        external_analysis_data.get("artifacts"), output_dir
    )
    notification_history = _serialize_notification_history(notifications, output_dir)
    latest_assessment = _serialize_latest_assessment(assessments, output_dir)
    review_enrichment_entry = _serialize_review_enrichment(
        external_analysis,
        output_dir,
        run_id,
        historical_entries,
    )
    plan_entry = _serialize_next_check_plan(external_analysis, output_dir, run_id)
    queue_entry = _build_next_check_queue(plan_entry, cluster_context_map)
    settings = external_analysis_settings or ExternalAnalysisSettings()
    review_config = _serialize_review_enrichment_policy(settings.review_enrichment)
    review_status = _build_review_enrichment_status(
        external_analysis_settings,
        available_adapters,
        bool(review_enrichment_entry),
        review_config,
    )
    planner_availability_entry = _build_next_check_planner_availability(
        plan_entry, review_enrichment_entry, review_status
    )
    auto_config = _serialize_auto_drilldown_policy(settings.auto_drilldown)
    diagnostic_pack_review_entry = _serialize_diagnostic_pack_review(
        external_analysis, output_dir, run_id
    )
    # Read Alertmanager compact artifact if available
    alertmanager_compact_entry = _serialize_alertmanager_compact(output_dir, run_id)
    # Read Alertmanager sources inventory if available
    alertmanager_sources_entry = _serialize_alertmanager_sources(output_dir, run_id)
    run_entry = {
        "run_id": run_id,
        "run_label": run_label,
        "timestamp": datetime.now(UTC).isoformat(),
        "collector_version": collector_version,
        "cluster_count": len(clusters),
        "drilldown_count": len(drilldowns),
        "proposal_count": len(proposals_data),
        "external_analysis_count": external_analysis_data.get("count", 0),
        "notification_count": len(notifications),
        "llm_stats": _build_llm_stats(external_analysis_data),
        "historical_llm_stats": _build_historical_llm_stats(
            output_dir / "external-analysis", historical_entries
        ),
        "llm_activity": _serialize_llm_activity(historical_entries, output_dir),
        "llm_policy": _build_llm_policy(
            settings,
            external_analysis,
            len(drilldowns),
        ),
        "provider_execution": _build_provider_execution(
            settings,
            external_analysis,
            drilldowns,
            review_config,
        ),
        "auto_drilldown_config": auto_config,
        "review_enrichment": review_enrichment_entry,
        "review_enrichment_config": review_config,
        "review_enrichment_status": review_status,
        "planner_availability": planner_availability_entry,
        "next_check_plan": plan_entry,
        "next_check_queue": queue_entry,
        "next_check_queue_explanation": _build_next_check_queue_explanation(
            clusters,
            drilldown_availability,
            plan_entry,
            queue_entry,
            review_enrichment_entry,
            review_status,
            deterministic_next_checks,
        ),
        "deterministic_next_checks": deterministic_next_checks,
        "diagnostic_pack_review": diagnostic_pack_review_entry,
        "diagnostic_pack": _serialize_diagnostic_pack(output_dir, run_id, run_label),
        "next_check_execution_history": _build_next_check_execution_history(
            external_analysis, output_dir, run_id
        ),
        "scheduler_interval_seconds": expected_scheduler_interval_seconds,
        "alertmanager_compact": alertmanager_compact_entry,
        "alertmanager_sources": alertmanager_sources_entry,
    }
    # Build proposal_status_summary ONCE for reuse in both index and review artifact
    # This avoids repeated scanning of proposals/ directory on each /api/run request
    proposal_status_summary = _serialize_proposal_status_summary(proposals_data)
    index = {
        "run": run_entry,
        "fleet_status": _serialize_fleet_status(clusters),
        "clusters": clusters,
        "drilldowns": drilldown_entries,
        "latest_drilldown": latest_drilldown,
        "proposal_status_summary": proposal_status_summary,
        "proposals": proposals_data,
        "drilldown_availability": drilldown_availability,
        "notification_history": notification_history,
        "external_analysis": external_analysis_data,
        "auto_drilldown_interpretations": auto_drilldown_data,
        "latest_assessment": latest_assessment,
        "next_check_plan": plan_entry,
        "deterministic_next_checks": deterministic_next_checks,
    }
    # Add proposal_status_summary to review artifact for fast selected-run loading
    # This enables _load_context_for_run() to skip proposals/ directory scan
    index["_review_proposal_status_summary"] = proposal_status_summary
    index["run_stats"] = _build_run_stats(output_dir / "reviews")
    # Build recent_runs_summary for fast /api/runs default path
    # This is the key optimization: avoid scanning all review files on each request
    index["recent_runs_summary"] = _build_recent_runs_summary(output_dir / "reviews")
    # Build notification_index for fast /api/notifications default path
    # This is the key optimization: avoid scanning all notification files on each request
    index["notification_index"] = _build_notification_index(notifications, output_dir)
    # Build promotions_index for fast /api/run promotions loading
    # This is the key optimization: avoid globbing all external-analysis files on each request
    index["promotions_index"] = _build_promotions_index(
        output_dir / "external-analysis", run_id
    )
    index_path = output_dir / "ui-index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    # Also write proposal_status_summary to review artifact for fast past-run loading
    # This avoids _load_context_for_run() scanning proposals/ directory on each request
    _write_proposal_status_summary_to_review(output_dir, run_id, proposal_status_summary)

    return index_path


def _latest_drilldown_map(drilldowns: Sequence[DrilldownArtifact]) -> dict[str, DrilldownArtifact]:
    mapping: dict[str, DrilldownArtifact] = {}
    for artifact in sorted(drilldowns, key=lambda item: item.timestamp, reverse=True):
        mapping.setdefault(artifact.label, artifact)
    return mapping


def _serialize_external_analysis(
    artifacts: Sequence[ExternalAnalysisArtifact],
    root_dir: Path,
) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    for artifact in sorted(artifacts, key=lambda item: item.timestamp, reverse=True):
        status = artifact.status.value
        counts[status] = counts.get(status, 0) + 1
        entry: dict[str, object] = {
            "tool_name": artifact.tool_name,
            "cluster_label": artifact.cluster_label,
            "run_id": artifact.run_id,
            "run_label": artifact.run_label,
            "status": status,
            "summary": artifact.summary,
            "findings": list(artifact.findings),
            "suggested_next_checks": list(artifact.suggested_next_checks),
            "timestamp": artifact.timestamp.isoformat(),
            "artifact_path": _relative_path(root_dir, artifact.artifact_path),
            "duration_ms": artifact.duration_ms,
            "provider": artifact.provider,
            "purpose": artifact.purpose.value,
            "payload": artifact.payload,
            "error_summary": artifact.error_summary,
            "skip_reason": artifact.skip_reason,
        }
        # Immutable artifact instance identity for provenance/debugging
        if artifact.artifact_id:
            entry["artifact_id"] = artifact.artifact_id
        entries.append(entry)
    status_counts: list[dict[str, object]] = []
    seen: set[str] = set()
    for status in _ANALYSIS_STATUS_ORDER:
        if status in counts:
            status_counts.append({"status": status, "count": counts[status]})
            seen.add(status)
    for status, count in sorted(counts.items()):
        if status in seen:
            continue
        status_counts.append({"status": status, "count": count})
    return {"count": len(entries), "status_counts": status_counts, "artifacts": entries}


def _serialize_review_enrichment(
    artifacts: Sequence[ExternalAnalysisArtifact],
    root_dir: Path,
    run_id: str,
    fallback: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object] | None:
    artifact = _find_review_enrichment_artifact(artifacts, run_id)
    if not artifact and fallback:
        fallback_entries: list[ExternalAnalysisArtifact] = []
        for raw in fallback:
            if not isinstance(raw, Mapping):
                continue
            try:
                candidate = ExternalAnalysisArtifact.from_dict(raw)
            except (ValueError, KeyError, TypeError):
                continue
            if candidate.run_id != run_id:
                continue
            if candidate.purpose != ExternalAnalysisPurpose.REVIEW_ENRICHMENT:
                continue
            fallback_entries.append(candidate)
        if fallback_entries:
            artifact = sorted(
                fallback_entries, key=lambda item: item.timestamp, reverse=True
            )[0]
    if not artifact:
        return None
    payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}

    # Merge interpretation field (which carries alertmanagerEvidenceReferences) into payload
    # This ensures the bounded evidence references are threaded through to the UI
    if artifact.interpretation and isinstance(artifact.interpretation, Mapping):
        for key, value in artifact.interpretation.items():
            if key not in payload:
                payload[key] = value

    def _list_from(*keys: str) -> list[str]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                return [str(item) for item in value]
            if value is not None:
                return [str(value)]
        return []

    # Extract alertmanager evidence references from merged payload
    alertmanager_refs = payload.get("alertmanagerEvidenceReferences") or payload.get("alertmanager_evidence_references")

    result: dict[str, object] = {
        "status": artifact.status.value,
        "provider": artifact.provider,
        "timestamp": artifact.timestamp.isoformat(),
        "summary": artifact.summary,
        "triageOrder": _list_from("triageOrder", "triage_order"),
        "topConcerns": _list_from("topConcerns", "top_concerns"),
        "evidenceGaps": _list_from("evidenceGaps", "evidence_gaps"),
        "nextChecks": _list_from("nextChecks", "next_checks"),
        "focusNotes": _list_from("focusNotes", "focus_notes", "caveats", "proposal_caveats"),
        "artifactPath": _relative_path(root_dir, artifact.artifact_path),
        "errorSummary": artifact.error_summary,
        "skipReason": artifact.skip_reason,
    }
    if alertmanager_refs is not None:
        result["alertmanagerEvidenceReferences"] = alertmanager_refs
    return result


def _find_review_enrichment_artifact(
    artifacts: Sequence[ExternalAnalysisArtifact], run_id: str
) -> ExternalAnalysisArtifact | None:
    from ..external_analysis.utils import artifact_matches_run
    for artifact in sorted(artifacts, key=lambda item: item.timestamp, reverse=True):
        if (
            artifact.purpose == ExternalAnalysisPurpose.REVIEW_ENRICHMENT
            and artifact_matches_run(artifact, run_id)
        ):
            return artifact
    return None


def _build_review_enrichment_status(
    settings: ExternalAnalysisSettings | None,
    adapters: Iterable[str] | None,
    has_artifact: bool,
    run_config: Mapping[str, object] | None,
) -> dict[str, object] | None:
    policy = (settings or ExternalAnalysisSettings()).review_enrichment
    provider_raw = policy.provider or ""
    provider = provider_raw.strip()
    provider_name = provider or None
    if has_artifact:
        return None
    adapter_available = _adapter_registered(provider, adapters) if provider else None
    status = "unknown"
    reason: str | None = None
    run_enabled: bool | None = None
    run_provider: str | None = None
    if isinstance(run_config, Mapping):
        if "enabled" in run_config:
            run_enabled = bool(run_config.get("enabled"))
        value = run_config.get("provider")
        run_provider_raw = str(value).strip() if value else ""
        run_provider = run_provider_raw or None
    if not policy.enabled:
        status = "policy-disabled"
        reason = "Review enrichment is disabled in the current configuration."
    elif not provider:
        status = "provider-missing"
        reason = "No provider is configured for review enrichment."
    elif adapter_available is False:
        status = "adapter-unavailable"
        reason = f"Adapter '{provider}' is not registered for review enrichment."
    elif not run_config or "enabled" not in run_config or "provider" not in run_config:
        status = "unknown"
        reason = reason or "Review enrichment metadata is incomplete for this run."
    elif run_enabled is False or not run_provider:
        status = "awaiting-next-run"
        if run_provider:
            reason = (
                "Review enrichment is enabled now, but the latest run was produced before "
                f"'{run_provider}' was active."
            )
        else:
            reason = "Review enrichment is enabled now, but the latest run predates this setting."
    else:
        status = "not-attempted"
        if run_provider:
            reason = (
                f"Review enrichment was enabled for '{run_provider}' in this run, "
                "but no artifact was recorded."
            )
        else:
            reason = "Review enrichment was enabled for this run, but no artifact was recorded."
    return {
        "status": status,
        "reason": reason,
        "provider": provider_name,
        "policyEnabled": policy.enabled,
        "providerConfigured": bool(provider),
        "adapterAvailable": adapter_available,
        "runEnabled": run_enabled,
        "runProvider": run_provider,
    }


def _adapter_registered(provider: str, adapters: Iterable[str] | None) -> bool | None:
    if not adapters:
        return None
    normalized = provider.lower()
    for adapter in adapters:
        if adapter and adapter.lower() == normalized:
            return True
    return False


def _serialize_auto_drilldown_interpretations(
    artifacts: object | None, root_dir: Path
) -> dict[str, dict[str, object]]:
    interpretations: dict[str, dict[str, object]] = {}
    if not isinstance(artifacts, Sequence):
        return interpretations
    seen: set[str] = set()
    for entry in artifacts:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("purpose") != ExternalAnalysisPurpose.AUTO_DRILLDOWN.value:
            continue
        cluster_label = str(entry.get("cluster_label") or "").strip()
        if not cluster_label or cluster_label in seen:
            continue
        seen.add(cluster_label)
        interpretations[cluster_label] = {
            "adapter": str(entry.get("tool_name") or ""),
            "status": str(entry.get("status") or ""),
            "summary": entry.get("summary"),
            "timestamp": str(entry.get("timestamp") or ""),
            "artifact_path": _relative_path(root_dir, entry.get("artifact_path")),
            "provider": entry.get("provider"),
            "duration_ms": entry.get("duration_ms"),
            "payload": entry.get("payload"),
            "error_summary": entry.get("error_summary"),
            "skip_reason": entry.get("skip_reason"),
        }
    return interpretations


_RUN_ID_TIMESTAMP_PATTERN = re.compile(r"(\d{8}T\d{6}Z)$")


def _build_run_stats(reviews_dir: Path) -> dict[str, object]:
    review_timestamps = _collect_review_timestamps(reviews_dir)
    total_runs = len(review_timestamps)
    measured: list[tuple[datetime, float]] = []
    durations: list[float] = []
    for run_id, finish in review_timestamps.items():
        start = _parse_run_start(run_id)
        if start is None:
            continue
        duration = (finish - start).total_seconds()
        if duration <= 0:
            continue
        measured.append((finish, duration))
        durations.append(duration)
    last_run_duration_seconds: int | None = None
    if measured:
        latest_entry = max(measured, key=lambda entry: entry[0])
        last_run_duration_seconds = int(latest_entry[1])
    percentile_values: dict[str, int | None] = {
        "p50": None,
        "p95": None,
        "p99": None,
    }
    if len(durations) >= 5:
        durations.sort()
        percentile_values["p50"] = _percentile_value(durations, 50)
        percentile_values["p95"] = _percentile_value(durations, 95)
        percentile_values["p99"] = _percentile_value(durations, 99)
    return {
        "last_run_duration_seconds": last_run_duration_seconds,
        "total_runs": total_runs,
        "p50_run_duration_seconds": percentile_values["p50"],
        "p95_run_duration_seconds": percentile_values["p95"],
        "p99_run_duration_seconds": percentile_values["p99"],
    }


def _collect_review_timestamps(reviews_dir: Path) -> dict[str, datetime]:
    timestamps: dict[str, datetime] = {}
    if not reviews_dir.is_dir():
        return timestamps
    for path in reviews_dir.glob("*-review.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Skipped malformed review timestamp artifact: %s", path.name, exc_info=True)
            continue
        run_id = raw.get("run_id")
        timestamp = raw.get("timestamp")
        if not isinstance(run_id, str) or not isinstance(timestamp, str):
            continue
        finish = parse_iso_to_utc(timestamp)
        if finish is None:
            continue
        existing = timestamps.get(run_id)
        if existing is None or finish > existing:
            timestamps[run_id] = finish
    return timestamps


def _build_recent_runs_summary(reviews_dir: Path, max_runs: int = 500) -> dict[str, object]:
    """Build a compact summary of recent runs for fast /api/runs default path.

    This is the key optimization to avoid scanning all review files on each request.
    Each entry contains only the fields needed for initial Recent Runs list:
    - run_id, run_label, timestamp, cluster_count

    Expensive fields (execution_count, reviewed_count, batch eligibility) are
    NOT included - they must be derived on-demand or for explicit include_expensive paths.

    Args:
        reviews_dir: Path to the reviews directory
        max_runs: Maximum number of run summaries to store (default 500 for most UIs)

    Returns:
        Dict with 'runs' list and 'total_count' (total discovered across all runs)
    """
    if not reviews_dir.is_dir():
        return {"runs": [], "total_count": 0, "generated_at": datetime.now(UTC).isoformat()}

    # Collect all run summaries
    run_summaries: list[dict[str, object]] = []
    for path in reviews_dir.glob("*-review.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Skipped malformed recent-run artifact: %s", path.name, exc_info=True)
            continue

        run_id = raw.get("run_id")
        timestamp = raw.get("timestamp")
        if not isinstance(run_id, str) or not isinstance(timestamp, str):
            continue

        # Only include minimal fields needed for initial load
        run_summaries.append({
            "run_id": run_id,
            "run_label": raw.get("run_label", run_id) if isinstance(raw.get("run_label"), str) else run_id,
            "timestamp": timestamp,
            "cluster_count": raw.get("cluster_count", 0) if isinstance(raw.get("cluster_count"), int) else 0,
        })

    # Sort by timestamp descending (newest first)
    # Parse timestamps for sorting
    def get_sort_key(entry: dict[str, object]) -> datetime:
        ts = entry.get("timestamp", "")
        parsed = parse_iso_to_utc(ts)
        return parsed if parsed else datetime.min.replace(tzinfo=UTC)

    run_summaries.sort(key=get_sort_key, reverse=True)

    # Store only the most recent runs (bounded for index size)
    total_count = len(run_summaries)
    recent_runs = run_summaries[:max_runs]

    return {
        "runs": recent_runs,
        "total_count": total_count,
        "generated_at": datetime.now(UTC).isoformat(),
        "version": 1,  # Schema version for future compatibility
    }


def _parse_run_start(run_id: str) -> datetime | None:
    match = _RUN_ID_TIMESTAMP_PATTERN.search(run_id or "")
    if not match:
        return None
    try:
        parsed = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC)


# Maximum number of notification summaries to store in the index
# This bounds index size while providing fast default list access
_NOTIFICATION_INDEX_LIMIT = 500


def _build_notification_index(
    notifications: Sequence[NotificationRecord],
    output_dir: Path,
) -> dict[str, object]:
    """Build a compact notification index for fast /api/notifications default path.

    This is the key optimization to avoid scanning all notification files on cold startup.
    Each entry contains only the fields needed for the initial notification list:
    - kind, summary, timestamp, runId, clusterLabel
    - artifactPath for provenance pointer to full artifact

    The index is bounded to latest 500 notifications to keep index size manageable.

    Args:
        notifications: Sequence of (NotificationArtifact, Path) tuples
        output_dir: Path to the health directory for relative path computation

    Returns:
        Dict with 'notifications' list, 'total_count', 'generated_at', 'version'
    """
    if not notifications:
        return {
            "notifications": [],
            "total_count": 0,
            "generated_at": datetime.now(UTC).isoformat(),
            "version": 1,
        }

    # Sort by timestamp descending (newest first)
    sorted_notifications = sorted(
        notifications,
        key=lambda item: item[0].timestamp,
        reverse=True,
    )

    total_count = len(sorted_notifications)

    # Build notification entries with list-view fields
    entries: list[dict[str, object]] = []
    for artifact, path in sorted_notifications:
        # Build minimal detail entries for the list view
        detail_entries = [
            {"label": str(key), "value": _stringify_notification_value(value)}
            for key, value in sorted(artifact.details.items())
        ]

        entry: dict[str, object] = {
            "kind": artifact.kind,
            "summary": artifact.summary,
            "timestamp": artifact.timestamp,
            "runId": artifact.run_id,
            "clusterLabel": artifact.cluster_label,
            "context": artifact.context,
            "details": detail_entries,
            "artifactPath": _relative_path(output_dir, path),
        }

        # Thread artifact_id for provenance/debugging surfaces (optional)
        if artifact.artifact_id:
            entry["artifact_id"] = artifact.artifact_id

        entries.append(entry)

    # Bound entries to limit
    bounded_entries = entries[:_NOTIFICATION_INDEX_LIMIT]

    return {
        "notifications": bounded_entries,
        "total_count": total_count,
        "generated_at": datetime.now(UTC).isoformat(),
        "version": 1,
    }


# Maximum number of promotion entries to store in the index
# Most runs have very few promotions, so this is generous
_PROMOTIONS_INDEX_LIMIT = 100


def _build_promotions_index(
    external_analysis_dir: Path,
    run_id: str,
) -> dict[str, object]:
    """Build a compact promotions index for fast /api/run promotions loading.

    This is the key optimization to avoid globbing all external-analysis files
    on each /api/run request. The index stores promotion entries for the current
    run only, with enough data to reconstruct queue entries without re-reading
    promotion artifacts.

    IMPORTANT: The index is run-scoped to prevent cross-run data leakage.
    When /api/run requests a historical run, it must validate that the index's
    run_id matches the requested run_id, otherwise fall back to file-based loading.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        run_id: The current run ID to filter promotions for

    Returns:
        Dict with 'run_id', 'promotions' list, 'total_count', 'generated_at', 'version'
    """
    if not external_analysis_dir.is_dir():
        return {
            "run_id": run_id,
            "promotions": [],
            "total_count": 0,
            "generated_at": datetime.now(UTC).isoformat(),
            "version": 1,
        }

    # SECURITY: Validate run_id before using in glob pattern to prevent path traversal
    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        # Invalid run_id - cannot safely search, return safe fallback
        return {
            "run_id": run_id,
            "promotions": [],
            "total_count": 0,
            "generated_at": datetime.now(UTC).isoformat(),
            "version": 1,
        }

    # Scan for promotion artifacts for this run only
    promotion_entries: list[dict[str, object]] = []
    # SECURITY: run_id validated by validate_run_id() before glob construction
    for artifact_path in external_analysis_dir.glob(safe_run_artifact_glob(validated_run_id, "-next-check-promotion-*.json")):
        try:
            raw = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Skipped malformed promotion artifact: %s", artifact_path.name, exc_info=True)
            continue

        # Extract payload for queue entry reconstruction
        payload = raw.get("payload")
        if not isinstance(payload, Mapping):
            continue

        # Build minimal queue entry from promotion payload
        entry: dict[str, object] = {
            "candidateId": payload.get("candidateId"),
            "candidateIndex": payload.get("promotionIndex", 0),
            "description": payload.get("description", "Deterministic next check"),
            "targetCluster": payload.get("clusterLabel", ""),
            "targetContext": payload.get("targetContext"),
            "sourceReason": (
                payload.get("whyNow") or payload.get("topProblem") or "Deterministic next check"
            ),
            "workstream": payload.get("workstream"),
            "urgency": payload.get("urgency"),
            "priorityScore": payload.get("priorityScore"),
            "sourceType": "deterministic",
            "approvalState": "approval-required",
            "executionState": "unexecuted",
            "queueStatus": "approval-needed",
            "artifactPath": _relative_path(external_analysis_dir.parent, artifact_path),
        }

        promotion_entries.append(entry)

    # Sort by promotion index (consistent ordering)
    promotion_entries.sort(key=lambda x: cast(int, x.get("candidateIndex") or 0))

    # Bound entries to limit
    bounded_entries = promotion_entries[:_PROMOTIONS_INDEX_LIMIT]

    return {
        "run_id": run_id,  # CRITICAL: run-scoped to prevent cross-run data leakage
        "promotions": bounded_entries,
        "total_count": len(promotion_entries),
        "generated_at": datetime.now(UTC).isoformat(),
        "version": 1,
    }


def _write_proposal_status_summary_to_review(
    output_dir: Path,
    run_id: str,
    proposal_status_summary: dict[str, object],
) -> None:
    """Write proposal_status_summary to review artifact for fast past-run loading.

    NOTE: The summary is stored as _proposal_status_summary in the review artifact.
    This is derived read-model metadata (underscore-prefixed to mark as internal
    indexing data), NOT source evidence. It provides a fast path to skip proposals/
    directory scanning when loading historical runs via /api/run?run_id=.
    
    Fallback behavior: If a review artifact lacks _proposal_status_summary (e.g., from
    an older run created before this optimization), _load_context_for_run() will fall
    back to scanning the proposals/ directory and building the summary on-demand.

    This is the key optimization to avoid _load_context_for_run() scanning
    the proposals/ directory on each /api/run request for historical runs.

    Args:
        output_dir: Path to the health directory (runs/health/)
        run_id: The run ID to update the review artifact for
        proposal_status_summary: The pre-computed proposal status summary dict
    """
    reviews_dir = output_dir / "reviews"
    review_path = reviews_dir / f"{run_id}-review.json"

    if not review_path.exists():
        return

    try:
        review_data = json.loads(review_path.read_text(encoding="utf-8"))
        if not isinstance(review_data, dict):
            return

        # Add proposal_status_summary to review artifact
        # Use underscore prefix to mark as internal indexing metadata
        review_data["_proposal_status_summary"] = proposal_status_summary

        # Write back preserving original formatting (compact write)
        review_path.write_text(json.dumps(review_data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        # Non-fatal: if we can't write the summary, past runs will still work
        # by falling back to the directory scan path
        logger.warning("Failed to write proposal status summary to review: %s", review_path.name, exc_info=True)
