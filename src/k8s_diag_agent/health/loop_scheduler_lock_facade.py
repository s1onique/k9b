"""Lock-method façade/wrappers for HealthLoopScheduler.

Extracted from loop_scheduler.py to reduce complexity.
These methods delegate to LockManager while preserving the private method
signature that tests patch.

Design rationale:
- LockManager already exists in loop_scheduler_locking.py with the actual implementation
- This module provides thin façade functions that accept LockManager as parameter
- HealthLoopScheduler keeps one-line delegation methods to preserve test compatibility
- Tests that patch scheduler._acquire_lock will still work because run() calls self._acquire_lock()

Modules relationship:
- loop_scheduler_lock_eval.py: Pure lock parsing/evaluation functions
- loop_scheduler_locking.py: LockManager class (stateful, side-effecting)
- loop_scheduler_lock_facade.py: Thin façade wrappers for test compatibility
- loop_scheduler.py: HealthLoopScheduler with delegation methods
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .loop_scheduler_locking import LockManager
    from .loop_scheduler_models import LockEvaluation, ProcessIdentity


# ============================================================================
# Façade functions - thin wrappers around LockManager methods
# These exist to provide a public seam that can be used by tests via monkeypatch
# ============================================================================


def acquire_lock(lock_manager: LockManager) -> bool:
    """Attempt to acquire the scheduler lock file.

    Delegates to LockManager.acquire_lock().
    """
    return lock_manager.acquire_lock()


def release_lock(lock_manager: LockManager) -> None:
    """Release the scheduler lock file if it exists.

    Delegates to LockManager.release_lock().
    """
    lock_manager.release_lock()


def evaluate_lock_state(lock_manager: LockManager) -> LockEvaluation:
    """Evaluate the current lock file state to determine staleness.

    Delegates to LockManager.evaluate_lock_state().
    """
    return lock_manager.evaluate_lock_state()


def remove_stale_lock(lock_manager: LockManager, evaluation: LockEvaluation) -> bool:
    """Remove a stale lock file and log the removal.

    Delegates to LockManager.remove_stale_lock().
    """
    return lock_manager.remove_stale_lock(evaluation)


def log_lock_held(lock_manager: LockManager, evaluation: LockEvaluation) -> None:
    """Log when a lock is held by another process.

    Delegates to LockManager.log_lock_held().
    """
    lock_manager.log_lock_held(evaluation)


def current_process_identity(lock_manager: LockManager) -> ProcessIdentity | None:
    """Get the identity of the current process.

    Delegates to LockManager.current_process_identity().
    """
    return lock_manager.current_process_identity()


def read_process_identity(lock_manager: LockManager, pid: int) -> ProcessIdentity | None:
    """Read process identity information from /proc.

    Delegates to LockManager.read_process_identity().
    """
    return lock_manager.read_process_identity(pid)


def serialize_identity(identity: ProcessIdentity | None) -> dict[str, str] | None:
    """Serialize identity to a dictionary for JSON storage.

    Delegates to LockManager.serialize_identity().
    """
    from .loop_scheduler_locking import LockManager

    return LockManager.serialize_identity_static(identity)


def pid_is_alive(lock_manager: LockManager, pid: int) -> bool:
    """Check if a process ID is still alive.

    Delegates to LockManager.pid_is_alive().
    """
    return lock_manager.pid_is_alive(pid)


# ============================================================================
# Re-exports for backward compatibility with tests that may import directly
# ============================================================================

__all__ = [
    "acquire_lock",
    "current_process_identity",
    "evaluate_lock_state",
    "log_lock_held",
    "pid_is_alive",
    "read_process_identity",
    "release_lock",
    "remove_stale_lock",
    "serialize_identity",
]
