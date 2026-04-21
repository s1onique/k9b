"""Notification payload helpers for future Mattermost integration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..external_analysis.artifact import ExternalAnalysisArtifact
from ..identity.artifact import new_artifact_id
from .adaptation import HealthProposal, ProposalEvaluation

if TYPE_CHECKING:
    from .loop import ComparisonTriggerArtifact, HealthAssessmentArtifact, HealthSnapshotRecord


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


@dataclass(frozen=True)
class NotificationArtifact:
    kind: str
    summary: str
    details: Mapping[str, object]
    run_id: str | None = None
    cluster_label: str | None = None
    context: str | None = None
    timestamp: str = field(default_factory=_timestamp)
    artifact_id: str | None = None  # None for legacy artifacts, auto-generated for new artifacts

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "kind": self.kind,
            "summary": self.summary,
            "details": dict(self.details),
            "run_id": self.run_id,
            "cluster_label": self.cluster_label,
            "context": self.context,
            "timestamp": self.timestamp,
        }
        # Include artifact_id when present (backward compat: legacy artifacts without it)
        if self.artifact_id is not None:
            data["artifact_id"] = self.artifact_id
        return data

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> NotificationArtifact:
        if not isinstance(raw, Mapping):
            raise ValueError("Notification artifact must be a mapping")
        details_raw = raw.get("details") or {}
        details = dict(details_raw) if isinstance(details_raw, Mapping) else {}
        timestamp = str(raw.get("timestamp")) if raw.get("timestamp") else _timestamp()
        # Parse artifact_id for backward compatibility (legacy artifacts without it)
        artifact_id_value = raw.get("artifact_id")
        parsed_artifact_id: str | None = None
        if artifact_id_value is not None and isinstance(artifact_id_value, str) and artifact_id_value:
            parsed_artifact_id = artifact_id_value
        return cls(
            kind=str(raw.get("kind") or ""),
            summary=str(raw.get("summary") or ""),
            details=details,
            run_id=str(raw.get("run_id")) if raw.get("run_id") else None,
            cluster_label=str(raw.get("cluster_label")) if raw.get("cluster_label") else None,
            context=str(raw.get("context")) if raw.get("context") else None,
            timestamp=timestamp,
            artifact_id=parsed_artifact_id,
        )


def make_notification_artifact(
    kind: str,
    summary: str,
    details: Mapping[str, object],
    *,
    run_id: str | None = None,
    cluster_label: str | None = None,
    context: str | None = None,
) -> NotificationArtifact:
    """Create a new notification artifact with an immutable artifact_id.

    This is the preferred factory for creating notification artifacts.
    Legacy artifacts without artifact_id remain readable via from_dict().
    """
    return NotificationArtifact(
        kind=kind,
        summary=summary,
        details=details,
        run_id=run_id,
        cluster_label=cluster_label,
        context=context,
        timestamp=_timestamp(),
        artifact_id=new_artifact_id(),
    )


def write_notification_artifact(directory: Path, artifact: NotificationArtifact) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{artifact.timestamp}-{artifact.kind}.json"
    path = directory / filename
    path.write_text(json.dumps(artifact.to_dict(), indent=2), encoding="utf-8")
    return path


def build_degraded_health_notification(
    run_id: str,
    record: HealthSnapshotRecord,
    assessment: HealthAssessmentArtifact,
) -> NotificationArtifact:
    return make_notification_artifact(
        kind="degraded-health",
        summary=f"{record.target.label} degraded ({assessment.health_rating.value})",
        details={
            "warnings": assessment.missing_evidence,
            "cluster": record.target.label,
            "context": record.target.context,
        },
        run_id=run_id,
        cluster_label=record.target.label,
        context=record.target.context,
    )


def build_suspicious_comparison_notification(
    trigger: ComparisonTriggerArtifact,
) -> NotificationArtifact:
    return make_notification_artifact(
        kind="suspicious-comparison",
        summary=f"Suspicious comparison {trigger.primary_label} vs {trigger.secondary_label}",
        details={
            "reasons": trigger.trigger_reasons,
            "differences": trigger.comparison_summary,
            "intent": trigger.comparison_intent,
        },
        run_id=trigger.run_id,
        cluster_label=trigger.primary_label,
        context=trigger.primary,
    )


def build_proposal_created_notification(run_id: str, proposal: HealthProposal) -> NotificationArtifact:
    return make_notification_artifact(
        kind="proposal-created",
        summary=f"Proposal {proposal.proposal_id} for {proposal.target}",
        details={
            "target": proposal.target,
            "rationale": proposal.rationale,
            "confidence": proposal.confidence.value,
        },
        run_id=run_id,
    )


def build_proposal_checked_notification(
    proposal: HealthProposal, evaluation: ProposalEvaluation | None
) -> NotificationArtifact:
    status = evaluation.test_outcome if evaluation else "not evaluated"
    return make_notification_artifact(
        kind="proposal-checked",
        summary=f"Proposal {proposal.proposal_id} replayed",
        details={
            "noise_reduction": evaluation.noise_reduction if evaluation else "n/a",
            "signal_loss": evaluation.signal_loss if evaluation else "n/a",
            "outcome": status,
        },
        run_id=proposal.source_run_id or proposal.proposal_id,
    )


def build_external_analysis_notification(
    artifact: ExternalAnalysisArtifact,
) -> NotificationArtifact:
    return make_notification_artifact(
        kind="external-analysis",
        summary=f"External analysis {artifact.tool_name} for {artifact.cluster_label}: {artifact.status.value}",
        details={
            "tool": artifact.tool_name,
            "cluster": artifact.cluster_label,
            "status": artifact.status.value,
            "summary": artifact.summary,
        },
        run_id=artifact.run_id,
        cluster_label=artifact.cluster_label,
        context=artifact.cluster_label,
    )
