"""Evidence artifact models for incident management.

This module provides backward-compatible imports from submodules:
- incident_evidence_types: Core types, enums, and models
- incident_evidence_llm_safe: LLM-safe evidence types and helpers

For new code, import directly from submodules for better tree-shaking:
    from k8s_diag_agent.collect.incident_evidence_types import (
        ArtifactId, EvidenceArtifact, EvidenceKind, ...
    )
    from k8s_diag_agent.collect.incident_evidence_llm_safe import (
        RedactedEvidenceSummary, make_redacted_evidence_text, ...
    )
"""

from __future__ import annotations

# Import constructor helpers from this module
from k8s_diag_agent.collect.incident_evidence_constructors import (
    make_artifact_id,
    make_diagnosis_loop_pass_id,
    make_external_analysis_artifact_id,
    make_external_storage_ref,
    make_llm_safe_artifact_ref,
    make_llm_safe_artifact_ref_from_safe_path,
    make_local_artifact_path,
    make_review_packet_id,
    make_review_packet_storage_ref,
    make_safe_relative_artifact_path,
    make_snapshot_bundle_id,
)

# Import everything from LLM-safe module for backward compatibility
from k8s_diag_agent.collect.incident_evidence_llm_safe import (
    RedactedEvidenceSummary,
    RedactedEvidenceText,
    SafeEvidenceExcerpt,
    evidence_artifact_to_llm_safe_summary,
    make_redacted_evidence_text,
    make_safe_evidence_excerpt,
)

# Import everything from types module for backward compatibility
from k8s_diag_agent.collect.incident_evidence_types import (
    ArtifactId,
    ArtifactStorageRef,
    DiagnosisLoopPassId,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceKindCode,
    EvidenceLink,
    EvidenceLinkId,
    EvidenceRole,
    EvidenceRoleCode,
    ExternalAnalysisArtifactId,
    ExternalStorageRef,
    LLMSafeArtifactRef,
    LocalArtifactPath,
    RedactionStatus,
    ReviewPacketId,
    ReviewPacketStorageRef,
    SafeRelativeArtifactPath,
    SnapshotBundleId,
)

__all__ = [
    # Branded ID types
    "ArtifactId",
    "ArtifactStorageRef",
    "DiagnosisLoopPassId",
    "EvidenceLinkId",
    "ExternalAnalysisArtifactId",
    "ReviewPacketId",
    "SnapshotBundleId",
    # Branded path/reference types
    "ExternalStorageRef",
    "LLMSafeArtifactRef",
    "LocalArtifactPath",
    "ReviewPacketStorageRef",
    "SafeRelativeArtifactPath",
    # LLM-safe evidence types
    "RedactedEvidenceSummary",
    "RedactedEvidenceText",
    "SafeEvidenceExcerpt",
    # ID conversion helpers
    "make_artifact_id",
    "make_diagnosis_loop_pass_id",
    "make_external_analysis_artifact_id",
    "make_review_packet_id",
    "make_snapshot_bundle_id",
    # Path/reference conversion helpers
    "make_external_storage_ref",
    "make_llm_safe_artifact_ref",
    "make_llm_safe_artifact_ref_from_safe_path",
    "make_local_artifact_path",
    "make_review_packet_storage_ref",
    "make_safe_relative_artifact_path",
    # LLM-safe evidence helpers
    "evidence_artifact_to_llm_safe_summary",
    "make_redacted_evidence_text",
    "make_safe_evidence_excerpt",
    # Models
    "EvidenceArtifact",
    "EvidenceKind",
    "EvidenceKindCode",
    "EvidenceLink",
    "EvidenceRole",
    "EvidenceRoleCode",
    "RedactionStatus",
]
