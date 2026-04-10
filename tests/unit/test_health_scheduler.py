import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import k8s_diag_agent.health.loop as health_loop
from k8s_diag_agent.external_analysis.config import ExternalAnalysisSettings
from k8s_diag_agent.health.loop import (
    HealthLoopScheduler,
    HealthRating,
    LockEvaluation,
    LockFileSnapshot,
    ProcessIdentity,
)


class HealthSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.config_path = self.tmpdir / "health-config.json"
        self.output_dir = self.tmpdir / "runs"
        self._uuid_patcher = patch(
            "k8s_diag_agent.health.loop.uuid4",
            return_value=SimpleNamespace(hex="instance-123"),
        )
        self._uuid_patcher.start()
        self.addCleanup(self._uuid_patcher.stop)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_scheduler(
        self,
        interval_seconds: int | None,
        max_runs: int | None,
        run_once: bool,
    ) -> HealthLoopScheduler:
        scheduler = HealthLoopScheduler(
            config_path=self.config_path,
            manual_triggers=(),
            manual_drilldown_contexts=(),
            manual_external_analysis=(),
            quiet=True,
            interval_seconds=interval_seconds,
            max_runs=max_runs,
            run_once=run_once,
            output_dir=self.output_dir,
        )
        return scheduler

    def test_scheduler_runs_up_to_max(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=3, run_once=False)
        with patch.object(scheduler, "_acquire_lock", return_value=True), patch.object(
            scheduler, "_release_lock", return_value=None
        ), patch("k8s_diag_agent.health.loop.run_health_loop") as run_mock, patch(
            "k8s_diag_agent.health.loop.time.sleep"
        ):
            run_mock.return_value = (0, [], [], [], [], ExternalAnalysisSettings())
            exit_code = scheduler.run()
        self.assertEqual(exit_code, 0)
        self.assertEqual(run_mock.call_count, 3)

    def test_scheduler_skips_when_lock_present(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=True)
        with patch.object(scheduler, "_acquire_lock", return_value=False), patch.object(
            scheduler, "_release_lock", return_value=None
        ), patch("k8s_diag_agent.health.loop.run_health_loop") as run_mock:
            exit_code = scheduler.run()
        self.assertEqual(exit_code, 0)
        self.assertEqual(run_mock.call_count, 0)

    def test_acquire_lock_removes_stale_lock_file(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=True)
        lock_path = scheduler._lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        lock_path.write_text(f"{timestamp} pid=999999\n", encoding="utf-8")
        with patch.object(scheduler, "_pid_is_alive", return_value=False), patch.object(
            scheduler, "_log_event"
        ) as log_mock:
            with patch.object(scheduler, "_stale_lock_age_threshold", return_value=1):
                acquired = scheduler._acquire_lock()
        self.assertTrue(acquired)
        self.assertTrue(lock_path.exists())
        self.assertEqual(log_mock.call_count, 1)
        severity, message = log_mock.call_args.args[:2]
        self.assertEqual(severity, "WARNING")
        self.assertEqual(message, "Removed stale lock file")
        metadata = log_mock.call_args.kwargs
        self.assertEqual(metadata["cleanup_reason"], "pid-not-running")
        self.assertEqual(metadata["lock_pid"], 999999)
        self.assertFalse(metadata["pid_alive"])
        self.assertEqual(metadata["lock_timestamp"], timestamp)
        self.assertGreater(metadata["lock_age_seconds"], 0)
        self.assertEqual(metadata["expected_interval_seconds"], 1)
        scheduler._release_lock()

    def test_acquire_lock_handles_malformed_lock_file(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=True)
        lock_path = scheduler._lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("corrupted content", encoding="utf-8")
        with patch.object(scheduler, "_log_event") as log_mock:
            with patch.object(scheduler, "_stale_lock_age_threshold", return_value=600):
                acquired = scheduler._acquire_lock()
        self.assertFalse(acquired)
        metadata = log_mock.call_args.kwargs
        self.assertEqual(metadata["stale_decision"], "missing-pid")
        self.assertIsNone(metadata["lock_pid"])
        self.assertIsNone(metadata["pid_alive"])
        self.assertEqual(metadata["repeated_lock_skips"], 1)
        self.assertIsNone(metadata.get("identity_match"))
        self.assertIsNone(metadata.get("current_identity_signature"))
        self.assertFalse(metadata.get("identity_mismatch", False))
        scheduler._release_lock()

    def test_acquire_lock_preserves_lock_when_process_alive(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=True)
        lock_path = scheduler._lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        hostname = scheduler._identity_hostname or "test-host"
        identity = ProcessIdentity("start-12345", "python3 -m k8s_diag_agent.cli", hostname)
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "pid": os.getpid(),
            "identity": {
                "start_time": identity.start_time,
                "cmdline": identity.cmdline,
                "hostname": identity.hostname,
            },
        }
        lock_path.write_text(json.dumps(payload), encoding="utf-8")
        with patch.object(scheduler, "_pid_is_alive", return_value=True), patch.object(
            scheduler, "_read_process_identity", return_value=identity
        ), patch.object(scheduler, "_log_event") as log_mock:
            acquired = scheduler._acquire_lock()
        self.assertFalse(acquired)
        self.assertTrue(lock_path.exists())
        self.assertEqual(log_mock.call_count, 1)
        severity, message = log_mock.call_args.args[:2]
        self.assertEqual(severity, "WARNING")
        self.assertEqual(message, "Health run skipped because lock is held")
        metadata = log_mock.call_args.kwargs
        self.assertEqual(metadata["stale_decision"], "identity-match")
        self.assertTrue(metadata["pid_alive"])
        self.assertEqual(metadata["lock_pid"], os.getpid())
        self.assertTrue(metadata["identity_match"])
        self.assertEqual(metadata["lock_identity_signature"], identity.signature)

    def test_identity_mismatch_old_lock_triggers_cleanup(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=True)
        lock_path = scheduler._lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        hostname = scheduler._identity_hostname or "test-host"
        stored_identity = {
            "start_time": "1000",
            "cmdline": "python3 scheduler",
            "hostname": hostname,
        }
        payload = {
            "timestamp": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            "pid": os.getpid(),
            "identity": stored_identity,
        }
        lock_path.write_text(json.dumps(payload), encoding="utf-8")
        with patch.object(scheduler, "_pid_is_alive", return_value=True), patch.object(
            scheduler,
            "_read_process_identity",
            return_value=ProcessIdentity(
                "2000", "python3 new-run", hostname
            ),
        ), patch.object(scheduler, "_stale_lock_age_threshold", return_value=1):
            evaluation = scheduler._evaluate_lock_state()
        self.assertTrue(evaluation.should_cleanup)
        self.assertEqual(evaluation.stale_decision, "identity-mismatch-old")
        self.assertEqual(evaluation.cleanup_reason, "identity-mismatch-old")
        self.assertFalse(evaluation.identity_match)
        scheduler._release_lock()

    def test_scheduler_instance_mismatch_cleanup_with_different_pid(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=True)
        lock_path = scheduler._lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        hostname = scheduler._identity_hostname or "test-host"
        stored_identity = {
            "start_time": "1000",
            "cmdline": "python3 scheduler",
            "hostname": hostname,
        }
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "pid": os.getpid() + 10,
            "identity": stored_identity,
            "scheduler_instance_id": "old-instance",
            "attempted_run_id": "old-run",
        }
        lock_path.write_text(json.dumps(payload), encoding="utf-8")
        scheduler._pending_run_id = "new-run"
        with patch.object(scheduler, "_pid_is_alive", return_value=True), patch.object(
            scheduler,
            "_read_process_identity",
            return_value=ProcessIdentity(
                "2000", "python3 new-run", hostname
            ),
        ):
            evaluation = scheduler._evaluate_lock_state()
        self.assertTrue(evaluation.should_cleanup)
        self.assertEqual(evaluation.stale_decision, "scheduler-instance-mismatch")
        self.assertEqual(evaluation.cleanup_reason, "scheduler-instance-mismatch")
        scheduler._release_lock()

    def test_scheduler_provenance_cleanup_on_pid_reuse(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=True)
        lock_path = scheduler._lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        hostname = scheduler._identity_hostname or "test-host"
        stored_identity = {
            "start_time": "1000",
            "cmdline": "python3 scheduler",
            "hostname": hostname,
        }
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "pid": os.getpid(),
            "identity": stored_identity,
            "scheduler_pid": os.getpid(),
            "child_pid": os.getpid(),
            "scheduler_instance_id": "old-instance",
            "attempted_run_id": "old-run",
        }
        lock_path.write_text(json.dumps(payload), encoding="utf-8")
        scheduler._pending_run_id = "new-run"
        with patch.object(scheduler, "_pid_is_alive", return_value=True), patch.object(
            scheduler,
            "_read_process_identity",
            return_value=ProcessIdentity(
                "2000", "python3 new-run", hostname
            ),
        ):
            evaluation = scheduler._evaluate_lock_state()
        self.assertTrue(evaluation.should_cleanup)
        self.assertEqual(evaluation.stale_decision, "pid-reuse-stale")
        self.assertEqual(evaluation.cleanup_reason, "pid-reuse-stale")
        scheduler._release_lock()

    def test_scheduler_provenance_pid_reuse_via_scheduler_fields(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=True)
        lock_path = scheduler._lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        hostname = scheduler._identity_hostname or "test-host"
        stored_identity = {
            "start_time": "1000",
            "cmdline": "python3 scheduler",
            "hostname": hostname,
        }
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "pid": os.getpid() + 5,
            "identity": stored_identity,
            "scheduler_pid": os.getpid(),
            "child_pid": os.getpid(),
            "scheduler_instance_id": "old-instance",
            "attempted_run_id": "old-run",
        }
        lock_path.write_text(json.dumps(payload), encoding="utf-8")
        scheduler._pending_run_id = "new-run"
        with patch.object(scheduler, "_pid_is_alive", return_value=True), patch.object(
            scheduler,
            "_read_process_identity",
            return_value=ProcessIdentity(
                "2000", "python3 new-run", hostname
            ),
        ):
            evaluation = scheduler._evaluate_lock_state()
        self.assertTrue(evaluation.should_cleanup)
        self.assertEqual(evaluation.stale_decision, "pid-reuse-stale")
        self.assertEqual(evaluation.cleanup_reason, "pid-reuse-stale")
        scheduler._release_lock()

    def test_foreign_live_lock_preserves_when_identity_missing(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=True)
        lock_path = scheduler._lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "pid": os.getpid(),
        }
        lock_path.write_text(json.dumps(payload), encoding="utf-8")
        with patch.object(scheduler, "_pid_is_alive", return_value=True), patch.object(
            scheduler,
            "_read_process_identity",
            return_value=None,
        ):
            evaluation = scheduler._evaluate_lock_state()
        self.assertFalse(evaluation.should_cleanup)
        self.assertEqual(evaluation.stale_decision, "foreign-live-lock")
        self.assertIsNone(evaluation.cleanup_reason)
        scheduler._release_lock()

    def test_lock_skip_emits_single_structured_event(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=True)
        lock_path = scheduler._lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        hostname = scheduler._identity_hostname or "test-host"
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "pid": os.getpid(),
            "identity": {
                "start_time": "1000",
                "cmdline": "python3 scheduler",
                "hostname": hostname,
            },
        }
        lock_path.write_text(json.dumps(payload), encoding="utf-8")
        with patch.object(scheduler, "_pid_is_alive", return_value=True), patch.object(
            scheduler,
            "_read_process_identity",
            return_value=ProcessIdentity(
                "2000", "python3 scheduler", hostname
            ),
        ), patch.object(scheduler, "_log_event") as log_mock:
            scheduler._acquire_lock()
        self.assertEqual(log_mock.call_count, 1)
        severity, message = log_mock.call_args.args[:2]
        self.assertEqual(severity, "WARNING")
        self.assertEqual(message, "Health run skipped because lock is held")
        metadata = log_mock.call_args.kwargs
        self.assertEqual(metadata["stale_decision"], "identity-mismatch-young-foreign")
        scheduler._release_lock()

    def test_log_lock_held_includes_expected_fields(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=5, max_runs=1, run_once=True)
        snapshot = LockFileSnapshot(
            timestamp_value="2026-01-01T00:00:00Z",
            timestamp=None,
            pid=42,
            mtime=None,
            identity=None,
            scheduler_instance_id=None,
            attempted_run_id=None,
            scheduler_pid=None,
            child_pid=None,
            child_start_time=None,
            run_label=None,
        )
        evaluation = LockEvaluation(
            snapshot=snapshot,
            lock_age_seconds=5.5,
            pid_alive=False,
            current_identity=None,
            identity_match=None,
            provenance_match=None,
            should_cleanup=False,
            stale_decision="pid-dead-young",
            cleanup_reason=None,
        )
        with patch.object(scheduler, "_log_event") as log_mock:
            scheduler._log_lock_held(evaluation)
        self.assertEqual(log_mock.call_count, 1)
        severity, message = log_mock.call_args.args[:2]
        self.assertEqual(severity, "WARNING")
        self.assertEqual(message, "Health run skipped because lock is held")
        metadata = log_mock.call_args.kwargs
        self.assertEqual(metadata["lock_age_seconds"], 5.5)
        self.assertEqual(metadata["lock_pid"], 42)
        self.assertEqual(metadata["stale_decision"], "pid-dead-young")
        self.assertEqual(metadata["expected_interval_seconds"], 5)
        self.assertEqual(metadata["repeated_lock_skips"], 1)
        self.assertNotIn("lock_skip_escalated", metadata)
        self.assertIsNone(metadata["identity_match"])
        self.assertIsNone(metadata["current_identity_signature"])

    def test_lock_skip_escalates_after_threshold(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=5, max_runs=1, run_once=True)
        scheduler._lock_skip_escalation_threshold = 2
        snapshot = LockFileSnapshot(
            timestamp_value="2026-01-01T00:00:00Z",
            timestamp=None,
            pid=43,
            mtime=None,
            identity=None,
            scheduler_instance_id=None,
            attempted_run_id=None,
            scheduler_pid=None,
            child_pid=None,
            child_start_time=None,
            run_label=None,
        )
        evaluation = LockEvaluation(
            snapshot=snapshot,
            lock_age_seconds=4.5,
            pid_alive=False,
            current_identity=None,
            identity_match=None,
            provenance_match=None,
            should_cleanup=False,
            stale_decision="pid-dead-young",
            cleanup_reason=None,
        )
        with patch.object(scheduler, "_log_event") as log_mock:
            scheduler._log_lock_held(evaluation)
            scheduler._log_lock_held(evaluation)
        self.assertEqual(log_mock.call_count, 2)
        _, metadata_first = log_mock.call_args_list[0]
        self.assertEqual(metadata_first["repeated_lock_skips"], 1)
        severity_last, _ = log_mock.call_args_list[1].args[:2]
        metadata_last = log_mock.call_args_list[1].kwargs
        self.assertEqual(severity_last, "ERROR")
        self.assertTrue(metadata_last.get("lock_skip_escalated"))
        self.assertEqual(metadata_last["repeated_lock_skips"], 2)

    def test_provenance_match_preserves_lock(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=True)
        lock_path = scheduler._lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        run_id = "run-provenance"
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "pid": os.getpid(),
            "scheduler_instance_id": "instance-123",
            "attempted_run_id": run_id,
        }
        lock_path.write_text(json.dumps(payload), encoding="utf-8")
        scheduler._pending_run_id = run_id
        with patch.object(scheduler, "_pid_is_alive", return_value=True):
            evaluation = scheduler._evaluate_lock_state()
        self.assertFalse(evaluation.should_cleanup)
        self.assertEqual(evaluation.stale_decision, "provenance-match")
        status = json.loads(scheduler._lock_status_path.read_text(encoding="utf-8"))
        self.assertEqual(status.get("stale_decision"), "provenance-match")

    def test_lock_status_artifact_written(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=True)
        lock_path = scheduler._lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        lock_path.write_text(f"{timestamp} pid=100\n", encoding="utf-8")
        scheduler._pending_run_id = "run-x"
        scheduler._pending_run_start = datetime.now(UTC)
        with patch.object(scheduler, "_pid_is_alive", return_value=False), patch.object(
            scheduler, "_stale_lock_age_threshold", return_value=0
        ):
            evaluation = scheduler._evaluate_lock_state()
        status = json.loads(scheduler._lock_status_path.read_text(encoding="utf-8"))
        self.assertEqual(status.get("stale_decision"), evaluation.stale_decision)
        self.assertEqual(status.get("stale_decision"), "pid-dead-old")
        self.assertEqual(status.get("cleanup_reason"), "pid-not-running")

    def test_summary_metadata_includes_health_counts(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=False)
        assessment = SimpleNamespace(run_id="run-123", health_rating=HealthRating.HEALTHY)
        with patch.object(scheduler, "_acquire_lock", return_value=True), patch.object(
            scheduler, "_release_lock", return_value=None
        ), patch(
            "k8s_diag_agent.health.loop.run_health_loop",
            return_value=(0, [assessment], [], [], [], ExternalAnalysisSettings()),
        ), patch.object(scheduler, "_log_event") as log_mock:
            exit_code = scheduler.run()
        self.assertEqual(exit_code, 0)
        summary_calls = [
            call
            for call in log_mock.call_args_list
            if len(call.args) > 1 and call.args[1] == "Health run summary"
        ]
        self.assertEqual(len(summary_calls), 1)
        metadata = summary_calls[0][1]
        self.assertEqual(metadata["healthy_count"], 1)
        self.assertEqual(metadata["degraded_count"], 0)
        provider_execution = metadata.get("provider_execution")
        self.assertIsInstance(provider_execution, dict)
        self.assertIn("auto_drilldown", provider_execution)
        self.assertIn("review_enrichment", provider_execution)

    def test_log_run_summary_reports_freshness_status(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=10, max_runs=1, run_once=False)
        with patch.object(scheduler, "_log_event") as log_mock:
            scheduler._log_run_summary(
                assessments=[],
                triggers=[],
                drilldowns=[],
                external_analysis=[],
                settings=ExternalAnalysisSettings(),
                freshness_age_seconds=25,
                expected_interval_seconds=10,
            )
        metadata = log_mock.call_args.kwargs
        self.assertEqual(metadata.get("freshness_age_seconds"), 25)
        self.assertEqual(metadata.get("expected_interval_seconds"), 10)
        self.assertEqual(metadata.get("freshness_status"), "stale")

    def test_maybe_build_diagnostic_pack_respects_env_gate(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=False)
        with patch.dict(os.environ, {"HEALTH_BUILD_DIAGNOSTIC_PACK": "0"}):
            with patch("k8s_diag_agent.health.loop.subprocess.run") as run_mock:
                scheduler._maybe_build_diagnostic_pack("run-123")
        run_mock.assert_not_called()

    def test_maybe_build_diagnostic_pack_invokes_scripts_when_enabled(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=False)
        run_id = "run-abc"
        expected_runs_dir = str(scheduler._runs_dir_base)
        build_script = health_loop._SCRIPTS_DIR / "build_diagnostic_pack.py"
        update_script = health_loop._SCRIPTS_DIR / "update_ui_index.py"
        with patch.dict(os.environ, {"HEALTH_BUILD_DIAGNOSTIC_PACK": "1"}):
            with patch("k8s_diag_agent.health.loop.subprocess.run") as run_mock:
                run_mock.return_value = None
                scheduler._maybe_build_diagnostic_pack(run_id)
        self.assertEqual(run_mock.call_count, 2)
        build_call = run_mock.call_args_list[0]
        build_cmd = build_call.args[0]
        self.assertEqual(build_cmd[0], sys.executable)
        self.assertEqual(build_cmd[1], str(build_script))
        self.assertEqual(build_cmd[3], run_id)
        self.assertEqual(build_cmd[5], expected_runs_dir)
        update_call = run_mock.call_args_list[1]
        update_cmd = update_call.args[0]
        self.assertEqual(update_cmd[1], str(update_script))
        self.assertEqual(update_cmd[3], run_id)
