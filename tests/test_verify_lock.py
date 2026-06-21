#!/usr/bin/env python3
"""
Tests for verification lock functionality.

Tests cover:
1. Lock status reports no-lock state
2. Lock status reports active owner PID
3. Lock status reports orphaned/stale lock when PID is absent
4. Active lock is not removed by stale unlock
5. Orphaned lock can be removed by stale unlock
6. Wait mode times out cleanly
7. Wait mode succeeds when lock disappears
8. Error message includes owner diagnostics
9. Discipline guard rejects rm -rf .verify_lock
10. Discipline guard rejects pkill -f
11. No code path uses pkill -f
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Test configuration
REPO_ROOT = Path(__file__).parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"


class TestLockStatusReporting(unittest.TestCase):
    """Test lock status reporting functionality."""
    
    def setUp(self) -> None:
        """Set up isolated temp directory for each test."""
        self._tmp_dir = tempfile.mkdtemp(prefix="test_lock_")
        self._lock_dir = Path(self._tmp_dir) / ".verify_lock"
        sys.path.insert(0, str(SCRIPT_DIR))
    
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


class TestSafeStaleUnlock(unittest.TestCase):
    """Test safe stale lock removal."""
    
    def setUp(self) -> None:
        """Set up isolated temp directory for each test."""
        self._tmp_dir = tempfile.mkdtemp(prefix="test_unlock_")
        self._lock_dir = Path(self._tmp_dir) / ".verify_lock"
        sys.path.insert(0, str(SCRIPT_DIR))
    
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


class TestWaitMode(unittest.TestCase):
    """Test wait for lock functionality."""
    
    def setUp(self) -> None:
        """Set up isolated temp directory for each test."""
        self._tmp_dir = tempfile.mkdtemp(prefix="test_wait_")
        self._lock_dir = Path(self._tmp_dir) / ".verify_lock"
        sys.path.insert(0, str(SCRIPT_DIR))
    
    def tearDown(self) -> None:
        """Clean up temp directory."""
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
    
    def test_wait_mode_timeout(self) -> None:
        """Wait mode should timeout cleanly."""
        from verify_all_lock import LockMetadata, wait_for_lock
        
        # Create an active lock (our own PID)
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        (self._lock_dir / "lock").touch()
        
        metadata = LockMetadata.create_current(profile="test")
        with open(self._lock_dir / "metadata.json", "w") as f:
            json.dump(metadata.to_dict(), f)
        
        # Wait with short timeout
        acquired, message = wait_for_lock(
            self._lock_dir.parent, 
            timeout_seconds=2, 
            poll_interval=1
        )
        
        self.assertFalse(acquired)
        self.assertIn("timeout", message.lower())
        self.assertIn(str(os.getpid()), message)
    
    def test_wait_mode_succeeds_when_lock_released(self) -> None:
        """Wait mode should succeed when lock is released."""
        from verify_all_lock import wait_for_lock
        
        # No lock exists
        acquired, message = wait_for_lock(
            self._lock_dir.parent,
            timeout_seconds=5,
            poll_interval=1
        )
        
        self.assertTrue(acquired)
        self.assertIn("proceeding", message.lower())


class TestErrorMessages(unittest.TestCase):
    """Test error messages include owner diagnostics."""
    
    def setUp(self) -> None:
        """Set up isolated temp directory for each test."""
        self._tmp_dir = tempfile.mkdtemp(prefix="test_errors_")
        self._lock_dir = Path(self._tmp_dir) / ".verify_lock"
        sys.path.insert(0, str(SCRIPT_DIR))
    
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


class TestDisciplineGuard(unittest.TestCase):
    """Test that discipline guard rejects forbidden commands."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        sys.path.insert(0, str(SCRIPT_DIR))
    
    def test_guard_rejects_rm_verify_lock(self) -> None:
        """Guard should reject rm -rf .verify_lock."""
        from verify_verification_discipline import scan_file_content
        
        content = "# Fix\nrm -rf .verify_lock"
        violations, _ = scan_file_content(content)
        
        self.assertGreater(len(violations), 0)
        self.assertTrue(any("rm -rf .verify_lock" in str(v) or "verify_lock" in str(v) for v in violations))
    
    def test_guard_rejects_pkill_f(self) -> None:
        """Guard should reject pkill -f."""
        from verify_verification_discipline import scan_file_content
        
        content = "# Cleanup\npkill -f verify"
        violations, _ = scan_file_content(content)
        
        self.assertGreater(len(violations), 0)
    
    def test_guard_rejects_rm_rf_in_generic_context(self) -> None:
        """Guard should reject rm -rf .verify_lock in generic context."""
        from verify_verification_discipline import scan_file_content
        
        # Generic code block without section marker
        content = '''
Some code:
```bash
rm -rf .verify_lock
```
'''
        violations, _ = scan_file_content(content)
        
        # Should be flagged - it's in a generic code block, not a bad example
        self.assertGreater(len(violations), 0)


class TestNoPkillInCodebase(unittest.TestCase):
    """Test that no code uses pkill -f."""
    
    def test_no_pkill_in_lock_module(self) -> None:
        """Lock module should not contain pkill."""
        lock_file = SCRIPT_DIR / "verify_all_lock.py"
        content = lock_file.read_text()
        
        self.assertNotIn("pkill", content.lower())
    
    def test_no_pkill_in_verify_all(self) -> None:
        """verify_all.py should not contain pkill."""
        verify_file = SCRIPT_DIR / "verify_all.py"
        content = verify_file.read_text()
        
        self.assertNotIn("pkill", content.lower())
    
    def test_no_pkill_in_scripts(self) -> None:
        """Scripts directory should not contain pkill in lock-related files."""
        lock_related = [
            "verify_all_lock.py",
            "verify_all.py",
            "verify_all.sh",
        ]
        
        for filename in lock_related:
            filepath = SCRIPT_DIR / filename
            if filepath.exists():
                content = filepath.read_text()
                self.assertNotIn("pkill", content.lower(), f"{filename} should not contain pkill")


class TestLockMetadata(unittest.TestCase):
    """Test lock metadata functionality."""
    
    def test_metadata_create_current(self) -> None:
        """LockMetadata.create_current should capture process info."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from verify_all_lock import LockMetadata
        
        metadata = LockMetadata.create_current(profile="fast")
        
        self.assertEqual(metadata.owner_pid, os.getpid())
        self.assertIn("python", metadata.command_line[0])
        self.assertEqual(metadata.profile, "fast")
        self.assertIsNotNone(metadata.created_at)
        self.assertIsNone(metadata.last_heartbeat)
    
    def test_metadata_serialization(self) -> None:
        """LockMetadata should serialize and deserialize correctly."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from verify_all_lock import LockMetadata
        
        original = LockMetadata.create_current(profile="test")
        data = original.to_dict()
        
        restored = LockMetadata.from_dict(data)
        
        self.assertEqual(restored.owner_pid, original.owner_pid)
        self.assertEqual(restored.profile, original.profile)
        self.assertEqual(restored.cwd, original.cwd)
        self.assertEqual(restored.hostname, original.hostname)
    
    def test_metadata_update_heartbeat(self) -> None:
        """LockMetadata.update_heartbeat should update timestamp."""
        sys.path.insert(0, str(SCRIPT_DIR))
        from verify_all_lock import LockMetadata
        
        metadata = LockMetadata.create_current(profile="test")
        self.assertIsNone(metadata.last_heartbeat)
        
        metadata.update_heartbeat()
        
        self.assertIsNotNone(metadata.last_heartbeat)


class TestVerifyAllLockStatusCommand(unittest.TestCase):
    """Test --lock-status command integration."""
    
    REPO_ROOT = Path(__file__).parent.parent
    VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        if not self.VERIFY_ALL.exists():
            self.skipTest("verify_all.sh not found")
        os.chmod(self.VERIFY_ALL, 0o755)
        self._tmp_dir = tempfile.mkdtemp(prefix="test_lock_cmd_")
    
    def tearDown(self) -> None:
        """Clean up temp directory."""
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
        # Clean up any existing lock
        lock_dir = self.REPO_ROOT / ".verify_lock"
        if lock_dir.exists():
            shutil.rmtree(lock_dir, ignore_errors=True)
    
    def test_lock_status_command_accepted(self) -> None:
        """--lock-status should be accepted."""
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--lock-status"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=self.REPO_ROOT,
        )
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("Lock Status", result.stdout)
    
    def test_lock_status_json_command(self) -> None:
        """--lock-status --json should emit valid JSON."""
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--lock-status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=self.REPO_ROOT,
        )
        
        self.assertEqual(result.returncode, 0)
        
        # Verify JSON is valid
        data = json.loads(result.stdout)
        
        required_fields = [
            "locked", "owner_pid", "owner_exists", "owner_command",
            "lock_age_seconds", "status", "safe_to_remove",
            "reason", "recommended_action"
        ]
        for field in required_fields:
            self.assertIn(field, data, f"Missing required JSON field: {field}")


class TestWaitForLockCommand(unittest.TestCase):
    """Test --wait-for-lock command integration."""
    
    REPO_ROOT = Path(__file__).parent.parent
    VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        if not self.VERIFY_ALL.exists():
            self.skipTest("verify_all.sh not found")
        os.chmod(self.VERIFY_ALL, 0o755)
    
    def tearDown(self) -> None:
        """Clean up any existing lock."""
        lock_dir = self.REPO_ROOT / ".verify_lock"
        if lock_dir.exists():
            shutil.rmtree(lock_dir, ignore_errors=True)
    
    def test_wait_for_lock_short_timeout(self) -> None:
        """--wait-for-lock with short timeout should work."""
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--act-local", "--wait-for-lock", "2"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=self.REPO_ROOT,
        )
        
        # Should complete - exit code indicates act-local result
        # 0 = act-local passed, 1 = act-local failed, 4 = lock timeout
        self.assertIn(result.returncode, [0, 1, 4])


if __name__ == "__main__":
    unittest.main()
