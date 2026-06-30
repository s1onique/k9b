"""Rendering helpers for human-readable diagnosis loop summaries.

This module provides:
- Human-readable formatting of pass artifacts and loop results
- UI-friendly output formatting
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


def render_runtime_summary(result: dict[str, Any]) -> str:
    """Render a human-readable summary of a runtime pass result.

    Args:
        result: The result dict from run_policy_enforced_loop_pass

    Returns:
        A human-readable summary string
    """
    lines = ["=== Diagnosis Loop Pass Summary ==="]

    # Basic info
    policy_enforced = result.get("policy_enforced", False)
    lines.append(f"Policy Enforced: {policy_enforced}")

    # Gate summary
    gate_summary = result.get("gate_summary", {})
    if gate_summary:
        lines.append(f"Checks: proposed={gate_summary.get('proposed', 0)}, "
                     f"accepted={gate_summary.get('accepted', 0)}, "
                     f"rejected_mutating={gate_summary.get('rejected_mutating', 0)}, "
                     f"rejected_sensitive={gate_summary.get('rejected_sensitive', 0)}, "
                     f"rejected_duplicate={gate_summary.get('rejected_duplicate', 0)}")

        rejected_checks = gate_summary.get("rejected_checks", [])
        if rejected_checks:
            lines.append(f"Rejected reasons: {', '.join(str(r) for r in rejected_checks[:5])}")

    # Budget info
    budget_exceeded = result.get("budget_exceeded", False)
    if budget_exceeded:
        lines.append(f"Budget Exceeded: True (reason: {result.get('budget_stop_reason', 'unknown')})")

    # Decision
    decision = result.get("decision", "")
    if decision:
        lines.append(f"Decision: {decision}")

    # Pass artifact info
    pass_artifact = result.get("pass_artifact", {})
    if pass_artifact:
        stop_reason = pass_artifact.get("stop_reason", "")
        should_continue = pass_artifact.get("should_continue", False)
        lines.append(f"Stop Reason: {stop_reason or 'none'}")
        lines.append(f"Should Continue: {should_continue}")

        root_cause = pass_artifact.get("root_cause_summary", "")
        if root_cause:
            lines.append(f"Root Cause: {root_cause[:100]}")

    # Artifact path
    p4c_path = result.get("p4c_artifact_path")
    if p4c_path:
        lines.append(f"P4C Artifact: {p4c_path}")

    return "\n".join(lines)


def render_loop_summary(result: dict[str, Any]) -> str:
    """Render a human-readable summary of a multi-pass loop result.

    Args:
        result: The result dict from run_policy_enforced_loop

    Returns:
        A human-readable summary string
    """
    lines = ["=== Diagnosis Loop Summary ==="]

    # Basic info
    loop_run_id = result.get("loop_run_id", "")
    incident_id = result.get("incident_id", "")
    total_passes = result.get("total_passes", 0)
    total_checks = result.get("total_checks_executed", 0)
    final_stop = result.get("final_stop_reason", "")

    lines.append(f"Loop Run ID: {loop_run_id}")
    lines.append(f"Incident ID: {incident_id}")
    lines.append(f"Total Passes: {total_passes}")
    lines.append(f"Total Checks Executed: {total_checks}")
    lines.append(f"Final Stop Reason: {final_stop or 'none'}")

    # Pass summaries
    pass_results = result.get("pass_results", [])
    if pass_results:
        lines.append("\nPass Details:")
        for i, pr in enumerate(pass_results, 1):
            stop = pr.get("stop_reason", "")
            budget = pr.get("budget_exceeded", False)
            lines.append(f"  Pass {i}: stop_reason={stop or 'running'}, "
                         f"budget_exceeded={budget}")

    return "\n".join(lines)


def render_gate_summary(gate_summary: dict[str, Any]) -> str:
    """Render a human-readable gate summary.

    Args:
        gate_summary: The gate summary dict

    Returns:
        A human-readable summary string
    """
    return (
        f"Gate: {gate_summary.get('proposed', 0)} proposed, "
        f"{gate_summary.get('accepted', 0)} accepted, "
        f"{gate_summary.get('rejected_mutating', 0) + gate_summary.get('rejected_sensitive', 0) + gate_summary.get('rejected_duplicate', 0)} rejected"
    )


__all__ = [
    "render_runtime_summary",
    "render_loop_summary",
    "render_gate_summary",
]
