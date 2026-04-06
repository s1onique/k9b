import unittest

from k8s_diag_agent.collect.cluster_snapshot import (
    ClusterSnapshot,
    CRDRecord,
    extract_cluster_snapshots,
)
from k8s_diag_agent.compare.two_cluster import compare_snapshots


class ClusterSnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.primary_data = {
            "metadata": {
                "cluster_id": "alpha",
                "captured_at": "2026-04-05T17:00:00Z",
                "control_plane_version": "1.28.0",
                "node_count": 3,
                "pod_count": 120,
                "region": "us-west-2",
                "labels": {"env": "staging"},
            },
            "workloads": {"deployments": {"frontend": {"replicas": 3}}},
            "metrics": {"cpu_usage": 55.2, "memory_usage": "2048"},
            "helm_releases": [
                {
                    "name": "frontend",
                    "namespace": "default",
                    "chart": "frontend-1.0.0",
                    "chart_version": "1.0.0",
                    "app_version": "2.1.0",
                }
            ],
            "crds": [
                {
                    "name": "widgets.example.com",
                    "served_versions": ["v1"],
                    "storage_version": "v1",
                }
            ],
        }
        self.secondary_data = {
            "metadata": {
                "cluster_id": "beta",
                "captured_at": "2026-04-05T17:03:00Z",
                "control_plane_version": "1.28.0",
                "node_count": 4,
                "pod_count": 118,
                "region": "us-west-2",
                "labels": {"env": "production"},
            },
            "workloads": {"deployments": {"frontend": {"replicas": 4}}},
            "metrics": {"cpu_usage": 60, "memory_usage": 2080},
            "helm_releases": [
                {
                    "name": "frontend",
                    "namespace": "default",
                    "chart": "frontend-1.1.0",
                    "chart_version": "1.1.0",
                    "app_version": "2.2.0",
                }
            ],
            "crds": [
                {
                    "name": "events.example.com",
                    "served_versions": ["v1", "v1beta1"],
                    "storage_version": "v1",
                }
            ],
        }

    def test_snapshot_from_dict(self) -> None:
        snapshot = ClusterSnapshot.from_dict(self.primary_data)
        self.assertEqual(snapshot.metadata.cluster_id, "alpha")
        self.assertEqual(snapshot.metrics["cpu_usage"], 55.2)
        self.assertEqual(snapshot.metadata.labels["env"], "staging")

    def test_extract_cluster_snapshots_handles_dict_and_list(self) -> None:
        fixture = {
            "cluster_snapshots": {
                "primary": self.primary_data,
                "secondary": self.secondary_data,
            }
        }
        snapshots = extract_cluster_snapshots(fixture)
        self.assertEqual(len(snapshots), 2)
        fixture_list = {"cluster_snapshots": [self.primary_data]}
        snapshots = extract_cluster_snapshots(fixture_list)
        self.assertEqual(len(snapshots), 1)

    def test_compare_snapshots_reports_differences(self) -> None:
        primary_snapshot = ClusterSnapshot.from_dict(self.primary_data)
        secondary_snapshot = ClusterSnapshot.from_dict(self.secondary_data)
        comparison = compare_snapshots(primary_snapshot, secondary_snapshot)
        self.assertIn("metadata", comparison.differences)
        self.assertIn("node_count", comparison.differences["metadata"])
        self.assertIn("metrics", comparison.differences)
        self.assertIn("cpu_usage", comparison.differences["metrics"])

    def test_snapshot_parses_helm_and_crds(self) -> None:
        snapshot = ClusterSnapshot.from_dict(self.primary_data)
        self.assertIn("default/frontend", snapshot.helm_releases)
        release = snapshot.helm_releases["default/frontend"]
        self.assertEqual(release.chart_version, "1.0.0")
        self.assertEqual(release.app_version, "2.1.0")
        self.assertIn("widgets.example.com", snapshot.crds)
        crd = snapshot.crds["widgets.example.com"]
        self.assertIsInstance(crd, CRDRecord)
        self.assertEqual(crd.served_versions, ("v1",))


if __name__ == "__main__":
    unittest.main()
