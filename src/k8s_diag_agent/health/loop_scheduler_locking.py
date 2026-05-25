"""Lock-file operations and side-effecting logic for loop scheduler.

Extracted from loop_scheduler_locking.py to reduce complexity.
This module contains side-effecting operations (file I/O, logging).

Pure parsing and evaluation logic is in loop_scheduler_lock_eval.py.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .loop_scheduler_lock_eval import (
    evaluate_lock_state as _evaluate_lock_state_pure,
)
from .loop_scheduler_lock_eval import (
    parse_lock_metadata,
    parse_lock_timestamp,
)
from .loop_scheduler_models import (
    _LOCK_SKIP_ESCALATION_THRESHOLD,
    _LOCK_STALE_MIN_SECONDS,
    LockEvaluation,
    LockFileSnapshot,
    ProcessIdentity,
)

if TYPE_CHECKING:
    from .loop_scheduler import HealthLoopScheduler


def _get_hostname() -> str | None:
    """Get hostname, returning None on failure."""
    import socket
    try:
        return socket.gethostname()
    except OSError:
        return None


class LockManager:
    """Manages lock-file operations for the health loop scheduler.

    This class encapsulates all lock-related state and operations,
    delegating to the parent scheduler for instance-specific configuration.
    """

    def __init__(self, scheduler: HealthLoopScheduler) -> None:
        self._scheduler = scheduler

    @property
    def _instance_id(self) -> str:
        return self._scheduler._instance_id

    @property
    def _pending_run_id(self) -> str | None:
        return self._scheduler._pending_run_id

    @property
    def _lock_path(self) -> Path:
        return self._scheduler._lock_path

    @property
    def _lock_status_path(self) -> Path:
        return self._scheduler._lock_status_path

    @property
    def _interval_seconds(self) -> int | None:
        return self._scheduler._interval_seconds

    @property
    def _identity_hostname(self) -> str | None:
        return self._scheduler._identity_hostname

    @property
    def _proc_root(self) -> Path | None:
        return self._scheduler._proc_root

    @property
    def _run_label(self) -> str:
        return self._scheduler._run_label

    @property
    def _log_event(self) -> Any:
        return self._scheduler._log_event

    def current_process_identity(self) -> ProcessIdentity | None:
        """Get the identity of the current process."""
        identity = self.read_process_identity(os.getpid())
        if identity is not None:
            return identity
        if self._identity_hostname is None:
            return None
        return ProcessIdentity(None, None, self._identity_hostname)

    def read_process_identity(self, pid: int) -> ProcessIdentity | None:
        """Read process identity information from /proc."""
        if pid <= 0:
            return None
        hostname = self._identity_hostname
        if self._proc_root is None:
            return ProcessIdentity(None, None, hostname)
        proc_dir = self._proc_root / str(pid)
        if not proc_dir.exists():
            return ProcessIdentity(None, None, hostname)
        start_time: str | None = None
        try:
            stat_content = (proc_dir / "stat").read_text(encoding="utf-8")
        except OSError:
            stat_content = ""
        if stat_content:
            parts = stat_content.split()
            if len(parts) > 21:
                start_time = parts[21]
        cmdline: str | None = None
        try:
            cmdline_bytes = (proc_dir / "cmdline").read_bytes()
            if cmdline_bytes:
                segments = [seg.decode("utf-8", "ignore") for seg in cmdline_bytes.split(b"\0") if seg]
                cmdline = " ".join(segments)
        except OSError:
            pass
        return ProcessIdentity(start_time, cmdline, hostname)

    def serialize_identity(self, identity: ProcessIdentity | None) -> dict[str, str] | None:
        """Serialize identity to a dictionary for JSON storage."""
        if identity is None:
            return None
        data: dict[str, str] = {}
        if identity.start_time is not None:
            data["start_time"] = identity.start_time
        if identity.cmdline is not None:
            data["cmdline"] = identity.cmdline
        if identity.hostname is not None:
            data["hostname"] = identity.hostname
        return data or None

    def load_lock_snapshot(self) -> LockFileSnapshot | None:
        """Load the current lock file snapshot."""
        try:
            stat_info = self._lock_path.stat()
        except OSError:
            return None
        try:
            contents = self._lock_path.read_text(encoding="utf-8")
        except OSError:
            contents = ""
        (
            timestamp_str,
            pid,
            identity,
            scheduler_instance_id,
            attempted_run_id,
            scheduler_pid,
            child_pid,
            child_start_time,
            run_label,
        ) = parse_lock_metadata(contents, self._identity_hostname)
        timestamp = parse_lock_timestamp(timestamp_str)
        return LockFileSnapshot(
            timestamp_value=timestamp_str,
            timestamp=timestamp,
            pid=pid,
            mtime=stat_info.st_mtime,
            identity=identity,
            scheduler_instance_id=scheduler_instance_id,
            attempted_run_id=attempted_run_id,
            scheduler_pid=scheduler_pid,
            child_pid=child_pid,
            child_start_time=child_start_time,
            run_label=run_label,
        )

    def pid_is_alive(self, pid: int) -> bool:
        """Check if a process ID is still alive."""
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return True
        return True

    def _write_lock_status(self, evaluation: LockEvaluation) -> None:
        """Write the lock evaluation status to a status file."""
        from .loop_history import _write_json
        snapshot = evaluation.snapshot
        data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "lock_file": str(self._lock_path),
            "lock_age_seconds": evaluation.lock_age_seconds,
            "lock_pid": snapshot.pid if snapshot else None,
            "lock_timestamp": snapshot.timestamp_value if snapshot else None,
            "pid_alive": evaluation.pid_alive,
            "identity_match": evaluation.identity_match,
            "provenance_match": evaluation.provenance_match,
            "stale_decision": evaluation.stale_decision,
            "cleanup_reason": evaluation.cleanup_reason,
            "scheduler_instance_id": snapshot.scheduler_instance_id if snapshot else None,
            "attempted_run_id": snapshot.attempted_run_id if snapshot else None,
            "scheduler_pid": snapshot.scheduler_pid if snapshot else None,
            "child_pid": snapshot.child_pid if snapshot else None,
            "child_start_time": snapshot.child_start_time if snapshot else None,
            "run_label": snapshot.run_label if snapshot else None,
        }
        try:
            self._lock_status_path.parent.mkdir(parents=True, exist_ok=True)
            _write_json(data, self._lock_status_path)
        except OSError:
            pass

    def evaluate_lock_state(self) -> LockEvaluation:
        """Evaluate the current lock file state to determine staleness."""
        snapshot = self.load_lock_snapshot()
        evaluation = _evaluate_lock_state_pure(
            snapshot=snapshot,
            current_pid=os.getpid(),
            interval_seconds=self._interval_seconds,
            instance_id=self._instance_id,
            pending_run_id=self._pending_run_id,
            read_identity_fn=self.read_process_identity,
            pid_alive_fn=self.pid_is_alive,
        )
        self._write_lock_status(evaluation)
        return evaluation

    def acquire_lock(self) -> bool:
        """Attempt to acquire the scheduler lock file."""
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                payload = {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "pid": os.getpid(),
                }
                identity = self.current_process_identity()
                identity_data = self.serialize_identity(identity)
                if identity_data:
                    payload["identity"] = identity_data
                payload["scheduler_instance_id"] = self._instance_id
                if self._pending_run_id:
                    payload["attempted_run_id"] = self._pending_run_id
                payload["scheduler_pid"] = os.getpid()
                payload["child_pid"] = os.getpid()
                if self._scheduler._pending_run_start:
                    payload["child_start_time"] = self._scheduler._pending_run_start.isoformat()
                payload["run_label"] = self._run_label
                with self._lock_path.open("x", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload))
                    handle.write("\n")
                self._scheduler._lock_skip_streak = 0
                return True
            except FileExistsError:
                evaluation = self.evaluate_lock_state()
                if evaluation.should_cleanup and self.remove_stale_lock(evaluation):
                    self._scheduler._lock_skip_streak = 0
                    continue
                self.log_lock_held(evaluation)
                return False

    def release_lock(self) -> None:
        """Release the scheduler lock file if it exists."""
        try:
            if self._lock_path.exists():
                self._lock_path.unlink()
        except OSError:
            pass

    def remove_stale_lock(self, evaluation: LockEvaluation) -> bool:
        """Remove a stale lock file and log the removal."""
        try:
            if self._lock_path.exists():
                self._lock_path.unlink()
        except OSError:
            return False
        snapshot = evaluation.snapshot
        metadata: dict[str, object | None] = {
            "lock_file": str(self._lock_path),
            "lock_age_seconds": evaluation.lock_age_seconds,
            "lock_pid": snapshot.pid if snapshot else None,
            "pid_alive": evaluation.pid_alive,
            "lock_timestamp": snapshot.timestamp_value if snapshot else None,
            "expected_interval_seconds": self._interval_seconds,
            "cleanup_reason": evaluation.cleanup_reason or evaluation.stale_decision,
            "event": "lock-stale",
            "identity_match": evaluation.identity_match,
            "current_identity_signature": evaluation.current_identity.signature if evaluation.current_identity else None,
            "scheduler_instance_id": snapshot.scheduler_instance_id if snapshot else None,
            "attempted_run_id": snapshot.attempted_run_id if snapshot else None,
            "scheduler_pid": snapshot.scheduler_pid if snapshot else None,
            "child_pid": snapshot.child_pid if snapshot else None,
            "child_start_time": snapshot.child_start_time if snapshot else None,
            "run_label": snapshot.run_label if snapshot else None,
            "provenance_match": evaluation.provenance_match,
        }
        last_run_ts = self._scheduler._format_last_run_timestamp()
        if last_run_ts is not None:
            metadata["last_successful_run_timestamp"] = last_run_ts
        if snapshot and snapshot.identity:
            metadata["lock_identity_signature"] = snapshot.identity.signature
            metadata["lock_identity_start_time"] = snapshot.identity.start_time
            metadata["lock_identity_hostname"] = snapshot.identity.hostname
        self._log_event(
            "WARNING",
            "Removed stale lock file",
            **metadata,
        )
        return True

    def log_lock_held(self, evaluation: LockEvaluation) -> None:
        """Log when a lock is held by another process."""
        self._scheduler._lock_skip_streak += 1
        escalated = self._scheduler._lock_skip_streak >= _LOCK_SKIP_ESCALATION_THRESHOLD
        severity = "ERROR" if escalated else "WARNING"
        snapshot = evaluation.snapshot
        metadata: dict[str, object | None] = {
            "reason": "lock-held",
            "lock_file": str(self._lock_path),
            "event": "lock-skip",
            "lock_age_seconds": evaluation.lock_age_seconds,
            "lock_pid": snapshot.pid if snapshot else None,
            "pid_alive": evaluation.pid_alive,
            "lock_timestamp": snapshot.timestamp_value if snapshot else None,
            "expected_interval_seconds": self._interval_seconds,
            "stale_decision": evaluation.stale_decision,
            "repeated_lock_skips": self._scheduler._lock_skip_streak,
            "identity_match": evaluation.identity_match,
            "current_identity_signature": evaluation.current_identity.signature if evaluation.current_identity else None,
            "scheduler_instance_id": snapshot.scheduler_instance_id if snapshot else None,
            "attempted_run_id": snapshot.attempted_run_id if snapshot else None,
            "scheduler_pid": snapshot.scheduler_pid if snapshot else None,
            "child_pid": snapshot.child_pid if snapshot else None,
            "child_start_time": snapshot.child_start_time if snapshot else None,
            "run_label": snapshot.run_label if snapshot else None,
            "provenance_match": evaluation.provenance_match,
        }
        last_run_ts = self._scheduler._format_last_run_timestamp()
        if last_run_ts is not None:
            metadata["last_successful_run_timestamp"] = last_run_ts
        if evaluation.identity_match is False:
            metadata["identity_mismatch"] = True
        if snapshot and snapshot.identity:
            metadata["lock_identity_signature"] = snapshot.identity.signature
            metadata["lock_identity_start_time"] = snapshot.identity.start_time
            metadata["lock_identity_hostname"] = snapshot.identity.hostname
        if escalated:
            metadata["lock_skip_escalated"] = True
            metadata["severity_reason"] = "repeated-lock-held"
        self._log_event(
            severity,
            "Health run skipped because lock is held",
            **metadata,
        )


# Re-export for backward compatibility
__all__ = [
    "LockManager",
    "LockEvaluation",
    "LockFileSnapshot",
    "ProcessIdentity",
    "_LOCK_SKIP_ESCALATION_THRESHOLD",
    "_LOCK_STALE_MIN_SECONDS",
]
