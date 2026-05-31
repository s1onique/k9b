"""Data models and constants for loop scheduling and lock management."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

# Module-level constants
_HEALTH_LOCK_FILENAME = ".health-loop.lock"
_HEALTH_ONLY_MESSAGE = "No peer mappings configured; running health-only mode."

# Subprocess timeout for diagnostic pack build scripts (120s)
DIAGNOSTIC_PACK_TIMEOUT_SECONDS = 120

# Stale lock evaluation thresholds
_LOCK_SKIP_ESCALATION_THRESHOLD = 3
_LOCK_STALE_MIN_SECONDS = 60
_LOCK_STALE_AGE_MULTIPLIER = 2


@dataclass(frozen=True)
class ProcessIdentity:
    """Identifies a running process by start time, command line, and hostname."""

    start_time: str | None
    cmdline: str | None
    hostname: str | None

    @property
    def signature(self) -> str | None:
        """Compute a SHA-256 signature from identity components."""
        values = (self.start_time, self.cmdline, self.hostname)
        if not any(values):
            return None
        payload = "|".join(value or "" for value in values)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LockFileSnapshot:
    """Captures the state of a lock file at a point in time."""

    timestamp_value: str | None
    timestamp: datetime | None
    pid: int | None
    mtime: float | None
    identity: ProcessIdentity | None
    scheduler_instance_id: str | None
    attempted_run_id: str | None
    scheduler_pid: int | None
    child_pid: int | None
    child_start_time: str | None
    run_label: str | None

    def age_seconds(self, reference: datetime) -> float | None:
        """Compute lock age in seconds from a reference time."""
        if self.timestamp is not None:
            return max(0.0, (reference - self.timestamp).total_seconds())
        if self.mtime is not None:
            return max(0.0, reference.timestamp() - self.mtime)
        return None


@dataclass(frozen=True)
class LockEvaluation:
    """Result of evaluating whether an existing lock is stale."""

    snapshot: LockFileSnapshot | None
    lock_age_seconds: float | None
    pid_alive: bool | None
    current_identity: ProcessIdentity | None
    identity_match: bool | None
    provenance_match: bool | None
    should_cleanup: bool
    stale_decision: str
    cleanup_reason: str | None


def _str_or_none(value: object | None) -> str | None:
    """Convert a value to a string or return None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    return str(value)


# Re-export for backward compatibility
__all__ = [
    "ProcessIdentity",
    "LockFileSnapshot",
    "LockEvaluation",
    "_str_or_none",
    "_HEALTH_LOCK_FILENAME",
    "_HEALTH_ONLY_MESSAGE",
    "DIAGNOSTIC_PACK_TIMEOUT_SECONDS",
    "_LOCK_SKIP_ESCALATION_THRESHOLD",
    "_LOCK_STALE_MIN_SECONDS",
    "_LOCK_STALE_AGE_MULTIPLIER",
]
