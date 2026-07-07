"""Unit tests for tool_budget_registry module.

Tests the tool budget registry and lookup functionality.
Reference: ACT-K9B-HOLMESGPT-TOOL-INFRA-SPLIT01
"""
from __future__ import annotations

import pytest

from k8s_diag_agent.collect.tool_budget_registry import (
    ToolBudgetRegistry,
    get_tool_budget_registry,
)
from k8s_diag_agent.collect.tool_budget_types import (
    ToolBudget,
    ToolBudgetValidationError,
)


class TestToolBudgetRegistry:
    def test_registry_has_defaults(self) -> None:
        """Global registry should have default budgets."""
        registry = get_tool_budget_registry()
        assert registry.get("kubectl_describe") is not None
        assert registry.get("kubectl_logs") is not None
        assert registry.get("kubectl_get") is not None
        assert registry.get("kubectl_top") is not None
        assert registry.get("kubectl_events") is not None

    def test_registry_get_unknown_returns_none(self) -> None:
        """Unknown tool should return None."""
        registry = get_tool_budget_registry()
        assert registry.get("unknown_tool") is None

    def test_registry_get_or_raise_unknown(self) -> None:
        """get_or_raise should raise for unknown tool."""
        registry = get_tool_budget_registry()
        with pytest.raises(KeyError):
            registry.get_or_raise("unknown_tool")

    def test_registry_register_valid_budget(self) -> None:
        """Registering valid budget should succeed."""
        registry = ToolBudgetRegistry()
        budget = ToolBudget(schema_name="custom_tool")
        registry.register("custom", budget)
        assert registry.get("custom") == budget

    def test_registry_register_invalid_budget_raises(self) -> None:
        """Registering invalid budget should raise."""
        registry = ToolBudgetRegistry()
        budget = ToolBudget(timeout_seconds=0)
        with pytest.raises(ToolBudgetValidationError):
            registry.register("invalid", budget)
