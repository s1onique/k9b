"""Entry point for the loop scheduler.

This module contains the schedule_health_loop() function which is the
public entry point for running health loops on a schedule.

Extracted from loop_scheduler_runner.py to reduce its size and improve
LLM-friendly traversal.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path


def schedule_health_loop(
    config_path: Path,
    manual_triggers: Sequence[str] | None = None,
    manual_drilldown_contexts: Sequence[str] | None = None,
    manual_external_analysis: Sequence[str] | None = None,
    quiet: bool = False,
    *,
    interval_seconds: int | None = None,
    max_runs: int | None = None,
    run_once: bool = False,
) -> int:
    """Schedule and run health loops at configured intervals.

    This function loads the configuration and creates a scheduler that manages
    lock-based execution of health loops.
    """
    from ..structured_logging import emit_structured_log
    from .loop import HealthRunConfig, run_health_loop
    from .loop_history import _safe_label
    from .loop_scheduler_runner import HealthLoopScheduler

    # Compute scripts_dir relative to project root
    project_root = Path(__file__).resolve().parents[3]
    scripts_dir = project_root / "scripts"

    try:
        config = HealthRunConfig.load(config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        emit_structured_log(
            component="health-scheduler",
            severity="ERROR",
            message=f"Unable to load health config {config_path}: {exc}",
            run_label=_safe_label(str(config_path.stem)),
            metadata={"config_path": str(config_path), "severity_reason": str(exc), "event": "config-load-failed"},
        )
        return 1
    scheduler = HealthLoopScheduler(
        config_path=config_path,
        manual_triggers=manual_triggers or [],
        manual_drilldown_contexts=manual_drilldown_contexts or [],
        manual_external_analysis=manual_external_analysis or [],
        quiet=quiet,
        interval_seconds=interval_seconds,
        max_runs=max_runs,
        run_once=run_once,
        output_dir=config.output_dir,
        scripts_dir=scripts_dir,
        run_health_loop_fn=run_health_loop,
        run_label=config.run_label,
    )
    # Pass config to scheduler for effective config logging
    scheduler._run_config = config
    return scheduler.run()


# Re-export for backward compatibility
__all__ = ["schedule_health_loop"]
