"""Shared fixtures for P4c outcome tests."""

from __future__ import annotations

from typing import Any


def make_base_evidence(**overrides: Any) -> dict[str, Any]:
    """Create a base evidence dict for P4c outcome tests.

    Provides sensible defaults that can be overridden for specific test cases.
    """
    base = {
        "real_loop_invoked": True,
        "terminal_no_checks_accepted": False,
        "pass_count": 2,
        "real_pass_artifacts_found": True,
        "incident_id": "test-incident",
        "root_cause_summary": "The shipping pod is Unschedulable because FailedScheduling",
        "read_only": True,
        "read_only_violations": [],
    }
    base.update(overrides)
    return base


def make_terminal_single_pass_evidence(**overrides: Any) -> dict[str, Any]:
    """Create evidence for terminal single-pass test cases."""
    base = {
        "real_loop_invoked": True,
        "terminal_no_checks_accepted": True,
        "pass_count": 1,
        "real_pass_artifacts_found": True,
        "incident_id": "test-incident",
        "terminal_decision_reached": "stop_no_checks_proposed",
        "pass_run_ids": ["run-123"],
        "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
        "read_only": True,
        "read_only_violations": [],
    }
    base.update(overrides)
    return base


def make_complete_scheduling_summary() -> str:
    """Generate a complete scheduling root-cause summary with all required terms."""
    return (
        "The shipping deployment has FailedScheduling due to nodeSelector mismatch. "
        "Pod requires k9b.dev/otel-lab-node=missing but no node matches. "
        "This is an Unschedulable pod situation."
    )
