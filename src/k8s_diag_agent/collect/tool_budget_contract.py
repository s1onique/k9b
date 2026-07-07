"""Tool Budget Contract for k9b incident workbench.

This module is a compatibility facade that re-exports all public symbols
from the tool budget contract submodules. The actual implementation has been
split into focused modules:

- tool_budget_types: Core types, enums, and validation
- tool_budget_defaults: Default budgets for kubectl operations
- tool_budget_registry: Registry for looking up budgets by tool ID

For new code, import directly from submodules:
    from k8s_diag_agent.collect.tool_budget_types import ToolBudget
    from k8s_diag_agent.collect.tool_budget_defaults import KUBECTL_GET_BUDGET
    from k8s_diag_agent.collect.tool_budget_registry import get_tool_budget_registry

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-BUDGET-CONTRACT01
"""

# Re-export all public symbols from submodules
from .tool_budget_defaults import (
    FORBIDDEN_TOOL_BUDGET,
    KUBECTL_DESCRIBE_BUDGET,
    KUBECTL_EVENTS_BUDGET,
    KUBECTL_GET_BUDGET,
    KUBECTL_LOGS_BUDGET,
    KUBECTL_TOP_BUDGET,
)
from .tool_budget_registry import (
    ToolBudgetRegistry,
    get_tool_budget_registry,
)
from .tool_budget_types import (
    TOOL_BUDGET_SCHEMA_VERSION,
    ToolApprovalClass,
    ToolBudget,
    ToolBudgetEnforcementResult,
    ToolBudgetValidationError,
    ToolRedactionPolicy,
    validate_and_enforce_budget,
)

__all__ = [
    # Version
    "TOOL_BUDGET_SCHEMA_VERSION",
    # Enums
    "ToolApprovalClass",
    "ToolRedactionPolicy",
    # Core classes
    "ToolBudget",
    "ToolBudgetValidationError",
    "ToolBudgetEnforcementResult",
    "ToolBudgetRegistry",
    # Helpers
    "validate_and_enforce_budget",
    "get_tool_budget_registry",
    # Default budgets
    "KUBECTL_DESCRIBE_BUDGET",
    "KUBECTL_LOGS_BUDGET",
    "KUBECTL_GET_BUDGET",
    "KUBECTL_TOP_BUDGET",
    "KUBECTL_EVENTS_BUDGET",
    "FORBIDDEN_TOOL_BUDGET",
]
