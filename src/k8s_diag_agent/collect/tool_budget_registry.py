"""Tool budget registry for managing tool-to-budget mappings.

This module provides the ToolBudgetRegistry class and singleton instance
for looking up budgets by tool identifier.

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-BUDGET-CONTRACT01
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .tool_budget_defaults import (
    KUBECTL_DESCRIBE_BUDGET,
    KUBECTL_EVENTS_BUDGET,
    KUBECTL_GET_BUDGET,
    KUBECTL_LOGS_BUDGET,
    KUBECTL_TOP_BUDGET,
)
from .tool_budget_types import ToolBudget, ToolBudgetValidationError

# =============================================================================
# Registry for Tool Budgets
# =============================================================================


@dataclass(frozen=True)
class ToolBudgetRegistry:
    """Registry mapping tool identifiers to their budgets."""

    budgets: dict[str, ToolBudget] = field(default_factory=dict)

    def register(self, tool_id: str, budget: ToolBudget) -> None:
        """Register a budget for a tool.
        
        Args:
            tool_id: Unique identifier for the tool
            budget: ToolBudget instance with configuration
            
        Raises:
            ToolBudgetValidationError: If the budget fails validation
        """
        is_valid, errors = budget.validate()
        if not is_valid:
            raise ToolBudgetValidationError(errors)
        object.__setattr__(self, "budgets", {**self.budgets, tool_id: budget})

    def get(self, tool_id: str) -> ToolBudget | None:
        """Get budget for a tool, or None if not registered.
        
        Args:
            tool_id: Unique identifier for the tool
            
        Returns:
            ToolBudget instance or None if not found
        """
        return self.budgets.get(tool_id)

    def get_or_raise(self, tool_id: str) -> ToolBudget:
        """Get budget for a tool, raising if not found.
        
        Args:
            tool_id: Unique identifier for the tool
            
        Returns:
            ToolBudget instance
            
        Raises:
            KeyError: If no budget is registered for the tool
        """
        budget = self.budgets.get(tool_id)
        if budget is None:
            raise KeyError(f"No budget registered for tool: {tool_id}")
        return budget


#: Global registry for tool budgets with default kubectl budgets pre-registered
_tool_budget_registry: ToolBudgetRegistry = ToolBudgetRegistry(
    budgets={
        "kubectl_describe": KUBECTL_DESCRIBE_BUDGET,
        "kubectl_logs": KUBECTL_LOGS_BUDGET,
        "kubectl_get": KUBECTL_GET_BUDGET,
        "kubectl_top": KUBECTL_TOP_BUDGET,
        "kubectl_events": KUBECTL_EVENTS_BUDGET,
    }
)


def get_tool_budget_registry() -> ToolBudgetRegistry:
    """Get the global tool budget registry.
    
    Returns:
        The singleton ToolBudgetRegistry instance
    """
    return _tool_budget_registry


__all__ = [
    "ToolBudgetRegistry",
    "get_tool_budget_registry",
]
