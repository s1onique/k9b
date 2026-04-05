import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from k8s_diag_agent.cli import main


class CliCompareTest(unittest.TestCase):
    def test_compare_reports_differences(self) -> None:
        snapshot_a = {
            "metadata": {
                "cluster_id": "alpha",
                "captured_at": "2026-04-05T00:00:00Z",
                "control_plane_version": "1.28.0",
                "node_count": 3,
            },
            "workloads": {},
            "metrics": {},
            "helm_releases": [
                {
                    "name": "frontend",
                    "namespace": "default",
                    "chart": "frontend-1.0.0",
                    "chart_version": "1.0.0",
                }
            ],
            "crds": [],
        }
        snapshot_b = {
            "metadata": {
                "cluster_id": "beta",
                "captured_at": "2026-04-05T01:00:00Z",
                "control_plane_version": "1.28.0",
                "node_count": 3,
            },
            "workloads": {},
            "metrics": {},
            "helm_releases": [
                {
                    "name": "frontend",
                    "namespace": "default",
                    "chart": "frontend-1.1.0",
                    "chart_version": "1.1.0",
                }
            ],
            "crds": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path_a = Path(tmpdir) / "a.json"
            path_b = Path(tmpdir) / "b.json"
            path_a.write_text(json.dumps(snapshot_a), encoding="utf-8")
            path_b.write_text(json.dumps(snapshot_b), encoding="utf-8")
            with patch("sys.stdout", new_callable=io.StringIO) as fake_out:
                exit_code = main(["compare", str(path_a), str(path_b)])
            self.assertEqual(exit_code, 0)
            output = fake_out.getvalue().strip()
            differences = json.loads(output)
            self.assertIn("helm_releases", differences)
