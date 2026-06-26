#!/usr/bin/env python3
"""
Wait and unlock wrapper functions for verify_all lock.

Provides high-level functions for waiting on locks and safely
removing stale locks.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from verify_all_lock_core import VerifyLock
from verify_all_lock_types import LockStatus


def get_lock_status(lock_dir: Path) -> LockStatus:
    """
    Get lock status for diagnostics.
    
    Args:
        lock_dir: Lock directory path
        
    Returns:
        LockStatus with detailed lock information
    """
    lock = VerifyLock(lock_dir)
    return lock.get_status()


def unlock_stale_lock(lock_dir: Path) -> tuple[bool, str]:
    """
    Safely remove a stale lock.
    
    Args:
        lock_dir: Lock directory path
        
    Returns:
        Tuple of (success, message)
    """
    lock = VerifyLock(lock_dir)
    success: bool
    message: str
    success, message = lock.unlock_stale()
    return (success, message)


def wait_for_lock(
    lock_dir: Path,
    timeout_seconds: int = 300,
    poll_interval: int = 5
) -> tuple[bool, str]:
    """
    Wait for lock to be released with bounded backoff.
    
    Args:
        lock_dir: Lock directory path
        timeout_seconds: Maximum time to wait
        poll_interval: Time between status checks
        
    Returns:
        Tuple of (acquired, message)
    """
    start_time = time.time()
    poll_count = 0
    
    while True:
        # Check if we've exceeded the timeout
        elapsed = time.time() - start_time
        if elapsed >= timeout_seconds:
            # Timeout - check lock status for the message
            status = get_lock_status(lock_dir)
            return False, f"Timeout after {timeout_seconds}s - lock still held by PID {status.owner_pid}"
        
        status = get_lock_status(lock_dir)
        
        if not status.locked:
            return True, "Lock released - proceeding"
        
        poll_count += 1
        
        # Print periodic diagnostics (every ~15 seconds)
        if poll_count % 3 == 1:
            print(f"Waiting for lock... ({int(elapsed)}s elapsed, owner PID: {status.owner_pid})", file=sys.stderr)
        
        # Calculate remaining time and sleep for min(poll_interval, remaining_time)
        remaining = timeout_seconds - elapsed
        sleep_time = min(poll_interval, remaining)
        if sleep_time > 0:
            time.sleep(sleep_time)
