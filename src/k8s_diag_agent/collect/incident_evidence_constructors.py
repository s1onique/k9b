"""Constructor helpers for evidence artifact types.

This module provides typed construction functions for evidence artifact types.
Use these at construction seams to ensure branded type safety.

All constructors validate input and raise ValueError for invalid values.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from k8s_diag_agent.collect.incident_evidence_types import (
    ArtifactId,
    DiagnosisLoopPassId,
    ExternalAnalysisArtifactId,
    ExternalStorageRef,
    LLMSafeArtifactRef,
    LocalArtifactPath,
    ReviewPacketId,
    ReviewPacketStorageRef,
    SafeRelativeArtifactPath,
    SnapshotBundleId,
)

# Allowed schemes for ExternalStorageRef (explicit allowlist)
_ALLOWED_EXTERNAL_STORAGE_SCHEMES = ("s3://", "gs://", "az://", "https://")


# -----------------------------------------------------------------------------
# Branded ID type constructors
# Use these to create typed ID values at construction seams.
# -----------------------------------------------------------------------------

def make_artifact_id(value: str) -> ArtifactId:
    """Convert a string to an ArtifactId."""
    return ArtifactId(value)


def make_snapshot_bundle_id(value: str) -> SnapshotBundleId:
    """Convert a string to a SnapshotBundleId."""
    return SnapshotBundleId(value)


def make_review_packet_id(value: str) -> ReviewPacketId:
    """Convert a string to a ReviewPacketId."""
    return ReviewPacketId(value)


def make_diagnosis_loop_pass_id(value: str) -> DiagnosisLoopPassId:
    """Convert a string to a DiagnosisLoopPassId."""
    return DiagnosisLoopPassId(value)


def make_external_analysis_artifact_id(value: str) -> ExternalAnalysisArtifactId:
    """Convert a string to an ExternalAnalysisArtifactId."""
    return ExternalAnalysisArtifactId(value)


# -----------------------------------------------------------------------------
# Branded path/reference type constructors with validation
# Use these to create typed path/reference values at construction seams.
# -----------------------------------------------------------------------------

def make_safe_relative_artifact_path(value: str) -> SafeRelativeArtifactPath:
    """Convert a string to a SafeRelativeArtifactPath.

    Safe relative artifact paths are allowed in review packets, case files,
    and LLM-facing outputs. They must NOT contain:
    - Empty string
    - Leading whitespace or trailing whitespace
    - Absolute paths (starting with /)
    - Home directory references (starting with ~)
    - Path traversal (.. components)
    - URL schemes (s3://, gs://, https://, file://, etc.)
    - Windows backslashes

    Args:
        value: The path string to validate

    Returns:
        SafeRelativeArtifactPath if valid

    Raises:
        ValueError: If the path is empty, absolute, or contains traversal/URLs
    """
    if not value or value.strip() != value:
        raise ValueError(
            f"Invalid SafeRelativeArtifactPath: '{value}' is empty or has whitespace"
        )
    # Reject URL schemes
    if "://" in value:
        raise ValueError(
            f"Invalid SafeRelativeArtifactPath: '{value}' contains a URL scheme"
        )
    # Reject absolute paths and home directory refs
    if value.startswith(("/", "~")):
        raise ValueError(
            f"Invalid SafeRelativeArtifactPath: '{value}' is absolute or home-relative"
        )
    # Reject Windows-style paths
    if "\\" in value:
        raise ValueError(
            f"Invalid SafeRelativeArtifactPath: '{value}' contains Windows backslashes"
        )
    # Check for traversal using PurePosixPath
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(
            f"Invalid SafeRelativeArtifactPath: '{value}' is absolute or contains traversal"
        )
    return SafeRelativeArtifactPath(value)


def make_local_artifact_path(value: str | Path) -> LocalArtifactPath:
    """Convert a value to a LocalArtifactPath.

    Local artifact paths are local filesystem paths used for implementation
    details (reading/writing artifacts). They may be absolute or relative.

    This type should NOT be used in review packets, case files, or LLM outputs.

    Args:
        value: The path string or Path object

    Returns:
        LocalArtifactPath
    """
    if isinstance(value, Path):
        return LocalArtifactPath(str(value))
    return LocalArtifactPath(value)


def make_external_storage_ref(value: str) -> ExternalStorageRef:
    """Convert a string to an ExternalStorageRef.

    External storage refs are references to external storage systems like
    S3, GCS, Azure Blob, or HTTPS URLs. They must use an allowed scheme.

    Allowed schemes: s3://, gs://, az://, https://

    Args:
        value: The storage reference string (e.g., s3://bucket/path)

    Returns:
        ExternalStorageRef

    Raises:
        ValueError: If the value doesn't contain an allowed URL scheme
    """
    if "://" not in value:
        raise ValueError(
            f"Invalid ExternalStorageRef: '{value}' must contain a URL scheme (s3://, gs://, az://, https://)"
        )
    # Check against allowed schemes
    scheme_found = None
    for scheme in _ALLOWED_EXTERNAL_STORAGE_SCHEMES:
        if value.startswith(scheme):
            scheme_found = scheme
            break

    if scheme_found is None:
        raise ValueError(
            f"Invalid ExternalStorageRef: '{value}' uses unsupported scheme. "
            f"Allowed: {', '.join(_ALLOWED_EXTERNAL_STORAGE_SCHEMES)}"
        )

    return ExternalStorageRef(value)


def make_review_packet_storage_ref(value: str) -> ReviewPacketStorageRef:
    """Convert a string to a ReviewPacketStorageRef.

    Review packet storage refs are storage references safe for review packet
    boundaries. They must be safe relative artifact paths.

    Args:
        value: The storage reference string

    Returns:
        ReviewPacketStorageRef

    Raises:
        ValueError: If the value is not a valid safe relative path
    """
    # Validate using safe relative path rules
    if not value or value.strip() != value:
        raise ValueError(
            f"Invalid ReviewPacketStorageRef: '{value}' is empty or has whitespace"
        )
    if "://" in value:
        raise ValueError(
            f"Invalid ReviewPacketStorageRef: '{value}' contains a URL scheme"
        )
    if value.startswith(("/", "~")):
        raise ValueError(
            f"Invalid ReviewPacketStorageRef: '{value}' is absolute or home-relative"
        )
    if "\\" in value:
        raise ValueError(
            f"Invalid ReviewPacketStorageRef: '{value}' contains Windows backslashes"
        )
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(
            f"Invalid ReviewPacketStorageRef: '{value}' is absolute or contains traversal"
        )
    return ReviewPacketStorageRef(value)


def make_llm_safe_artifact_ref(value: str) -> LLMSafeArtifactRef:
    """Convert a string to an LLMSafeArtifactRef.

    LLM-safe artifact refs are artifact references safe for LLM-facing outputs.
    They must be safe relative artifact paths (not local absolute paths).

    Args:
        value: The artifact reference string

    Returns:
        LLMSafeArtifactRef

    Raises:
        ValueError: If the value is not a valid safe relative path
    """
    # Validate using safe relative path rules
    if not value or value.strip() != value:
        raise ValueError(
            f"Invalid LLMSafeArtifactRef: '{value}' is empty or has whitespace"
        )
    if "://" in value:
        raise ValueError(
            f"Invalid LLMSafeArtifactRef: '{value}' contains a URL scheme"
        )
    if value.startswith(("/", "~")):
        raise ValueError(
            f"Invalid LLMSafeArtifactRef: '{value}' is absolute or home-relative"
        )
    if "\\" in value:
        raise ValueError(
            f"Invalid LLMSafeArtifactRef: '{value}' contains Windows backslashes"
        )
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(
            f"Invalid LLMSafeArtifactRef: '{value}' is absolute or contains traversal"
        )
    return LLMSafeArtifactRef(value)


def make_llm_safe_artifact_ref_from_safe_path(path: SafeRelativeArtifactPath) -> LLMSafeArtifactRef:
    """Convert a SafeRelativeArtifactPath to an LLMSafeArtifactRef.

    This is the preferred way to create LLM-safe refs from safe relative paths.

    Args:
        path: A SafeRelativeArtifactPath

    Returns:
        LLMSafeArtifactRef
    """
    return LLMSafeArtifactRef(str(path))
