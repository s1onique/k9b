"""Tests for ClusterSnapshot artifact_id field (REM-AI-02)."""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.cluster_snapshot import (
    ClusterSnapshot,
    ClusterSnapshotMetadata,
)


class TestClusterSnapshotArtifactId(unittest.TestCase):
    """Tests for ClusterSnapshot artifact_id field."""

    def _make_minimal_metadata(self) -> ClusterSnapshotMetadata:
        """Create a minimal metadata for testing."""
        return ClusterSnapshotMetadata(
            cluster_id="test-cluster",
            captured_at=datetime.now(UTC),
            control_plane_version="1.28.0",
            node_count=3,
        )

    def test_new_snapshot_with_artifact_id(self) -> None:
        """New ClusterSnapshot with explicit artifact_id should have it."""
        snapshot = ClusterSnapshot(
            metadata=self._make_minimal_metadata(),
            artifact_id="0192a1b8-3c4e-5678-abcd-1234567890ab",
        )
        self.assertEqual(snapshot.artifact_id, "0192a1b8-3c4e-5678-abcd-1234567890ab")

    def test_new_snapshot_without_artifact_id(self) -> None:
        """New ClusterSnapshot without artifact_id should have None (backward compat)."""
        snapshot = ClusterSnapshot(
            metadata=self._make_minimal_metadata(),
        )
        self.assertIsNone(snapshot.artifact_id)

    def test_snapshot_to_dict_includes_artifact_id_when_present(self) -> None:
        """Snapshot serialization should include artifact_id when present."""
        snapshot = ClusterSnapshot(
            metadata=self._make_minimal_metadata(),
            artifact_id="0192a1b8-3c4e-5678-abcd-1234567890ab",
        )
        data = snapshot.to_dict()
        self.assertIn("artifact_id", data)
        self.assertEqual(data["artifact_id"], "0192a1b8-3c4e-5678-abcd-1234567890ab")

    def test_snapshot_to_dict_excludes_artifact_id_when_none(self) -> None:
        """Snapshot serialization should not include artifact_id when None."""
        snapshot = ClusterSnapshot(
            metadata=self._make_minimal_metadata(),
            # artifact_id defaults to None
        )
        data = snapshot.to_dict()
        self.assertNotIn("artifact_id", data)

    def test_snapshot_from_dict_parses_artifact_id(self) -> None:
        """Snapshot deserialization should parse artifact_id."""
        raw = {
            "metadata": {
                "cluster_id": "test-cluster",
                "captured_at": "2024-01-01T00:00:00Z",
                "control_plane_version": "1.28.0",
                "node_count": 3,
            },
            "artifact_id": "0192a1b8-3c4e-5678-abcd-1234567890ab",
        }
        snapshot = ClusterSnapshot.from_dict(raw)
        self.assertEqual(snapshot.artifact_id, "0192a1b8-3c4e-5678-abcd-1234567890ab")

    def test_snapshot_from_dict_returns_none_for_legacy_artifact(self) -> None:
        """Legacy artifact without artifact_id should return None (not generate new ID)."""
        raw = {
            "metadata": {
                "cluster_id": "test-cluster",
                "captured_at": "2024-01-01T00:00:00Z",
                "control_plane_version": "1.28.0",
                "node_count": 3,
            },
            # No artifact_id field
        }
        snapshot = ClusterSnapshot.from_dict(raw)
        # Legacy artifacts return None for artifact_id (backward compatibility)
        self.assertIsNone(snapshot.artifact_id)

    def test_snapshot_roundtrip_preserves_artifact_id(self) -> None:
        """Roundtrip serialization/deserialization should preserve artifact_id."""
        original = ClusterSnapshot(
            metadata=self._make_minimal_metadata(),
            artifact_id="0192a1b8-3c4e-5678-abcd-1234567890ab",
        )
        data = original.to_dict()
        restored = ClusterSnapshot.from_dict(data)
        self.assertEqual(restored.artifact_id, original.artifact_id)

    def test_snapshot_artifact_id_distinct_from_cluster_id(self) -> None:
        """artifact_id should be distinct from cluster_id."""
        snapshot = ClusterSnapshot(
            metadata=self._make_minimal_metadata(),
            artifact_id="0192a1b8-3c4e-5678-abcd-1234567890ab",
        )
        # artifact_id is UUID-like, cluster_id is a string label
        self.assertNotEqual(snapshot.artifact_id, snapshot.metadata.cluster_id)
        # Check UUID format (8-4-4-4-12 pattern)
        assert isinstance(snapshot.artifact_id, str)  # for mypy
        parts = snapshot.artifact_id.split("-")
        self.assertEqual(len(parts), 5)
        self.assertEqual(len(parts[0]), 8)  # First part is 8 chars
        self.assertEqual(len(parts[4]), 12)  # Last part is 12 chars

    def test_legacy_snapshot_json_loads(self) -> None:
        """Legacy snapshot JSON without artifact_id should load successfully."""
        legacy_json = json.dumps({
            "metadata": {
                "cluster_id": "legacy-cluster",
                "captured_at": "2024-01-01T00:00:00Z",
                "control_plane_version": "1.27.0",
                "node_count": 2,
            },
            # No artifact_id
        })
        snapshot = ClusterSnapshot.from_dict(json.loads(legacy_json))
        # Legacy artifacts return None for artifact_id (backward compatibility)
        self.assertIsNone(snapshot.artifact_id)
        self.assertEqual(snapshot.metadata.cluster_id, "legacy-cluster")

    def test_new_artifacts_can_be_distinguished_when_explicit(self) -> None:
        """Multiple new artifacts with explicit artifact_ids should have unique IDs."""
        ids = set()
        for i in range(100):
            snapshot = ClusterSnapshot(
                metadata=self._make_minimal_metadata(),
                artifact_id=f"0192a1b8-3c4e-5678-abcd-{i:012x}",
            )
            ids.add(snapshot.artifact_id)
        # All explicit IDs should be unique
        self.assertEqual(len(ids), 100)

    def test_new_artifacts_without_explicit_id_are_none(self) -> None:
        """New artifacts without explicit artifact_id should have None (backward compat)."""
        for _ in range(100):
            snapshot = ClusterSnapshot(
                metadata=self._make_minimal_metadata(),
            )
            # Default is None for backward compatibility
            self.assertIsNone(snapshot.artifact_id)


class TestBackwardCompatibility(unittest.TestCase):
    """Tests for backward compatibility with legacy artifacts."""

    def test_legacy_snapshot_without_artifact_id_loads(self) -> None:
        """Legacy artifact format should load without artifact_id."""
        raw = {
            "metadata": {
                "cluster_id": "legacy-cluster",
                "captured_at": "2024-01-01T00:00:00Z",
                "control_plane_version": "1.27.0",
                "node_count": 2,
            },
            "workloads": {},
            "metrics": {},
        }
        snapshot = ClusterSnapshot.from_dict(raw)
        self.assertIsNone(snapshot.artifact_id)
        self.assertEqual(snapshot.metadata.cluster_id, "legacy-cluster")

    def test_legacy_snapshot_to_dict_roundtrip(self) -> None:
        """Legacy artifact should roundtrip correctly without artifact_id."""
        raw = {
            "metadata": {
                "cluster_id": "legacy-cluster",
                "captured_at": "2024-01-01T00:00:00Z",
                "control_plane_version": "1.27.0",
                "node_count": 2,
            },
        }
        snapshot = ClusterSnapshot.from_dict(raw)
        self.assertIsNone(snapshot.artifact_id)

        # to_dict should not include artifact_id when None
        data = snapshot.to_dict()
        self.assertNotIn("artifact_id", data)

    def test_new_artifact_with_explicit_id_to_dict(self) -> None:
        """New artifact with explicit artifact_id should include it in to_dict."""
        snapshot = ClusterSnapshot(
            metadata=self._make_minimal_metadata(),
            artifact_id="0192a1b8-3c4e-5678-abcd-1234567890ab",
        )
        data = snapshot.to_dict()
        self.assertIn("artifact_id", data)
        self.assertEqual(data["artifact_id"], "0192a1b8-3c4e-5678-abcd-1234567890ab")

    def _make_minimal_metadata(self) -> ClusterSnapshotMetadata:
        """Create a minimal metadata for testing."""
        return ClusterSnapshotMetadata(
            cluster_id="test-cluster",
            captured_at=datetime.now(UTC),
            control_plane_version="1.28.0",
            node_count=3,
        )


if __name__ == "__main__":
    unittest.main()
