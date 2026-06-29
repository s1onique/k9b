"""HealthLoopScheduler class extracted from loop_scheduler.py.

Extracted from loop_scheduler.py to reduce its size and improve LLM-friendly traversal.
Preserves behavior exactly - no lock semantics, scheduling cadence, logging, or artifact shape changes.

The HealthLoopScheduler class manages scheduled health loop execution with file-based locking.
Delegates to pure functions in loop_scheduler_lock_eval for lock evaluation logic.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4 as _default_uuid4

if TYPE_CHECKING:
    from .loop import HealthRunConfig
    from .loop_scheduler_models import LockEvaluation, LockFileSnapshot, ProcessIdentity

from .loop_scheduler_config import (  # noqa: F401 - re-exported for backward compatibility
    _LOCK_STALE_AGE_MULTIPLIER,
    _LOCK_STALE_MIN_SECONDS,
    compute_stale_lock_age_threshold,
    format_last_run_timestamp,
    parse_lock_timestamp,
    resolve_hostname,
)
from .loop_scheduler_cycle import (  # noqa: F401 - re-exported for backward compatibility
    CycleState,  # noqa: F401 - re-exported for backward compatibility
    compute_cycle_exit_code,  # noqa: F401 - re-exported for backward compatibility
    compute_sleep_duration,  # noqa: F401 - re-exported for backward compatibility
    should_break_after_cycle,  # noqa: F401 - re-exported for backward compatibility
    should_continue_scheduler,  # noqa: F401 - re-exported for backward compatibility
)
from .loop_scheduler_diagnostics import (
    build_diagnostic_pack,  # noqa: F401 - re-exported for backward compatibility
    log_run_summary,  # noqa: F401 - re-exported for backward compatibility
)
from .loop_scheduler_lock_eval import (  # Use pure functions instead of duplicating logic
    evaluate_lock_state,
    parse_lock_metadata,
    stale_lock_age_threshold,
)
from .loop_scheduler_lock_facade import (  # noqa: F401 - re-exported for backward compatibility
    acquire_lock as _facade_acquire_lock,
)
from .loop_scheduler_lock_facade import (
    log_lock_held as _facade_log_lock_held,
)
from .loop_scheduler_lock_facade import (
    release_lock as _facade_release_lock,
)
from .loop_scheduler_lock_facade import (
    remove_stale_lock as _facade_remove_stale_lock,
)
from .loop_scheduler_locking import LockManager
from .loop_scheduler_models import (  # noqa: F401 - re-exported for backward compatibility
    _HEALTH_LOCK_FILENAME,
    _HEALTH_ONLY_MESSAGE,
    _LOCK_SKIP_ESCALATION_THRESHOLD,
    LockEvaluation,  # noqa: F401 - re-exported for backward compatibility
    LockFileSnapshot,  # noqa: F401 - re-exported for backward compatibility
    ProcessIdentity,  # noqa: F401 - re-exported for backward compatibility
    _str_or_none,
)
from .loop_scheduler_run import run_scheduler_loop


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

        # Look up uuid4 from loop_scheduler module at runtime to respect test patches.
        # The test patches k8s_diag_agent.health.loop_scheduler.uuid4, so we use
        # sys.modules to dynamically look up the name at instance creation time.
        # Try both import paths and fall back to default.
        _facade = (
            sys.modules.get("k8s_diag_agent.health.loop_scheduler")
            or sys.modules.get("src.k8s_diag_agent.health.loop_scheduler")
        )
        _uuid4 = getattr(_facade, "uuid4", _default_uuid4) if _facade else _default_uuid4
        self._instance_id = _uuid4().hex
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

        # Initialize LockManager for lock operations
        self._lock_manager = LockManager(self)

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
        """Resolve the local hostname, returning None on failure.

        Delegates to the extracted resolve_hostname function for the actual implementation.
        """
        return resolve_hostname()

    def _acquire_lock(self) -> bool:
        """Attempt to acquire the scheduler lock file.

        Delegates to the lock facade for actual implementation.
        """
        return _facade_acquire_lock(self._lock_manager)

    def _release_lock(self) -> None:
        """Release the scheduler lock file if it exists.

        Delegates to the lock facade for actual implementation.
        """
        _facade_release_lock(self._lock_manager)

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

    def _evaluate_lock_state(self) -> LockEvaluation:
        """Evaluate the current lock file state to determine staleness.

        Delegates to the pure evaluate_lock_state function from loop_scheduler_lock_eval.
        """
        snapshot = self._load_lock_snapshot()
        evaluation = evaluate_lock_state(
            snapshot=snapshot,
            current_pid=os.getpid(),
            interval_seconds=self._interval_seconds,
            instance_id=self._instance_id,
            pending_run_id=self._pending_run_id,
            read_identity_fn=self._read_process_identity,
            pid_alive_fn=self._pid_is_alive,
        )
        self._write_lock_status(evaluation)
        return evaluation

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
        """Parse lock file metadata from JSON or legacy text format.

        Delegates to the pure parse_lock_metadata function from loop_scheduler_lock_eval.
        """
        return parse_lock_metadata(
            contents,
            identity_hostname=self._identity_hostname,
            proc_root=self._proc_root,
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
        """Parse lock timestamp to timezone-aware UTC datetime.

        Delegates to the extracted parse_lock_timestamp function for the actual implementation.
        """
        return parse_lock_timestamp(value)

    def _stale_lock_age_threshold(self) -> float:
        """Compute the threshold for considering a lock stale.

        Delegates to the extracted compute_stale_lock_age_threshold function.
        """
        return stale_lock_age_threshold(self._interval_seconds)

    def _format_last_run_timestamp(self) -> str | None:
        """Format the last run finish time as ISO string.

        Delegates to the extracted format_last_run_timestamp function.
        """
        return format_last_run_timestamp(self._last_run_finish_time)

    def _remove_stale_lock(self, evaluation: LockEvaluation) -> bool:
        """Remove a stale lock file and log the removal.

        Delegates to the lock facade for actual implementation.
        """
        return _facade_remove_stale_lock(self._lock_manager, evaluation)

    def _log_lock_held(self, evaluation: LockEvaluation) -> None:
        """Log when a lock is held by another process.

        Delegates to the lock facade for actual implementation.
        """
        _facade_log_lock_held(self._lock_manager, evaluation)

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
        """Log a summary of a completed health run.

        Delegates to the extracted log_run_summary function for the actual implementation.
        """
        log_run_summary(
            log_fn=self._log_event,
            assessments=assessments,
            triggers=triggers,
            drilldowns=drilldowns,
            external_analysis=external_analysis,
            settings=settings,
            last_run_finish_time=self._last_run_finish_time,
            freshness_age_seconds=freshness_age_seconds,
            expected_interval_seconds=expected_interval_seconds,
        )

    def _maybe_build_diagnostic_pack(self, run_id: str) -> None:
        """Build diagnostic pack if configured via environment.

        Delegates to the extracted build_diagnostic_pack function for the actual implementation.
        """
        build_diagnostic_pack(
            log_fn=self._log_event,
            scripts_dir=self._scripts_dir,
            runs_dir_base=self._runs_dir_base,
            run_id=run_id,
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
        """Execute the scheduler loop, running health loops at configured intervals.

        Delegates to run_scheduler_loop() for the orchestration body, preserving
        all behavior exactly while keeping this surface minimal for test compatibility.
        """
        return run_scheduler_loop(self)


# Re-export constants for external use
__all__ = [
    "ProcessIdentity",
    "LockFileSnapshot",
    "LockEvaluation",
    "HealthLoopScheduler",
    "_HEALTH_LOCK_FILENAME",
    "_LOCK_SKIP_ESCALATION_THRESHOLD",
    "_LOCK_STALE_MIN_SECONDS",
]
