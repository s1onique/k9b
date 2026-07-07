"""Unit tests for tool_budget_defaults module.

Tests default budgets for kubectl operations.
Reference: ACT-K9B-HOLMESGPT-TOOL-INFRA-SPLIT01
"""
from __future__ import annotations


from k8s_diag_agent.collect.tool_budget_defaults import (
    FORBIDDEN_TOOL_BUDGET,
    KUBECTL_DESCRIBE_BUDGET,
    KUBECTL_EVENTS_BUDGET,
    KUBECTL_GET_BUDGET,
    KUBECTL_LOGS_BUDGET,
    KUBECTL_TOP_BUDGET,
)


class TestDefaultBudgets:
    def test_kubectl_describe_budget_valid(self) -> None:
        """kubectl describe budget should be valid."""
        is_valid, errors = KUBECTL_DESCRIBE_BUDGET.validate()
        assert is_valid, errors

    def test_kubectl_logs_budget_valid(self) -> None:
        """kubectl logs budget should be valid."""
        is_valid, errors = KUBECTL_LOGS_BUDGET.validate()
        assert is_valid, errors

    def test_kubectl_get_budget_valid(self) -> None:
        """kubectl get budget should be valid."""
        is_valid, errors = KUBECTL_GET_BUDGET.validate()
        assert is_valid, errors

    def test_kubectl_top_budget_valid(self) -> None:
        """kubectl top budget should be valid."""
        is_valid, errors = KUBECTL_TOP_BUDGET.validate()
        assert is_valid, errors

    def test_kubectl_events_budget_valid(self) -> None:
        """kubectl events budget should be valid."""
        is_valid, errors = KUBECTL_EVENTS_BUDGET.validate()
        assert is_valid, errors

    def test_forbidden_budget_intentionally_invalid(self) -> None:
        """Forbidden budget is intentionally invalid (sentinel value).
        
        The FORBIDDEN_TOOL_BUDGET has timeout=0 which violates normal
        validation rules. This is by design - it's a sentinel value
        that should never be used for actual execution.
        """
        is_valid, errors = FORBIDDEN_TOOL_BUDGET.validate()
        assert not is_valid  # Expected to be invalid
        assert any("timeout" in e for e in errors)
