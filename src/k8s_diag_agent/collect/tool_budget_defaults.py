"""Default budgets for common tool types.

This module provides pre-configured ToolBudget instances for kubectl operations.
These defaults can be used directly or as templates for custom budgets.

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-BUDGET-CONTRACT01
"""
from __future__ import annotations

from .tool_budget_types import (
    ToolApprovalClass,
    ToolBudget,
)

# =============================================================================
# Default Budgets for Common Tool Types
# =============================================================================


#: Default budget for kubectl describe operations
KUBECTL_DESCRIBE_BUDGET = ToolBudget(
    timeout_seconds=30,
    stdout_bytes=131072,  # 128KB
    stderr_bytes=8192,    # 8KB
    llm_visible_bytes=16384,  # 16KB
    artifact_spill_threshold_bytes=32768,  # 32KB
    approval_class=ToolApprovalClass.READ_ONLY.value,
    schema_name="kubectl_describe_output",
)

#: Default budget for kubectl logs operations
KUBECTL_LOGS_BUDGET = ToolBudget(
    timeout_seconds=30,
    stdout_bytes=262144,  # 256KB
    stderr_bytes=4096,    # 4KB
    llm_visible_bytes=32768,  # 32KB
    artifact_spill_threshold_bytes=65536,  # 64KB
    approval_class=ToolApprovalClass.READ_ONLY.value,
    schema_name="kubectl_logs_output",
)

#: Default budget for kubectl get operations
KUBECTL_GET_BUDGET = ToolBudget(
    timeout_seconds=20,
    stdout_bytes=65536,  # 64KB
    stderr_bytes=4096,  # 4KB
    llm_visible_bytes=8192,  # 8KB
    artifact_spill_threshold_bytes=16384,  # 16KB
    approval_class=ToolApprovalClass.READ_ONLY.value,
    schema_name="kubectl_get_output",
)

#: Default budget for kubectl top operations
KUBECTL_TOP_BUDGET = ToolBudget(
    timeout_seconds=30,
    stdout_bytes=32768,  # 32KB
    stderr_bytes=4096,   # 4KB
    llm_visible_bytes=8192,  # 8KB
    artifact_spill_threshold_bytes=16384,  # 16KB
    approval_class=ToolApprovalClass.READ_ONLY.value,
    schema_name="kubectl_top_output",
)

#: Budget for events retrieval (usually small)
KUBECTL_EVENTS_BUDGET = ToolBudget(
    timeout_seconds=20,
    stdout_bytes=49152,  # 48KB
    stderr_bytes=2048,   # 2KB
    llm_visible_bytes=12288,  # 12KB
    artifact_spill_threshold_bytes=24576,  # 24KB
    approval_class=ToolApprovalClass.READ_ONLY.value,
    schema_name="kubectl_events_output",
)


# =============================================================================
# Special Budgets
# =============================================================================


#: Budget for forbidden operations (always rejected).
#:
#: DESIGN NOTE: This budget intentionally violates normal validation rules
#: (timeout_seconds=0) to ensure the tool is never executed. It is a sentinel
#: value used to mark tools that must never run regardless of configuration.
#: When registered in ToolBudgetRegistry, validation will fail as expected.
#: This is by design - the FORBIDDEN budget should only be used as a marker,
#: not as a valid budget for execution.
FORBIDDEN_TOOL_BUDGET = ToolBudget(
    timeout_seconds=0,  # Intentionally invalid - prevents execution
    memory_bytes=None,
    stdout_bytes=0,
    stderr_bytes=0,
    llm_visible_bytes=0,
    artifact_spill_threshold_bytes=0,
    approval_class=ToolApprovalClass.FORBIDDEN.value,
    schema_name="forbidden",
)


__all__ = [
    "KUBECTL_DESCRIBE_BUDGET",
    "KUBECTL_LOGS_BUDGET",
    "KUBECTL_GET_BUDGET",
    "KUBECTL_TOP_BUDGET",
    "KUBECTL_EVENTS_BUDGET",
    "FORBIDDEN_TOOL_BUDGET",
]
