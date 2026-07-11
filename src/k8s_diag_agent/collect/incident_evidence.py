"""Evidence artifact models for incident management.

This module provides backward-compatible imports from submodules:
- incident_evidence_types: Core types, enums, and models (canonical source)
- incident_evidence_redaction: Privacy-state types and raw-to-redacted-to-LLM-safe pipeline
- incident_evidence_llm_safe: LLM-safe evidence types and helpers

NOTE: This module is a compatibility facade only. The canonical sources are:
- incident_evidence_types.py: Core type definitions (ArtifactId, EvidenceRole, EvidenceKind, etc.)
- incident_evidence_redaction.py: Privacy-state types and projection pipeline
- incident_evidence_llm_safe.py: LLM-safe evidence helpers

Privacy-state hierarchy:
- RawEvidenceText: unprocessed evidence text
- RedactedEvidenceText: text after canonical redaction (NOT inherently LLM-safe)
- LLMSafeEvidenceText: text validated to satisfy LLM-safe policy
- SafeEvidenceExcerpt: bounded excerpt from LLMSafeEvidenceText

For new code, import directly from submodules for better tree-shaking:
    from k8s_diag_agent.collect.incident_evidence_types import (
        ArtifactId, EvidenceArtifact, EvidenceKind, ...
    )
    from k8s_diag_agent.collect.incident_evidence_redaction import (
        RawEvidenceText, RedactedEvidenceText, LLMSafeEvidenceText,
        SafeEvidenceExcerpt, redact_evidence_text, approve_redacted_evidence_text,
        project_raw_evidence_text_for_llm, make_safe_evidence_excerpt,
        UnsafeEvidenceTextError, SAFE_OMISSION_MARKER,
    )
    from k8s_diag_agent.collect.incident_evidence_llm_safe import (
        RedactedEvidenceSummary, evidence_artifact_to_llm_safe_summary,
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

# Import LLM-safe helpers from incident_evidence_llm_safe (backward compatibility)
from k8s_diag_agent.collect.incident_evidence_llm_safe import (
    RedactedEvidenceSummary,
    evidence_artifact_to_llm_safe_summary,
    make_redacted_evidence_text,
)
from k8s_diag_agent.collect.incident_evidence_llm_safe import (
    make_safe_evidence_excerpt as make_safe_evidence_excerpt_from_llm_safe,
)

# Import privacy-state types and pipeline from incident_evidence_redaction
from k8s_diag_agent.collect.incident_evidence_redaction import (
    # Safe omission
    SAFE_OMISSION_MARKER,
    LLMSafeEvidenceText,
    # Privacy-state types
    RawEvidenceText,
    RedactedEvidenceText,
    SafeEvidenceExcerpt,
    # Exception
    UnsafeEvidenceTextError,
    # Production API
    approve_redacted_evidence_text,
    project_raw_evidence_text_for_llm,
    redact_evidence_text,
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


def make_safe_evidence_excerpt(
    value: LLMSafeEvidenceText | str,
    *,
    max_chars: int | None = None,
) -> SafeEvidenceExcerpt:
    """Create a bounded excerpt from LLM-safe evidence text.

    This function delegates to incident_evidence_llm_safe.make_safe_evidence_excerpt
    for backward compatibility.

    Args:
        value: The LLM-safe text (or str for backward compatibility)
        max_chars: Maximum character limit for the excerpt. Default is 500 chars
                   if not specified (backward-compatible default).

    Returns:
        SafeEvidenceExcerpt

    Raises:
        ValueError: If the value is empty
    """
    return make_safe_evidence_excerpt_from_llm_safe(value, max_chars=max_chars)


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
    # Privacy-state types (from incident_evidence_redaction)
    "RawEvidenceText",
    "RedactedEvidenceText",
    "LLMSafeEvidenceText",
    "SafeEvidenceExcerpt",
    # Safe omission
    "SAFE_OMISSION_MARKER",
    # Exception
    "UnsafeEvidenceTextError",
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
    # Production pipeline helpers
    "approve_redacted_evidence_text",
    "project_raw_evidence_text_for_llm",
    "redact_evidence_text",
    # Models
    "EvidenceArtifact",
    "EvidenceKind",
    "EvidenceKindCode",
    "EvidenceLink",
    "EvidenceRole",
    "EvidenceRoleCode",
    "RedactedEvidenceSummary",
    "RedactionStatus",
]
