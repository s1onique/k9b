import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
            run_mock.return_value = (0, [], [], [], [])
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

    def test_summary_metadata_includes_health_counts(self) -> None:
        scheduler = self._make_scheduler(interval_seconds=1, max_runs=1, run_once=False)
        assessment = SimpleNamespace(run_id="run-123", health_rating=HealthRating.HEALTHY)
        with patch.object(scheduler, "_acquire_lock", return_value=True), patch.object(
            scheduler, "_release_lock", return_value=None
        ), patch("k8s_diag_agent.health.loop.run_health_loop", return_value=(0, [assessment], [], [], [])), patch.object(
            scheduler, "_log_event"
        ) as log_mock:
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
