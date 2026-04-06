import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from k8s_diag_agent.health.loop import HealthLoopScheduler


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
            run_mock.return_value = (0, [], [], [])
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
