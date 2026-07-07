"""Spill artifact pipeline.

This module contains the main spill pipeline functions:
- spill_tool_output: Main entry point for tool output handling with spill behavior
- create_tool_output_result: Creates combined spill result and reduced output

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-SPILL-ARTIFACT01
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .tool_budget_types import ToolBudget
from .tool_output_reducers import get_default_reducer
from .tool_reducer_protocol import ToolReducedOutput
from .tool_spill_content import (
    compute_size_bytes,
    detect_content_type,
    should_spill,
)
from .tool_spill_types import (
    SPILL_SCHEMA_VERSION,
    ToolOutputSpillResult,
)
from .tool_spill_writer import write_raw_tool_artifact

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


__all__ = [
    "spill_tool_output",
    "create_tool_output_result",
]
