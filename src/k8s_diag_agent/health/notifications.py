"""Notification payload helpers for future Mattermost integration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Mapping

from .adaptation import HealthProposal, ProposalEvaluation
from .loop import ComparisonTriggerArtifact, HealthAssessmentArtifact, HealthSnapshotRecord, UTC


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

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "details": dict(self.details),
            "run_id": self.run_id,
            "cluster_label": self.cluster_label,
            "context": self.context,
            "timestamp": self.timestamp,
        }


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
    return NotificationArtifact(
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
    return NotificationArtifact(
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
    return NotificationArtifact(
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
    return NotificationArtifact(
        kind="proposal-checked",
        summary=f"Proposal {proposal.proposal_id} replayed",
        details={
            "noise_reduction": evaluation.noise_reduction if evaluation else "n/a",
            "signal_loss": evaluation.signal_loss if evaluation else "n/a",
            "outcome": status,
        },
        run_id=proposal.source_run_id or proposal.proposal_id,
    )
