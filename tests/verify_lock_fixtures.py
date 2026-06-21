#!/usr/bin/env python3
"""
Shared fixtures and helpers for lock tests.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

# Test configuration
REPO_ROOT = Path(__file__).parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"


def setup_lock_dir(tmp_dir: str | Path) -> Path:
    """
    Create an isolated lock directory in temp space.
    
    Args:
        tmp_dir: Temporary directory path
        
    Returns:
        Path to the lock directory
    """
    lock_dir = Path(tmp_dir) / ".verify_lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir


def cleanup_lock_dir(lock_dir: Path | None) -> None:
    """
    Clean up a lock directory.
    
    Args:
        lock_dir: Lock directory to clean up
    """
    if lock_dir and lock_dir.exists():
        shutil.rmtree(lock_dir, ignore_errors=True)


def create_lock_file(lock_dir: Path, touch: bool = True) -> Path:
    """
    Create a lock file in the lock directory.
    
    Args:
        lock_dir: Lock directory
        touch: Whether to touch the lock file
        
    Returns:
        Path to the lock file
    """
    lock_file = lock_dir / "lock"
    if touch:
        lock_file.touch()
    return lock_file


def add_sys_path() -> None:
    """Add scripts directory to sys.path for imports."""
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))


def create_metadata_file(
    lock_dir: Path,
    owner_pid: int | None = None,
    profile: str = "test",
    cwd: str | None = None,
    command_line: list[str] | None = None,
) -> Path:
    """
    Create a metadata.json file in the lock directory.
    
    Args:
        lock_dir: Lock directory
        owner_pid: Owner PID (defaults to current process)
        profile: Verification profile
        cwd: Working directory
        command_line: Command line args
        
    Returns:
        Path to the metadata file
    """
    from verify_all_lock_types import LockMetadata
    
    if owner_pid is None:
        owner_pid = os.getpid()
    
    metadata = LockMetadata.create_current(profile=profile)
    metadata.owner_pid = owner_pid
    
    if cwd:
        metadata.cwd = cwd
    if command_line:
        metadata.command_line = command_line
    
    metadata_file = lock_dir / "metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata.to_dict(), f)
    
    return metadata_file
