"""Budget enforcement for the diagnosis loop runtime.

This module provides enforce_budgets() which checks hard budget limits
BEFORE any execution happens.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
    LoopStopReason,
)

from .runtime_state import LoopRuntimeState

if TYPE_CHECKING:
    pass


def enforce_budgets(
    policy: DiagnosisLoopPolicy,
    runtime_state: LoopRuntimeState,
    elapsed_seconds: float,
) -> tuple[bool, LoopStopReason | None]:
    """Enforce hard budget limits BEFORE execution.
    
    Returns:
        Tuple of (exceeded, stop_reason)
        - If exceeded=True, NO checks should be executed
        - stop_reason contains the reason if exceeded
    """
    # Check pass index against max_passes
    if runtime_state.pass_index > policy.max_passes:
        return True, LoopStopReason.MAX_PASSES_REACHED

    # Check total checks against max_total_checks
    if runtime_state.total_checks_executed >= policy.max_total_checks:
        return True, LoopStopReason.MAX_CHECKS_REACHED

    # Check checks proposed this pass against max_checks_per_pass
    # (This is approximate since we don't know exact count until planning)
    
    # Check model calls against max_model_calls
    if runtime_state.total_model_calls >= policy.max_model_calls:
        return True, LoopStopReason.MAX_MODEL_CALLS_REACHED

    # Check wall clock against max_wall_clock_seconds
    if elapsed_seconds >= policy.max_wall_clock_seconds:
        return True, LoopStopReason.MAX_WALL_CLOCK_REACHED

    return False, None


__all__ = ["enforce_budgets"]
