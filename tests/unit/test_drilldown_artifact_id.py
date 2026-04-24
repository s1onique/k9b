"""Tests for DrilldownArtifact artifact_id support."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.health.drilldown import DrilldownArtifact
from k8s_diag_agent.identity.artifact import new_artifact_id


def _make_drilldown_artifact(
    run_id: str = "test-run",
    label: str = "test-cluster",
    artifact_id: str | None = None,
) -> DrilldownArtifact:
    """Create a test DrilldownArtifact with optional artifact_id."""
    timestamp = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    return DrilldownArtifact(
        run_label="test-run",
        run_id=run_id,
        timestamp=timestamp,
        snapshot_timestamp=timestamp,
        context="test-context",
        label=label,
        cluster_id="test-cluster-id",
        trigger_reasons=("warning_event_threshold",),
        missing_evidence=(),
        evidence_summary={"warning_events": 5},
        affected_namespaces=("default",),
        affected_workloads=(),
        warning_events=(),
        non_running_pods=(),
        pod_descriptions={},
        rollout_status=(),
        collection_timestamps={"warning_events": timestamp.isoformat()},
        artifact_id=artifact_id,
    )


class TestDrilldownArtifactId(unittest.TestCase):
    """Tests for DrilldownArtifact artifact_id support."""

    def test_new_artifact_has_artifact_id(self) -> None:
        """New drilldown artifacts should have artifact_id when created with it."""
        aid = new_artifact_id()
        artifact = _make_drilldown_artifact(artifact_id=aid)
        self.assertIsNotNone(artifact.artifact_id)
        self.assertEqual(artifact.artifact_id, aid)

    def test_legacy_artifact_has_none_artifact_id(self) -> None:
        """Legacy drilldown artifacts without artifact_id should have None."""
        artifact = _make_drilldown_artifact()  # No artifact_id
        self.assertIsNone(artifact.artifact_id)

    def test_serialization_includes_artifact_id(self) -> None:
        """Serialized drilldown artifact should include artifact_id when present."""
        aid = new_artifact_id()
        artifact = _make_drilldown_artifact(artifact_id=aid)
        data = artifact.to_dict()
        self.assertIn("artifact_id", data)
        self.assertEqual(data["artifact_id"], aid)

    def test_serialization_excludes_none_artifact_id(self) -> None:
        """Serialized drilldown artifact should not include artifact_id when None (backward compat)."""
        artifact = _make_drilldown_artifact()  # No artifact_id
        data = artifact.to_dict()
        # artifact_id should not be in the dict when None (backward compatibility)
        self.assertNotIn("artifact_id", data)

    def test_deserialization_parses_artifact_id(self) -> None:
        """Deserialized drilldown artifact should parse artifact_id correctly."""
        aid = new_artifact_id()
        artifact = _make_drilldown_artifact(artifact_id=aid)
        data = artifact.to_dict()
        parsed = DrilldownArtifact.from_dict(data)
        self.assertEqual(parsed.artifact_id, aid)

    def test_deserialization_handles_missing_artifact_id(self) -> None:
        """Deserialization should handle legacy artifacts without artifact_id."""
        artifact = _make_drilldown_artifact()  # No artifact_id
        data = artifact.to_dict()
        # Ensure no artifact_id in raw data
        self.assertNotIn("artifact_id", data)
        # Should parse successfully
        parsed = DrilldownArtifact.from_dict(data)
        self.assertIsNone(parsed.artifact_id)

    def test_roundtrip_preserves_artifact_id(self) -> None:
        """Roundtrip (to_dict -> from_dict) should preserve artifact_id."""
        aid = new_artifact_id()
        original = _make_drilldown_artifact(artifact_id=aid)
        data = original.to_dict()
        restored = DrilldownArtifact.from_dict(data)
        self.assertEqual(restored.artifact_id, original.artifact_id)
        self.assertEqual(restored.artifact_id, aid)

    def test_roundtrip_preserves_none_artifact_id(self) -> None:
        """Roundtrip should preserve None artifact_id for legacy artifacts."""
        original = _make_drilldown_artifact()  # No artifact_id
        data = original.to_dict()
        restored = DrilldownArtifact.from_dict(data)
        self.assertIsNone(restored.artifact_id)

    def test_artifact_id_distinct_from_run_id(self) -> None:
        """artifact_id should be distinct from run_id - different concepts."""
        aid = new_artifact_id()
        artifact = _make_drilldown_artifact(run_id="distinct-run-id", artifact_id=aid)
        # Different strings
        self.assertNotEqual(artifact.artifact_id, artifact.run_id)
        # Both are non-empty
        self.assertIsNotNone(artifact.artifact_id)
        self.assertTrue(len(artifact.run_id) > 0)

    def test_artifact_id_uuid_format(self) -> None:
        """artifact_id should be in UUID-like format (8-4-4-4-12)."""
        aid = new_artifact_id()
        artifact = _make_drilldown_artifact(artifact_id=aid)
        self.assertIsNotNone(artifact.artifact_id)
        assert artifact.artifact_id is not None
        aid_str = artifact.artifact_id
        parts = aid_str.split("-")
        self.assertEqual(len(parts), 5)
        self.assertEqual(len(parts[0]), 8)
        self.assertEqual(len(parts[1]), 4)
        self.assertEqual(len(parts[2]), 4)
        self.assertEqual(len(parts[3]), 4)
        self.assertEqual(len(parts[4]), 12)

    def test_unique_artifact_ids(self) -> None:
        """Multiple artifacts should get unique artifact_ids."""
        ids = {new_artifact_id() for _ in range(10)}
        self.assertEqual(len(ids), 10)

    def test_artifact_id_is_immutable(self) -> None:
        """artifact_id should be immutable once set."""
        aid = new_artifact_id()
        artifact = _make_drilldown_artifact(artifact_id=aid)
        # Frozen dataclass - should not be modifiable
        with self.assertRaises((TypeError, AttributeError)):
            artifact.artifact_id = "new-id"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
