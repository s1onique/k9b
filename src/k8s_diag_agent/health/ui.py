"""Utilities that build a compact artifact index for UI consumers."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from .adaptation import HealthProposal
from .notifications import NotificationArtifact

if TYPE_CHECKING:
    from .loop import DrilldownArtifact, HealthAssessmentArtifact, HealthSnapshotRecord


def _serialize_cluster(
    record: HealthSnapshotRecord,
    assessment_map: Mapping[str, HealthAssessmentArtifact | None],
    drilldown_map: Mapping[str, DrilldownArtifact],
    root_dir: Path,
) -> dict[str, object]:
    assessment = assessment_map.get(record.target.label)
    warning_events = len(record.snapshot.health_signals.warning_events)
    pod_counts = record.snapshot.health_signals.pod_counts
    snapshot_path = _relative_path(root_dir, record.path)
    assessment_path = _relative_path(root_dir, assessment.artifact_path if assessment else None)
    drilldown = drilldown_map.get(record.target.label)
    if drilldown:
        drilldown_path = _relative_path(root_dir, drilldown.artifact_path)
        drilldown_timestamp = drilldown.timestamp.isoformat()
        trigger_reason = drilldown.trigger_reasons[0] if drilldown.trigger_reasons else None
    else:
        drilldown_path = None
        drilldown_timestamp = None
        trigger_reason = None
    return {
        "label": record.target.label,
        "context": record.target.context,
        "cluster_class": record.target.cluster_class,
        "cluster_role": record.target.cluster_role,
        "health_rating": assessment.health_rating.value if assessment else "unknown",
        "warnings": warning_events,
        "non_running_pods": pod_counts.non_running,
        "node_count": record.snapshot.metadata.node_count,
        "control_plane_version": record.snapshot.metadata.control_plane_version or "unknown",
        "baseline_cohort": record.target.baseline_cohort,
        "baseline_policy_path": record.baseline_policy_path,
        "missing_evidence": list(assessment.missing_evidence) if assessment else [],
        "latest_run_timestamp": record.snapshot.metadata.captured_at.isoformat(),
        "top_trigger_reason": trigger_reason,
        "artifact_paths": {
            "snapshot": snapshot_path,
            "assessment": assessment_path,
            "drilldown": drilldown_path,
        },
        "drilldown_available": bool(drilldown),
        "drilldown_timestamp": drilldown_timestamp,
    }


def _serialize_drilldown(artifact: DrilldownArtifact, root_dir: Path) -> dict[str, object]:
    pod_entries = [pod.to_dict() for pod in artifact.non_running_pods]
    rollout_entries = [entry.to_dict() for entry in artifact.rollout_status]
    return {
        "label": artifact.label,
        "context": artifact.context,
        "cluster_id": artifact.cluster_id,
        "trigger_reasons": list(artifact.trigger_reasons),
        "missing_evidence": list(artifact.missing_evidence),
        "warning_events": len(artifact.warning_events),
        "non_running_pods": pod_entries,
        "summary": artifact.evidence_summary,
        "rollout_status": rollout_entries,
        "pattern_details": artifact.pattern_details,
        "artifact_path": _relative_path(root_dir, artifact.artifact_path),
    }


def _serialize_proposal(proposal: HealthProposal, root_dir: Path) -> dict[str, object]:
    latest_status = proposal.lifecycle_history[-1]
    return {
        "proposal_id": proposal.proposal_id,
        "target": proposal.target,
        "confidence": proposal.confidence.value,
        "rationale": proposal.rationale,
        "expected_benefit": proposal.expected_benefit,
        "status": latest_status.status.value,
        "lifecycle_history": [entry.to_dict() for entry in proposal.lifecycle_history],
        "source_run_id": proposal.source_run_id,
        "artifact_path": _relative_path(root_dir, proposal.artifact_path),
        "review_artifact": _relative_path(root_dir, proposal.source_artifact_path),
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
) -> Path:
    assessment_map = {artifact.label: artifact for artifact in assessments}
    drilldown_map = _latest_drilldown_map(drilldowns)
    clusters = [
        _serialize_cluster(record, assessment_map, drilldown_map, output_dir)
        for record in records
    ]
    drilldown_entries = [
        _serialize_drilldown(artifact, output_dir)
        for artifact in sorted(drilldowns, key=lambda item: item.timestamp, reverse=True)
    ]
    latest_drilldown = drilldown_entries[0] if drilldown_entries else None
    proposals_data = [_serialize_proposal(proposal, output_dir) for proposal in proposals]
    drilldown_availability = _serialize_drilldown_availability(records, drilldown_map, output_dir)
    external_analysis_data = _serialize_external_analysis(external_analysis, output_dir)
    notification_history = _serialize_notification_history(notifications, output_dir)
    latest_assessment = _serialize_latest_assessment(assessments, output_dir)
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
    }
    index = {
        "run": run_entry,
        "fleet_status": _serialize_fleet_status(clusters),
        "clusters": clusters,
        "drilldowns": drilldown_entries,
        "latest_drilldown": latest_drilldown,
        "proposal_status_summary": _serialize_proposal_status_summary(proposals_data),
        "proposals": proposals_data,
        "drilldown_availability": drilldown_availability,
        "notification_history": notification_history,
        "external_analysis": external_analysis_data,
        "latest_assessment": latest_assessment,
    }
    index["run_stats"] = _build_run_stats(output_dir / "reviews")
    index_path = output_dir / "ui-index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index_path


def _relative_path(base: Path, target: object | None) -> str | None:
    if target is None:
        return None
    candidate = Path(str(target))
    try:
        return str(candidate.relative_to(base))
    except ValueError:
        return str(candidate)


def _latest_drilldown_map(drilldowns: Sequence[DrilldownArtifact]) -> dict[str, DrilldownArtifact]:
    mapping: dict[str, DrilldownArtifact] = {}
    for artifact in sorted(drilldowns, key=lambda item: item.timestamp, reverse=True):
        mapping.setdefault(artifact.label, artifact)
    return mapping


_RATING_ORDER = ("degraded", "healthy", "unknown")
_PROPOSAL_STATUS_ORDER = (
    "pending",
    "checked",
    "accepted",
    "rejected",
    "applied",
    "proposed",
    "replayed",
    "promoted",
)
_ANALYSIS_STATUS_ORDER = tuple(status.value for status in ExternalAnalysisStatus)
_NOTIFICATION_HISTORY_LIMIT = 20


def _serialize_fleet_status(clusters: Sequence[dict[str, object]]) -> dict[str, object]:
    counts: dict[str, int] = {}
    degraded: list[str] = []
    for cluster in clusters:
        rating = str(cluster.get("health_rating") or "unknown").lower()
        counts[rating] = counts.get(rating, 0) + 1
        if rating == "degraded":
            degraded.append(str(cluster.get("label")))
    ordered: list[dict[str, object]] = []
    seen: set[str] = set()
    for rating in _RATING_ORDER:
        if rating in counts:
            ordered.append({"rating": rating, "count": counts[rating]})
            seen.add(rating)
    for rating, count in sorted(counts.items()):
        if rating in seen:
            continue
        ordered.append({"rating": rating, "count": count})
    return {"rating_counts": ordered, "degraded_clusters": degraded}


def _serialize_proposal_status_summary(proposals: Sequence[dict[str, object]]) -> dict[str, object]:
    counts: dict[str, int] = {}
    for proposal in proposals:
        status = str(proposal.get("status") or "unknown").lower()
        counts[status] = counts.get(status, 0) + 1
    ordered: list[dict[str, object]] = []
    seen: set[str] = set()
    for status in _PROPOSAL_STATUS_ORDER:
        if status in counts:
            ordered.append({"status": status, "count": counts[status]})
            seen.add(status)
    for status, count in sorted(counts.items()):
        if status in seen:
            continue
        ordered.append({"status": status, "count": count})
    return {"status_counts": ordered}


def _serialize_drilldown_availability(
    records: Sequence[HealthSnapshotRecord],
    drilldown_map: Mapping[str, DrilldownArtifact],
    root_dir: Path,
) -> dict[str, object]:
    coverage: list[dict[str, object]] = []
    available = 0
    missing_labels: list[str] = []
    for record in sorted(records, key=lambda item: item.target.label):
        artifact = drilldown_map.get(record.target.label)
        if artifact:
            available += 1
            timestamp = artifact.timestamp.isoformat()
            path = _relative_path(root_dir, artifact.artifact_path)
            available_flag = True
        else:
            timestamp = None
            path = None
            missing_labels.append(record.target.label)
            available_flag = False
        coverage.append(
            {
                "label": record.target.label,
                "context": record.target.context,
                "available": available_flag,
                "timestamp": timestamp,
                "artifact_path": path,
            }
        )
    total = len(records)
    return {
        "total_clusters": total,
        "available": available,
        "missing": max(total - available, 0),
        "coverage": coverage,
        "missing_clusters": missing_labels,
    }


def _serialize_external_analysis(
    artifacts: Sequence[ExternalAnalysisArtifact],
    root_dir: Path,
) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    for artifact in sorted(artifacts, key=lambda item: item.timestamp, reverse=True):
        status = artifact.status.value
        counts[status] = counts.get(status, 0) + 1
        entries.append(
            {
                "tool_name": artifact.tool_name,
                "cluster_label": artifact.cluster_label,
                "status": status,
                "summary": artifact.summary,
                "findings": list(artifact.findings),
                "suggested_next_checks": list(artifact.suggested_next_checks),
                "timestamp": artifact.timestamp.isoformat(),
                "artifact_path": _relative_path(root_dir, artifact.artifact_path),
                "duration_ms": artifact.duration_ms,
                "provider": artifact.provider,
            }
        )
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


def _parse_optional_int(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int,)):  # keep ints as is
        return int(value)
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _parse_timestamp(value: object | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _build_llm_stats(external_analysis: dict[str, object]) -> dict[str, object]:
    artifacts = external_analysis.get("artifacts") or ()
    if not isinstance(artifacts, Sequence):
        artifacts = ()
    total_calls = 0
    successful_calls = 0
    failed_calls = 0
    durations: list[int] = []
    latest_timestamp: datetime | None = None
    latest_timestamp_str: str | None = None
    provider_counts: dict[str, dict[str, int]] = {}
    for entry in artifacts:
        if not isinstance(entry, Mapping):
            continue
        status = str(entry.get("status") or "").lower()
        if status not in ("success", "failed"):
            continue
        total_calls += 1
        if status == "success":
            successful_calls += 1
        if status == "failed":
            failed_calls += 1
        raw_timestamp = entry.get("timestamp")
        timestamp = _parse_timestamp(raw_timestamp)
        if timestamp:
            if latest_timestamp is None or timestamp > latest_timestamp:
                latest_timestamp = timestamp
                latest_timestamp_str = raw_timestamp if isinstance(raw_timestamp, str) else latest_timestamp_str
        duration = _parse_optional_int(entry.get("duration_ms"))
        if duration is not None:
            durations.append(duration)
        provider = str(entry.get("tool_name") or "unknown")
        counter = provider_counts.setdefault(provider, {"calls": 0, "failedCalls": 0})
        counter["calls"] += 1
        if status == "failed":
            counter["failedCalls"] += 1
    percentile_values: dict[str, int | None] = {
        "p50": None,
        "p95": None,
        "p99": None,
    }
    if durations:
        float_durations = [float(value) for value in durations]
        float_durations.sort()
        percentile_values["p50"] = _percentile_value(float_durations, 50)
        percentile_values["p95"] = _percentile_value(float_durations, 95)
        percentile_values["p99"] = _percentile_value(float_durations, 99)
    provider_breakdown = [
        {"provider": provider, "calls": data["calls"], "failedCalls": data["failedCalls"]}
        for provider, data in sorted(provider_counts.items())
    ]
    return {
        "totalCalls": total_calls,
        "successfulCalls": successful_calls,
        "failedCalls": failed_calls,
        "lastCallTimestamp": latest_timestamp_str,
        "p50LatencyMs": percentile_values["p50"],
        "p95LatencyMs": percentile_values["p95"],
        "p99LatencyMs": percentile_values["p99"],
        "providerBreakdown": provider_breakdown,
    }


def _serialize_notification_history(
    records: Sequence[NotificationRecord],
    root_dir: Path,
    limit: int = _NOTIFICATION_HISTORY_LIMIT,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    sorted_records = sorted(records, key=lambda item: item[0].timestamp, reverse=True)
    for artifact, path in sorted_records[:limit]:
        detail_entries = [
            {"label": str(key), "value": _stringify_notification_value(value)}
            for key, value in sorted(artifact.details.items())
        ]
        entries.append(
            {
                "kind": artifact.kind,
                "summary": artifact.summary,
                "timestamp": artifact.timestamp,
                "run_id": artifact.run_id,
                "cluster_label": artifact.cluster_label,
                "context": artifact.context,
                "details": detail_entries,
                "artifact_path": _relative_path(root_dir, path),
            }
        )
    return entries


def _stringify_notification_value(value: object | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def _serialize_latest_assessment(
    assessments: Sequence[HealthAssessmentArtifact],
    root_dir: Path,
) -> dict[str, object] | None:
    if not assessments:
        return None
    latest = max(assessments, key=lambda artifact: artifact.timestamp)
    return _serialize_assessment(latest, root_dir)


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
        except Exception:
            continue
        run_id = raw.get("run_id")
        timestamp = raw.get("timestamp")
        if not isinstance(run_id, str) or not isinstance(timestamp, str):
            continue
        try:
            finish = datetime.fromisoformat(timestamp)
        except ValueError:
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


def _percentile_value(values: list[float], percentile: float) -> int:
    if not values:
        return 0
    idx = math.ceil((percentile / 100) * len(values)) - 1
    idx = max(0, min(idx, len(values) - 1))
    return int(values[idx])


def _serialize_assessment(artifact: HealthAssessmentArtifact, root_dir: Path) -> dict[str, object]:
    data: dict[str, object] = dict(artifact.assessment or {})
    data.update(
        {
            "cluster_label": artifact.label,
            "context": artifact.context,
            "timestamp": artifact.timestamp.isoformat(),
            "health_rating": artifact.health_rating.value,
            "missing_evidence": list(artifact.missing_evidence),
            "artifact_path": _relative_path(root_dir, artifact.artifact_path),
            "snapshot_path": _relative_path(root_dir, artifact.snapshot_path),
        }
    )
    return data
