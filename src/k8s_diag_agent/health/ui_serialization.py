"""Pure serialization helpers for UI artifact output.

This module owns the canonical home for low-level artifact-to-dict conversions
used by write_health_ui_index. These functions are stateless and side-effect free.

Separated from ui.py to provide a crisp seam between serialization logic and
orchestration/planning/execution logic.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from ..external_analysis.artifact import ExternalAnalysisStatus
from .adaptation import HealthProposal
from .notifications import NotificationArtifact
from .ui_shared import _relative_path

if TYPE_CHECKING:
    from .loop import DrilldownArtifact, HealthAssessmentArtifact, HealthSnapshotRecord


# Ordering constants for consistent UI output
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
_LLM_ACTIVITY_LIMIT = 20
_NOTIFICATION_HISTORY_LIMIT = 20

NotificationRecord = tuple[NotificationArtifact, Path]


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
    data: dict[str, object] = {
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
    # Thread artifact_id for provenance/debugging surfaces (optional)
    if proposal.artifact_id:
        data["artifact_id"] = proposal.artifact_id
    return data


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


def _serialize_latest_assessment(
    assessments: Sequence[HealthAssessmentArtifact],
    root_dir: Path,
) -> dict[str, object] | None:
    if not assessments:
        return None
    latest = max(assessments, key=lambda artifact: artifact.timestamp)
    return _serialize_assessment(latest, root_dir)


def _stringify_notification_value(value: object | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


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
        entry: dict[str, object] = {
            "kind": artifact.kind,
            "summary": artifact.summary,
            "timestamp": artifact.timestamp,
            "run_id": artifact.run_id,
            "cluster_label": artifact.cluster_label,
            "context": artifact.context,
            "details": detail_entries,
            "artifact_path": _relative_path(root_dir, path),
        }
        # Thread artifact_id for provenance/debugging surfaces (optional)
        if artifact.artifact_id:
            entry["artifact_id"] = artifact.artifact_id
        entries.append(entry)
    return entries


# Re-export constants for consumers that need them
__all__ = [
    "_serialize_cluster",
    "_serialize_drilldown",
    "_serialize_proposal",
    "_serialize_fleet_status",
    "_serialize_proposal_status_summary",
    "_serialize_drilldown_availability",
    "_serialize_assessment",
    "_serialize_latest_assessment",
    "_serialize_notification_history",
    "_stringify_notification_value",
    "_RATING_ORDER",
    "_PROPOSAL_STATUS_ORDER",
    "_ANALYSIS_STATUS_ORDER",
    "_LLM_ACTIVITY_LIMIT",
    "_NOTIFICATION_HISTORY_LIMIT",
]
