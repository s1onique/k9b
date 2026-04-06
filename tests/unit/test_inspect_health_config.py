import sys
import unittest
from datetime import timezone
from pathlib import Path
from unittest.mock import patch

from k8s_diag_agent.health.loop import HealthTarget
from scripts import inspect_health_config


class DummySnapshotHelperTest(unittest.TestCase):
    def test_dummy_snapshot_uses_utc_timestamp(self) -> None:
        target = HealthTarget(
            context="cluster-alpha",
            label="cluster-alpha",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
            cluster_class="production",
            cluster_role="primary",
            baseline_cohort="fleet-production",
        )
        snapshot = inspect_health_config._dummy_snapshot(target)
        self.assertEqual(snapshot.metadata.cluster_id, target.context)
        self.assertIs(snapshot.metadata.captured_at.tzinfo, timezone.utc)  # noqa: UP017


class InspectHealthConfigCLITest(unittest.TestCase):
    def test_main_with_example_config_runs_to_completion(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        config_path = project_root / "runs" / "health-config.local.example.json"
        self.assertTrue(config_path.exists())
        with patch.object(sys, "argv", ["inspect_health_config", str(config_path)]):
            with self.assertRaises(SystemExit) as exc:
                inspect_health_config.main()
        self.assertEqual(exc.exception.code, 0)
