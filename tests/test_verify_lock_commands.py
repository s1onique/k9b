#!/usr/bin/env python3
"""
Tests for lock command integration.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Test configuration
REPO_ROOT = Path(__file__).parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"
VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"

# Add scripts to path for imports
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


class TestVerifyAllLockStatusCommand(unittest.TestCase):
    """Test --lock-status command integration."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        if not VERIFY_ALL.exists():
            self.skipTest("verify_all.sh not found")
        os.chmod(VERIFY_ALL, 0o755)
        self._tmp_dir = tempfile.mkdtemp(prefix="test_lock_cmd_")
    
    def tearDown(self) -> None:
        """Clean up temp directory."""
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
        # Clean up any existing lock
        lock_dir = REPO_ROOT / ".verify_lock"
        if lock_dir.exists():
            shutil.rmtree(lock_dir, ignore_errors=True)
    
    def test_lock_status_command_accepted(self) -> None:
        """--lock-status should be accepted."""
        result = subprocess.run(
            [str(VERIFY_ALL), "--lock-status"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=REPO_ROOT,
        )
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("Lock Status", result.stdout)
    
    def test_lock_status_json_command(self) -> None:
        """--lock-status --json should emit valid JSON."""
        result = subprocess.run(
            [str(VERIFY_ALL), "--lock-status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=REPO_ROOT,
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


if __name__ == "__main__":
    unittest.main()
