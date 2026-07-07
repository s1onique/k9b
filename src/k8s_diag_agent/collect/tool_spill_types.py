"""Spill artifact types and schemas.

This module contains the foundational types for spill-to-artifact behavior:
- Schema version
- Enums (SpillReason, ToolOutputContentType)
- Result dataclasses (ToolOutputSpillResult, RawToolOutputArtifact)

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-SPILL-ARTIFACT01
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# =============================================================================
# Schema version
# =============================================================================

SPILL_SCHEMA_VERSION = "1.0"

# =============================================================================
# Enums
# =============================================================================


class SpillReason(StrEnum):
    """Reason for spilling to artifact."""

    #: Content exceeded artifact_spill_threshold_bytes
    SIZE_THRESHOLD = "size_threshold"

    #: Content exceeded llm_visible_bytes
    LLM_VISIBLE_EXCEEDED = "llm_visible_exceeded"

    #: Deprecated: use LLM_VISIBLE_EXCEEDED. Kept for import compatibility.
    LLMR_VISIBLE_EXCEEDED = "llm_visible_exceeded"

    #: Content was explicitly flagged for artifact storage
    EXPLICIT_FLAG = "explicit_flag"

    #: Content type indicated artifact storage was appropriate
    CONTENT_TYPE = "content_type"


# =============================================================================
# Tool Output Content Types
# =============================================================================


class ToolOutputContentType(StrEnum):
    """Content type of tool output."""

    #: Plain text output
    TEXT = "text"

    #: JSON-structured output
    JSON = "json"

    #: Kubernetes resource manifest
    MANIFEST = "manifest"

    #: Log output
    LOG = "log"

    #: Event output
    EVENT = "event"

    #: Metrics output
    METRICS = "metrics"

    #: Unknown/unstructured
    UNKNOWN = "unknown"


# =============================================================================
# Spill Result Schema
# =============================================================================


@dataclass(frozen=True)
class ToolOutputSpillResult:
    """Result of spill-to-artifact decision and execution.

    This schema represents the canonical output from the spill decision:
    - Whether spill occurred
    - If spill occurred: artifact reference and raw artifact ID
    - LLM-visible projection
    - Provenance tracking
    """

    schema_version: str = SPILL_SCHEMA_VERSION
    spill_occurred: bool = False
    spill_reason: str | None = None
    raw_artifact_id: str | None = None
    raw_artifact_path: str | None = None
    raw_size_bytes: int = 0
    projected_size_bytes: int = 0
    llm_visible_size_bytes: int = 0
    content_type: str = ToolOutputContentType.UNKNOWN.value
    llm_visible: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for artifact storage."""
        return {
            "schema_version": self.schema_version,
            "spill_occurred": self.spill_occurred,
            "spill_reason": self.spill_reason,
            "raw_artifact_id": self.raw_artifact_id,
            "raw_artifact_path": self.raw_artifact_path,
            "raw_size_bytes": self.raw_size_bytes,
            "projected_size_bytes": self.projected_size_bytes,
            "llm_visible_size_bytes": self.llm_visible_size_bytes,
            "content_type": self.content_type,
            "llm_visible": self.llm_visible,
            "provenance": self.provenance,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolOutputSpillResult:
        """Deserialize from dict."""
        return cls(
            schema_version=data.get("schema_version", SPILL_SCHEMA_VERSION),
            spill_occurred=data.get("spill_occurred", False),
            spill_reason=data.get("spill_reason"),
            raw_artifact_id=data.get("raw_artifact_id"),
            raw_artifact_path=data.get("raw_artifact_path"),
            raw_size_bytes=data.get("raw_size_bytes", 0),
            projected_size_bytes=data.get("projected_size_bytes", 0),
            llm_visible_size_bytes=data.get("llm_visible_size_bytes", 0),
            content_type=data.get("content_type", ToolOutputContentType.UNKNOWN.value),
            llm_visible=data.get("llm_visible", {}),
            provenance=data.get("provenance", {}),
            error=data.get("error"),
        )

    @property
    def has_raw_artifact(self) -> bool:
        """Check if raw artifact was written."""
        return self.raw_artifact_id is not None

    @property
    def spill_ratio(self) -> float:
        """Calculate ratio of raw to projected size."""
        if self.projected_size_bytes == 0:
            return 0.0
        return self.raw_size_bytes / self.projected_size_bytes


# =============================================================================
# Raw Tool Output Artifact Schema
# =============================================================================


@dataclass(frozen=True)
class RawToolOutputArtifact:
    """Immutable artifact for raw tool output storage.

    This artifact captures the complete raw output before any reduction.
    It serves as the source of truth for audit and replay scenarios.
    """

    schema_version: str = "1.0"
    artifact_id: str = ""
    source_tool: str = ""
    content_type: str = ToolOutputContentType.UNKNOWN.value
    raw_content: str = ""
    size_bytes: int = 0
    timestamp: str = ""
    budget_snapshot: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Serialize to dict for artifact storage."""
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "source_tool": self.source_tool,
            "content_type": self.content_type,
            "raw_content": self.raw_content,
            "size_bytes": self.size_bytes,
            "timestamp": self.timestamp,
            "budget_snapshot": self.budget_snapshot,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RawToolOutputArtifact:
        """Deserialize from dict."""
        return cls(
            schema_version=data.get("schema_version", "1.0"),
            artifact_id=data.get("artifact_id", ""),
            source_tool=data.get("source_tool", ""),
            content_type=data.get("content_type", ToolOutputContentType.UNKNOWN.value),
            raw_content=data.get("raw_content", ""),
            size_bytes=data.get("size_bytes", 0),
            timestamp=data.get("timestamp", ""),
            budget_snapshot=data.get("budget_snapshot"),
            metadata=data.get("metadata", {}),
        )


__all__ = [
    "SPILL_SCHEMA_VERSION",
    "SpillReason",
    "ToolOutputContentType",
    "ToolOutputSpillResult",
    "RawToolOutputArtifact",
]
