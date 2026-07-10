"""Core evidence artifact types.

This module contains:
- EvidenceKind, EvidenceRole, RedactionStatus enums
- EvidenceRoleCode, EvidenceKindCode: closed typed aliases for role/kind values
- Branded ID types: ArtifactId, EvidenceLinkId, SnapshotBundleId, ReviewPacketId,
  DiagnosisLoopPassId, ExternalAnalysisArtifactId
- Branded path/reference types: SafeRelativeArtifactPath, LocalArtifactPath,
  ExternalStorageRef, ReviewPacketStorageRef, LLMSafeArtifactRef

Design notes:
- EvidenceArtifacts are stored separately from incidents to keep incidents lightweight
- EvidenceLinks provide explicit traceability
- Multiple evidence types can be attached over the incident lifecycle
- Typed aliases (EvidenceRoleCode, EvidenceKindCode) provide closed contracts
  for string values crossing the domain/store boundary
- Branded NewType IDs prevent accidental mixing of different identifier types
- Branded path/reference types prevent mixing local paths, external refs, and safe refs
- Serialization (to_dict, API) still emits plain strings for compatibility

Branding rationale:
- ArtifactId: generic evidence artifact identifier
- EvidenceLinkId: unique link identifier between incident and artifact
- SnapshotBundleId: snapshot bundle artifact identifier
- ReviewPacketId: review packet artifact identifier
- DiagnosisLoopPassId: diagnosis loop pass artifact identifier
- ExternalAnalysisArtifactId: external analysis artifact identifier
- SafeRelativeArtifactPath: relative artifact path safe for review/LLM boundaries
- LocalArtifactPath: local filesystem path for implementation details
- ExternalStorageRef: external storage reference (s3://, gs://, etc.)
- ReviewPacketStorageRef: storage reference for review packet boundaries
- LLMSafeArtifactRef: artifact reference safe for LLM-facing outputs
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, NewType

# -----------------------------------------------------------------------------
# Branded ID types for evidence/artifact identifiers
# These NewType aliases prevent accidental mixing of different ID types.
# Runtime values are still plain strings; branding is enforced statically.
# -----------------------------------------------------------------------------

ArtifactId = NewType("ArtifactId", str)
EvidenceLinkId = NewType("EvidenceLinkId", str)
SnapshotBundleId = NewType("SnapshotBundleId", str)
ReviewPacketId = NewType("ReviewPacketId", str)
DiagnosisLoopPassId = NewType("DiagnosisLoopPassId", str)
ExternalAnalysisArtifactId = NewType("ExternalAnalysisArtifactId", str)

# -----------------------------------------------------------------------------
# Branded path/reference types for artifact storage references
# These NewType aliases prevent mixing of:
# - SafeRelativeArtifactPath: relative paths for review/LLM boundaries
# - LocalArtifactPath: local filesystem paths (implementation only)
# - ExternalStorageRef: external storage references (s3://, gs://, az://, https://)
# - ReviewPacketStorageRef: storage refs for review packet boundaries
# - LLMSafeArtifactRef: artifact refs safe for LLM-facing outputs
#
# ArtifactStorageRef is a union of the valid storage ref types that can be used
# as the type for EvidenceArtifact.storage_ref.
# -----------------------------------------------------------------------------

SafeRelativeArtifactPath = NewType("SafeRelativeArtifactPath", str)
LocalArtifactPath = NewType("LocalArtifactPath", str)
ExternalStorageRef = NewType("ExternalStorageRef", str)
ReviewPacketStorageRef = NewType("ReviewPacketStorageRef", str)
LLMSafeArtifactRef = NewType("LLMSafeArtifactRef", str)

# Allowed schemes for ExternalStorageRef (explicit allowlist)
_ALLOWED_EXTERNAL_STORAGE_SCHEMES = ("s3://", "gs://", "az://", "https://")

# Union type for storage_ref field - accepts all valid storage ref types
# This is used as the explicit type annotation for EvidenceArtifact.storage_ref
# to enforce that only branded path/reference types are used.
ArtifactStorageRef = SafeRelativeArtifactPath | LocalArtifactPath | ExternalStorageRef


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

    storage_ref is typed as ArtifactStorageRef (a union of SafeRelativeArtifactPath,
    LocalArtifactPath, ExternalStorageRef) to enforce branded type usage at the
    evidence boundary. Use constructor helpers like make_safe_relative_artifact_path()
    or make_external_storage_ref() to create valid storage_ref values.
    """

    artifact_id: ArtifactId
    kind: EvidenceKind
    storage_ref: ArtifactStorageRef
    content_hash: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    collected_by: str = "system"  # "system" or "user"
    redaction_status: RedactionStatus = RedactionStatus.RAW

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "kind": self.kind.value,
            "storage_ref": str(self.storage_ref),
            "content_hash": self.content_hash,
            "created_at": self.created_at.isoformat(),
            "collected_by": self.collected_by,
            "redaction_status": self.redaction_status.value,
        }


@dataclass(frozen=True)
class EvidenceLink:
    """Link between an incident and an evidence artifact."""

    incident_id: str
    artifact_id: ArtifactId
    role: EvidenceRole
    attached_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "artifact_id": str(self.artifact_id),
            "role": self.role.value,
            "attached_at": self.attached_at.isoformat(),
        }
