"""Spill-to-artifact behavior for large tool outputs.

This module provides first-class spill-to-artifact functionality that:
- Captures raw tool output
- Compares against artifact_spill_threshold_bytes
- Writes oversized output to immutable artifacts
- Returns bounded projections with artifact references
- Tracks provenance for audit trail

Canonical pipeline:
    tool execution
    → raw output capture
    → size check against artifact_spill_threshold
    → if exceeded: write raw artifact, return bounded projection
    → if not exceeded: return bounded projection directly

Design principles:
- Raw artifacts are immutable (append-only)
- Spill decisions are deterministic based on budget
- Provenance is always tracked
- No silent data loss on spill

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-SPILL-ARTIFACT01
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..identity.artifact import new_artifact_id, write_append_only_json_artifact
from .tool_budget_contract import ToolBudget
from .tool_output_reducers import get_default_reducer
from .tool_reducer_protocol import ToolReducedOutput

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


# =============================================================================
# Content Type Detection
# =============================================================================


def detect_content_type(output: str | dict[str, Any]) -> ToolOutputContentType:
    """Detect content type from tool output.

    Args:
        output: Raw tool output (string or dict)

    Returns:
        Detected content type
    """
    if isinstance(output, dict):
        # Check for Kubernetes resource structure
        if "apiVersion" in output and "kind" in output:
            return ToolOutputContentType.MANIFEST
        # Check for metrics structure
        if "metrics" in output or "results" in output:
            return ToolOutputContentType.METRICS
        return ToolOutputContentType.JSON

    # String content analysis
    if not output:
        return ToolOutputContentType.UNKNOWN

    output_lower = output.lower().strip()

    # Check for common patterns
    if "event" in output_lower[:200]:
        return ToolOutputContentType.EVENT
    if any(marker in output_lower[:500] for marker in ["timestamp=", "level=", "severity="]):
        return ToolOutputContentType.LOG
    if output.strip().startswith("{"):
        try:
            json.loads(output)
            return ToolOutputContentType.JSON
        except (json.JSONDecodeError, ValueError):
            pass
    if "---" in output[:100] or "apiVersion:" in output[:100]:
        return ToolOutputContentType.MANIFEST

    return ToolOutputContentType.TEXT


# =============================================================================
# Core Spill Logic
# =============================================================================


def compute_size_bytes(content: str | dict[str, Any]) -> int:
    """Compute size in bytes of content."""
    if isinstance(content, dict):
        content = json.dumps(content)
    return len(content.encode("utf-8"))


def should_spill(
    raw_size: int,
    budget: ToolBudget,
    content_type: ToolOutputContentType,
) -> tuple[bool, SpillReason | None]:
    """Determine if content should spill to artifact.

    Args:
        raw_size: Raw content size in bytes
        budget: Tool budget with thresholds
        content_type: Detected content type

    Returns:
        Tuple of (should_spill, reason)
    """
    # Check against artifact spill threshold
    if raw_size > budget.artifact_spill_threshold_bytes:
        return True, SpillReason.SIZE_THRESHOLD

    # Check if content type suggests artifact storage
    if content_type in (ToolOutputContentType.MANIFEST, ToolOutputContentType.LOG, ToolOutputContentType.EVENT):
        # For structured content types, use a lower threshold
        content_threshold = budget.artifact_spill_threshold_bytes // 2
        if raw_size > content_threshold:
            return True, SpillReason.CONTENT_TYPE

    return False, None


# =============================================================================
# Artifact Writing
# =============================================================================


def write_raw_tool_artifact(
    artifact_dir: Path,
    source_tool: str,
    raw_content: str,
    content_type: ToolOutputContentType,
    budget_snapshot: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[RawToolOutputArtifact, Path]:
    """Write raw tool output to immutable artifact.

    Args:
        artifact_dir: Directory to write artifact
        source_tool: Tool identifier (e.g., "kubectl_get")
        raw_content: Raw output content
        content_type: Detected content type
        budget_snapshot: Optional budget state at capture time
        metadata: Optional additional metadata

    Returns:
        Tuple of (artifact, path)
    """
    artifact_id = new_artifact_id()
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    artifact = RawToolOutputArtifact(
        schema_version="1.0",
        artifact_id=artifact_id,
        source_tool=source_tool,
        content_type=content_type.value,
        raw_content=raw_content,
        size_bytes=len(raw_content.encode("utf-8")),
        timestamp=timestamp,
        budget_snapshot=budget_snapshot,
        metadata=metadata or {},
    )

    # Generate artifact path
    artifact_path = artifact_dir / f"tool-raw-{artifact_id}.json"

    # Write with immutability enforcement
    write_append_only_json_artifact(artifact_path, artifact.to_dict())

    return artifact, artifact_path


# =============================================================================
# Main Spill Function
# =============================================================================


def spill_tool_output(
    raw_output: str | dict[str, Any],
    budget: ToolBudget,
    source_tool: str,
    artifact_dir: Path | None = None,
    reducer_type: str = "auto",
    provenance: dict[str, Any] | None = None,
) -> ToolOutputSpillResult:
    """Process tool output with spill-to-artifact behavior.

    This is the canonical entry point for tool output handling:
    1. Detect content type
    2. Compute raw size
    3. Check against spill threshold
    4. If spill: write artifact, reduce content, return reference
    5. If no spill: reduce content, return bounded projection

    Args:
        raw_output: Raw tool output (string or dict)
        budget: Tool budget with thresholds
        source_tool: Tool identifier
        artifact_dir: Directory for raw artifacts (required if spill occurs)
        reducer_type: Type of reducer to use ("auto", "json", "line", "count")
        provenance: Optional provenance metadata

    Returns:
        ToolOutputSpillResult with spill decision and projections
    """
    # Detect content type
    content_type = detect_content_type(raw_output)

    # Compute sizes
    raw_size = compute_size_bytes(raw_output)
    budget_snapshot = budget.to_dict()

    # Build provenance
    prov = provenance or {}
    prov.update({
        "source_tool": source_tool,
        "content_type": content_type.value,
        "spill_schema_version": SPILL_SCHEMA_VERSION,
    })

    # Check spill conditions
    should_spill_result, spill_reason = should_spill(raw_size, budget, content_type)

    # Get appropriate reducer
    reducer = get_default_reducer(reducer_type)

    # Reduce the output to LLM-visible size
    try:
        reduced = reducer.reduce(
            raw_output,
            max_bytes=budget.llm_visible_bytes,
            source_tool=source_tool,
        )
    except Exception as exc:
        return ToolOutputSpillResult(
            spill_occurred=False,
            error=f"reduction_failed: {exc}",
            raw_size_bytes=raw_size,
            content_type=content_type.value,
            provenance=prov,
        )

    llm_visible_size = compute_size_bytes(json.dumps(reduced.llm_visible))

    # Handle spill if needed
    if should_spill_result:
        if artifact_dir is None:
            # Cannot spill without directory - return error
            return ToolOutputSpillResult(
                spill_occurred=False,
                error="spill_required_but_no_artifact_dir",
                raw_size_bytes=raw_size,
                projected_size_bytes=raw_size,
                llm_visible_size_bytes=llm_visible_size,
                content_type=content_type.value,
                llm_visible=reduced.llm_visible,
                provenance=prov,
            )

        # Write raw artifact
        raw_content = json.dumps(raw_output) if isinstance(raw_output, dict) else raw_output
        try:
            artifact, artifact_path = write_raw_tool_artifact(
                artifact_dir=artifact_dir,
                source_tool=source_tool,
                raw_content=raw_content,
                content_type=content_type,
                budget_snapshot=budget_snapshot,
            )
        except Exception as exc:
            return ToolOutputSpillResult(
                spill_occurred=False,
                error=f"artifact_write_failed: {exc}",
                raw_size_bytes=raw_size,
                projected_size_bytes=raw_size,
                llm_visible_size_bytes=llm_visible_size,
                content_type=content_type.value,
                llm_visible=reduced.llm_visible,
                provenance=prov,
            )

        return ToolOutputSpillResult(
            spill_occurred=True,
            spill_reason=spill_reason.value if spill_reason else None,
            raw_artifact_id=artifact.artifact_id,
            raw_artifact_path=str(artifact_path),
            raw_size_bytes=raw_size,
            projected_size_bytes=raw_size,
            llm_visible_size_bytes=llm_visible_size,
            content_type=content_type.value,
            llm_visible=reduced.llm_visible,
            provenance=prov,
        )

    # No spill needed
    return ToolOutputSpillResult(
        spill_occurred=False,
        raw_size_bytes=raw_size,
        projected_size_bytes=raw_size,
        llm_visible_size_bytes=llm_visible_size,
        content_type=content_type.value,
        llm_visible=reduced.llm_visible,
        provenance=prov,
    )


# =============================================================================
# Integration Helper
# =============================================================================


def create_tool_output_result(
    raw_output: str | dict[str, Any],
    budget: ToolBudget,
    source_tool: str,
    artifact_dir: Path | None = None,
) -> tuple[ToolOutputSpillResult, ToolReducedOutput]:
    """Create combined spill result and reduced output.

    This helper returns both the spill result (for artifact tracking)
    and the reduced output (for LLM consumption).

    Args:
        raw_output: Raw tool output
        budget: Tool budget
        source_tool: Tool identifier
        artifact_dir: Directory for artifacts

    Returns:
        Tuple of (spill_result, reduced_output)
    """
    spill_result = spill_tool_output(
        raw_output=raw_output,
        budget=budget,
        source_tool=source_tool,
        artifact_dir=artifact_dir,
    )

    # Convert spill result to reduced output
    reduced_output = ToolReducedOutput(
        schema_version=spill_result.schema_version,
        source_tool=source_tool,
        raw_artifact_id=spill_result.raw_artifact_id,
        reduction_policy="spill_or_direct",
        counts={
            "raw_items": spill_result.raw_size_bytes,
            "visible_items": spill_result.llm_visible_size_bytes,
            "omitted_items": max(0, spill_result.raw_size_bytes - spill_result.llm_visible_size_bytes),
        },
        truncated=spill_result.spill_occurred,
        llm_visible=spill_result.llm_visible,
        error=spill_result.error,
    )

    return spill_result, reduced_output


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Version
    "SPILL_SCHEMA_VERSION",
    # Enums
    "SpillReason",
    "ToolOutputContentType",
    # Core result schema
    "ToolOutputSpillResult",
    # Raw artifact schema
    "RawToolOutputArtifact",
    # Core functions
    "detect_content_type",
    "should_spill",
    "compute_size_bytes",
    "write_raw_tool_artifact",
    "spill_tool_output",
    # Helpers
    "create_tool_output_result",
]
