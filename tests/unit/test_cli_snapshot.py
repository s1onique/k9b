import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from k8s_diag_agent.cli import main
from k8s_diag_agent.collect.cluster_snapshot import (
    ClusterSnapshot,
    ClusterSnapshotMetadata,
)
from datetime import datetime, timezone


class CliSnapshotTest(unittest.TestCase):
    def test_snapshot_writes_json(self) -> None:
        metadata = ClusterSnapshotMetadata(
            cluster_id="demo",
            captured_at=datetime(2026, 4, 5, tzinfo=timezone.utc),
            control_plane_version="1.28.0",
            node_count=1,
        )
        snapshot = ClusterSnapshot(metadata=metadata)
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "snapshot.json"
            with patch("k8s_diag_agent.cli.list_kube_contexts", return_value=["demo"]), patch(
                "k8s_diag_agent.cli.collect_cluster_snapshot",
                return_value=snapshot,
            ), patch("builtins.print"):
                exit_code = main(["snapshot", "--context", "demo", "--output", str(output_path)])
            self.assertEqual(exit_code, 0)
            content = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(content["metadata"]["cluster_id"], "demo")

    def test_batch_snapshot_collects_targets(self) -> None:
        metadata = ClusterSnapshotMetadata(
            cluster_id="demo",
            captured_at=datetime(2026, 4, 5, tzinfo=timezone.utc),
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
            with patch("k8s_diag_agent.cli.list_kube_contexts", return_value=["alpha", "beta"]), patch(
                "k8s_diag_agent.cli.collect_cluster_snapshot",
                side_effect=lambda ctx: snapshot if ctx == "alpha" else (_ for _ in ()).throw(RuntimeError("boom")),
            ), patch("builtins.print"):
                exit_code = main(["batch-snapshot", "--config", str(config_path)])
            self.assertEqual(exit_code, 0)
            alpha_path = output_dir / "alpha.json"
            self.assertTrue(alpha_path.exists())
            data = json.loads(alpha_path.read_text(encoding="utf-8"))
            self.assertEqual(data["metadata"]["cluster_id"], "demo")
