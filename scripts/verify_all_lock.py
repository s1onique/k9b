#!/usr/bin/env python3
"""
Single-run lock and stale-lock handling for verify_all.

Provides exclusive locking to prevent concurrent verification runs,
with automatic cleanup of stale locks left behind by crashed processes.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

# Lock file age threshold for considering a lock stale (seconds)
STALE_LOCK_THRESHOLD = 3600  # 1 hour


class LockError(Exception):
    """Raised when lock acquisition fails."""
    pass


class VerifyLock:
    """
    Single-run lock with stale-lock handling.
    
    Uses mkdir for atomic lock acquisition (race-safe).
    Stores PID in lock file for verification.
    Cleans up on exit via atexit handler.
    """
    
    def __init__(self, lock_dir: str | Path):
        self.lock_dir = Path(lock_dir)
        self.lock_file = self.lock_dir / "lock"
        self.pid_file = self.lock_dir / "pid"
        self._acquired = False
    
    def acquire(self) -> bool:
        """
        Attempt to acquire the lock.
        
        Returns True if lock acquired, False if already locked.
        Raises LockError on unexpected errors.
        """
        # Ensure lock directory exists
        try:
            self.lock_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise LockError(f"Cannot create lock directory: {e}")
        
        # Check for stale lock first
        if self._is_stale():
            self._cleanup_stale()
        
        # Try to acquire lock atomically using mkdir
        try:
            os.mkdir(str(self.lock_file))
        except FileExistsError:
            # Lock is held by another process
            return False
        except OSError as e:
            raise LockError(f"Cannot acquire lock: {e}")
        
        # Write PID file
        try:
            with open(self.pid_file, "w") as f:
                f.write(str(os.getpid()))
        except OSError:
            # Non-fatal, lock is still valid
            pass
        
        self._acquired = True
        
        # Register cleanup handler
        try:
            import atexit
            atexit.register(self.release)
        except Exception:
            pass
        
        # Register signal handlers for clean exit
        def cleanup_handler(signum, frame):
            self.release()
            sys.exit(128 + signum)
        
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            try:
                signal.signal(sig, cleanup_handler)
            except (ValueError, OSError):
                pass
        
        return True
    
    def release(self) -> None:
        """Release the lock if held."""
        if not self._acquired:
            return
        
        self._acquired = False
        
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except OSError:
            pass
        
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
        except OSError:
            pass
    
    def _is_stale(self) -> bool:
        """Check if the lock is stale (old process or crashed)."""
        if not self.lock_file.exists():
            return False
        
        # Check lock file age
        try:
            mtime = self.lock_file.stat().st_mtime
            age = time.time() - mtime
            if age < STALE_LOCK_THRESHOLD:
                # Lock is recent, check if process is alive
                if self.pid_file.exists():
                    try:
                        pid = int(self.pid_file.read_text().strip())
                        # Check if process is still running
                        os.kill(pid, 0)
                        return False  # Process is alive, lock is valid
                    except (ValueError, OSError, ProcessLookupError, PermissionError):
                        # Process is dead or we can't check, treat as stale
                        return True
                return age >= STALE_LOCK_THRESHOLD
        except OSError:
            pass
        
        return True
    
    def _cleanup_stale(self) -> None:
        """Remove a stale lock."""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except OSError:
            pass
        
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
        except OSError:
            pass
    
    def is_locked(self) -> bool:
        """Check if the lock is currently held (by any process)."""
        return self.lock_file.exists()
    
    def __enter__(self) -> VerifyLock:
        if not self.acquire():
            raise LockError("Another verification run is active")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()


def acquire_verify_lock(repo_root: str | Path) -> VerifyLock:
    """
    Acquire the verification lock.
    
    Args:
        repo_root: Repository root directory
        
    Returns:
        VerifyLock instance (already acquired)
        
    Raises:
        LockError: If lock cannot be acquired
    """
    lock_dir = Path(repo_root) / ".verify_lock"
    lock = VerifyLock(lock_dir)
    
    if not lock.acquire():
        print("ERROR: Another verification run is active.", file=sys.stderr)
        raise LockError("Another verification run is active")
    
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