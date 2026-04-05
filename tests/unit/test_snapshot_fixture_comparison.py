import json
import unittest
from pathlib import Path

from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot
from k8s_diag_agent.compare.two_cluster import compare_snapshots


class SnapshotFixtureComparisonTest(unittest.TestCase):
    def test_sanitized_fixture_matches_expected_diff(self) -> None:
        base_path = Path(__file__).resolve().parents[1] / "fixtures"
        primary_path = base_path / "snapshots" / "sanitized-alpha.json"
        diff_path = base_path / "comparisons" / "sanitized-alpha-vs-beta.json"
        primary_data = json.loads(primary_path.read_text(encoding="utf-8"))
        primary_snapshot = ClusterSnapshot.from_dict(primary_data)

        secondary_data = json.loads(primary_path.read_text(encoding="utf-8"))
        secondary_data["metadata"]["node_count"] = 4
        secondary_data["metadata"]["pod_count"] = 61
        secondary_data["helm_releases"][0]["chart_version"] = "2.2.0"
        secondary_data["helm_releases"][0]["chart"] = "payments-2.2.0"
        secondary_data["helm_releases"][0]["app_version"] = "2.2.0"
        secondary_data["crds"] = [
            {
                "name": "widgets.example.com",
                "served_versions": ["v1"],
                "storage_version": "v1",
            }
        ]
        secondary_snapshot = ClusterSnapshot.from_dict(secondary_data)

        comparison = compare_snapshots(primary_snapshot, secondary_snapshot)
        expected = json.loads(diff_path.read_text(encoding="utf-8"))["differences"]
        self.assertEqual(comparison.differences, expected)
