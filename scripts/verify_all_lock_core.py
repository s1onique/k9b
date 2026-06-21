#!/usr/bin/env python3
"""
Core lock implementation for verify_all.

Provides the VerifyLock class with acquire/release/status logic.
"""

from __future__ import annotations

import atexit
import json
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from verify_all_lock_process import get_process_command, pid_exists
from verify_all_lock_types import (
    STALE_LOCK_THRESHOLD,
    LockError,
    LockMetadata,
    LockStatus,
)


class VerifyLock:
    """
    Single-run lock with rich metadata and stale-lock handling.
    
    Uses mkdir for atomic lock acquisition (race-safe).
    Stores rich JSON metadata for diagnostics.
    Cleans up on exit via atexit handler.
    """
    
    def __init__(self, lock_dir: str | Path):
        self.lock_dir = Path(lock_dir)
        self.lock_file = self.lock_dir / "lock"
        self.metadata_file = self.lock_dir / "metadata.json"
        self._acquired = False
        self._profile: str | None = None
    
    def acquire(self, profile: str | None = None) -> bool:
        """
        Attempt to acquire the lock.
        
        Args:
            profile: The verification profile (act-local, fast, full)
            
        Returns True if lock acquired, False if already locked.
        Raises LockError on unexpected errors.
        """
        self._profile = profile
        
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
        
        # Write rich metadata
        try:
            metadata = LockMetadata.create_current(profile=profile)
            with open(self.metadata_file, "w") as f:
                json.dump(metadata.to_dict(), f, indent=2)
        except OSError:
            # Non-fatal, lock is still valid
            pass
        
        self._acquired = True
        
        # Register cleanup handler
        try:
            atexit.register(self.release)
        except Exception:
            pass
        
        # Register signal handlers for clean exit
        def cleanup_handler(signum: int, frame: object) -> None:
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
        
        # Remove metadata file first
        try:
            if self.metadata_file.exists():
                self.metadata_file.unlink()
        except OSError:
            pass
        
        # Remove lock file (may be file or directory from mkdir)
        try:
            if self.lock_file.exists():
                if self.lock_file.is_dir():
                    self.lock_file.rmdir()
                else:
                    self.lock_file.unlink()
        except OSError:
            pass
    
    def _read_metadata(self) -> LockMetadata | None:
        """Read lock metadata from file."""
        if not self.metadata_file.exists():
            return None
        try:
            with open(self.metadata_file) as f:
                data = json.load(f)
            return LockMetadata.from_dict(data)
        except (OSError, json.JSONDecodeError, TypeError):
            return None
    
    def _check_owner_exists(self, pid: int) -> bool:
        """Check if owner process exists."""
        return bool(pid_exists(pid))
    
    def _get_process_command(self, pid: int) -> str | None:
        """Get process command line for diagnostics."""
        result: str | None = get_process_command(pid)
        return result
    
    def _is_stale(self) -> bool:
        """
        Check if the lock is stale.
        
        A lock is considered stale ONLY if:
        1. Owner PID no longer exists, OR
        2. Owner PID exists but command/cwd clearly doesn't match recorded identity
        3. Heartbeat is older than threshold AND owner process is absent
        
        Note: Age alone is NOT enough to consider a lock stale if owner PID is alive.
        """
        if not self.lock_file.exists():
            return False
        
        metadata = self._read_metadata()
        
        # Check lock file age
        try:
            mtime = self.lock_file.stat().st_mtime
            age = time.time() - mtime
            
            if metadata and metadata.owner_pid:
                # Check if owner process is still running
                owner_exists = self._check_owner_exists(metadata.owner_pid)
                
                if owner_exists:
                    # Owner PID is alive - lock is valid regardless of age
                    return False
                
                # Owner PID is absent - check if heartbeat is too old
                if metadata.last_heartbeat:
                    try:
                        hb_time = datetime.fromisoformat(metadata.last_heartbeat.replace('Z', '+00:00'))
                        hb_age = (datetime.now(UTC) - hb_time).total_seconds()
                        if hb_age < STALE_LOCK_THRESHOLD:
                            # Heartbeat is recent, lock might still be valid
                            # but owner is gone - consider orphaned
                            return True
                    except ValueError:
                        pass
                
                # No heartbeat or heartbeat is old - consider stale
                if age >= STALE_LOCK_THRESHOLD:
                    return True
            else:
                # No metadata or no PID - use age threshold
                return bool(age >= STALE_LOCK_THRESHOLD)
                
        except OSError:
            pass
        
        return True
    
    def _cleanup_stale(self) -> None:
        """Remove a stale lock (handles both file and directory-based locks)."""
        try:
            if self.lock_file.exists():
                # Could be a file or directory (old lock uses mkdir)
                import shutil
                if self.lock_file.is_dir():
                    shutil.rmtree(self.lock_file)
                else:
                    self.lock_file.unlink()
        except OSError:
            pass
        
        try:
            if self.metadata_file.exists():
                self.metadata_file.unlink()
        except OSError:
            pass
    
    def get_status(self) -> LockStatus:
        """
        Get the current lock status for diagnostics.
        
        Returns LockStatus with detailed information about the lock state.
        """
        if not self.lock_file.exists():
            return LockStatus(
                locked=False,
                owner_pid=None,
                owner_exists=False,
                owner_command=None,
                lock_age_seconds=0.0,
                status="no_lock",
                safe_to_remove=False,
                reason="No lock file exists",
                recommended_action="No action needed - lock is available",
            )
        
        # Lock exists - get metadata and check status
        metadata = self._read_metadata()
        try:
            mtime = self.lock_file.stat().st_mtime
            age = time.time() - mtime
        except OSError:
            age = 0.0
        
        if metadata and metadata.owner_pid:
            owner_exists = self._check_owner_exists(metadata.owner_pid)
            owner_command = self._get_process_command(metadata.owner_pid)
            
            if owner_exists:
                # Owner PID is alive - lock is active
                return LockStatus(
                    locked=True,
                    owner_pid=metadata.owner_pid,
                    owner_exists=True,
                    owner_command=owner_command or " ".join(metadata.command_line),
                    lock_age_seconds=age,
                    status="active",
                    safe_to_remove=False,
                    reason=f"Owner process {metadata.owner_pid} is running",
                    recommended_action="Run: ./scripts/verify_all.sh --wait-for-lock <seconds> to wait, or ./scripts/verify_all.sh --lock-status for diagnostics",
                )
            else:
                # Owner PID is absent - check heartbeat
                if metadata.last_heartbeat:
                    try:
                        hb_time = datetime.fromisoformat(metadata.last_heartbeat.replace('Z', '+00:00'))
                        hb_age = (datetime.now(UTC) - hb_time).total_seconds()
                        if hb_age < STALE_LOCK_THRESHOLD:
                            # Heartbeat recent but owner gone - orphaned
                            return LockStatus(
                                locked=True,
                                owner_pid=metadata.owner_pid,
                                owner_exists=False,
                                owner_command=" ".join(metadata.command_line),
                                lock_age_seconds=age,
                                status="orphaned",
                                safe_to_remove=True,
                                reason=f"Owner process {metadata.owner_pid} is gone but heartbeat was recent ({int(hb_age)}s ago)",
                                recommended_action=f"Owner PID {metadata.owner_pid} is absent. Run: ./scripts/verify_all.sh --unlock-stale to remove",
                            )
                    except ValueError:
                        pass
                
                # Owner gone, heartbeat old or missing - stale
                return LockStatus(
                    locked=True,
                    owner_pid=metadata.owner_pid,
                    owner_exists=False,
                    owner_command=" ".join(metadata.command_line),
                    lock_age_seconds=age,
                    status="stale",
                    safe_to_remove=True,
                    reason=f"Owner process {metadata.owner_pid} is absent and lock is older than threshold",
                    recommended_action=f"Owner PID {metadata.owner_pid} is absent. Run: ./scripts/verify_all.sh --unlock-stale to remove",
                )
        else:
            # No metadata - conservative handling
            # Missing metadata is NOT proof that owner is absent
            # Only consider safe to remove if lock is provably stale (> threshold age)
            if age >= STALE_LOCK_THRESHOLD:
                return LockStatus(
                    locked=True,
                    owner_pid=None,
                    owner_exists=False,
                    owner_command=None,
                    lock_age_seconds=age,
                    status="stale",
                    safe_to_remove=True,
                    reason="Lock is old and has no owner metadata - treating as stale",
                    recommended_action="Lock has no metadata and is old. Run: ./scripts/verify_all.sh --unlock-stale to remove",
                )
            else:
                # Lock is recent but no metadata - could be active owner with failed metadata write
                return LockStatus(
                    locked=True,
                    owner_pid=None,
                    owner_exists=False,
                    owner_command=None,
                    lock_age_seconds=age,
                    status="unknown",
                    safe_to_remove=False,
                    reason="Lock exists but no owner metadata found - may be active owner with failed metadata write",
                    recommended_action="Lock exists with no metadata. Run: ./scripts/verify_all.sh --lock-status for more diagnostics, or wait for owner to complete",
                )
    
    def unlock_stale(self) -> tuple[bool, str]:
        """
        Safely remove a stale lock.
        
        Returns:
            Tuple of (success, message)
            
        Only removes lock if:
        - Owner process is absent, OR
        - Owner process identity mismatch proves stale/orphaned
        """
        status = self.get_status()
        
        if status.status == "no_lock":
            return True, "No lock to remove"
        
        if status.status == "active":
            return False, f"Cannot remove active lock - owner process {status.owner_pid} is running"
        
        if not status.safe_to_remove:
            return False, f"Lock removal not safe: {status.reason}"
        
        # Safe to remove
        self._cleanup_stale()
        
        # Verify removal
        if self.lock_file.exists():
            return False, "Failed to remove lock file"
        
        return True, f"Successfully removed stale lock (was: {status.status})"
    
    def is_locked(self) -> bool:
        """Check if the lock is currently held (by any process)."""
        return self.lock_file.exists()
    
    def update_heartbeat(self) -> None:
        """Update the heartbeat timestamp in metadata."""
        metadata = self._read_metadata()
        if metadata:
            metadata.update_heartbeat()
            try:
                with open(self.metadata_file, "w") as f:
                    json.dump(metadata.to_dict(), f, indent=2)
            except OSError:
                pass
    
    def __enter__(self) -> VerifyLock:
        if not self.acquire(profile=self._profile):
            raise LockError("Another verification run is active")
        return self
    
    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.release()
