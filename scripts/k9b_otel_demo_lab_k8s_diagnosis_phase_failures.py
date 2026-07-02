"""Failure collection and classification helpers for K8s diagnosis phase.

This module contains pure helper functions for collecting and classifying
validation failures. It is extracted from the phase facade to keep the
main orchestration module under the LLM-friendly file-size gate.
"""

from __future__ import annotations

from typing import Any

from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import MIN_REQUIRED_PASSES
from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import _check_read_only_contract


def _diagnosis_used_simulation(pass_run_ids: list[str]) -> bool:
    """Check if any pass run ID indicates simulation was used.

    Simulation pass IDs follow the pattern 'sim-{incident_id[:8]}-pass{N}'.
    Even if simulation_used flag is not set, checking pass_run_ids provides
    an additional guard against simulated diagnosis being treated as success.

    Args:
        pass_run_ids: List of pass run IDs

    Returns:
        True if any pass_run_id starts with 'sim-'
    """
    return any(str(rid).startswith("sim-") for rid in pass_run_ids)


def _collect_failures(evidence: dict[str, Any], term_checks: dict[str, bool]) -> list[str]:
    """Collect validation failure reasons."""
    failures: list[str] = []

    # Check for simulation: either via flag or via pass_run_ids markers
    pass_run_ids = evidence.get("pass_run_ids", [])
    if evidence["simulation_used"] or _diagnosis_used_simulation(pass_run_ids):
        failures.append("simulation_used_but_not_allowed")
    if not evidence["real_loop_invoked"]:
        failures.append("real_loop_not_invoked")
    if not evidence["real_pass_artifacts_found"]:
        failures.append("real_pass_artifacts_missing")

    # Terminal no-checks single-pass is an accepted success mode - bypass pass_count check
    terminal_no_checks_accepted = evidence.get("terminal_no_checks_accepted", False)
    is_terminal_mode = (
        terminal_no_checks_accepted
        and evidence["pass_count"] >= 1
        and evidence.get("real_pass_artifacts_found", False)
    )

    if not is_terminal_mode and evidence["pass_count"] < MIN_REQUIRED_PASSES:
        failures.append(f"insufficient_passes: {evidence['pass_count']} < {MIN_REQUIRED_PASSES}")

    executed = evidence.get("executed_checks", [])
    is_read_only, violations = _check_read_only_contract(executed)
    evidence["read_only"] = is_read_only
    evidence["read_only_violations"] = violations
    if not is_read_only:
        failures.append(f"read_only_contract_violated: {violations}")

    # Terminal no-checks mode: root-cause evidence comes from deterministic K8s evidence, not diagnosis prose
    # Only require term markers for multi-pass mode
    if not is_terminal_mode:
        for term, found in term_checks.items():
            if not found:
                failures.append(f"missing_root_cause_term: {term}")
    return failures
