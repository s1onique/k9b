#!/usr/bin/env python3
"""
Lock metadata types and contracts for verify_all.

This module defines the data structures used for lock metadata,
status reporting, and machine-parsable output.
"""

from __future__ import annotations

import dataclasses
import os
import socket
import sys
from datetime import UTC, datetime

# Lock file age threshold for considering a lock stale (seconds)
# Only used when owner PID is absent AND heartbeat is too old
STALE_LOCK_THRESHOLD = 3600  # 1 hour

# Heartbeat interval (seconds) - lock owner should update this
HEARTBEAT_INTERVAL = 60  # 1 minute


class LockError(Exception):
    """Raised when lock acquisition fails."""
    pass


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


def format_lock_status_human(status: LockStatus) -> str:
    """Format lock status for human-readable output."""
    lines = [
        "=== Lock Status ===",
        f"Locked: {'Yes' if status.locked else 'No'}",
        f"Status: {status.status}",
        f"Lock age: {int(status.lock_age_seconds)}s",
    ]
    
    if status.owner_pid is not None:
        lines.append(f"Owner PID: {status.owner_pid}")
        lines.append(f"Owner exists: {'Yes' if status.owner_exists else 'No'}")
        if status.owner_command:
            lines.append(f"Owner command: {status.owner_command}")
    
    lines.extend([
        "",
        f"Reason: {status.reason}",
        f"Safe to remove: {'Yes' if status.safe_to_remove else 'No'}",
        "",
        f"Recommended action: {status.recommended_action}",
    ])
    
    return "\n".join(lines)
