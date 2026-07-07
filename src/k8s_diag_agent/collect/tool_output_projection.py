"""Tool output projection adapter for bounded LLM-visible output.

This module provides the canonical entry point for projecting tool output
through the budget and spill infrastructure:

1. Resolve ToolBudget from registry or use explicit budget
2. Execute or receive raw read-only output
3. Pass through spill_tool_output() for reduction and spill decision
4. Return bounded projection for LLM-visible context

Reference: ACT-K9B-HOLMESGPT-TOOL-INFRA-PRODUCTION-SEAM01
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .tool_budget_registry import get_tool_budget_registry
from .tool_budget_types import ToolBudget
from .tool_spill_pipeline import spill_tool_output
from .tool_spill_types import ToolOutputSpillResult

# Safe default budget for unknown tools (fail-closed)
_UNKNOWN_TOOL_BUDGET = ToolBudget(
    timeout_seconds=10,
    stdout_bytes=8192,  # 8KB
    stderr_bytes=2048,  # 2KB
    llm_visible_bytes=4096,  # 4KB - conservative
    artifact_spill_threshold_bytes=8192,  # 8KB
    approval_class="read_only",
    schema_name="unknown_tool_output",
)


def project_read_only_tool_output(
    *,
    source_tool: str,
    raw_output: str | dict[str, Any],
    artifact_dir: Path | None = None,
    budget: ToolBudget | None = None,
    reducer_type: str = "auto",
    provenance: dict[str, Any] | None = None,
) -> ToolOutputSpillResult:
    """Project read-only tool output through budget and spill infrastructure.

    This is the canonical entry point for bounded tool output handling:
    1. Resolve budget from registry or use explicit budget
    2. Pass raw output through spill_tool_output()
    3. Return bounded projection for LLM-visible context

    Rules:
    - explicit budget wins
    - otherwise resolve from ToolBudgetRegistry
    - unknown tool returns fail-closed bounded error (never unbounded)

    Args:
        source_tool: Tool identifier (e.g., "kubectl_get")
        raw_output: Raw tool output (string or dict)
        artifact_dir: Directory for raw artifacts (required if spill occurs)
        budget: Explicit budget (takes precedence over registry lookup)
        reducer_type: Type of reducer to use ("auto", "json", "line", "count")
        provenance: Optional provenance metadata

    Returns:
        ToolOutputSpillResult with spill decision and bounded projection.
        Never returns unbounded raw output.
    """
    # Resolve budget: explicit > registry > safe default
    budget_source: str

    if budget is not None:
        resolved_budget = budget
        budget_source = "explicit"
    else:
        registry = get_tool_budget_registry()
        budget_from_registry = registry.get(source_tool)
        if budget_from_registry is None:
            # Fail-closed: use conservative safe default for unknown tools
            resolved_budget = _UNKNOWN_TOOL_BUDGET
            budget_source = "unknown_tool_safe_default"
        else:
            resolved_budget = budget_from_registry
            budget_source = "registry"

    # Build provenance with source tracking
    prov = provenance.copy() if provenance else {}
    prov.update({
        "budget_source": budget_source,
        "projection_schema_version": "1.0",
    })

    # Pass through spill pipeline
    return spill_tool_output(
        raw_output=raw_output,
        budget=resolved_budget,
        source_tool=source_tool,
        artifact_dir=artifact_dir,
        reducer_type=reducer_type,
        provenance=prov,
    )


__all__ = [
    "project_read_only_tool_output",
]
