"""Lock-file read/write/evaluation and stale-lock decision logic for loop scheduler.

Extracted from loop_scheduler.py to reduce complexity.
Preserves behavior exactly - no lock semantics changes.

The LockManager class wraps a reference to the parent scheduler to access
its configuration (instance_id, pending_run_id, lock_path, etc.).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
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

    def identity_from_mapping(
        self, raw: Mapping[str, object] | None
    ) -> ProcessIdentity | None:
        """Reconstruct ProcessIdentity from a mapping."""
        if not raw:
            return None
        start_time_raw = raw.get("start_time")
        start_time = _str_or_none(start_time_raw if isinstance(start_time_raw, str) else None)
        cmdline_raw = raw.get("cmdline")
        cmdline = _str_or_none(cmdline_raw if isinstance(cmdline_raw, str) else None)
        hostname_raw = raw.get("hostname")
        hostname = _str_or_none(hostname_raw if isinstance(hostname_raw, str) else None) or self._identity_hostname
        if start_time is None and cmdline is None and hostname is None:
            return None
        return ProcessIdentity(start_time, cmdline, hostname)

    def identity_matches(
        self,
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

    @staticmethod
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
        ) = self._parse_lock_metadata(contents)
        timestamp = self._parse_lock_timestamp(timestamp_str)
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

    def _parse_lock_metadata(
        self, contents: str
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
        """Parse lock file metadata from JSON or legacy text format."""
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
            pid = self.coerce_pid(raw.get("pid"))
            identity_raw = raw.get("identity")
            identity = (
                self.identity_from_mapping(identity_raw)
                if isinstance(identity_raw, Mapping)
                else None
            )
            scheduler_instance_id = _str_or_none(raw.get("scheduler_instance_id"))
            attempted_run_id = _str_or_none(raw.get("attempted_run_id"))
            scheduler_pid = self.coerce_pid(raw.get("scheduler_pid"))
            child_pid = self.coerce_pid(raw.get("child_pid"))
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

    def _parse_lock_timestamp(self, value: str | None) -> datetime | None:
        """Parse lock timestamp to timezone-aware UTC datetime."""
        from ..datetime_utils import parse_iso_to_utc
        return parse_iso_to_utc(value)

    def stale_lock_age_threshold(self) -> float:
        """Compute the threshold for considering a lock stale."""
        interval = self._interval_seconds or _LOCK_STALE_MIN_SECONDS
        base = max(interval, _LOCK_STALE_MIN_SECONDS)
        return base * _LOCK_STALE_AGE_MULTIPLIER

    def provenance_matches(self, snapshot: LockFileSnapshot | None) -> bool:
        """Check if the lock's provenance matches this scheduler instance."""
        if not snapshot or not self._pending_run_id:
            return False
        return (
            snapshot.scheduler_instance_id == self._instance_id
            and snapshot.attempted_run_id == self._pending_run_id
        )

    def evaluate_lock_state(self) -> LockEvaluation:
        """Evaluate the current lock file state to determine staleness."""
        snapshot = self.load_lock_snapshot()
        now = datetime.now(UTC)
        lock_age = snapshot.age_seconds(now) if snapshot else None
        current_pid = os.getpid()
        pid_alive: bool | None = None
        current_identity: ProcessIdentity | None = None
        identity_match: bool | None = None
        if snapshot and snapshot.pid is not None:
            pid_alive = self.pid_is_alive(snapshot.pid)
            if pid_alive:
                current_identity = self.read_process_identity(snapshot.pid)
                identity_match = self.identity_matches(snapshot.identity, current_identity)
        provenance_match = self.provenance_matches(snapshot)
        threshold = self.stale_lock_age_threshold()
        if snapshot is None:
            return self._build_evaluation(
                snapshot=None, lock_age=lock_age, pid_alive=pid_alive,
                current_identity=current_identity, identity_match=identity_match,
                provenance_match=provenance_match, should_cleanup=False,
                stale_decision="unreadable", cleanup_reason=None
            )
        if snapshot.pid is None:
            stale_decision = "missing-pid"
            cleanup_reason = None
            should_cleanup = False
            if lock_age is not None and lock_age >= threshold:
                should_cleanup = True
                cleanup_reason = "missing-pid-old"
            return self._build_evaluation(
                snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
                current_identity=current_identity, identity_match=identity_match,
                provenance_match=provenance_match, should_cleanup=should_cleanup,
                stale_decision=stale_decision, cleanup_reason=cleanup_reason
            )
        if pid_alive:
            if provenance_match:
                return self._build_evaluation(
                    snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
                    current_identity=current_identity, identity_match=identity_match,
                    provenance_match=provenance_match, should_cleanup=False,
                    stale_decision="provenance-match", cleanup_reason=None
                )
            if identity_match is True:
                return self._build_evaluation(
                    snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
                    current_identity=current_identity, identity_match=identity_match,
                    provenance_match=provenance_match, should_cleanup=False,
                    stale_decision="identity-match", cleanup_reason=None
                )
            if identity_match is False:
                has_scheduler_provenance = bool(
                    snapshot.scheduler_instance_id and snapshot.attempted_run_id
                )
                scheduler_mismatch = (
                    has_scheduler_provenance
                    and self._pending_run_id is not None
                    and (
                        snapshot.scheduler_instance_id != self._instance_id
                        or snapshot.attempted_run_id != self._pending_run_id
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
                    return self._build_evaluation(
                        snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
                        current_identity=current_identity, identity_match=identity_match,
                        provenance_match=provenance_match, should_cleanup=True,
                        stale_decision=stale_decision, cleanup_reason=stale_decision
                    )
                cleanup_due_to_identity = lock_age is not None and lock_age >= threshold
                if cleanup_due_to_identity:
                    return self._build_evaluation(
                        snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
                        current_identity=current_identity, identity_match=identity_match,
                        provenance_match=provenance_match, should_cleanup=True,
                        stale_decision="identity-mismatch-old", cleanup_reason="identity-mismatch-old"
                    )
                stale_decision = (
                    "foreign-live-lock"
                    if snapshot.identity is None or current_identity is None
                    else "identity-mismatch-young-foreign"
                )
                return self._build_evaluation(
                    snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
                    current_identity=current_identity, identity_match=identity_match,
                    provenance_match=provenance_match, should_cleanup=False,
                    stale_decision=stale_decision, cleanup_reason=None
                )
            return self._build_evaluation(
                snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
                current_identity=current_identity, identity_match=identity_match,
                provenance_match=provenance_match, should_cleanup=False,
                stale_decision="foreign-live-lock", cleanup_reason=None
            )
        if lock_age is None:
            return self._build_evaluation(
                snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
                current_identity=current_identity, identity_match=identity_match,
                provenance_match=provenance_match, should_cleanup=False,
                stale_decision="pid-dead-unknown-age", cleanup_reason=None
            )
        if lock_age < threshold:
            return self._build_evaluation(
                snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
                current_identity=current_identity, identity_match=identity_match,
                provenance_match=provenance_match, should_cleanup=False,
                stale_decision="pid-dead-young", cleanup_reason=None
            )
        return self._build_evaluation(
            snapshot=snapshot, lock_age=lock_age, pid_alive=pid_alive,
            current_identity=current_identity, identity_match=identity_match,
            provenance_match=provenance_match, should_cleanup=True,
            stale_decision="pid-dead-old", cleanup_reason="pid-not-running"
        )

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

    def _build_evaluation(
        self,
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
        """Build and log a lock evaluation."""
        evaluation = LockEvaluation(
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
