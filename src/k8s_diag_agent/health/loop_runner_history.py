"""History load/persist seam extracted from HealthLoopRunner.

This module provides focused helpers for loading and persisting health loop
history state, including fact artifact handling. Preserves behavior exactly -
no schema or artifact contract changes.

These helpers are pure functions with no runner logic. They delegate to
loop_history module for core load/persist and handle fact artifact logic
and logging setup.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .loop_history import (
    HealthHistoryEntry,
    load_history,
    persist_history,
    persist_history_fact_artifacts,
)

# Type alias for log event callback to avoid hard coupling to runner
LogEventFn = Callable[..., None]


def load_runner_history(*, history_path: Path) -> dict[str, HealthHistoryEntry]:
    """Load health history entries from the history file.

    Preserves exact behavior from HealthLoopRunner._load_history():
    - Returns empty dict if file doesn't exist
    - Parses JSON and constructs HealthHistoryEntry for each cluster
    - Skips non-dict entries gracefully

    Args:
        history_path: path to history.json

    Returns:
        dict mapping cluster_id to HealthHistoryEntry
    """
    return load_history(history_path)


def persist_runner_history(
    *,
    history: dict[str, HealthHistoryEntry],
    directories: dict[str, Path],
    run_id: str,
    log_event_fn: LogEventFn | None = None,
) -> None:
    """Persist health history including fact artifacts and aggregate JSON.

    Preserves exact behavior from HealthLoopRunner._persist_history():
    1. Writes immutable fact artifacts for each cluster (non-fatal on failure)
    2. Writes mutable aggregate history.json (backward compatibility)

    Args:
        history: mapping of cluster_id to HealthHistoryEntry
        directories: dict with "history" and optional "history_facts" keys
        run_id: the current run identifier (used for fact artifact naming)
        log_event_fn: optional callback for logging events (severity, message, metadata)
                     If None, logging is skipped (wrapper handles it)
    """
    # First, write immutable fact artifacts for each cluster
    history_facts_dir = directories.get("history_facts")
    if history_facts_dir:
        try:
            from ..identity.artifact import new_artifact_id

            persist_history_fact_artifacts(
                history=history,
                run_id=run_id,
                history_dir=history_facts_dir,
                artifact_id_fn=new_artifact_id,
            )
            if log_event_fn:
                log_event_fn(
                    "health-loop",
                    "INFO",
                    "History fact artifacts written",
                    artifact_count=len(history),
                    history_facts_dir=str(history_facts_dir),
                    event="history-facts-written",
                )
        except OSError as exc:
            # Fact artifact write failure is non-fatal; log and continue
            if log_event_fn:
                log_event_fn(
                    "health-loop",
                    "WARNING",
                    "Failed to write history fact artifacts",
                    severity_reason=str(exc),
                    event="history-facts-failed",
                )

    # Then, write the mutable aggregate history.json (backward compatibility)
    history_path = directories["history"]
    persist_history(history, history_path)
