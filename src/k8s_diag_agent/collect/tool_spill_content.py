"""Spill artifact content detection and size computation.

This module contains content type detection and size calculation logic:
- detect_content_type: Determines content type from tool output
- compute_size_bytes: Computes byte size of content
- should_spill: Determines if content should spill to artifact

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-SPILL-ARTIFACT01
"""
from __future__ import annotations

import json
from typing import Any

from .tool_budget_types import ToolBudget
from .tool_spill_types import SpillReason, ToolOutputContentType

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
# Size Computation
# =============================================================================


def compute_size_bytes(content: str | dict[str, Any]) -> int:
    """Compute size in bytes of content.

    Args:
        content: Content to measure (string or dict)

    Returns:
        Size in bytes
    """
    if isinstance(content, dict):
        content = json.dumps(content)
    return len(content.encode("utf-8"))


# =============================================================================
# Spill Decision Logic
# =============================================================================


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


__all__ = [
    "detect_content_type",
    "compute_size_bytes",
    "should_spill",
]
