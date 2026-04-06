import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import k8s_diag_agent.cli as cli
from k8s_diag_agent.cli import main
from k8s_diag_agent.collect.cluster_snapshot import (
    ClusterSnapshot,
    ClusterSnapshotMetadata,
)


class CliSnapshotTest(unittest.TestCase):
    def test_snapshot_writes_json(self) -> None:
        metadata = ClusterSnapshotMetadata(
            cluster_id="demo",
            captured_at=datetime(2026, 4, 5, tzinfo=UTC),
            control_plane_version="1.28.0",
            node_count=1,
        )
        snapshot = ClusterSnapshot(metadata=metadata)
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "snapshot.json"
            with patch("k8s_diag_agent.cli_handlers.list_kube_contexts", return_value=["demo"]), patch(
                "k8s_diag_agent.cli_handlers.collect_cluster_snapshot",
                return_value=snapshot,
            ), patch("builtins.print"):
                exit_code = main(["snapshot", "--context", "demo", "--output", str(output_path)])
            self.assertEqual(exit_code, 0)
            content = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(content["metadata"]["cluster_id"], "demo")

    def test_batch_snapshot_collects_targets(self) -> None:
        metadata = ClusterSnapshotMetadata(
            cluster_id="demo",
            captured_at=datetime(2026, 4, 5, tzinfo=UTC),
            control_plane_version="1.28.0",
            node_count=1,
        )
        snapshot = ClusterSnapshot(metadata=metadata)
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "out"
            config = {
                "output_dir": str(output_dir),
                "targets": [
                    {"context": "alpha"},
                    {"context": "beta"},
                ],
            }
            config_path = Path(tmpdir) / "targets.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with patch("k8s_diag_agent.cli_handlers.list_kube_contexts", return_value=["alpha", "beta"]), patch(
                "k8s_diag_agent.cli_handlers.collect_cluster_snapshot",
                side_effect=lambda ctx: snapshot if ctx == "alpha" else (_ for _ in ()).throw(RuntimeError("boom")),
            ), patch("builtins.print"):
                exit_code = main(["batch-snapshot", "--config", str(config_path)])
            self.assertEqual(exit_code, 0)
            alpha_path = output_dir / "alpha.json"
            self.assertTrue(alpha_path.exists())
            data = json.loads(alpha_path.read_text(encoding="utf-8"))
            self.assertEqual(data["metadata"]["cluster_id"], "demo")

    def test_main_respects_sys_argv_when_no_explicit_arguments(self) -> None:
        metadata = ClusterSnapshotMetadata(
            cluster_id="demo",
            captured_at=datetime(2026, 4, 5, tzinfo=UTC),
            control_plane_version="1.28.0",
            node_count=1,
        )
        snapshot = ClusterSnapshot(metadata=metadata)
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "snapshot.json"
            cli_args = [
                "k8s_diag_agent.cli",
                "snapshot",
                "--context",
                "demo",
                "--output",
                str(output_path),
            ]
            with patch("k8s_diag_agent.cli_handlers.list_kube_contexts", return_value=["demo"]), patch(
                "k8s_diag_agent.cli_handlers.collect_cluster_snapshot",
                return_value=snapshot,
            ), patch("builtins.print"), patch.object(sys, "argv", cli_args):
                exit_code = main()
            self.assertEqual(exit_code, 0)
            data = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(data["metadata"]["cluster_id"], "demo")


class CliConfigFallbackTest(unittest.TestCase):
    @patch("builtins.print")
    def test_batch_snapshot_rejects_example_config(self, printed: Any) -> None:
        with patch.object(cli, "_DEFAULT_BATCH_CONFIG", Path("snapshots/targets.local.test.json")):
            exit_code = main(["batch-snapshot"])
        self.assertNotEqual(exit_code, 0)
        self.assertTrue(
            any("Local config" in args[0] for args, _ in printed.call_args_list),
            "Should print a local config error",
        )

    @patch("builtins.print")
    def test_run_feedback_rejects_example_config(self, printed: Any) -> None:
        with patch.object(cli, "_RUN_CONFIG_DEFAULT", Path("runs/run-config.local.test.json")):
            exit_code = main(["run-feedback"])
        self.assertNotEqual(exit_code, 0)
        self.assertTrue(
            any("Local config" in args[0] for args, _ in printed.call_args_list),
            "Should print a local config error",
        )

    def test_run_feedback_allows_explicit_example_config(self) -> None:
        with patch("builtins.print"), patch(
            "k8s_diag_agent.cli_handlers.run_feedback_loop", return_value=(0, [])
        ) as run_feedback:
            exit_code = main(["run-feedback", "--config", "runs/run-config.local.example.json"])
        self.assertEqual(exit_code, 0)
        run_feedback.assert_called_once()
