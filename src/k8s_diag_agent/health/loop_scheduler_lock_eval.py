"""Pure lock-file parsing and evaluation logic for loop scheduler.

Extracted from loop_scheduler_locking.py to reduce complexity.
These functions contain no side effects - only data transformation and decision logic.

The module provides:
- Lock metadata parsing (JSON and legacy formats)
- Process identity comparison
- Stale-lock age threshold computation
- Lock state evaluation and decision building
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .loop_scheduler_models import (
    _LOCK_SKIP_ESCALATION_THRESHOLD,
    _LOCK_STALE_AGE_MULTIPLIER,
    _LOCK_STALE_MIN_SECONDS,
    LockEvaluation,
    LockFileSnapshot,
    ProcessIdentity,
    _str_or_none,
)

if TYPE_CHECKING:
    from pathlib import Path


def _get_hostname() -> str | None:
    """Get hostname, returning None on failure."""
    import socket
    try:
        return socket.gethostname()
    except OSError:
        return None


def coerce_pid(raw: object | None) -> int | None:
    """Convert a value to a PID integer."""
    if raw is None:
        return None
    if isinstance(raw, str):
        if raw.isdigit():
            return int(raw)
        try:
            return int(raw)
        except ValueError:
            return None
    if isinstance(raw, (int, float)):
        return int(raw)
    return None


def parse_lock_timestamp(value: str | None) -> datetime | None:
    """Parse lock timestamp to timezone-aware UTC datetime."""
    from ..datetime_utils import parse_iso_to_utc
    return parse_iso_to_utc(value)


def parse_lock_metadata(
    contents: str,
    identity_hostname: str | None = None,
    proc_root: Path | None = None,
) -> tuple[
    str | None,
    int | None,
    ProcessIdentity | None,
    str | None,
    str | None,
    int | None,
    int | None,
    str | None,
    str | None,
]:
    """Parse lock file metadata from JSON or legacy text format.

    Args:
        contents: The raw lock file contents
        identity_hostname: Hostname for reconstructing process identity
        proc_root: Path to /proc directory for reading process info

    Returns:
        Tuple of (timestamp_str, pid, identity, scheduler_instance_id,
        attempted_run_id, scheduler_pid, child_pid, child_start_time, run_label)
    """
    trimmed = contents.strip()
    if trimmed.startswith("{"):
        try:
            raw = json.loads(trimmed)
        except json.JSONDecodeError:
            return (
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        timestamp = _str_or_none(raw.get("timestamp"))
        pid = coerce_pid(raw.get("pid"))
        identity_raw = raw.get("identity")
        identity = (
            identity_from_mapping(identity_raw, identity_hostname)
            if isinstance(identity_raw, Mapping)
            else None
        )
        scheduler_instance_id = _str_or_none(raw.get("scheduler_instance_id"))
        attempted_run_id = _str_or_none(raw.get("attempted_run_id"))
        scheduler_pid = coerce_pid(raw.get("scheduler_pid"))
        child_pid = coerce_pid(raw.get("child_pid"))
        child_start_time = _str_or_none(raw.get("child_start_time"))
        run_label = _str_or_none(raw.get("run_label"))
        return (
            timestamp,
            pid,
            identity,
            scheduler_instance_id,
            attempted_run_id,
            scheduler_pid,
            child_pid,
            child_start_time,
            run_label,
        )
    line = contents.splitlines()[0] if contents else ""
    parts = line.split()
    legacy_timestamp: str | None = parts[0] if parts else None
    legacy_pid: int | None = None
    for part in parts:
        if part.startswith("pid="):
            try:
                legacy_pid = int(part.split("=", 1)[1])
            except ValueError:
                legacy_pid = None
            break
    return (
        legacy_timestamp,
        legacy_pid,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def identity_from_mapping(
    raw: Mapping[str, object] | None,
    default_hostname: str | None = None,
) -> ProcessIdentity | None:
    """Reconstruct ProcessIdentity from a mapping."""
    if not raw:
        return None
    start_time_raw = raw.get("start_time")
    start_time = _str_or_none(start_time_raw if isinstance(start_time_raw, str) else None)
    cmdline_raw = raw.get("cmdline")
    cmdline = _str_or_none(cmdline_raw if isinstance(cmdline_raw, str) else None)
    hostname_raw = raw.get("hostname")
    hostname = _str_or_none(hostname_raw if isinstance(hostname_raw, str) else None) or default_hostname
    if start_time is None and cmdline is None and hostname is None:
        return None
    return ProcessIdentity(start_time, cmdline, hostname)


def identity_matches(
    stored: ProcessIdentity | None,
    current: ProcessIdentity | None,
) -> bool | None:
    """Compare two process identities for equality."""
    if stored is None or current is None:
        return None
    stored_sig = stored.signature
    current_sig = current.signature
    if stored_sig is not None and current_sig is not None:
        return stored_sig == current_sig
    if stored == current:
        return True
    return None


def stale_lock_age_threshold(interval_seconds: int | None) -> float:
    """Compute the threshold for considering a lock stale."""
    interval = interval_seconds or _LOCK_STALE_MIN_SECONDS
    base = max(interval, _LOCK_STALE_MIN_SECONDS)
    return base * _LOCK_STALE_AGE_MULTIPLIER


def provenance_matches(
    snapshot: LockFileSnapshot | None,
    instance_id: str | None,
    pending_run_id: str | None,
) -> bool:
    """Check if the lock's provenance matches a scheduler instance."""
    if not snapshot or not pending_run_id:
        return False
    return (
        snapshot.scheduler_instance_id == instance_id
        and snapshot.attempted_run_id == pending_run_id
    )


def build_evaluation(
    snapshot: LockFileSnapshot | None,
    lock_age: float | None,
    pid_alive: bool | None,
    current_identity: ProcessIdentity | None,
    identity_match: bool | None,
    provenance_match: bool | None,
    should_cleanup: bool,
    stale_decision: str,
    cleanup_reason: str | None,
) -> LockEvaluation:
    """Build a lock evaluation result."""
    return LockEvaluation(
        snapshot=snapshot,
        lock_age_seconds=lock_age,
        pid_alive=pid_alive,
        current_identity=current_identity,
        identity_match=identity_match,
        provenance_match=provenance_match,
        should_cleanup=should_cleanup,
        stale_decision=stale_decision,
        cleanup_reason=cleanup_reason,
    )


def evaluate_lock_state(
    snapshot: LockFileSnapshot | None,
    current_pid: int,
    interval_seconds: int | None,
    instance_id: str | None,
    pending_run_id: str | None,
    read_identity_fn: Any,  # Callable[[int], ProcessIdentity | None]
    pid_alive_fn: Any,  # Callable[[int], bool]
) -> LockEvaluation:
    """Evaluate a lock file snapshot to determine staleness.

    This is a pure function that takes all dependencies as parameters.

    Args:
        snapshot: The loaded lock file snapshot
        current_pid: The current process ID
        interval_seconds: The configured interval for stale threshold
        instance_id: The scheduler instance ID
        pending_run_id: The pending run ID
        read_identity_fn: Function to read process identity
        pid_alive_fn: Function to check if PID is alive

    Returns:
        A LockEvaluation with the staleness decision
    """
    now = datetime.now(UTC)
    lock_age = snapshot.age_seconds(now) if snapshot else None
    pid_alive: bool | None = None
    current_identity: ProcessIdentity | None = None
    identity_match: bool | None = None
    if snapshot and snapshot.pid is not None:
        pid_alive = pid_alive_fn(snapshot.pid)
        if pid_alive:
            current_identity = read_identity_fn(snapshot.pid)
            identity_match = identity_matches(snapshot.identity, current_identity)
    prov_match = provenance_matches(snapshot, instance_id, pending_run_id)
    threshold = stale_lock_age_threshold(interval_seconds)

    if snapshot is None:
        return build_evaluation(
            snapshot=None, lock_age=lock_age, pid_alive=pid_alive,
            current_identity=current_identity, identity_match=identity_match,
            provenance_match=prov_match, should_cleanup=False,
            stale_decision="unreadable", cleanup_reason=None
        )
    if snapshot.pid is None:
        stale_decision = "missing-pid"
        cleanup_reason = None
        should_cleanup = False
        if lock_age is not None and lock_age >= threshold:
            should_cleanup = True
            cleanup_reason = "missing-pid-old"
        return build_evaluation(
            snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
            current_identity=current_identity, identity_match=identity_match,
            provenance_match=prov_match, should_cleanup=should_cleanup,
            stale_decision=stale_decision, cleanup_reason=cleanup_reason
        )
    if pid_alive:
        if prov_match:
            return build_evaluation(
                snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
                current_identity=current_identity, identity_match=identity_match,
                provenance_match=prov_match, should_cleanup=False,
                stale_decision="provenance-match", cleanup_reason=None
            )
        if identity_match is True:
            return build_evaluation(
                snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
                current_identity=current_identity, identity_match=identity_match,
                provenance_match=prov_match, should_cleanup=False,
                stale_decision="identity-match", cleanup_reason=None
            )
        if identity_match is False:
            has_scheduler_provenance = bool(
                snapshot.scheduler_instance_id and snapshot.attempted_run_id
            )
            scheduler_mismatch = (
                has_scheduler_provenance
                and pending_run_id is not None
                and (
                    snapshot.scheduler_instance_id != instance_id
                    or snapshot.attempted_run_id != pending_run_id
                )
            )
            strong_identity = snapshot.identity is not None and current_identity is not None
            if scheduler_mismatch and strong_identity:
                pid_collision = any(
                    pid == current_pid
                    for pid in (
                        snapshot.pid,
                        snapshot.scheduler_pid,
                        snapshot.child_pid,
                    )
                    if pid is not None
                )
                stale_decision = "pid-reuse-stale" if pid_collision else "scheduler-instance-mismatch"
                return build_evaluation(
                    snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
                    current_identity=current_identity, identity_match=identity_match,
                    provenance_match=prov_match, should_cleanup=True,
                    stale_decision=stale_decision, cleanup_reason=stale_decision
                )
            cleanup_due_to_identity = lock_age is not None and lock_age >= threshold
            if cleanup_due_to_identity:
                return build_evaluation(
                    snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
                    current_identity=current_identity, identity_match=identity_match,
                    provenance_match=prov_match, should_cleanup=True,
                    stale_decision="identity-mismatch-old", cleanup_reason="identity-mismatch-old"
                )
            stale_decision = (
                "foreign-live-lock"
                if snapshot.identity is None or current_identity is None
                else "identity-mismatch-young-foreign"
            )
            return build_evaluation(
                snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
                current_identity=current_identity, identity_match=identity_match,
                provenance_match=prov_match, should_cleanup=False,
                stale_decision=stale_decision, cleanup_reason=None
            )
        return build_evaluation(
            snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
            current_identity=current_identity, identity_match=identity_match,
            provenance_match=prov_match, should_cleanup=False,
            stale_decision="foreign-live-lock", cleanup_reason=None
        )
    if lock_age is None:
        return build_evaluation(
            snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
            current_identity=current_identity, identity_match=identity_match,
            provenance_match=prov_match, should_cleanup=False,
            stale_decision="pid-dead-unknown-age", cleanup_reason=None
        )
    if lock_age < threshold:
        return build_evaluation(
            snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
            current_identity=current_identity, identity_match=identity_match,
            provenance_match=prov_match, should_cleanup=False,
            stale_decision="pid-dead-young", cleanup_reason=None
        )
    return build_evaluation(
        snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
        current_identity=current_identity, identity_match=identity_match,
        provenance_match=prov_match, should_cleanup=True,
        stale_decision="pid-dead-old", cleanup_reason="pid-not-running"
    )


# Re-export for backward compatibility
__all__ = [
    "LockEvaluation",
    "LockFileSnapshot",
    "ProcessIdentity",
    "_LOCK_SKIP_ESCALATION_THRESHOLD",
    "_LOCK_STALE_AGE_MULTIPLIER",
    "_LOCK_STALE_MIN_SECONDS",
    "_get_hostname",
    "build_evaluation",
    "coerce_pid",
    "evaluate_lock_state",
    "identity_from_mapping",
    "identity_matches",
    "parse_lock_metadata",
    "parse_lock_timestamp",
    "provenance_matches",
    "stale_lock_age_threshold",
]
