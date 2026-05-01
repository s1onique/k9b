"""Regression tests for _build_clusters_and_drilldown_availability."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from k8s_diag_agent.ui.server_read_support import (
    _build_clusters_and_drilldown_availability,
    _build_clusters_from_review,
)


class TestBuildClustersAndDrilldownAvailability(unittest.TestCase):
    """Verify _build_clusters_and_drilldown_availability label matching behavior."""

    def setUp(self) -> None:
        """Create temp directory with drilldowns structure."""
        self.temp_dir = tempfile.mkdtemp()
        self.drilldowns_dir = Path(self.temp_dir) / "health" / "drilldowns"
        self.drilldowns_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_drilldown_artifact(
        self, run_id: str, label: str, timestamp: str = "2024-01-01T00:00:00Z"
    ) -> None:
        """Write a drilldown artifact file."""
        artifact_path = self.drilldowns_dir / f"{run_id}-{label}-diagnostic.json"
        artifact_data = {
            "run_id": run_id,
            "cluster_label": label,
            "timestamp": timestamp,
            "status": "success",
        }
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

    def _build_review(self, labels: list[str]) -> dict[str, object]:
        """Build a review artifact with selected_drilldowns."""
        selected_drilldowns = [
            {
                "label": label,
                "context": f"context for {label}",
                "node_count": 3,
                "warning_event_count": 0,
                "non_running_pod_count": 0,
            }
            for label in labels
        ]
        return {
            "run_id": "test-run",
            "run_label": "test-run",
            "timestamp": "2024-01-01T00:00:00Z",
            "selected_drilldowns": selected_drilldowns,
        }

    def test_hyphenated_cluster_label_resolves_artifact(self) -> None:
        """Hyphenated label 'cluster-prod-a' resolves its drilldown artifact correctly."""
        run_id = "health-run-20260501"
        label = "cluster-prod-a"

        self._write_drilldown_artifact(run_id, label)
        review_data = self._build_review([label])

        clusters, drilldown_availability = _build_clusters_and_drilldown_availability(
            run_id, review_data, Path(self.temp_dir)
        )

        # Verify the cluster with hyphenated label is available
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["label"], label)
        self.assertTrue(clusters[0]["drilldown_available"])
        self.assertIsNotNone(clusters[0]["drilldown_timestamp"])

        # Verify drilldown availability reflects the match
        self.assertEqual(drilldown_availability["total_clusters"], 1)
        self.assertEqual(drilldown_availability["available"], 1)
        self.assertEqual(drilldown_availability["missing"], 0)
        self.assertEqual(drilldown_availability["missing_clusters"], [])

    def test_prefix_collision_prefers_longest_match(self) -> None:
        """Prefix collision: 'cluster' and 'cluster-prod' should not pick wrong artifact."""
        run_id = "health-run-20260501"

        # Create artifacts for both labels
        self._write_drilldown_artifact(run_id, "cluster")
        self._write_drilldown_artifact(run_id, "cluster-prod")

        # Review contains both labels
        review_data = self._build_review(["cluster", "cluster-prod"])

        clusters, drilldown_availability = _build_clusters_and_drilldown_availability(
            run_id, review_data, Path(self.temp_dir)
        )

        # Both clusters should be available and matched to correct artifacts
        self.assertEqual(len(clusters), 2)
        self.assertEqual(drilldown_availability["total_clusters"], 2)
        self.assertEqual(drilldown_availability["available"], 2)
        self.assertEqual(drilldown_availability["missing"], 0)
        self.assertEqual(drilldown_availability["missing_clusters"], [])

        # Check each cluster is matched to its own artifact (not a prefix match)
        cluster_labels = {c["label"]: c for c in clusters}

        # 'cluster-prod' should have its own artifact
        self.assertIn("cluster-prod", cluster_labels)
        self.assertTrue(cluster_labels["cluster-prod"]["drilldown_available"])
        artifact_path = cluster_labels["cluster-prod"]["artifact_paths"]["drilldown"]
        self.assertIsNotNone(artifact_path)
        self.assertIn("cluster-prod", artifact_path)

        # 'cluster' should have its own artifact
        self.assertIn("cluster", cluster_labels)
        self.assertTrue(cluster_labels["cluster"]["drilldown_available"])
        artifact_path = cluster_labels["cluster"]["artifact_paths"]["drilldown"]
        self.assertIsNotNone(artifact_path)
        self.assertIn("cluster-", artifact_path)  # Should be "cluster-" prefix, not "clusterprod-"

    def test_missing_drilldown_reports_available_false(self) -> None:
        """Missing drilldown artifact should report available=false and appear in missing_clusters."""
        run_id = "health-run-20260501"
        label = "cluster-missing"

        # Do NOT create an artifact for this label
        review_data = self._build_review([label])

        clusters, drilldown_availability = _build_clusters_and_drilldown_availability(
            run_id, review_data, Path(self.temp_dir)
        )

        # Verify the cluster is marked as unavailable
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["label"], label)
        self.assertFalse(clusters[0]["drilldown_available"])
        self.assertIsNone(clusters[0]["drilldown_timestamp"])
        self.assertIsNone(clusters[0]["artifact_paths"]["drilldown"])

        # Verify drilldown availability reflects the missing cluster
        self.assertEqual(drilldown_availability["total_clusters"], 1)
        self.assertEqual(drilldown_availability["available"], 0)
        self.assertEqual(drilldown_availability["missing"], 1)
        self.assertEqual(drilldown_availability["missing_clusters"], [label])

        # Verify coverage entry shows unavailable
        self.assertEqual(len(drilldown_availability["coverage"]), 1)
        self.assertFalse(drilldown_availability["coverage"][0]["available"])

    def test_backward_compatible_clusters_only(self) -> None:
        """_build_clusters_from_review should still return only clusters list."""
        run_id = "health-run-20260501"
        label = "cluster-a"

        self._write_drilldown_artifact(run_id, label)
        review_data = self._build_review([label])

        # _build_clusters_from_review is a wrapper that should return only clusters
        clusters = _build_clusters_from_review(
            run_id, review_data, Path(self.temp_dir)
        )

        # Should return a list (not a tuple)
        self.assertIsInstance(clusters, list)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["label"], label)

    def test_multiple_hyphen_labels(self) -> None:
        """Multiple hyphenated labels with different numbers of hyphens."""
        run_id = "health-run-20260501"
        labels = ["cluster-a", "cluster-prod-a", "cluster-prod-a-region1"]

        for label in labels:
            self._write_drilldown_artifact(run_id, label)
        review_data = self._build_review(labels)

        clusters, drilldown_availability = _build_clusters_and_drilldown_availability(
            run_id, review_data, Path(self.temp_dir)
        )

        # All clusters should be available
        self.assertEqual(len(clusters), 3)
        self.assertEqual(drilldown_availability["total_clusters"], 3)
        self.assertEqual(drilldown_availability["available"], 3)
        self.assertEqual(drilldown_availability["missing"], 0)

        # Each should have its own artifact
        cluster_map = {c["label"]: c for c in clusters}
        for label in labels:
            self.assertIn(label, cluster_map)
            self.assertTrue(cluster_map[label]["drilldown_available"])
            self.assertIn(label, cluster_map[label]["artifact_paths"]["drilldown"] or "")

    def test_partial_match_does_not_spoof(self) -> None:
        """Run ID prefix collision should not match unrelated labels."""
        run_id = "health-run"
        wrong_label = "health-run-wrong"  # This looks like it starts with run_id but isn't
        correct_label = "correct-label"

        # Create artifact that looks like it might match but shouldn't
        self._write_drilldown_artifact(run_id, wrong_label)
        self._write_drilldown_artifact(run_id, correct_label)

        # Review only asks for the correct label
        review_data = self._build_review([correct_label])

        clusters, drilldown_availability = _build_clusters_and_drilldown_availability(
            run_id, review_data, Path(self.temp_dir)
        )

        # Only the correct label should match
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["label"], correct_label)
        self.assertTrue(clusters[0]["drilldown_available"])


class TestBuildClustersAndDrilldownAvailabilityEdgeCases(unittest.TestCase):
    """Edge case tests for label extraction."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.drilldowns_dir = Path(self.temp_dir) / "health" / "drilldowns"
        self.drilldowns_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_empty_selected_drilldowns(self) -> None:
        """Empty selected_drilldowns should return empty clusters list."""
        run_id = "health-run-20260501"
        review_data = {
            "run_id": run_id,
            "timestamp": "2024-01-01T00:00:00Z",
            "selected_drilldowns": [],
        }

        clusters, drilldown_availability = _build_clusters_and_drilldown_availability(
            run_id, review_data, Path(self.temp_dir)
        )

        self.assertEqual(clusters, [])
        self.assertEqual(drilldown_availability["total_clusters"], 0)
        self.assertEqual(drilldown_availability["available"], 0)

    def test_missing_selected_drilldowns_key(self) -> None:
        """Missing selected_drilldowns key should be treated as empty."""
        run_id = "health-run-20260501"
        review_data = {
            "run_id": run_id,
            "timestamp": "2024-01-01T00:00:00Z",
        }

        clusters, drilldown_availability = _build_clusters_and_drilldown_availability(
            run_id, review_data, Path(self.temp_dir)
        )

        self.assertEqual(clusters, [])
        self.assertEqual(drilldown_availability["total_clusters"], 0)

    def test_non_list_selected_drilldowns(self) -> None:
        """Non-list selected_drilldowns should be treated as empty."""
        run_id = "health-run-20260501"
        review_data = {
            "run_id": run_id,
            "timestamp": "2024-01-01T00:00:00Z",
            "selected_drilldowns": "not a list",
        }

        clusters, drilldown_availability = _build_clusters_and_drilldown_availability(
            run_id, review_data, Path(self.temp_dir)
        )

        self.assertEqual(clusters, [])
        self.assertEqual(drilldown_availability["total_clusters"], 0)


if __name__ == "__main__":
    unittest.main()
