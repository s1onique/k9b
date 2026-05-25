"""Utilities that build a compact artifact index for UI consumers."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..datetime_utils import parse_iso_to_utc
from ..external_analysis.artifact import ExternalAnalysisArtifact
from ..external_analysis.config import ExternalAnalysisSettings
from ..security.deanonymization import safe_alias_mapping
from .adaptation import HealthProposal
from .ui_deterministic_next_checks import (
    _build_deterministic_next_checks_projection,
    _classify_deterministic_next_check,
)
from .ui_diagnostic_pack import (
    _serialize_alertmanager_compact,
    _serialize_alertmanager_sources,
    _serialize_diagnostic_pack,
    _serialize_diagnostic_pack_review,
    _serialize_vmalert_sources,
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

# Import from extracted ui_projection modules for backward compatibility
from .ui_projection import (
    NotificationRecord,  # noqa: F401  # re-exported for type compatibility
    _build_notification_index,
    _build_promotions_index,
    _build_recent_runs_summary,
    _build_review_enrichment_status,
    _find_review_enrichment_artifact,
    _serialize_auto_drilldown_interpretations,
    _serialize_auto_drilldown_policy,
    _serialize_review_enrichment,
    _serialize_review_enrichment_policy,
    _write_proposal_status_summary_to_review,
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
)
from .ui_shared import _relative_path

logger = logging.getLogger(__name__)

# Re-export: required by test_health_ui.py
__all__ = ["_classify_deterministic_next_check"]

if TYPE_CHECKING:
    from .loop import DrilldownArtifact, HealthAssessmentArtifact, HealthSnapshotRecord


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
        _serialize_cluster(record, assessment_map, drilldown_map, output_dir) for record in records
    ]
    deterministic_next_checks = _build_deterministic_next_checks_projection(
        clusters,
        assessment_map,
        drilldown_map,
        output_dir,
    )
    cluster_context_map = {
        record.target.label: record.target.context for record in records
    }
    drilldown_entries = [
        _serialize_drilldown(artifact, output_dir)
        for artifact in sorted(drilldowns, key=lambda item: item.timestamp, reverse=True)
    ]
    latest_drilldown = drilldown_entries[0] if drilldown_entries else None
    # Wire transitions_dir for current-state derivation from event artifacts
    transitions_dir = output_dir / "proposals" / "transitions"
    proposals_data = [
        _serialize_proposal(proposal, output_dir, transitions_dir) for proposal in proposals
    ]
    drilldown_availability = _serialize_drilldown_availability(
        records, drilldown_map, output_dir
    )
    external_analysis_data = _serialize_external_analysis(external_analysis, output_dir)
    historical_entries = _collect_historical_external_analysis_entries(
        output_dir / "external-analysis"
    )
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
    # Extract alias_mapping from review enrichment for use in other serializers
    alias_mapping: dict[str, str] = {}
    if review_enrichment_entry:
        review_artifact = _find_review_enrichment_artifact(external_analysis, run_id)
        if review_artifact:
            alias_mapping = safe_alias_mapping(getattr(review_artifact, "alias_mapping", None))
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
    # Read vmalert sources inventory if available
    vmalert_sources_entry = _serialize_vmalert_sources(output_dir, run_id)
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
        "llm_activity": _serialize_llm_activity(
            historical_entries, output_dir, alias_mapping=alias_mapping
        ),
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
        "vmalert_sources": vmalert_sources_entry,
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
    # Pass external_analysis_dir to compute batch eligibility during index generation
    index["recent_runs_summary"] = _build_recent_runs_summary(
        output_dir / "reviews",
        external_analysis_dir=output_dir / "external-analysis",
    )
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


def _latest_drilldown_map(
    drilldowns: Sequence[DrilldownArtifact],
) -> dict[str, DrilldownArtifact]:
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
            logger.warning(
                "Skipped malformed review timestamp artifact: %s", path.name, exc_info=True
            )
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


def _parse_run_start(run_id: str) -> datetime | None:
    match = _RUN_ID_TIMESTAMP_PATTERN.search(run_id or "")
    if not match:
        return None
    try:
        parsed = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC)