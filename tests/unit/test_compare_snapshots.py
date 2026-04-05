import unittest

from datetime import datetime, timezone

from k8s_diag_agent.collect.cluster_snapshot import (
    ClusterSnapshot,
    ClusterSnapshotMetadata,
    CRDRecord,
    HelmReleaseRecord,
)
from k8s_diag_agent.compare.two_cluster import compare_snapshots


class CompareSnapshotsTest(unittest.TestCase):
    def setUp(self) -> None:
        metadata = ClusterSnapshotMetadata(
            cluster_id="alpha",
            captured_at=datetime(2026, 4, 5, 0, 0, tzinfo=timezone.utc),
            control_plane_version="1.28.0",
            node_count=3,
            pod_count=120,
        )
        self.primary = ClusterSnapshot(
            metadata=metadata,
            workloads={},
            metrics={},
            helm_releases={
                "default/frontend": HelmReleaseRecord(
                    name="frontend",
                    namespace="default",
                    chart="frontend-1.0.0",
                    chart_version="1.0.0",
                    app_version="2.1.0",
                )
            },
            crds={
                "widgets.example.com": CRDRecord(
                    name="widgets.example.com",
                    served_versions=("v1", "v1beta1"),
                    storage_version="v1",
                )
            },
        )
        self.secondary = ClusterSnapshot(
            metadata=metadata,
            workloads={},
            metrics={},
            helm_releases={
                "default/frontend": HelmReleaseRecord(
                    name="frontend",
                    namespace="default",
                    chart="frontend-1.1.0",
                    chart_version="1.1.0",
                    app_version="2.2.0",
                )
            },
            crds={
                "widgets.example.com": CRDRecord(
                    name="widgets.example.com",
                    served_versions=("v1",),
                    storage_version="v1",
                )
            },
        )

    def test_comparison_includes_helm_and_crd_diffs(self) -> None:
        comparison = compare_snapshots(self.primary, self.secondary)
        self.assertIn("helm_releases", comparison.differences)
        helm_diff = comparison.differences["helm_releases"]
        self.assertIn("default/frontend", helm_diff)
        self.assertEqual(
            helm_diff["default/frontend"]["primary"]["chart_version"], "1.0.0"
        )
        self.assertEqual(
            helm_diff["default/frontend"]["secondary"]["chart_version"], "1.1.0"
        )
        self.assertIn("crds", comparison.differences)
        crd_diff = comparison.differences["crds"]
        self.assertIn("widgets.example.com", crd_diff)
        self.assertEqual(crd_diff["widgets.example.com"]["primary"]["served_versions"], ["v1", "v1beta1"])
        self.assertEqual(crd_diff["widgets.example.com"]["secondary"]["served_versions"], ["v1"])


if __name__ == "__main__":
    unittest.main()
