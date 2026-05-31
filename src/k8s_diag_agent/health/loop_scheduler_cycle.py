"""Run-cycle orchestration helpers for the health loop scheduler.

Extracted from loop_scheduler.py to reduce its size and improve LLM-friendly traversal.
Preserves behavior exactly - no timing, lock, or artifact contract changes.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from .loop_history import _build_runtime_run_id

# =============================================================================
# Loop Control Helpers
# =============================================================================


def should_continue_scheduler(
    executed_runs: int,
    run_once: bool,
    max_runs: int | None,
) -> bool:
    """Determine if the scheduler loop should continue for another iteration.

    Args:
        executed_runs: Number of runs already executed in this scheduler session
        run_once: Whether the scheduler is configured for single-shot mode
        max_runs: Maximum number of runs allowed, or None for unlimited

    Returns:
        True if the scheduler should continue running, False if it should exit
    """
    if run_once and executed_runs >= 1:
        return False
    if max_runs is not None and executed_runs >= max_runs:
        return False
    return True


def should_break_after_cycle(
    run_executed: bool,
    run_once: bool,
    executed_runs: int,
    max_runs: int | None,
    interval_seconds: int | None,
) -> bool:
    """Determine if the scheduler should break out of the loop after completing a cycle.

    Checks all conditions that would prevent the next iteration.

    Args:
        run_executed: Whether the current cycle executed a health run
        run_once: Whether running in single-shot mode
        executed_runs: Number of runs executed so far
        max_runs: Maximum runs allowed, or None for unlimited
        interval_seconds: Interval between runs, or None

    Returns:
        True if the loop should break, False if it should continue
    """
    # If run was not executed and we only run once, break
    if not run_executed and run_once:
        return True

    # If run_once mode, break after execution
    if run_once:
        return True

    # If max runs reached, break
    if max_runs is not None and executed_runs >= max_runs:
        return True

    # If no interval set, break (single-shot without run_once=false is handled above)
    if not interval_seconds:
        return True

    return False


def compute_sleep_duration(interval_seconds: int | None) -> float:
    """Compute the sleep duration for the scheduler loop.

    Args:
        interval_seconds: The configured interval in seconds, or None

    Returns:
        Sleep duration in seconds; returns 0 if no interval is configured
    """
    if interval_seconds is None:
        return 0.0
    return float(interval_seconds)


# =============================================================================
# Pending Run Metadata Helpers
# =============================================================================


def create_pending_run_metadata(
    run_label: str,
) -> tuple[str, datetime]:
    """Create pending run metadata for the next health loop execution.

    Args:
        run_label: Label for this scheduler run (e.g., "health-scheduler")

    Returns:
        Tuple of (run_id, start_time) for the pending run
    """
    run_id = _build_runtime_run_id(run_label)
    start_time = datetime.now(UTC)
    return run_id, start_time


def clear_pending_run_metadata() -> tuple[None, None]:
    """Clear pending run metadata after a run completes.

    Returns:
        Tuple of (None, None) to reset pending state
    """
    return None, None


# =============================================================================
# Post-Run Bookkeeping Helpers
# =============================================================================


def compute_freshness_age(
    run_start_time: float,
    last_run_finish_time: float | None,
) -> float | None:
    """Compute the freshness age based on timing between runs.

    Args:
        run_start_time: Start time of the current run (Unix timestamp)
        last_run_finish_time: Finish time of the previous run, or None if no previous run

    Returns:
        Age in seconds since the last run finished, or None if no previous run
    """
    if last_run_finish_time is None:
        return None
    return run_start_time - last_run_finish_time


def update_finish_time() -> float:
    """Record the current time as the run finish time.

    Returns:
        Unix timestamp of the current moment
    """
    return time.time()


def compute_cycle_exit_code(
    exit_code: int,
    run_executed: bool,
) -> int | None:
    """Determine the exit code for this cycle.

    Args:
        exit_code: The exit code from the health run
        run_executed: Whether the run was actually executed

    Returns:
        The exit code to return, or None if the run was skipped
    """
    if not run_executed:
        return None
    return exit_code


# =============================================================================
# Cycle Execution State
# =============================================================================


class CycleState:
    """Encapsulates state for a single scheduler cycle iteration."""

    __slots__ = (
        "_run_executed",
        "_executed_runs",
        "_last_exit",
        "_run_once",
        "_max_runs",
        "_interval_seconds",
        "_pending_run_id",
        "_pending_run_start",
    )

    def __init__(
        self,
        run_once: bool,
        max_runs: int | None,
        interval_seconds: int | None,
    ) -> None:
        self._run_executed = False
        self._executed_runs = 0
        self._last_exit = 0
        self._run_once = run_once
        self._max_runs = max_runs
        self._interval_seconds = interval_seconds
        self._pending_run_id: str | None = None
        self._pending_run_start: datetime | None = None

    @property
    def run_executed(self) -> bool:
        return self._run_executed

    @property
    def executed_runs(self) -> int:
        return self._executed_runs

    @property
    def last_exit(self) -> int:
        return self._last_exit

    @property
    def pending_run_id(self) -> str | None:
        return self._pending_run_id

    @pending_run_id.setter
    def pending_run_id(self, value: str | None) -> None:
        self._pending_run_id = value

    @property
    def pending_run_start(self) -> datetime | None:
        return self._pending_run_start

    @pending_run_start.setter
    def pending_run_start(self, value: datetime | None) -> None:
        self._pending_run_start = value

    def mark_executed(self, exit_code: int) -> None:
        """Mark a run as executed with the given exit code."""
        self._run_executed = True
        self._executed_runs += 1
        self._last_exit = exit_code

    def mark_skipped(self) -> None:
        """Mark the cycle as skipped (lock held)."""
        self._run_executed = False

    def reset_cycle(self) -> None:
        """Reset per-cycle state for the next iteration."""
        self._run_executed = False
        self._pending_run_id = None
        self._pending_run_start = None

    def should_continue(self) -> bool:
        """Check if the scheduler loop should continue."""
        return should_continue_scheduler(
            executed_runs=self._executed_runs,
            run_once=self._run_once,
            max_runs=self._max_runs,
        )

    def should_break_after(self) -> bool:
        """Check if we should break the loop after this cycle."""
        return should_break_after_cycle(
            run_executed=self._run_executed,
            run_once=self._run_once,
            executed_runs=self._executed_runs,
            max_runs=self._max_runs,
            interval_seconds=self._interval_seconds,
        )

    def sleep_seconds(self) -> float:
        """Return the sleep duration for this cycle."""
        return compute_sleep_duration(self._interval_seconds)


# =============================================================================
# Re-exports for backward compatibility
# =============================================================================

__all__ = [
    "CycleState",
    "clear_pending_run_metadata",
    "compute_cycle_exit_code",
    "compute_freshness_age",
    "compute_sleep_duration",
    "create_pending_run_metadata",
    "should_break_after_cycle",
    "should_continue_scheduler",
    "update_finish_time",
]
