"""Scheduler and lock-management family for the health loop.

Extracts process-identity, lock-file, and scheduling infrastructure from loop.py into a focused module.
Preserves behavior exactly - no lock semantics, scheduling cadence, logging, or artifact shape changes.

This module provides the scheduling logic that:
1. Manages per-interval health loop execution
2. Acquires/releases file-based locks with provenance tracking
3. Evaluates lock staleness based on process identity and age
4. Logs scheduler events and run summaries

The run_health_loop function is injected as a parameter to avoid circular imports.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from .loop import HealthRunConfig


# Module-level constants
_HEALTH_LOCK_FILENAME = ".health-loop.lock"
_HEALTH_ONLY_MESSAGE = "No peer mappings configured; running health-only mode."

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


class HealthLoopScheduler:
    """Manages scheduled health loop execution with file-based locking."""

    _LOCK_SKIP_ESCALATION_THRESHOLD = _LOCK_SKIP_ESCALATION_THRESHOLD
    _LOCK_STALE_MIN_SECONDS = _LOCK_STALE_MIN_SECONDS
    _LOCK_STALE_AGE_MULTIPLIER = _LOCK_STALE_AGE_MULTIPLIER

    def __init__(
        self,
        config_path: Path,
        manual_triggers: Sequence[str],
        manual_drilldown_contexts: Sequence[str] | None,
        manual_external_analysis: Sequence[str] | None,
        quiet: bool,
        interval_seconds: int | None,
        max_runs: int | None,
        run_once: bool,
        output_dir: Path,
        scripts_dir: Path,
        run_health_loop_fn: Callable[..., tuple[int, list[Any], list[Any], list[Any], list[Any], Any]],
        run_label: str | None = None,
    ) -> None:
        self._config_path = config_path
        self._manual_triggers = tuple(manual_triggers)
        self._manual_drilldown_contexts = tuple(manual_drilldown_contexts or [])
        self._manual_external_analysis = tuple(manual_external_analysis or [])
        self._quiet = quiet
        self._interval_seconds = interval_seconds
        self._max_runs = max_runs
        self._run_once = run_once
        self._lock_path = output_dir / "health" / _HEALTH_LOCK_FILENAME
        self._run_label = run_label or "health-scheduler"
        self._log_path = output_dir / "health" / "scheduler.log"
        self._last_run_finish_time: float | None = None
        self._runs_dir_base = output_dir

        self._instance_id = uuid4().hex
        self._pending_run_id: str | None = None
        self._pending_run_start: datetime | None = None
        self._lock_status_path = self._lock_path.parent / "lock-status.json"

        self._identity_hostname = self._resolve_hostname()
        self._proc_root = Path("/proc") if Path("/proc").exists() else None

        self._lock_skip_streak = 0
        self._lock_skip_escalation_threshold = self._LOCK_SKIP_ESCALATION_THRESHOLD

        self._scripts_dir = scripts_dir
        self._run_health_loop_fn = run_health_loop_fn
        # Store config reference for effective config logging at startup
        self._run_config: HealthRunConfig | None = None

    def _log_event(self, severity: str, message: str, **metadata: Any) -> None:
        """Emit a structured log event for the scheduler."""
        from ..structured_logging import emit_structured_log
        emit_structured_log(
            component="health-scheduler",
            message=message,
            severity=severity,
            run_label=self._run_label,
            log_path=self._log_path,
            metadata=metadata or None,
        )

    def _resolve_hostname(self) -> str | None:
        """Resolve the local hostname, returning None on failure."""
        try:
            return socket.gethostname()
        except OSError:
            return None

    def _resolve_run_id(
        self,
        assessments: list[Any],
        triggers: list[Any],
    ) -> str:
        """Resolve the run ID from assessments or triggers."""
        if assessments:
            return getattr(assessments[0], 'run_id', "<unknown>")
        if triggers:
            return getattr(triggers[0], 'run_id', "<unknown>")
        return "<unknown>"

    def _acquire_lock(self) -> bool:
        """Attempt to acquire the scheduler lock file."""
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                payload = {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "pid": os.getpid(),
                }
                identity = self._current_process_identity()
                identity_data = self._serialize_identity(identity)
                if identity_data:
                    payload["identity"] = identity_data
                payload["scheduler_instance_id"] = self._instance_id
                if self._pending_run_id:
                    payload["attempted_run_id"] = self._pending_run_id
                payload["scheduler_pid"] = os.getpid()
                payload["child_pid"] = os.getpid()
                if self._pending_run_start:
                    payload["child_start_time"] = self._pending_run_start.isoformat()
                payload["run_label"] = self._run_label
                with self._lock_path.open("x", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload))
                    handle.write("\n")
                self._lock_skip_streak = 0
                return True
            except FileExistsError:
                evaluation = self._evaluate_lock_state()
                if evaluation.should_cleanup and self._remove_stale_lock(evaluation):
                    self._lock_skip_streak = 0
                    continue
                self._log_lock_held(evaluation)
                return False

    def _release_lock(self) -> None:
        """Release the scheduler lock file if it exists."""
        try:
            if self._lock_path.exists():
                self._lock_path.unlink()
        except OSError:
            pass

    def _current_process_identity(self) -> ProcessIdentity | None:
        """Get the identity of the current process."""
        identity = self._read_process_identity(os.getpid())
        if identity is not None:
            return identity
        if self._identity_hostname is None:
            return None
        return ProcessIdentity(None, None, self._identity_hostname)

    def _read_process_identity(self, pid: int) -> ProcessIdentity | None:
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

    def _serialize_identity(self, identity: ProcessIdentity | None) -> dict[str, str] | None:
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

    def _identity_from_mapping(
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

    def _identity_matches(
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

    def _coerce_pid(self, raw: object | None) -> int | None:
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

    def _evaluate_lock_state(self) -> LockEvaluation:
        """Evaluate the current lock file state to determine staleness."""
        snapshot = self._load_lock_snapshot()
        now = datetime.now(UTC)
        lock_age = snapshot.age_seconds(now) if snapshot else None
        current_pid = os.getpid()
        pid_alive: bool | None = None
        current_identity: ProcessIdentity | None = None
        identity_match: bool | None = None
        if snapshot and snapshot.pid is not None:
            pid_alive = self._pid_is_alive(snapshot.pid)
            if pid_alive:
                current_identity = self._read_process_identity(snapshot.pid)
                identity_match = self._identity_matches(snapshot.identity, current_identity)
        provenance_match = self._provenance_matches(snapshot)
        threshold = self._stale_lock_age_threshold()
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

    def _provenance_matches(self, snapshot: LockFileSnapshot | None) -> bool:
        """Check if the lock's provenance matches this scheduler instance."""
        if not snapshot or not self._pending_run_id:
            return False
        return (
            snapshot.scheduler_instance_id == self._instance_id
            and snapshot.attempted_run_id == self._pending_run_id
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

    def _load_lock_snapshot(self) -> LockFileSnapshot | None:
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
            pid = self._coerce_pid(raw.get("pid"))
            identity_raw = raw.get("identity")
            identity = (
                self._identity_from_mapping(identity_raw)
                if isinstance(identity_raw, Mapping)
                else None
            )
            scheduler_instance_id = _str_or_none(raw.get("scheduler_instance_id"))
            attempted_run_id = _str_or_none(raw.get("attempted_run_id"))
            scheduler_pid = self._coerce_pid(raw.get("scheduler_pid"))
            child_pid = self._coerce_pid(raw.get("child_pid"))
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

    def _pid_is_alive(self, pid: int) -> bool:
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

    def _stale_lock_age_threshold(self) -> float:
        """Compute the threshold for considering a lock stale."""
        interval = self._interval_seconds or self._LOCK_STALE_MIN_SECONDS
        base = max(interval, self._LOCK_STALE_MIN_SECONDS)
        return base * self._LOCK_STALE_AGE_MULTIPLIER

    def _format_last_run_timestamp(self) -> str | None:
        """Format the last run finish time as ISO string."""
        if self._last_run_finish_time is None:
            return None
        return datetime.fromtimestamp(self._last_run_finish_time, UTC).isoformat()

    def _remove_stale_lock(self, evaluation: LockEvaluation) -> bool:
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
        last_run_ts = self._format_last_run_timestamp()
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

    def _log_lock_held(self, evaluation: LockEvaluation) -> None:
        """Log when a lock is held by another process."""
        self._lock_skip_streak += 1
        escalated = self._lock_skip_streak >= self._lock_skip_escalation_threshold
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
            "repeated_lock_skips": self._lock_skip_streak,
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
        last_run_ts = self._format_last_run_timestamp()
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

    def _log_run_summary(
        self,
        assessments: list[Any],
        triggers: list[Any],
        drilldowns: list[Any],
        external_analysis: list[Any],
        settings: Any,
        freshness_age_seconds: float | None = None,
        expected_interval_seconds: int | None = None,
    ) -> None:
        """Log a summary of a completed health run."""
        from .freshness import freshness_status
        from .ui import _build_provider_execution, _serialize_review_enrichment_policy
        run_id = self._resolve_run_id(assessments, triggers)
        healthy_count = sum(
            1 for artifact in assessments 
            if getattr(getattr(artifact, 'health_rating', None), 'value', None) == "healthy"
        )
        degraded_count = len(assessments) - healthy_count
        review_config = _serialize_review_enrichment_policy(settings.review_enrichment)
        provider_execution = _build_provider_execution(
            settings,
            external_analysis,
            drilldowns,
            review_config,
        )
        metadata: dict[str, object] = {
            "run_id": run_id,
            "assessment_count": len(assessments),
            "healthy_count": healthy_count,
            "degraded_count": degraded_count,
            "trigger_count": len(triggers),
            "drilldown_count": len(drilldowns),
            "external_analysis_count": len(external_analysis),
            "provider_execution": provider_execution,
            "event": "run-summary",
        }
        if expected_interval_seconds is not None:
            metadata["expected_interval_seconds"] = expected_interval_seconds
            if freshness_age_seconds is not None:
                age_value = int(max(0.0, freshness_age_seconds))
                metadata["freshness_age_seconds"] = age_value
                status = freshness_status(age_value, expected_interval_seconds)
                if status:
                    metadata["freshness_status"] = status
        self._log_event(
            "INFO",
            "Health run summary",
            **metadata,
        )

    def _maybe_build_diagnostic_pack(self, run_id: str) -> None:
        """Build diagnostic pack if configured via environment."""
        from .loop_history import _env_is_truthy
        env_value = os.environ.get("HEALTH_BUILD_DIAGNOSTIC_PACK")
        if not _env_is_truthy(env_value):
            return
        if not run_id or run_id == "<unknown>":
            self._log_event(
                "INFO",
                "Skipping diagnostic pack generation; run_id unavailable",
                run_id=run_id,
                event="diag-pack-skipped",
            )
            return
        runs_dir = str(self._runs_dir_base)
        build_script = self._scripts_dir / "build_diagnostic_pack.py"
        build_cmd = [
            sys.executable,
            str(build_script),
            "--run-id",
            run_id,
            "--runs-dir",
            runs_dir,
        ]
        try:
            subprocess.run(build_cmd, check=True, env=os.environ)
        except (subprocess.CalledProcessError, OSError) as exc:
            self._log_event(
                "ERROR",
                "Scheduled diagnostic pack build failed",
                run_id=run_id,
                severity_reason=str(exc),
                event="diag-pack-build-failed",
            )
            return
        update_script = self._scripts_dir / "update_ui_index.py"
        update_cmd = [
            sys.executable,
            str(update_script),
            "--run-id",
            run_id,
            "--runs-dir",
            runs_dir,
        ]
        try:
            subprocess.run(update_cmd, check=True, env=os.environ)
        except (subprocess.CalledProcessError, OSError) as exc:
            self._log_event(
                "ERROR",
                "Scheduled UI index refresh failed after diagnostic pack build",
                run_id=run_id,
                severity_reason=str(exc),
                event="diag-pack-ui-refresh-failed",
            )
            return
        self._log_event(
            "INFO",
            "Scheduled diagnostic pack generated",
            run_id=run_id,
            runs_dir=runs_dir,
            event="diag-pack-generated",
        )


    def _log_effective_scheduler_config(self) -> None:
        """Emit the effective scheduler configuration log event.

        This is called once at startup, after config/env has been resolved
        but before the first run begins.
        """
        from .loop_config_logging import _log_effective_scheduler_config as _emit_config_log

        config = self._run_config
        if config is None:
            # Config not available - skip logging to avoid errors
            return

        _emit_config_log(
            config=config,
            interval_seconds=self._interval_seconds,
            max_runs=self._max_runs,
            run_once=self._run_once,
            log_fn=self._log_event,
        )


    def run(self) -> int:
        """Execute the scheduler loop, running health loops at configured intervals."""
        from .loop_history import _build_runtime_run_id
        executed_runs = 0
        last_exit = 0
        self._log_event(
            "INFO",
            "Health scheduler started",
            interval_seconds=self._interval_seconds,
            max_runs=self._max_runs,
            run_once=self._run_once,
        )
        # Emit effective scheduler config log (one-time startup event)
        self._log_effective_scheduler_config()
        _run_health_loop = self._run_health_loop_fn
        try:
            while True:
                if self._run_once and executed_runs >= 1:
                    break
                if self._max_runs is not None and executed_runs >= self._max_runs:
                    break
                run_executed = False
                self._pending_run_id = _build_runtime_run_id(self._run_label)
                self._pending_run_start = datetime.now(UTC)
                if not self._acquire_lock():
                    run_executed = False
                else:
                    try:
                        run_start_time = time.time()
                        freshness_age_seconds = (
                            run_start_time - self._last_run_finish_time
                            if self._last_run_finish_time is not None
                            else None
                        )
                        (
                            exit_code,
                            assessments,
                            triggers,
                            drilldowns,
                            external_artifacts,
                            settings,
                        ) = _run_health_loop(
                            self._config_path,
                            manual_triggers=self._manual_triggers,
                            manual_drilldown_contexts=self._manual_drilldown_contexts,
                            manual_external_analysis=self._manual_external_analysis,
                            quiet=self._quiet,
                            expected_scheduler_interval_seconds=self._interval_seconds,
                            run_id=self._pending_run_id,
                        )
                        run_id = self._resolve_run_id(assessments, triggers)
                        run_executed = True
                        last_exit = exit_code
                        if exit_code != 0:
                            self._log_event(
                                "ERROR",
                                "Health run failed",
                                run_id=run_id,
                                severity_reason=f"exit_code={exit_code}",
                                event="run-failure",
                            )
                            return exit_code
                        executed_runs += 1
                        self._log_run_summary(
                            assessments,
                            triggers,
                            drilldowns,
                            external_artifacts,
                            settings,
                            freshness_age_seconds=freshness_age_seconds,
                            expected_interval_seconds=self._interval_seconds,
                        )
                        self._maybe_build_diagnostic_pack(run_id)
                        self._last_run_finish_time = time.time()
                    finally:
                        self._pending_run_id = None
                        self._pending_run_start = None
                        self._release_lock()
                if not run_executed and self._run_once:
                    break
                if self._run_once:
                    break
                if self._max_runs is not None and executed_runs >= self._max_runs:
                    break
                if not self._interval_seconds:
                    break
                time.sleep(self._interval_seconds)
        except KeyboardInterrupt:
            self._log_event(
                "WARNING",
                "Health scheduler interrupted",
                event="interrupted",
                reason="keyboard",
            )
            return 1
        self._log_event(
            "INFO",
            "Health scheduler stopped",
            exit_code=last_exit,
            event="stop",
        )
        return last_exit


def schedule_health_loop(
    config_path: Path,
    manual_triggers: Sequence[str] | None = None,
    manual_drilldown_contexts: Sequence[str] | None = None,
    manual_external_analysis: Sequence[str] | None = None,
    quiet: bool = False,
    *,
    interval_seconds: int | None = None,
    max_runs: int | None = None,
    run_once: bool = False,
) -> int:
    """Schedule and run health loops at configured intervals.

    This function loads the configuration and creates a scheduler that manages
    lock-based execution of health loops.
    """
    from ..structured_logging import emit_structured_log
    from .loop import HealthRunConfig, run_health_loop
    from .loop_history import _safe_label

    # Compute scripts_dir relative to project root
    project_root = Path(__file__).resolve().parents[3]
    scripts_dir = project_root / "scripts"

    try:
        config = HealthRunConfig.load(config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        emit_structured_log(
            component="health-scheduler",
            severity="ERROR",
            message=f"Unable to load health config {config_path}: {exc}",
            run_label=_safe_label(str(config_path.stem)),
            metadata={"config_path": str(config_path), "severity_reason": str(exc), "event": "config-load-failed"},
        )
        return 1
    scheduler = HealthLoopScheduler(
        config_path=config_path,
        manual_triggers=manual_triggers or [],
        manual_drilldown_contexts=manual_drilldown_contexts or [],
        manual_external_analysis=manual_external_analysis or [],
        quiet=quiet,
        interval_seconds=interval_seconds,
        max_runs=max_runs,
        run_once=run_once,
        output_dir=config.output_dir,
        scripts_dir=scripts_dir,
        run_health_loop_fn=run_health_loop,
        run_label=config.run_label,
    )
    # Pass config to scheduler for effective config logging
    scheduler._run_config = config
    return scheduler.run()


# Re-export constants for external use
__all__ = [
    "ProcessIdentity",
    "LockFileSnapshot",
    "LockEvaluation",
    "HealthLoopScheduler",
    "schedule_health_loop",
    "_HEALTH_LOCK_FILENAME",
    "_LOCK_SKIP_ESCALATION_THRESHOLD",
    "_LOCK_STALE_MIN_SECONDS",
]
