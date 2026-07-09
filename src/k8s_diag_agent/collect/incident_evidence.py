"""Evidence artifact models for incident management.

This module contains:
- EvidenceArtifact: immutable evidence blob
- EvidenceLink: relationship between incident and artifact
- EvidenceKind, EvidenceRole, RedactionStatus enums
- EvidenceRoleCode, EvidenceKindCode: closed typed aliases for role/kind values

Design notes:
- EvidenceArtifacts are stored separately from incidents to keep incidents lightweight
- EvidenceLinks provide explicit traceability
- Multiple evidence types can be attached over the incident lifecycle
- Typed aliases (EvidenceRoleCode, EvidenceKindCode) provide closed contracts
  for string values crossing the domain/store boundary
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

# -----------------------------------------------------------------------------
# Closed typed aliases for evidence role/kind values
# EvidenceRoleCode mirrors EvidenceRole.
# EvidenceKindCode contains EvidenceKind plus legacy/production extended kind
# literals found at evidence seams (e.g., read_only_kubernetes, backing_pods).
# -----------------------------------------------------------------------------

# NOTE: EvidenceRoleCode mirrors EvidenceRole enum values.
# EvidenceRole enum is used for runtime model; EvidenceRoleCode provides
# the closed seam contract for evidence role strings at boundaries.
EvidenceRoleCode = Literal[
    "primary",
    "supporting",
    "snapshot",
    "review_packet",
    "debug",
]

# EvidenceKindCode mirrors EvidenceKind enum values.
# EvidenceKind enum is used for runtime model; EvidenceKindCode provides
# the closed seam contract for evidence kind strings at boundaries.
# NOTE: Only include evidence kinds that are genuinely evidence artifacts,
# not Kubernetes object kinds (Pod, Deployment, etc.) or unrelated domain values.
EvidenceKindCode = Literal[
    "snapshot_bundle",
    "review_packet",
    "log_excerpt",
    "metric_window",
    "trace",
    "run_summary",
    "external_analysis",
]


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
    "EvidenceKindCode",
    "EvidenceLink",
    "EvidenceRole",
    "EvidenceRoleCode",
    "RedactionStatus",
]
