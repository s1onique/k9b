"""Evidence artifact models for incident management.

This module contains:
- EvidenceArtifact: immutable evidence blob
- EvidenceLink: relationship between incident and artifact
- EvidenceKind, EvidenceRole, RedactionStatus enums

Design notes:
- EvidenceArtifacts are stored separately from incidents to keep incidents lightweight
- EvidenceLinks provide explicit traceability
- Multiple evidence types can be attached over the incident lifecycle
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class EvidenceKind(StrEnum):
    """Kind of evidence artifact."""

    SNAPSHOT_BUNDLE = "snapshot_bundle"
    REVIEW_PACKET = "review_packet"
    LOG_EXCERPT = "log_excerpt"
    METRIC_WINDOW = "metric_window"
    TRACE = "trace"
    RUN_SUMMARY = "run_summary"
    EXTERNAL_ANALYSIS = "external_analysis"


class EvidenceRole(StrEnum):
    """Role of evidence in the incident."""

    PRIMARY = "primary"
    SUPPORTING = "supporting"
    SNAPSHOT = "snapshot"
    REVIEW_PACKET = "review_packet"
    DEBUG = "debug"


class RedactionStatus(StrEnum):
    """Redaction status of the artifact."""

    RAW = "raw"
    REDACTED = "redacted"
    SAFE_FOR_REVIEW = "safe_for_review"


@dataclass(frozen=True)
class EvidenceArtifact:
    """Immutable evidence artifact attached to an incident.

    Evidence is stored separately from the incident to keep the incident
    lightweight and to support multiple evidence types over time.
    """

    artifact_id: str
    kind: EvidenceKind
    storage_ref: str
    content_hash: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    collected_by: str = "system"  # "system" or "user"
    redaction_status: RedactionStatus = RedactionStatus.RAW

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind.value,
            "storage_ref": self.storage_ref,
            "content_hash": self.content_hash,
            "created_at": self.created_at.isoformat(),
            "collected_by": self.collected_by,
            "redaction_status": self.redaction_status.value,
        }


@dataclass(frozen=True)
class EvidenceLink:
    """Link between an incident and an evidence artifact."""

    incident_id: str
    artifact_id: str
    role: EvidenceRole
    attached_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "artifact_id": self.artifact_id,
            "role": self.role.value,
            "attached_at": self.attached_at.isoformat(),
        }


__all__ = [
    "EvidenceArtifact",
    "EvidenceKind",
    "EvidenceLink",
    "EvidenceRole",
    "RedactionStatus",
]
