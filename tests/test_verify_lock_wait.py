#!/usr/bin/env python3
"""
Tests for wait-for-lock functionality.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Test configuration
REPO_ROOT = Path(__file__).parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"
VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"

# Add scripts to path for imports
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


class TestWaitMode(unittest.TestCase):
    """Test wait for lock functionality."""
    
    def setUp(self) -> None:
        """Set up isolated temp directory for each test."""
        self._tmp_dir = tempfile.mkdtemp(prefix="test_wait_")
        # _repo_root is the parent of _lock_dir
        self._repo_root = self._tmp_dir
        self._lock_dir = Path(self._tmp_dir) / ".verify_lock"
    
    def tearDown(self) -> None:
        """Clean up temp directory."""
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
    
    def test_wait_mode_timeout(self) -> None:
        """Wait mode should timeout cleanly."""
        from verify_all_lock import LockMetadata, wait_for_lock
        
        # Create an active lock (our own PID) - use repo_root as argument
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        (self._lock_dir / "lock").touch()
        
        metadata = LockMetadata.create_current(profile="test")
        with open(self._lock_dir / "metadata.json", "w") as f:
            json.dump(metadata.to_dict(), f)
        
        # Wait with short timeout - pass repo_root, not lock_dir
        acquired, message = wait_for_lock(
            self._repo_root,
            timeout_seconds=2, 
            poll_interval=1
        )
        
        self.assertFalse(acquired)
        self.assertIn("timeout", message.lower())
        self.assertIn(str(os.getpid()), message)
    
    def test_wait_mode_succeeds_when_lock_released(self) -> None:
        """Wait mode should succeed when lock is released."""
        from verify_all_lock import wait_for_lock
        
        # No lock exists - pass repo_root
        acquired, message = wait_for_lock(
            self._repo_root,
            timeout_seconds=5,
            poll_interval=1
        )
        
        self.assertTrue(acquired)
        self.assertIn("proceeding", message.lower())


class TestFacadePathSemantics(unittest.TestCase):
    """Test that facade functions use correct .verify_lock path."""
    
    def setUp(self) -> None:
        """Set up isolated temp directory for each test."""
        self._tmp_dir = tempfile.mkdtemp(prefix="test_path_semantics_")
        self._repo_root = self._tmp_dir
        self._lock_dir = Path(self._tmp_dir) / ".verify_lock"
    
    def tearDown(self) -> None:
        """Clean up temp directory."""
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
    
    def test_get_lock_status_uses_verify_lock_dir(self) -> None:
        """get_lock_status should inspect .verify_lock, not repo_root directly."""
        from verify_all_lock import LockMetadata, get_lock_status
        
        # Create lock in .verify_lock subdirectory
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        (self._lock_dir / "lock").touch()
        
        metadata = LockMetadata.create_current(profile="test")
        with open(self._lock_dir / "metadata.json", "w") as f:
            json.dump(metadata.to_dict(), f)
        
        # Call with repo_root - should see the lock
        status = get_lock_status(self._repo_root)
        
        self.assertTrue(status.locked)
        self.assertEqual(status.status, "active")
    
    def test_no_lock_when_verify_lock_does_not_exist(self) -> None:
        """get_lock_status should report no lock when .verify_lock doesn't exist."""
        from verify_all_lock import get_lock_status
        
        # Don't create .verify_lock directory
        # Call with repo_root - should report no lock
        status = get_lock_status(self._repo_root)
        
        self.assertFalse(status.locked)
        self.assertEqual(status.status, "no_lock")
    
    def test_wait_for_lock_uses_verify_lock_dir(self) -> None:
        """wait_for_lock should wait on .verify_lock, not repo_root directly."""
        from verify_all_lock import LockMetadata, wait_for_lock
        
        # Create an active lock
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        (self._lock_dir / "lock").touch()
        
        metadata = LockMetadata.create_current(profile="test")
        with open(self._lock_dir / "metadata.json", "w") as f:
            json.dump(metadata.to_dict(), f)
        
        # Wait with repo_root - should timeout (lock exists)
        acquired, message = wait_for_lock(
            self._repo_root,
            timeout_seconds=2,
            poll_interval=1
        )
        
        self.assertFalse(acquired)
        self.assertIn("timeout", message.lower())


class TestWaitForLockCommand(unittest.TestCase):
    """Test --wait-for-lock command integration."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        if not VERIFY_ALL.exists():
            self.skipTest("verify_all.sh not found")
        os.chmod(VERIFY_ALL, 0o755)
        # Create a held lock fixture so wait-for-lock times out
        now = datetime.now(timezone.utc).isoformat()
        self._lock_dir = REPO_ROOT / ".verify_lock"
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        (self._lock_dir / "lock").touch()
        metadata = {
            "owner_pid": os.getpid(),
            "parent_pid": os.getppid(),
            "process_group_id": os.getpgid(os.getpid()),
            "command_line": [str(VERIFY_ALL), "--act-local"],
            "cwd": str(REPO_ROOT),
            "hostname": "test fixture",
            "user": "test",
            "created_at": now,
            "last_heartbeat": now,
            "profile": "test",
        }
        with open(self._lock_dir / "metadata.json", "w") as f:
            json.dump(metadata, f)
    
    def tearDown(self) -> None:
        """Clean up any existing lock."""
        if hasattr(self, "_lock_dir") and self._lock_dir.exists():
            shutil.rmtree(self._lock_dir, ignore_errors=True)
    
    def test_wait_for_lock_short_timeout(self) -> None:
        """--wait-for-lock with short timeout should work."""
        result = subprocess.run(
            [str(VERIFY_ALL), "--act-local", "--wait-for-lock", "2"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=REPO_ROOT,
        )
        
        # Lock is held by fixture - should timeout with exit code 4
        self.assertEqual(result.returncode, 4)


if __name__ == "__main__":
    unittest.main()
