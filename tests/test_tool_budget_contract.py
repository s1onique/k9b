"""Unit tests for tool_budget_contract module.

This module is a compatibility facade that re-exports all public symbols
from the tool budget contract submodules.

Reference: ACT-K9B-HOLMESGPT-TOOL-INFRA-SPLIT01
"""

# Import from the facade module to verify backward compatibility
from k8s_diag_agent.collect.tool_budget_contract import (
    FORBIDDEN_TOOL_BUDGET,
    KUBECTL_DESCRIBE_BUDGET,
    KUBECTL_EVENTS_BUDGET,
    KUBECTL_GET_BUDGET,
    KUBECTL_LOGS_BUDGET,
    KUBECTL_TOP_BUDGET,
    TOOL_BUDGET_SCHEMA_VERSION,
    ToolApprovalClass,
    ToolBudget,
    ToolBudgetEnforcementResult,
    ToolBudgetRegistry,
    ToolBudgetValidationError,
    ToolRedactionPolicy,
    get_tool_budget_registry,
    validate_and_enforce_budget,
)


# Re-export all tests from submodules for backward compatibility
# Tests are implemented in:
# - test_tool_budget_contract_types.py
# - test_tool_budget_contract_defaults.py
# - test_tool_budget_contract_registry.py
