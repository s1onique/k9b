#!/usr/bin/env python3
"""
Tests for safe stale lock removal functionality.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Test configuration
REPO_ROOT = Path(__file__).parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"

# Add scripts to path for imports
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


class TestSafeStaleUnlock(unittest.TestCase):
    """Test safe stale lock removal."""
    
    def setUp(self) -> None:
        """Set up isolated temp directory for each test."""
        self._tmp_dir = tempfile.mkdtemp(prefix="test_unlock_")
        self._lock_dir = Path(self._tmp_dir) / ".verify_lock"
    
    def tearDown(self) -> None:
        """Clean up temp directory."""
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
    
    def test_active_lock_not_removed(self) -> None:
        """Active lock should NOT be removed by stale unlock."""
        from verify_all_lock import LockMetadata, VerifyLock
        
        # Create an active lock (our own PID)
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        (self._lock_dir / "lock").touch()
        
        metadata = LockMetadata.create_current(profile="test")
        with open(self._lock_dir / "metadata.json", "w") as f:
            json.dump(metadata.to_dict(), f)
        
        lock = VerifyLock(self._lock_dir)
        success, message = lock.unlock_stale()
        
        self.assertFalse(success)
        self.assertIn("active", message.lower())
        self.assertIn("running", message.lower())
        # Lock should still exist
        self.assertTrue((self._lock_dir / "lock").exists())
    
    def test_orphaned_lock_can_be_removed(self) -> None:
        """Orphaned lock should be safely removable."""
        from verify_all_lock import LockMetadata, VerifyLock
        
        # Create an orphaned lock (non-existent PID)
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        (self._lock_dir / "lock").touch()
        
        # Set file mtime to be old
        old_time = time.time() - 7200
        os.utime(self._lock_dir / "lock", (old_time, old_time))
        
        metadata = LockMetadata.create_current(profile="test")
        metadata.owner_pid = 999999  # Non-existent PID
        with open(self._lock_dir / "metadata.json", "w") as f:
            json.dump(metadata.to_dict(), f)
        
        lock = VerifyLock(self._lock_dir)
        success, message = lock.unlock_stale()
        
        self.assertTrue(success)
        self.assertIn("stale", message.lower())
        # Lock should be removed
        self.assertFalse((self._lock_dir / "lock").exists())
        self.assertFalse((self._lock_dir / "metadata.json").exists())
    
    def test_no_lock_unlock_succeeds(self) -> None:
        """Unlocking when no lock exists should succeed."""
        from verify_all_lock import VerifyLock
        
        lock = VerifyLock(self._lock_dir)
        success, message = lock.unlock_stale()
        
        self.assertTrue(success)
        self.assertIn("no lock", message.lower())


class TestLockRelease(unittest.TestCase):
    """Test lock acquire/release lifecycle."""
    
    def setUp(self) -> None:
        """Set up isolated temp directory for each test."""
        self._tmp_dir = tempfile.mkdtemp(prefix="test_release_")
        self._repo_root = Path(self._tmp_dir)
        self._lock_dir = self._repo_root / ".verify_lock"
    
    def tearDown(self) -> None:
        """Clean up temp directory."""
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
    
    def test_release_removes_mkdir_lock(self) -> None:
        """release() should properly remove lock created via mkdir (directory)."""
        from verify_all_lock import VerifyLock
        
        lock = VerifyLock(self._lock_dir)
        
        # Acquire creates a directory lock via mkdir
        self.assertTrue(lock.acquire(profile="test"))
        
        # Verify lock is a directory (created via mkdir)
        lock_path = self._lock_dir / "lock"
        self.assertTrue(lock_path.exists())
        self.assertTrue(lock_path.is_dir())
        
        # Release should remove the lock
        lock.release()
        
        # Lock should be gone
        self.assertFalse(lock_path.exists())
    
    def test_acquire_release_via_facade(self) -> None:
        """acquire_verify_lock and release should work correctly."""
        from verify_all_lock import acquire_verify_lock
        
        # Acquire lock via facade
        lock = acquire_verify_lock(self._repo_root, profile="test")
        
        # Verify lock exists
        lock_path = self._lock_dir / "lock"
        self.assertTrue(lock_path.exists())
        
        # Release via the VerifyLock object
        lock.release()
        
        # Lock should be gone
        self.assertFalse(lock_path.exists())
    
    def test_context_manager_release(self) -> None:
        """Context manager should properly release lock."""
        from verify_all_lock import VerifyLock
        
        lock = VerifyLock(self._lock_dir)
        lock_path = self._lock_dir / "lock"
        
        # Use context manager
        with lock:
            self.assertTrue(lock_path.exists())
        
        # Lock should be released after context
        self.assertFalse(lock_path.exists())


if __name__ == "__main__":
    unittest.main()
