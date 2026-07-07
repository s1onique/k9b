"""Canonical schema for tool output projection metadata.

This module defines the stable contract for projection metadata emitted by
incident collectors (collect_pods, collect_events). Before adding more collectors,
this schema ensures consistent metadata shape.

Reference: ACT-K9B-HOLMESGPT-TOOL-PROJECTION-CONTRACT01

## Artifact Path Policy

**Decision: raw_artifact_path is NOT persisted in IncidentEvidenceBundle.**

Rationale:
- `raw_artifact_path` contains local absolute filesystem paths
- IncidentEvidenceBundle may be uploaded/shared to external systems
- Exposing local paths creates information leakage risk
- `raw_artifact_id` provides sufficient artifact reference for audit/debug

Internal-only usage (not persisted):
- The spill pipeline uses `raw_artifact_path` for local artifact operations
- The canonical metadata only includes `raw_artifact_id` for external reference

If artifact path is needed internally, access it from ToolOutputSpillResult directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# =============================================================================
# Schema version
# =============================================================================

PROJECTION_METADATA_SCHEMA_VERSION = "1.0"


# =============================================================================
# Canonical Metadata Schema
# =============================================================================


@dataclass(frozen=True)
class ToolProjectionMetadata:
    """Canonical projection metadata for tool output spill/budget decisions.

    This schema represents the stable contract for projection metadata:
    - schema_version: Schema version for forward compatibility
    - source_tool: Source tool identifier (required, non-empty)
    - spill_occurred: Whether content was spilled to artifact
    - spill_reason: Reason for spill (if occurred)
    - raw_artifact_id: Artifact reference ID (if spilled)
    - raw_size_bytes: Raw tool output size in bytes (non-negative)
    - llm_visible_size_bytes: LLM-visible projection size in bytes (non-negative)
    - content_type: Content type (e.g., "json", "manifest")
    - error: Error message if bounded error occurred
    - provenance: Provenance tracking dict

    Artifact path policy:
    - raw_artifact_path is NOT included to prevent local path leakage
    - Use raw_artifact_id for artifact reference in shared contexts
    """

    schema_version: str
    source_tool: str
    spill_occurred: bool
    spill_reason: str | None
    raw_artifact_id: str | None
    raw_size_bytes: int
    llm_visible_size_bytes: int
    content_type: str
    error: str | None
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for IncidentEvidenceBundle storage.

        Returns a JSON-compatible dict with all required fields.
        Does NOT include raw_artifact_path per artifact path policy.
        """
        return {
            "schema_version": self.schema_version,
            "source_tool": self.source_tool,
            "spill_occurred": self.spill_occurred,
            "spill_reason": self.spill_reason,
            "raw_artifact_id": self.raw_artifact_id,
            "raw_size_bytes": self.raw_size_bytes,
            "llm_visible_size_bytes": self.llm_visible_size_bytes,
            "content_type": self.content_type,
            "error": self.error,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolProjectionMetadata:
        """Deserialize from dict."""
        return cls(
            schema_version=data.get("schema_version", PROJECTION_METADATA_SCHEMA_VERSION),
            source_tool=data.get("source_tool", ""),
            spill_occurred=data.get("spill_occurred", False),
            spill_reason=data.get("spill_reason"),
            raw_artifact_id=data.get("raw_artifact_id"),
            raw_size_bytes=data.get("raw_size_bytes", 0),
            llm_visible_size_bytes=data.get("llm_visible_size_bytes", 0),
            content_type=data.get("content_type", "unknown"),
            error=data.get("error"),
            provenance=data.get("provenance", {}),
        )


# =============================================================================
# Public builder function
# =============================================================================


def build_tool_projection_metadata(
    spill_result: Any,
    source_tool: str,
) -> ToolProjectionMetadata:
    """Build canonical projection metadata from ToolOutputSpillResult.

    This is the canonical entry point for building projection metadata.
    It transforms the internal spill result into the stable external contract.

    Args:
        spill_result: ToolOutputSpillResult from project_read_only_tool_output()
        source_tool: Source tool identifier (e.g., "kubectl_get", "kubectl_events")

    Returns:
        ToolProjectionMetadata with stable schema

    Raises:
        TypeError: If spill_result is not compatible with the expected interface
    """
    # Extract fields using getattr for compatibility
    schema_version = getattr(spill_result, "schema_version", PROJECTION_METADATA_SCHEMA_VERSION)
    spill_occurred = getattr(spill_result, "spill_occurred", False)
    spill_reason = getattr(spill_result, "spill_reason", None)
    raw_artifact_id = getattr(spill_result, "raw_artifact_id", None)
    raw_size_bytes = getattr(spill_result, "raw_size_bytes", 0)
    llm_visible_size_bytes = getattr(spill_result, "llm_visible_size_bytes", 0)
    content_type = getattr(spill_result, "content_type", "unknown")
    error = getattr(spill_result, "error", None)
    provenance = getattr(spill_result, "provenance", {})

    # Validate source_tool
    if not source_tool or not isinstance(source_tool, str):
        raise ValueError(f"source_tool must be a non-empty string, got: {source_tool!r}")

    # Validate non-negative integers
    if raw_size_bytes < 0:
        raise ValueError(f"raw_size_bytes must be non-negative, got: {raw_size_bytes}")
    if llm_visible_size_bytes < 0:
        raise ValueError(f"llm_visible_size_bytes must be non-negative, got: {llm_visible_size_bytes}")

    return ToolProjectionMetadata(
        schema_version=schema_version,
        source_tool=source_tool,
        spill_occurred=spill_occurred,
        spill_reason=spill_reason,
        raw_artifact_id=raw_artifact_id,
        raw_size_bytes=raw_size_bytes,
        llm_visible_size_bytes=llm_visible_size_bytes,
        content_type=content_type,
        error=error,
        provenance=provenance,
    )


# =============================================================================
# Legacy compatibility wrapper
# =============================================================================


def _build_projection_metadata(
    spill_result: Any,
    source_tool: str,
) -> dict[str, Any]:
    """Build projection metadata dict (legacy compatibility wrapper).

    DEPRECATED: Use build_tool_projection_metadata() instead.

    This wrapper maintains backward compatibility for existing callers
    while delegating to the canonical implementation.

    Args:
        spill_result: ToolOutputSpillResult from project_read_only_tool_output()
        source_tool: Source tool identifier

    Returns:
        Metadata dict matching the previous _build_projection_metadata interface
    """
    metadata = build_tool_projection_metadata(spill_result, source_tool)
    return metadata.to_dict()


__all__ = [
    "PROJECTION_METADATA_SCHEMA_VERSION",
    "ToolProjectionMetadata",
    "build_tool_projection_metadata",
    "_build_projection_metadata",  # Deprecated compatibility wrapper
]
