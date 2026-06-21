#!/usr/bin/env python3
"""
Single-run lock and stale-lock handling for verify_all.

This module is a thin compatibility facade that re-exports the public API
from the modular lock components.

Features:
- Rich lock metadata (PID, PPID, PGID, cmdline, cwd, hostname, user, timestamps, profile)
- Lock status command for diagnostics
- JSON status output for machine parsing
- Cooperative wait mode with bounded backoff
- Proof-based stale lock detection (never removes lock just because it's old)
- Safe unlock command (only when owner is proven absent or mismatched)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from verify_all_lock_core import VerifyLock
from verify_all_lock_types import LockError, LockMetadata, LockStatus  # noqa: F401
from verify_all_lock_wait import (
    get_lock_status as _get_lock_status,
)
from verify_all_lock_wait import (
    unlock_stale_lock as _unlock_stale_lock,
)
from verify_all_lock_wait import (
    wait_for_lock as _wait_for_lock,
)


def get_lock_status(repo_root: str | Path) -> LockStatus:
    """
    Get lock status for diagnostics.
    
    Args:
        repo_root: Repository root directory
        
    Returns:
        LockStatus with detailed lock information
    """
    lock_dir = Path(repo_root) / ".verify_lock"
    return _get_lock_status(lock_dir)


def unlock_stale_lock(repo_root: str | Path) -> tuple[bool, str]:
    """
    Safely remove a stale lock.
    
    Args:
        repo_root: Repository root directory
        
    Returns:
        Tuple of (success, message)
    """
    lock_dir = Path(repo_root) / ".verify_lock"
    success: bool
    message: str
    success, message = _unlock_stale_lock(lock_dir)
    return (success, message)


def wait_for_lock(
    repo_root: str | Path,
    timeout_seconds: int = 300,
    poll_interval: int = 5,
) -> tuple[bool, str]:
    """
    Wait for lock to be released with bounded backoff.
    
    Args:
        repo_root: Repository root directory
        timeout_seconds: Maximum time to wait
        poll_interval: Time between status checks
        
    Returns:
        Tuple of (acquired, message)
    """
    lock_dir = Path(repo_root) / ".verify_lock"
    acquired: bool
    message: str
    acquired, message = _wait_for_lock(
        lock_dir,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
    )
    return (acquired, message)


def acquire_verify_lock(repo_root: str | Path, profile: str | None = None) -> VerifyLock:
    """
    Acquire the verification lock.
    
    Args:
        repo_root: Repository root directory
        profile: The verification profile (act-local, fast, full)
        
    Returns:
        VerifyLock instance (already acquired)
        
    Raises:
        LockError: If lock cannot be acquired
    """
    lock_dir = Path(repo_root) / ".verify_lock"
    lock = VerifyLock(lock_dir)
    lock._profile = profile
    
    if not lock.acquire(profile=profile):
        # Get status for better error message
        status = lock.get_status()
        error_msg = f"Another verification run is active (PID: {status.owner_pid}, age: {int(status.lock_age_seconds)}s)"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        print("Hint: Run ./scripts/verify_all.sh --lock-status for diagnostics", file=sys.stderr)
        raise LockError(error_msg)
    
    return lock


def check_recursion() -> bool:
    """
    Check if verification is already running (recursion guard).
    
    Returns True if recursion detected, False otherwise.
    """
    return os.environ.get("VERIFY_ALL_ACTIVE") == "1"


def set_recursion_guard() -> None:
    """Set the recursion guard environment variable."""
    os.environ["VERIFY_ALL_ACTIVE"] = "1"
