#!/usr/bin/env python3
"""
Process identity helpers for lock handling.

Provides functions for checking if a process exists and getting
process command information.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def pid_exists(pid: int) -> bool:
    """
    Check if a process with the given PID exists.
    
    Args:
        pid: Process ID to check
        
    Returns:
        True if process exists, False otherwise
    """
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def get_process_command(pid: int) -> str | None:
    """
    Get process command line for diagnostics.
    
    Args:
        pid: Process ID to query
        
    Returns:
        Command string if available, None otherwise
    """
    # Try /proc on Linux/Unix
    cmdline_file = Path(f"/proc/{pid}/cmdline")
    if cmdline_file.exists():
        try:
            with open(cmdline_file) as f:
                cmdline = f.read().replace('\x00', ' ').strip()
            return cmdline if cmdline else None
        except (OSError, PermissionError):
            pass
    
    # Fallback: try ps command
    try:
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
