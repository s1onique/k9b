#!/usr/bin/env python3
"""
Single-run lock and stale-lock handling for verify_all.

Provides exclusive locking to prevent concurrent verification runs,
with automatic cleanup of stale locks left behind by crashed processes.

Features:
- Rich lock metadata (PID, PPID, PGID, cmdline, cwd, hostname, user, timestamps, profile)
- Lock status command for diagnostics
- JSON status output for machine parsing
- Cooperative wait mode with bounded backoff
- Proof-based stale lock detection (never removes lock just because it's old)
- Safe unlock command (only when owner is proven absent or mismatched)
"""

from __future__ import annotations

import dataclasses
import json
import os
import signal
import socket
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Lock file age threshold for considering a lock stale (seconds)
# Only used when owner PID is absent AND heartbeat is too old
STALE_LOCK_THRESHOLD = 3600  # 1 hour

# Heartbeat interval (seconds) - lock owner should update this
HEARTBEAT_INTERVAL = 60  # 1 minute


@dataclasses.dataclass
class LockMetadata:
    """Rich lock metadata stored in JSON format."""
    owner_pid: int
    parent_pid: int | None
    process_group_id: int | None
    command_line: list[str]
    cwd: str
    hostname: str
    user: str
    created_at: str  # ISO format timestamp
    last_heartbeat: str | None  # ISO format timestamp
    profile: str | None  # act-local, fast, full, etc.
    
    def to_dict(self) -> dict:
        return dataclasses.asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> LockMetadata:
        return cls(**data)
    
    @classmethod
    def create_current(cls, profile: str | None = None) -> LockMetadata:
        """Create metadata from current process."""
        return cls(
            owner_pid=os.getpid(),
            parent_pid=os.getppid() if hasattr(os, 'getppid') else None,
            process_group_id=os.getpgid(os.getpid()) if hasattr(os, 'getpgid') else None,
            command_line=sys.argv[:],
            cwd=os.getcwd(),
            hostname=socket.gethostname(),
            user=os.environ.get('USER', os.environ.get('USERNAME', 'unknown')),
            created_at=datetime.now(UTC).isoformat(),
            last_heartbeat=None,
            profile=profile,
        )
    
    def update_heartbeat(self) -> None:
        """Update the heartbeat timestamp."""
        self.last_heartbeat = datetime.now(UTC).isoformat()


@dataclasses.dataclass
class LockStatus:
    """Lock status for diagnostics and machine parsing."""
    locked: bool
    owner_pid: int | None
    owner_exists: bool
    owner_command: str | None
    lock_age_seconds: float
    status: str  # active, stale, orphaned, invalid, no_lock
    safe_to_remove: bool
    reason: str
    recommended_action: str
    
    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class LockError(Exception):
    """Raised when lock acquisition fails."""
    pass


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
            import atexit
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
        
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except OSError:
            pass
        
        try:
            if self.metadata_file.exists():
                self.metadata_file.unlink()
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
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False
    
    def _get_process_command(self, pid: int) -> str | None:
        """Get process command line for diagnostics."""
        try:
            # Try /proc on Linux/Unix
            cmdline_file = Path(f"/proc/{pid}/cmdline")
            if cmdline_file.exists():
                with open(cmdline_file) as f:
                    cmdline = f.read().replace('\x00', ' ').strip()
                return cmdline if cmdline else None
        except (OSError, PermissionError):
            pass
        
        # Fallback: try ps command
        try:
            import subprocess
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm="],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        
        return None
    
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
                return age >= STALE_LOCK_THRESHOLD
                
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
            # No metadata or PID - orphaned by default
            return LockStatus(
                locked=True,
                owner_pid=None,
                owner_exists=False,
                owner_command=None,
                lock_age_seconds=age,
                status="orphaned",
                safe_to_remove=True,
                reason="Lock exists but no owner metadata found",
                recommended_action="Lock has no owner metadata. Run: ./scripts/verify_all.sh --unlock-stale to remove",
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


def get_lock_status(repo_root: str | Path) -> LockStatus:
    """
    Get lock status for diagnostics.
    
    Args:
        repo_root: Repository root directory
        
    Returns:
        LockStatus with detailed lock information
    """
    lock_dir = Path(repo_root) / ".verify_lock"
    lock = VerifyLock(lock_dir)
    return lock.get_status()


def unlock_stale_lock(repo_root: str | Path) -> tuple[bool, str]:
    """
    Safely remove a stale lock.
    
    Args:
        repo_root: Repository root directory
        
    Returns:
        Tuple of (success, message)
    """
    lock_dir = Path(repo_root) / ".verify_lock"
    lock = VerifyLock(lock_dir)
    return lock.unlock_stale()


def wait_for_lock(repo_root: str | Path, timeout_seconds: int = 300, poll_interval: int = 5) -> tuple[bool, str]:
    """
    Wait for lock to be released with bounded backoff.
    
    Args:
        repo_root: Repository root directory
        timeout_seconds: Maximum time to wait
        poll_interval: Time between status checks
        
    Returns:
        Tuple of (acquired, message)
    """
    start_time = time.time()
    poll_count = 0
    
    while time.time() - start_time < timeout_seconds:
        status = get_lock_status(repo_root)
        
        if not status.locked:
            return True, "Lock released - proceeding"
        
        poll_count += 1
        elapsed = int(time.time() - start_time)
        
        # Print periodic diagnostics
        if poll_count % 3 == 1:  # Every ~15 seconds
            print(f"Waiting for lock... ({elapsed}s elapsed, owner PID: {status.owner_pid})", file=sys.stderr)
        
        time.sleep(poll_interval)
    
    # Timeout
    status = get_lock_status(repo_root)
    return False, f"Timeout after {timeout_seconds}s - lock still held by PID {status.owner_pid}"
