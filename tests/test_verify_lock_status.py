#!/usr/bin/env python3
"""
Tests for lock status reporting functionality.
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


class TestLockStatusReporting(unittest.TestCase):
    """Test lock status reporting functionality."""
    
    def setUp(self) -> None:
        """Set up isolated temp directory for each test."""
        self._tmp_dir = tempfile.mkdtemp(prefix="test_lock_status_")
        self._lock_dir = Path(self._tmp_dir) / ".verify_lock"
    
    def tearDown(self) -> None:
        """Clean up temp directory."""
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
    
    def test_no_lock_status(self) -> None:
        """Lock status should report no-lock state correctly."""
        from verify_all_lock import VerifyLock
        
        lock = VerifyLock(self._lock_dir)
        status = lock.get_status()
        
        self.assertFalse(status.locked)
        self.assertEqual(status.status, "no_lock")
        self.assertIsNone(status.owner_pid)
        self.assertFalse(status.safe_to_remove)
        self.assertIn("No lock file exists", status.reason)
    
    def test_active_lock_status(self) -> None:
        """Lock status should report active owner PID correctly."""
        from verify_all_lock import LockMetadata, VerifyLock
        
        # Create a lock with our PID as owner
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        (self._lock_dir / "lock").touch()
        
        # Write metadata with our PID
        metadata = LockMetadata.create_current(profile="test")
        with open(self._lock_dir / "metadata.json", "w") as f:
            json.dump(metadata.to_dict(), f)
        
        lock = VerifyLock(self._lock_dir)
        status = lock.get_status()
        
        self.assertTrue(status.locked)
        self.assertEqual(status.status, "active")
        self.assertEqual(status.owner_pid, os.getpid())
        self.assertTrue(status.owner_exists)
        self.assertFalse(status.safe_to_remove)
        self.assertIn("running", status.reason)
    
    def test_stale_lock_status_absent_pid(self) -> None:
        """Lock status should report stale lock when PID is absent."""
        from verify_all_lock import LockMetadata, VerifyLock
        
        # Create a lock with a non-existent PID (999999)
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        (self._lock_dir / "lock").touch()
        
        # Set file mtime to be old (> 1 hour ago)
        old_time = time.time() - 7200  # 2 hours ago
        os.utime(self._lock_dir / "lock", (old_time, old_time))
        
        # Write metadata with non-existent PID
        metadata = LockMetadata.create_current(profile="test")
        metadata.owner_pid = 999999  # Non-existent PID
        with open(self._lock_dir / "metadata.json", "w") as f:
            json.dump(metadata.to_dict(), f)
        
        lock = VerifyLock(self._lock_dir)
        status = lock.get_status()
        
        self.assertTrue(status.locked)
        self.assertIn(status.status, ["stale", "orphaned"])
        self.assertFalse(status.owner_exists)
        self.assertTrue(status.safe_to_remove)
        self.assertIn("absent", status.reason)
    
    def test_lock_status_json_output(self) -> None:
        """Lock status JSON should have required fields."""
        from verify_all_lock import VerifyLock
        
        lock = VerifyLock(self._lock_dir)
        status = lock.get_status()
        
        data = status.to_dict()
        
        # Check required fields
        required_fields = [
            "locked", "owner_pid", "owner_exists", "owner_command",
            "lock_age_seconds", "status", "safe_to_remove", 
            "reason", "recommended_action"
        ]
        for field in required_fields:
            self.assertIn(field, data, f"Missing required field: {field}")
        
        # Verify JSON is valid
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["locked"], data["locked"])


class TestLockErrorMessages(unittest.TestCase):
    """Test error messages include owner diagnostics."""
    
    def setUp(self) -> None:
        """Set up isolated temp directory for each test."""
        self._tmp_dir = tempfile.mkdtemp(prefix="test_errors_")
        self._lock_dir = Path(self._tmp_dir) / ".verify_lock"
    
    def tearDown(self) -> None:
        """Clean up temp directory."""
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
    
    def test_lock_error_includes_pid(self) -> None:
        """Lock acquisition error should include owner PID."""
        from verify_all_lock import LockMetadata, VerifyLock
        
        # Create an active lock
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        (self._lock_dir / "lock").touch()
        
        metadata = LockMetadata.create_current(profile="test")
        metadata.owner_pid = 12345
        with open(self._lock_dir / "metadata.json", "w") as f:
            json.dump(metadata.to_dict(), f)
        
        # Try to acquire (should fail)
        lock = VerifyLock(self._lock_dir)
        status = lock.get_status()
        
        self.assertIn("12345", status.reason)
        self.assertIn("12345", status.recommended_action)
    
    def test_lock_error_includes_age(self) -> None:
        """Lock acquisition error should include lock age."""
        from verify_all_lock import LockMetadata, VerifyLock
        
        # Create an active lock with known age
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        (self._lock_dir / "lock").touch()
        
        # Set file mtime to be old
        old_time = time.time() - 300  # 5 minutes ago
        os.utime(self._lock_dir / "lock", (old_time, old_time))
        
        metadata = LockMetadata.create_current(profile="test")
        metadata.owner_pid = 999998
        with open(self._lock_dir / "metadata.json", "w") as f:
            json.dump(metadata.to_dict(), f)
        
        lock = VerifyLock(self._lock_dir)
        status = lock.get_status()
        
        # Lock age should be reported
        self.assertGreater(status.lock_age_seconds, 200)


if __name__ == "__main__":
    unittest.main()
