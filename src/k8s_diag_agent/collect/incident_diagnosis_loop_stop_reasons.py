"""Loop stop reasons enum for the diagnosis loop.

This module provides a closed set of typed stop reasons.
"""

from __future__ import annotations

from enum import StrEnum

# =============================================================================
# Schema version
# =============================================================================

SCHEMA_VERSION = "1.0"


class LoopStopReason(StrEnum):
    """Why the diagnosis loop stopped.

    Every loop run must end with exactly one stop reason from this closed set.
    """

    # RCA confirmed with evidence (preferred stop)
    ROOT_CAUSE_CONFIRMED_BY_EVIDENCE = "root_cause_confirmed_by_evidence"

    # High confidence root cause reached
    HIGH_CONFIDENCE_ROOT_CAUSE = "high_confidence_root_cause"

    # Budget exhausted
    MAX_PASSES_REACHED = "max_passes_reached"
    MAX_CHECKS_REACHED = "max_checks_reached"
    MAX_MODEL_CALLS_REACHED = "max_model_calls_reached"
    MAX_WALL_CLOCK_REACHED = "max_wall_clock_reached"

    # Quality stops
    NO_NEW_EVIDENCE = "no_new_evidence"
    REPEATED_PLAN = "repeated_plan"

    # Safety/availability stops
    NO_SAFE_CHECKS_PROPOSED = "no_safe_checks_proposed"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    CHECK_RUNNER_FAILED = "check_runner_failed"

    # Bounds exceeded
    CASE_FILE_BOUNDS_EXCEEDED = "case_file_bounds_exceeded"

    # Legacy/compatibility
    ROOT_CAUSE_FOUND = "root_cause_found"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NO_SAFE_CHECKS = "no_safe_checks"
    LOW_CONFIDENCE_NO_PROGRESS = "low_confidence_no_progress"
    SAFETY_BLOCKED = "safety_blocked"
    NO_CHECKS_PROPOSED = "no_checks_proposed"


# Acceptable stop reasons for P4c (clean trajectory)
ACCEPTABLE_P4C_STOP_REASONS: frozenset[str] = frozenset({
    LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
    LoopStopReason.HIGH_CONFIDENCE_ROOT_CAUSE,
})

# Warning-grade stop reasons (acceptable only if RCA verdict is valid)
WARNING_GRADE_P4C_STOP_REASONS: frozenset[str] = frozenset({
    LoopStopReason.MAX_PASSES_REACHED,
})


__all__ = [
    "SCHEMA_VERSION",
    "LoopStopReason",
    "ACCEPTABLE_P4C_STOP_REASONS",
    "WARNING_GRADE_P4C_STOP_REASONS",
]
