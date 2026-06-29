"""Facade module for loop scheduler.

This module provides backward-compatible imports for the loop scheduler.
The main implementation has been moved to loop_scheduler_runner.py.

FAÇADE PATTERN: This file re-exports all public names from the extracted
modules to maintain import compatibility with existing code.

Public names available:
- HealthLoopScheduler
- schedule_health_loop
- ProcessIdentity
- LockFileSnapshot
- LockEvaluation
- _HEALTH_LOCK_FILENAME
- _LOCK_SKIP_ESCALATION_THRESHOLD
- _LOCK_STALE_MIN_SECONDS
- uuid4

Do not add implementation here - all logic is in loop_scheduler_runner.py.
"""

from __future__ import annotations

# Re-export uuid4 for backward compatibility with tests that patch it
from uuid import uuid4  # noqa: F401

# Re-export additional backward-compatibility items from other modules
from .loop_scheduler_config import (  # noqa: F401
    _LOCK_STALE_AGE_MULTIPLIER,
    compute_stale_lock_age_threshold,
    format_last_run_timestamp,
    parse_lock_timestamp,
    resolve_hostname,
)
from .loop_scheduler_cycle import (  # noqa: F401
    CycleState,
    compute_cycle_exit_code,
    compute_sleep_duration,
    should_break_after_cycle,
    should_continue_scheduler,
)
from .loop_scheduler_diagnostics import (  # noqa: F401
    build_diagnostic_pack,
    log_run_summary,
)
from .loop_scheduler_entrypoint import schedule_health_loop  # noqa: F401
from .loop_scheduler_lock_facade import (  # noqa: F401
    acquire_lock,
    log_lock_held,
    release_lock,
    remove_stale_lock,
)
from .loop_scheduler_locking import LockManager  # noqa: F401
from .loop_scheduler_models import (  # noqa: F401
    _HEALTH_ONLY_MESSAGE,
    DIAGNOSTIC_PACK_TIMEOUT_SECONDS,
    _str_or_none,
)

# Re-export the main classes and functions from loop_scheduler_runner
from .loop_scheduler_runner import (  # noqa: F401
    # Re-export constants
    _HEALTH_LOCK_FILENAME,
    _LOCK_SKIP_ESCALATION_THRESHOLD,
    _LOCK_STALE_MIN_SECONDS,
    HealthLoopScheduler,
    # Re-export models for backward compatibility
    LockEvaluation,
    LockFileSnapshot,
    ProcessIdentity,
)

# Public API - all names that were available from the original loop_scheduler.py
__all__ = [
    # uuid4 for backward compatibility
    "uuid4",
    # Main classes and functions
    "HealthLoopScheduler",
    "schedule_health_loop",
    # Models
    "ProcessIdentity",
    "LockFileSnapshot",
    "LockEvaluation",
    # Constants
    "_HEALTH_LOCK_FILENAME",
    "_HEALTH_ONLY_MESSAGE",
    "_LOCK_SKIP_ESCALATION_THRESHOLD",
    "_LOCK_STALE_MIN_SECONDS",
    "_LOCK_STALE_AGE_MULTIPLIER",
    "DIAGNOSTIC_PACK_TIMEOUT_SECONDS",
    # Helper functions
    "_str_or_none",
    "compute_stale_lock_age_threshold",
    "format_last_run_timestamp",
    "parse_lock_timestamp",
    "resolve_hostname",
    # Cycle helpers
    "CycleState",
    "compute_cycle_exit_code",
    "compute_sleep_duration",
    "should_break_after_cycle",
    "should_continue_scheduler",
    # Diagnostic helpers
    "build_diagnostic_pack",
    "log_run_summary",
    # Lock helpers
    "LockManager",
    "acquire_lock",
    "log_lock_held",
    "release_lock",
    "remove_stale_lock",
]
