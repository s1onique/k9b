"""Utilities that build a compact artifact index for UI consumers."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .adaptation import HealthProposal

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
    drilldown_path = _relative_path(root_dir, drilldown.artifact_path if drilldown else None)
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
        "artifact_paths": {
            "snapshot": snapshot_path,
            "assessment": assessment_path,
            "drilldown": drilldown_path,
        },
    }


def _serialize_drilldown(artifact: DrilldownArtifact, root_dir: Path) -> dict[str, object]:
    return {
        "label": artifact.label,
        "context": artifact.context,
        "cluster_id": artifact.cluster_id,
        "trigger_reasons": list(artifact.trigger_reasons),
        "warning_events": len(artifact.warning_events),
        "non_running_pods": artifact.non_running_pods,
        "summary": artifact.evidence_summary,
        "rollout_status": artifact.rollout_status,
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


def write_health_ui_index(
    output_dir: Path,
    run_id: str,
    run_label: str,
    collector_version: str,
    records: Sequence[HealthSnapshotRecord],
    assessments: Sequence[HealthAssessmentArtifact],
    drilldowns: Sequence[DrilldownArtifact],
    proposals: Sequence[HealthProposal],
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
    index = {
        "run": {
            "run_id": run_id,
            "run_label": run_label,
            "timestamp": datetime.now(UTC).isoformat(),
            "collector_version": collector_version,
            "cluster_count": len(clusters),
            "drilldown_count": len(drilldowns),
            "proposal_count": len(proposals_data),
        },
        "fleet_status": _serialize_fleet_status(clusters),
        "clusters": clusters,
        "drilldowns": drilldown_entries,
        "latest_drilldown": latest_drilldown,
        "proposal_status_summary": _serialize_proposal_status_summary(proposals_data),
        "proposals": proposals_data,
    }
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
