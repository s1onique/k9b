#!/usr/bin/env python3
"""
Tests for verification discipline guard.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Test configuration
REPO_ROOT = Path(__file__).parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"

# Add scripts to path for imports
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


class TestDisciplineGuard(unittest.TestCase):
    """Test that discipline guard rejects forbidden commands."""
    
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
    
    def test_no_pkill_in_lock_core(self) -> None:
        """Lock core module should not contain pkill."""
        lock_core_file = SCRIPT_DIR / "verify_all_lock_core.py"
        content = lock_core_file.read_text()
        
        self.assertNotIn("pkill", content.lower())
    
    def test_no_pkill_in_lock_process(self) -> None:
        """Lock process module should not contain pkill."""
        lock_process_file = SCRIPT_DIR / "verify_all_lock_process.py"
        content = lock_process_file.read_text()
        
        self.assertNotIn("pkill", content.lower())
    
    def test_no_pkill_in_lock_wait(self) -> None:
        """Lock wait module should not contain pkill."""
        lock_wait_file = SCRIPT_DIR / "verify_all_lock_wait.py"
        content = lock_wait_file.read_text()
        
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
            "verify_all_lock_core.py",
            "verify_all_lock_process.py",
            "verify_all_lock_wait.py",
            "verify_all.py",
            "verify_all.sh",
        ]
        
        for filename in lock_related:
            filepath = SCRIPT_DIR / filename
            if filepath.exists():
                content = filepath.read_text()
                self.assertNotIn("pkill", content.lower(), f"{filename} should not contain pkill")


if __name__ == "__main__":
    unittest.main()
