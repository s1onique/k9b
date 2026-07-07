"""Tool Reducer Protocol for k9b incident workbench.

This module defines the canonical output schema for all tool output reducers.
It is a standalone module to keep the protocol definition small and focused.

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-OUTPUT-REDUCERS01
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# =============================================================================
# Schema version
# =============================================================================

REDUCER_SCHEMA_VERSION = "1.0"


# =============================================================================
# Reducer Output Schema
# =============================================================================


@dataclass(frozen=True)
class ToolReducedOutput:
    """Canonical reduced output shape for LLM-visible tool results.

    This is the schema that all reducers must produce.
    It includes:
    - Schema version for forward compatibility
    - Source tool identifier
    - Raw artifact reference
    - Reduction policy applied
    - Count tracking (raw, visible, omitted)
    - Truncation and redaction flags
    - LLM-visible content

    The model sees bounded projections with explicit metadata about
    what was omitted, truncated, transformed, or redacted.
    """

    schema_version: str = REDUCER_SCHEMA_VERSION
    source_tool: str = ""
    raw_artifact_id: str | None = None
    reduction_policy: str = "none"
    counts: dict[str, int] = field(
        default_factory=lambda: {
            "raw_items": 0,
            "visible_items": 0,
            "omitted_items": 0,
        }
    )
    truncated: bool = False
    redacted: bool = False
    llm_visible: dict[str, Any] = field(default_factory=dict)
    truncation_reason: str | None = None
    redaction_count: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for artifact storage."""
        return {
            "schema_version": self.schema_version,
            "source_tool": self.source_tool,
            "raw_artifact_id": self.raw_artifact_id,
            "reduction_policy": self.reduction_policy,
            "counts": self.counts,
            "truncated": self.truncated,
            "redacted": self.redacted,
            "llm_visible": self.llm_visible,
            "truncation_reason": self.truncation_reason,
            "redaction_count": self.redaction_count,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolReducedOutput:
        """Deserialize from dict."""
        return cls(
            schema_version=data.get("schema_version", REDUCER_SCHEMA_VERSION),
            source_tool=data.get("source_tool", ""),
            raw_artifact_id=data.get("raw_artifact_id"),
            reduction_policy=data.get("reduction_policy", "none"),
            counts=data.get("counts", {"raw_items": 0, "visible_items": 0, "omitted_items": 0}),
            truncated=data.get("truncated", False),
            redacted=data.get("redacted", False),
            llm_visible=data.get("llm_visible", {}),
            truncation_reason=data.get("truncation_reason"),
            redaction_count=data.get("redaction_count", 0),
            error=data.get("error"),
        )

    @property
    def is_error(self) -> bool:
        """Check if this is an error result."""
        return self.error is not None

    @property
    def has_omissions(self) -> bool:
        """Check if any items were omitted."""
        return self.counts.get("omitted_items", 0) > 0

    @property
    def omission_ratio(self) -> float:
        """Calculate fraction of items omitted."""
        raw = self.counts.get("raw_items", 0)
        if raw == 0:
            return 0.0
        return self.counts.get("omitted_items", 0) / raw


# =============================================================================
# Reducer Interface
# =============================================================================


class ToolOutputReducer:
    """Base interface for tool output reducers.

    All reducers must:
    1. Accept raw output and budget constraints
    2. Return ToolReducedOutput with bounded LLM-visible content
    3. Preserve counts (raw, visible, omitted)
    4. Set truncation/redaction flags appropriately
    5. Be deterministic (same input → same output)
    """

    def reduce(
        self,
        raw_output: str | dict[str, Any],
        *,
        max_bytes: int,
        source_tool: str,
        raw_artifact_id: str | None = None,
    ) -> ToolReducedOutput:
        """Reduce raw output to bounded LLM-visible projection.

        Args:
            raw_output: The raw tool output (string or dict)
            max_bytes: Maximum bytes allowed in LLM-visible output
            source_tool: Identifier for the source tool
            raw_artifact_id: Optional reference to raw artifact

        Returns:
            ToolReducedOutput with bounded projection and provenance metadata
        """
        raise NotImplementedError("Subclasses must implement reduce()")


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "REDUCER_SCHEMA_VERSION",
    "ToolReducedOutput",
    "ToolOutputReducer",
]
