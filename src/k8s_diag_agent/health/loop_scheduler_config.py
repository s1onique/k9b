"""Scheduler configuration and timing helpers.

Extracted from loop_scheduler.py to reduce its size and improve LLM-friendly traversal.
Preserves behavior exactly - no lock semantics, scheduling cadence, or artifact contract changes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .loop import HealthRunConfig


# =============================================================================
# Constants for stale lock threshold computation
# =============================================================================

# These are re-exported here for backward compatibility with tests that may
# reference them through the scheduler class.
_LOCK_STALE_MIN_SECONDS = 60
_LOCK_STALE_AGE_MULTIPLIER = 3.0


# =============================================================================
# Pure Timing/Config Helpers
# =============================================================================


def compute_stale_lock_age_threshold(
    interval_seconds: int | None,
    min_seconds: int = _LOCK_STALE_MIN_SECONDS,
    age_multiplier: float = _LOCK_STALE_AGE_MULTIPLIER,
) -> float:
    """Compute the threshold for considering a lock stale.

    Args:
        interval_seconds: The scheduler interval setting, or None if not set
        min_seconds: Minimum threshold in seconds (default: 60)
        age_multiplier: Multiplier for computing threshold from interval (default: 3.0)

    Returns:
        The age threshold in seconds; a lock older than this may be considered stale
    """
    interval = interval_seconds or min_seconds
    base = max(interval, min_seconds)
    return base * age_multiplier


def format_last_run_timestamp(last_run_finish_time: float | None) -> str | None:
    """Format the last run finish time as an ISO string in UTC.

    Args:
        last_run_finish_time: Unix timestamp of the last run completion, or None

    Returns:
        ISO-formatted timestamp string, or None if input is None
    """
    if last_run_finish_time is None:
        return None
    return datetime.fromtimestamp(last_run_finish_time, UTC).isoformat()


def parse_lock_timestamp(value: str | None) -> datetime | None:
    """Parse lock timestamp string to timezone-aware UTC datetime.

    Args:
        value: ISO timestamp string, or None

    Returns:
        Timezone-aware UTC datetime, or None if parsing fails
    """
    from ..datetime_utils import parse_iso_to_utc

    return parse_iso_to_utc(value)


def resolve_hostname() -> str | None:
    """Resolve the local hostname, returning None on failure.

    Returns:
        The hostname string, or None if resolution fails
    """
    import socket

    try:
        return socket.gethostname()
    except OSError:
        return None


# =============================================================================
# Scheduler Config Payload Construction
# =============================================================================


def build_scheduler_startup_metadata(
    interval_seconds: int | None,
    max_runs: int | None,
    run_once: bool,
) -> dict[str, Any]:
    """Build metadata dictionary for scheduler startup log event.

    Args:
        interval_seconds: Scheduler interval setting
        max_runs: Maximum runs limit, or None for unlimited
        run_once: Whether running in single-shot mode

    Returns:
        Dictionary with scheduler startup metadata
    """
    return {
        "interval_seconds": interval_seconds,
        "max_runs": max_runs,
        "run_once": run_once,
    }


def build_effective_scheduler_config_payload(
    config: HealthRunConfig,
    interval_seconds: int | None,
    max_runs: int | None,
    run_once: bool,
) -> dict[str, Any]:
    """Build the effective scheduler configuration payload for logging.

    This extracts safe, non-secret runtime settings for observability.
    It does not change scheduler behavior and avoids forcing side effects.

    Args:
        config: The loaded HealthRunConfig
        interval_seconds: Scheduler interval setting
        max_runs: Maximum runs limit
        run_once: Whether running in single-shot mode

    Returns:
        Dictionary suitable for structured log metadata
    """
    from .loop_config_logging import _build_effective_scheduler_config_log

    return _build_effective_scheduler_config_log(
        config=config,
        interval_seconds=interval_seconds,
        max_runs=max_runs,
        run_once=run_once,
    )


def log_effective_scheduler_config(
    config: HealthRunConfig,
    interval_seconds: int | None,
    max_runs: int | None,
    run_once: bool,
    log_fn: Any,
) -> None:
    """Emit the effective scheduler configuration log event.

    This function should be called once at scheduler startup, after config
    has been resolved but before the first run begins.

    Args:
        config: The loaded HealthRunConfig
        interval_seconds: Scheduler interval setting
        max_runs: Maximum runs limit
        run_once: Whether running in single-shot mode
        log_fn: Function to call for logging (e.g., scheduler._log_event)
    """
    from .loop_config_logging import _log_effective_scheduler_config as _emit_config_log

    _emit_config_log(
        config=config,
        interval_seconds=interval_seconds,
        max_runs=max_runs,
        run_once=run_once,
        log_fn=log_fn,
    )


# =============================================================================
# Re-exports for backward compatibility
# =============================================================================

__all__ = [
    "_LOCK_STALE_AGE_MULTIPLIER",
    "_LOCK_STALE_MIN_SECONDS",
    "build_effective_scheduler_config_payload",
    "build_scheduler_startup_metadata",
    "compute_stale_lock_age_threshold",
    "format_last_run_timestamp",
    "log_effective_scheduler_config",
    "parse_lock_timestamp",
    "resolve_hostname",
]
