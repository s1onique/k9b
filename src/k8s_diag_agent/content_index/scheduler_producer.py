"""Scheduler content index producer.

This module provides the scheduler-facing wrapper for content index production.
The scheduler is the single normal producer/writer of the SQLite content index.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .indexer import (
    ContentIndexRoots,
    IndexerConfig,
    IndexerSummary,
    rebuild_index,
    update_index,
    validate_index,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

# =============================================================================
# Type Aliases
# =============================================================================

SchedulerLogFn = Callable[..., None]

# =============================================================================
# Environment Variables
# =============================================================================

CONTENT_INDEX_ENABLED_ENV_VAR = "K9B_CONTENT_INDEX_ENABLED"
CONTENT_INDEX_DB_PATH_ENV_VAR = "K9B_CONTENT_INDEX_DB_PATH"
CONTENT_INDEX_UPDATE_MODE_ENV_VAR = "K9B_CONTENT_INDEX_UPDATE_MODE"

# Default update modes
DEFAULT_UPDATE_MODE: Literal["update", "rebuild_if_missing", "rebuild"] = "update"

# =============================================================================
# Configuration Dataclass
# =============================================================================


@dataclass(frozen=True)
class SchedulerContentIndexConfig:
    """Configuration for the scheduler content index producer.

    Attributes:
        enabled: Whether the content index producer is enabled.
        runs_dir: Base directory for run artifacts (used to derive default DB path).
        db_path: Path to the SQLite content index database.
        update_mode: Update mode (update, rebuild_if_missing, rebuild).
        max_duration_seconds: Optional maximum duration for index operations.
    """

    enabled: bool
    runs_dir: Path
    db_path: Path
    update_mode: Literal["update", "rebuild_if_missing", "rebuild"] = "update"
    max_duration_seconds: float | None = None


# =============================================================================
# Result Dataclass
# =============================================================================


@dataclass(frozen=True)
class SchedulerContentIndexResult:
    """Result of a scheduler content index update operation.

    Attributes:
        attempted: Whether an update was attempted.
        created: Whether the database was created.
        updated: Whether the database was updated.
        skipped_reason: Reason for skipping, if any.
        db_path: Path to the database.
        duration_ms: Duration of the operation in milliseconds.
        indexed_count: Number of items indexed.
        error: Error message if operation failed.
    """

    attempted: bool
    created: bool
    updated: bool
    skipped_reason: str | None
    db_path: Path
    duration_ms: float
    indexed_count: int | None = None
    error: str | None = None


# =============================================================================
# Configuration Loading
# =============================================================================


def load_scheduler_content_index_config_from_env(
    env: Mapping[str, str] | None = None,
    *,
    default_runs_dir: Path,
) -> SchedulerContentIndexConfig:
    """Load scheduler content index configuration from environment variables.

    Args:
        env: Optional environment mapping. Defaults to os.environ.
        default_runs_dir: Default runs directory to use for DB path if not specified.

    Returns:
        SchedulerContentIndexConfig with producer settings.
    """
    if env is None:
        import os as _os

        env = _os.environ

    # Check feature flag (default: enabled for scheduler producer)
    enabled_str = env.get(CONTENT_INDEX_ENABLED_ENV_VAR, "true").lower()
    enabled = enabled_str in ("true", "1", "yes")

    # Get database path
    db_path_str = env.get(CONTENT_INDEX_DB_PATH_ENV_VAR)
    if db_path_str:
        db_path = Path(db_path_str)
    else:
        # Default to shared /app/runs volume
        db_path = default_runs_dir / "content-index.sqlite"

    # Get update mode
    update_mode_str = env.get(CONTENT_INDEX_UPDATE_MODE_ENV_VAR, DEFAULT_UPDATE_MODE)
    if update_mode_str not in ("update", "rebuild_if_missing", "rebuild"):
        update_mode_str = DEFAULT_UPDATE_MODE
    update_mode: Literal["update", "rebuild_if_missing", "rebuild"] = update_mode_str  # type: ignore[assignment]

    return SchedulerContentIndexConfig(
        enabled=enabled,
        runs_dir=default_runs_dir,
        db_path=db_path,
        update_mode=update_mode,
    )


# =============================================================================
# Content Index Producer
# =============================================================================


def update_content_index_after_scheduler_run(
    config: SchedulerContentIndexConfig,
    *,
    run_id: str | None = None,
    log_fn: SchedulerLogFn | None = None,
) -> SchedulerContentIndexResult:
    """Update the content index after a scheduler run.

    This function is called after the scheduler completes a health run.
    It updates the SQLite content index for use by the backend read path.

    Args:
        config: Scheduler content index configuration.
        run_id: Optional run ID for logging.
        log_fn: Optional logging function (signature: fn(severity, message, **kwargs)).

    Returns:
        SchedulerContentIndexResult with operation outcome.
    """
    start_time = time.monotonic()

    def _log(severity: str, message: str, **kwargs: object) -> None:
        if log_fn is not None:
            log_fn(severity, message, **kwargs)

    # Skip if disabled
    if not config.enabled:
        _log("DEBUG", "Scheduler content index update skipped", skipped_reason="disabled")
        return SchedulerContentIndexResult(
            attempted=False,
            created=False,
            updated=False,
            skipped_reason="disabled",
            db_path=config.db_path,
            duration_ms=(time.monotonic() - start_time) * 1000,
        )

    # Build content index roots from runs directory
    runs_dir = config.runs_dir

    # Determine which roots are available
    incident_store = runs_dir / "incidents"
    artifact_root = runs_dir
    lab_root = runs_dir / "lab"
    trace_capture_root = runs_dir / "trace-capture"
    perf_baseline_root = runs_dir / "trace-capture" / "perf-baseline"

    roots = ContentIndexRoots(
        incident_store=incident_store if incident_store.exists() else None,
        artifact_root=artifact_root if artifact_root.exists() else None,
        lab_root=lab_root if lab_root.exists() else None,
        trace_capture_root=trace_capture_root if trace_capture_root.exists() else None,
        perf_baseline_root=perf_baseline_root if perf_baseline_root.exists() else None,
    )

    # Check if any roots are active
    active_roots = roots.get_active_roots()
    if not active_roots:
        _log("DEBUG", "Scheduler content index update skipped", skipped_reason="no_roots")
        return SchedulerContentIndexResult(
            attempted=False,
            created=False,
            updated=False,
            skipped_reason="no_roots",
            db_path=config.db_path,
            duration_ms=(time.monotonic() - start_time) * 1000,
        )

    try:
        # Check if database exists
        db_exists = config.db_path.exists()

        # Determine operation based on update mode and DB state
        if config.update_mode == "rebuild":
            _log("INFO", "Scheduler content index rebuild requested", db_path=str(config.db_path))
            summary = _run_rebuild(config.db_path, roots)
        elif config.update_mode == "rebuild_if_missing":
            if not db_exists:
                _log("INFO", "Scheduler content index DB missing, rebuilding", db_path=str(config.db_path))
                summary = _run_rebuild(config.db_path, roots)
            else:
                # Validate existing DB
                validation = validate_index(config.db_path)
                if not validation.get("valid", False):
                    _log("WARNING", "Scheduler content index DB invalid, rebuilding",
                         db_path=str(config.db_path), errors=validation.get("errors", []))
                    summary = _run_rebuild(config.db_path, roots)
                else:
                    _log("INFO", "Scheduler content index updating existing DB", db_path=str(config.db_path))
                    summary = _run_update(config.db_path, roots)
        else:  # update mode
            if not db_exists:
                _log("INFO", "Scheduler content index DB missing, rebuilding", db_path=str(config.db_path))
                summary = _run_rebuild(config.db_path, roots)
            else:
                # Validate existing DB before update (safety check)
                validation = validate_index(config.db_path)
                if not validation.get("valid", False):
                    _log("WARNING", "Scheduler content index DB invalid, rebuilding",
                         db_path=str(config.db_path), errors=validation.get("errors", []))
                    summary = _run_rebuild(config.db_path, roots)
                else:
                    _log("INFO", "Scheduler content index updating existing DB", db_path=str(config.db_path))
                    summary = _run_update(config.db_path, roots)

        duration_ms = (time.monotonic() - start_time) * 1000

        # Check for errors in summary
        if summary.status == "failed" or summary.errors:
            error_msg = "; ".join(summary.errors[:3]) if summary.errors else "unknown error"
            _log("WARNING", "Scheduler content index update failed; backend fallback remains available",
                 db_path=str(config.db_path), run_id=run_id, error_type=type(summary).__name__, error=error_msg)
            return SchedulerContentIndexResult(
                attempted=True,
                created=not db_exists,
                updated=db_exists,
                skipped_reason=None,
                db_path=config.db_path,
                duration_ms=duration_ms,
                indexed_count=summary.items_indexed,
                error=error_msg,
            )

        # Success
        _log("INFO", "Scheduler content index update completed",
             db_path=str(config.db_path),
             run_id=run_id,
             created=not db_exists,
             updated=db_exists,
             duration_ms=round(duration_ms, 2),
             indexed_count=summary.items_indexed)

        return SchedulerContentIndexResult(
            attempted=True,
            created=not db_exists,
            updated=db_exists,
            skipped_reason=None,
            db_path=config.db_path,
            duration_ms=duration_ms,
            indexed_count=summary.items_indexed,
        )

    except Exception as e:
        duration_ms = (time.monotonic() - start_time) * 1000
        error_msg = str(e)
        _log("WARNING", "Scheduler content index update failed; backend fallback remains available",
             db_path=str(config.db_path), run_id=run_id, error_type=type(e).__name__, error=error_msg)
        return SchedulerContentIndexResult(
            attempted=True,
            created=False,
            updated=False,
            skipped_reason=None,
            db_path=config.db_path,
            duration_ms=duration_ms,
            error=error_msg,
        )


def _run_rebuild(db_path: Path, roots: ContentIndexRoots) -> IndexerSummary:
    """Run a full rebuild of the content index.

    Args:
        db_path: Path to the target database.
        roots: Content index roots.

    Returns:
        IndexerSummary with operation results.
    """
    config = IndexerConfig(strict_mode=False, include_detail_projections=False)
    return rebuild_index(db_path, roots, config)


def _run_update(db_path: Path, roots: ContentIndexRoots) -> IndexerSummary:
    """Run an incremental update of the content index.

    Args:
        db_path: Path to the database.
        roots: Content index roots.

    Returns:
        IndexerSummary with operation results.
    """
    config = IndexerConfig(strict_mode=False, include_detail_projections=False)
    return update_index(db_path, roots, config)


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "SchedulerContentIndexConfig",
    "SchedulerContentIndexResult",
    "SchedulerLogFn",
    "load_scheduler_content_index_config_from_env",
    "update_content_index_after_scheduler_run",
    # Re-export env var names for convenience
    "CONTENT_INDEX_ENABLED_ENV_VAR",
    "CONTENT_INDEX_DB_PATH_ENV_VAR",
    "CONTENT_INDEX_UPDATE_MODE_ENV_VAR",
]
