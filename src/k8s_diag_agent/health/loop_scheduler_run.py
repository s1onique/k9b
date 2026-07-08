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

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .loop_scheduler_cycle import (
    CycleState,
    clear_pending_run_metadata,
    compute_freshness_age,
    create_pending_run_metadata,
    update_finish_time,
)
from .loop_scheduler_diagnostics import resolve_run_id

if TYPE_CHECKING:
    from k8s_diag_agent.content_index.scheduler_producer import (
        SchedulerContentIndexConfig,
    )

# =============================================================================
# Content Index Producer (lazy import to avoid circular deps)
# =============================================================================

_CONTENT_INDEX_CONFIG: SchedulerContentIndexConfig | None = None
_CONTENT_INDEX_HOOK_ENABLED = False


def _derive_content_index_runs_dir(raw_runs_dir: str | None) -> Path:
    """Derive the content index runs directory from HEALTH_RUNS_DIR.

    Scheduler's HEALTH_RUNS_DIR is commonly /app/runs/health.
    The content index root must be the shared runs parent.

    Args:
        raw_runs_dir: Raw HEALTH_RUNS_DIR value or None.

    Returns:
        Path to the runs directory for content indexing.
    """
    if not raw_runs_dir:
        return Path("/app/runs")

    path = Path(raw_runs_dir.rstrip("/"))

    # Scheduler health runs dir is commonly /app/runs/health.
    # The content index root must be the shared runs parent.
    if path.name == "health":
        return path.parent

    return path


def _init_content_index_producer(env_vars: dict[str, str] | None = None) -> None:
    """Initialize the content index producer config from environment.

    This is called once at scheduler startup to set up the producer configuration.
    """
    global _CONTENT_INDEX_CONFIG, _CONTENT_INDEX_HOOK_ENABLED
    try:
        from k8s_diag_agent.content_index.scheduler_producer import (
            load_scheduler_content_index_config_from_env,
        )

        # Get runs_dir from environment or use default
        if env_vars is None:
            _env = dict(os.environ)
        else:
            _env = env_vars

        raw_runs_dir = _env.get("HEALTH_RUNS_DIR")
        default_runs_dir = _derive_content_index_runs_dir(raw_runs_dir)

        _CONTENT_INDEX_CONFIG = load_scheduler_content_index_config_from_env(
            env=_env,
            default_runs_dir=default_runs_dir,
        )
        _CONTENT_INDEX_HOOK_ENABLED = True
    except ImportError:
        # Content index producer not available (older build)
        _CONTENT_INDEX_CONFIG = None
        _CONTENT_INDEX_HOOK_ENABLED = False


def _update_content_index(
    scheduler: Any,
    run_id: str | None,
    env_vars: dict[str, str] | None = None,
) -> None:
    """Update content index after a successful scheduler run.

    This hook is called after a health run completes successfully.
    It updates the SQLite content index for backend read-path consumption.
    """
    global _CONTENT_INDEX_HOOK_ENABLED, _CONTENT_INDEX_CONFIG

    if not _CONTENT_INDEX_HOOK_ENABLED:
        return

    if _CONTENT_INDEX_CONFIG is None:
        return

    try:
        # Import here to avoid import-time side effects
        from k8s_diag_agent.content_index.scheduler_producer import (
            update_content_index_after_scheduler_run,
        )

        # Use scheduler's _log_event for structured logging
        result = update_content_index_after_scheduler_run(
            config=_CONTENT_INDEX_CONFIG,
            run_id=run_id,
            log_fn=None,  # We handle logging below
        )

        # Emit canonical structured log with component identifier
        # (producer module logs internally at debug level if log_fn provided)
        if result.skipped_reason:
            scheduler._log_event(
                "DEBUG",
                "Scheduler content index update skipped",
                component="content-index-scheduler",
                db_path=str(result.db_path),
                skipped_reason=result.skipped_reason,
                duration_ms=round(result.duration_ms, 2),
            )
        elif result.error:
            scheduler._log_event(
                "WARNING",
                "Scheduler content index update failed; backend fallback remains available",
                component="content-index-scheduler",
                db_path=str(result.db_path),
                run_id=run_id,
                error_type="ContentIndexUpdateError",
                error=result.error,
                duration_ms=round(result.duration_ms, 2),
            )
        else:
            scheduler._log_event(
                "INFO",
                "Scheduler content index update completed",
                component="content-index-scheduler",
                db_path=str(result.db_path),
                run_id=run_id,
                created=result.created,
                updated=result.updated,
                duration_ms=round(result.duration_ms, 2),
                indexed_count=result.indexed_count,
            )
    except Exception as exc:
        # Never let content index failure propagate to scheduler loop
        # Backend fallback remains available, but log structured warning
        scheduler._log_event(
            "WARNING",
            "Scheduler content index update hook failed; backend fallback remains available",
            component="content-index-scheduler",
            run_id=run_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )


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
        - Content index update
        - Exit code propagation from failed runs
        - KeyboardInterrupt handling
    """
    # Set up cycle state from scheduler configuration
    cycle = CycleState(
        run_once=scheduler._run_once,
        max_runs=scheduler._max_runs,
        interval_seconds=scheduler._interval_seconds,
    )

    # Initialize content index producer
    _init_content_index_producer()

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

                    # Update content index after successful run
                    _update_content_index(scheduler, run_id)

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
