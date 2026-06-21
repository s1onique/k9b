#!/usr/bin/env python3
"""
Tests for lock metadata functionality.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Test configuration
REPO_ROOT = Path(__file__).parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"

# Add scripts to path for imports
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


class TestLockMetadata(unittest.TestCase):
    """Test lock metadata functionality."""
    
    def test_metadata_create_current(self) -> None:
        """LockMetadata.create_current should capture process info."""
        from verify_all_lock_types import LockMetadata
        
        metadata = LockMetadata.create_current(profile="fast")
        
        self.assertEqual(metadata.owner_pid, os.getpid())
        self.assertIn("python", metadata.command_line[0])
        self.assertEqual(metadata.profile, "fast")
        self.assertIsNotNone(metadata.created_at)
        self.assertIsNone(metadata.last_heartbeat)
    
    def test_metadata_serialization(self) -> None:
        """LockMetadata should serialize and deserialize correctly."""
        from verify_all_lock_types import LockMetadata
        
        original = LockMetadata.create_current(profile="test")
        data = original.to_dict()
        
        restored = LockMetadata.from_dict(data)
        
        self.assertEqual(restored.owner_pid, original.owner_pid)
        self.assertEqual(restored.profile, original.profile)
        self.assertEqual(restored.cwd, original.cwd)
        self.assertEqual(restored.hostname, original.hostname)
    
    def test_metadata_update_heartbeat(self) -> None:
        """LockMetadata.update_heartbeat should update timestamp."""
        from verify_all_lock_types import LockMetadata
        
        metadata = LockMetadata.create_current(profile="test")
        self.assertIsNone(metadata.last_heartbeat)
        
        metadata.update_heartbeat()
        
        self.assertIsNotNone(metadata.last_heartbeat)
    
    def test_metadata_to_dict(self) -> None:
        """LockMetadata.to_dict should produce valid dict."""
        from verify_all_lock_types import LockMetadata
        
        metadata = LockMetadata.create_current(profile="test")
        data = metadata.to_dict()
        
        # Check required fields
        required_fields = [
            "owner_pid", "parent_pid", "process_group_id", "command_line",
            "cwd", "hostname", "user", "created_at", "last_heartbeat", "profile"
        ]
        for field in required_fields:
            self.assertIn(field, data, f"Missing required field: {field}")
    
    def test_metadata_from_dict(self) -> None:
        """LockMetadata.from_dict should restore all fields."""
        from verify_all_lock_types import LockMetadata
        
        original = LockMetadata.create_current(profile="unit")
        data = original.to_dict()
        
        restored = LockMetadata.from_dict(data)
        
        self.assertEqual(restored.owner_pid, original.owner_pid)
        self.assertEqual(restored.parent_pid, original.parent_pid)
        self.assertEqual(restored.process_group_id, original.process_group_id)
        self.assertEqual(restored.command_line, original.command_line)
        self.assertEqual(restored.cwd, original.cwd)
        self.assertEqual(restored.hostname, original.hostname)
        self.assertEqual(restored.user, original.user)
        self.assertEqual(restored.created_at, original.created_at)
        self.assertEqual(restored.last_heartbeat, original.last_heartbeat)
        self.assertEqual(restored.profile, original.profile)


if __name__ == "__main__":
    unittest.main()
