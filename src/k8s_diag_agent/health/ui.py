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


def _serialize_cluster(record: HealthSnapshotRecord, assessment_map: Mapping[str, HealthAssessmentArtifact | None]) -> dict[str, object]:
    assessment = assessment_map.get(record.target.label)
    warning_events = len(record.snapshot.health_signals.warning_events)
    pod_counts = record.snapshot.health_signals.pod_counts
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
    }


def _serialize_drilldown(artifact: DrilldownArtifact) -> dict[str, object]:
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
    }


def _serialize_proposal(proposal: HealthProposal) -> dict[str, object]:
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
    clusters: list[dict[str, object]] = []
    assessment_map = {artifact.label: artifact for artifact in assessments}
    for record in records:
        clusters.append(_serialize_cluster(record, assessment_map))
    drilldown_entries = [ _serialize_drilldown(artifact) for artifact in sorted(drilldowns, key=lambda item: item.timestamp, reverse=True) ]
    latest_drilldown = drilldown_entries[0] if drilldown_entries else None
    proposals_data = [_serialize_proposal(proposal) for proposal in proposals]
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
        "clusters": clusters,
        "drilldowns": drilldown_entries,
        "latest_drilldown": latest_drilldown,
        "proposals": proposals_data,
    }
    index_path = output_dir / "ui-index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index_path
