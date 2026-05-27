"""Run loop orchestration for the health loop scheduler.

Extracted from loop_scheduler.py to reduce its size and improve LLM-friendly traversal.
Preserves behavior exactly - no timing, lock, or artifact contract changes.

This module contains the main scheduler loop body. HealthLoopScheduler.run() delegates
to run_scheduler_loop() to keep the compatibility surface minimal while enabling
testability of the orchestration logic.

Preserves test monkeypatch surfaces by calling scheduler private methods rather than
accessing LockManager directly.
"""

from __future__ import annotations

import time
from typing import Any

from .loop_scheduler_cycle import (
    CycleState,
    clear_pending_run_metadata,
    compute_freshness_age,
    create_pending_run_metadata,
    update_finish_time,
)
from .loop_scheduler_diagnostics import resolve_run_id

# =============================================================================
# Run Loop Orchestration
# =============================================================================


def run_scheduler_loop(scheduler: Any) -> int:
    """Execute the scheduler loop, running health loops at configured intervals.

    Args:
        scheduler: The HealthLoopScheduler instance to run.

    Returns:
        Exit code from the last executed health loop, or 1 if interrupted.

    Behavior preserved exactly:
        - Run-once and max-runs constraints via CycleState
        - Lock acquisition/release with skip behavior
        - Sleep cadence between cycles
        - Freshness age reporting
        - Diagnostic pack invocation
        - Exit code propagation from failed runs
        - KeyboardInterrupt handling
    """
    # Set up cycle state from scheduler configuration
    cycle = CycleState(
        run_once=scheduler._run_once,
        max_runs=scheduler._max_runs,
        interval_seconds=scheduler._interval_seconds,
    )

    # Log scheduler startup
    scheduler._log_event(
        "INFO",
        "Health scheduler started",
        interval_seconds=scheduler._interval_seconds,
        max_runs=scheduler._max_runs,
        run_once=scheduler._run_once,
    )

    # Emit effective scheduler config log (one-time startup event)
    scheduler._log_effective_scheduler_config()

    _run_health_loop = scheduler._run_health_loop_fn

    try:
        while cycle.should_continue():
            cycle.reset_cycle()

            # Create pending run metadata
            scheduler._pending_run_id, scheduler._pending_run_start = create_pending_run_metadata(
                scheduler._run_label,
            )

            # Attempt to acquire the lock
            if not scheduler._acquire_lock():
                cycle.mark_skipped()
            else:
                try:
                    run_start_time = time.time()
                    freshness_age_seconds = compute_freshness_age(
                        run_start_time=run_start_time,
                        last_run_finish_time=scheduler._last_run_finish_time,
                    )

                    # Execute the health loop
                    (
                        exit_code,
                        assessments,
                        triggers,
                        drilldowns,
                        external_artifacts,
                        settings,
                    ) = _run_health_loop(
                        scheduler._config_path,
                        manual_triggers=scheduler._manual_triggers,
                        manual_drilldown_contexts=scheduler._manual_drilldown_contexts,
                        manual_external_analysis=scheduler._manual_external_analysis,
                        quiet=scheduler._quiet,
                        expected_scheduler_interval_seconds=scheduler._interval_seconds,
                        run_id=scheduler._pending_run_id,
                    )

                    run_id = resolve_run_id(assessments, triggers)
                    cycle.mark_executed(exit_code)

                    # Handle non-zero exit code as failure
                    if exit_code != 0:
                        scheduler._log_event(
                            "ERROR",
                            "Health run failed",
                            run_id=run_id,
                            severity_reason=f"exit_code={exit_code}",
                            event="run-failure",
                        )
                        return int(exit_code)

                    # Log run summary with freshness
                    scheduler._log_run_summary(
                        assessments,
                        triggers,
                        drilldowns,
                        external_artifacts,
                        settings,
                        freshness_age_seconds=freshness_age_seconds,
                        expected_interval_seconds=scheduler._interval_seconds,
                    )

                    # Build diagnostic pack if configured
                    scheduler._maybe_build_diagnostic_pack(run_id)

                    # Record finish time for next cycle's freshness computation
                    scheduler._last_run_finish_time = update_finish_time()

                finally:
                    # Clear pending metadata and release lock
                    scheduler._pending_run_id, scheduler._pending_run_start = (
                        clear_pending_run_metadata()
                    )
                    scheduler._release_lock()

            # Check break condition after lock release
            if cycle.should_break_after():
                break

            # Sleep for configured interval before next cycle
            time.sleep(cycle.sleep_seconds())

    except KeyboardInterrupt:
        scheduler._log_event(
            "WARNING",
            "Health scheduler interrupted",
            event="interrupted",
            reason="keyboard",
        )
        return 1

    # Log scheduler shutdown with final exit code
    scheduler._log_event(
        "INFO",
        "Health scheduler stopped",
        exit_code=cycle.last_exit,
        event="stop",
    )
    return cycle.last_exit


# =============================================================================
# Re-exports for backward compatibility
# =============================================================================

__all__ = [
    "run_scheduler_loop",
]
