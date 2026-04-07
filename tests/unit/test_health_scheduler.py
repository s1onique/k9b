import os
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from k8s_diag_agent.external_analysis.config import ExternalAnalysisSettings
from k8s_diag_agent.health.loop import HealthLoopScheduler, HealthRating


class HealthSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.config_path = self.tmpdir / "health-config.json"
        self.output_dir = self.tmpdir / "runs"

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
        lock_path.write_text(
            f"{datetime.now(UTC).isoformat()} pid=999999\n", encoding="utf-8"
        )
        with patch.object(scheduler, "_pid_is_alive", return_value=False), patch.object(
            scheduler, "_log_event"
        ) as log_mock:
            acquired = scheduler._acquire_lock()
        self.assertTrue(acquired)
        self.assertTrue(lock_path.exists())
        self.assertEqual(log_mock.call_count, 1)
        severity, message = log_mock.call_args.args[:2]
        self.assertEqual(severity, "WARNING")
        self.assertEqual(message, "Removed stale lock file")
        metadata = log_mock.call_args.kwargs
        self.assertEqual(metadata["reason"], "pid-not-running")
        self.assertIsNotNone(metadata["lock_timestamp"])
        self.assertIsNotNone(metadata["lock_pid"])
        scheduler._release_lock()

    def test_acquire_lock_handles_malformed_lock_file(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=True)
        lock_path = scheduler._lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("corrupted content", encoding="utf-8")
        with patch.object(scheduler, "_pid_is_alive", return_value=False), patch.object(
            scheduler, "_log_event"
        ) as log_mock:
            acquired = scheduler._acquire_lock()
        self.assertTrue(acquired)
        metadata = log_mock.call_args.kwargs
        self.assertEqual(metadata["reason"], "malformed")
        scheduler._release_lock()

    def test_acquire_lock_preserves_lock_when_process_alive(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=True)
        lock_path = scheduler._lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(f"{datetime.now(UTC).isoformat()} pid={os.getpid()}\n", encoding="utf-8")
        with patch.object(scheduler, "_pid_is_alive", return_value=True), patch.object(
            scheduler, "_log_event"
        ) as log_mock:
            acquired = scheduler._acquire_lock()
        self.assertFalse(acquired)
        self.assertTrue(lock_path.exists())
        log_mock.assert_not_called()

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
