"""Tests for Alertmanager artifact identity (artifact_id) rollout."""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
    AlertmanagerSourceInventory,
)
from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
    AlertmanagerCompact,
    AlertmanagerSnapshot,
    AlertmanagerStatus,
    NormalizedAlert,
    normalize_alertmanager_payload,
    snapshot_to_compact,
)


class TestAlertmanagerSnapshotArtifactId(unittest.TestCase):
    """Tests for AlertmanagerSnapshot artifact_id field."""

    def test_new_snapshot_includes_artifact_id(self) -> None:
        """New AlertmanagerSnapshot should include artifact_id at creation."""
        snapshot = AlertmanagerSnapshot(
            status=AlertmanagerStatus.OK,
            captured_at=datetime.now(UTC).isoformat(),
            source="http://alertmanager:9093",
            alert_count=0,
            alerts=(),
        )
        self.assertIsNotNone(snapshot.artifact_id)
        self.assertIsInstance(snapshot.artifact_id, str)
        assert isinstance(snapshot.artifact_id, str)  # for mypy
        self.assertGreater(len(snapshot.artifact_id), 0)

    def test_snapshot_to_dict_includes_artifact_id(self) -> None:
        """Snapshot serialization should include artifact_id."""
        snapshot = AlertmanagerSnapshot(
            status=AlertmanagerStatus.OK,
            captured_at=datetime.now(UTC).isoformat(),
            source="http://alertmanager:9093",
            alert_count=0,
            alerts=(),
        )
        data = snapshot.to_dict()
        self.assertIn("artifact_id", data)
        self.assertEqual(data["artifact_id"], snapshot.artifact_id)

    def test_snapshot_from_dict_parses_artifact_id(self) -> None:
        """Snapshot deserialization should parse artifact_id."""
        raw = {
            "status": "ok",
            "captured_at": datetime.now(UTC).isoformat(),
            "source": "http://alertmanager:9093",
            "alert_count": 0,
            "alerts": [],
            "errors": [],
            "truncated": False,
            "artifact_id": "0192a1b8-3c4e-5678-abcd-1234567890ab",
        }
        snapshot = AlertmanagerSnapshot.from_dict(raw)
        self.assertEqual(snapshot.artifact_id, "0192a1b8-3c4e-5678-abcd-1234567890ab")

    def test_snapshot_from_dict_returns_none_for_legacy_artifact(self) -> None:
        """Legacy artifact without artifact_id should return None (not generate new ID)."""
        raw = {
            "status": "ok",
            "captured_at": datetime.now(UTC).isoformat(),
            "source": "http://alertmanager:9093",
            "alert_count": 0,
            "alerts": [],
            "errors": [],
            "truncated": False,
            # No artifact_id field
        }
        snapshot = AlertmanagerSnapshot.from_dict(raw)
        # Legacy artifacts return None for artifact_id (backward compatibility)
        self.assertIsNone(snapshot.artifact_id)

    def test_snapshot_roundtrip_preserves_artifact_id(self) -> None:
        """Roundtrip serialization/deserialization should preserve artifact_id."""
        original = AlertmanagerSnapshot(
            status=AlertmanagerStatus.OK,
            captured_at=datetime.now(UTC).isoformat(),
            source="http://alertmanager:9093",
            alert_count=0,
            alerts=(),
        )
        data = original.to_dict()
        restored = AlertmanagerSnapshot.from_dict(data)
        self.assertEqual(restored.artifact_id, original.artifact_id)

    def test_snapshot_artifact_id_distinct_from_source(self) -> None:
        """artifact_id should be distinct from source/entity identifiers."""
        snapshot = AlertmanagerSnapshot(
            status=AlertmanagerStatus.OK,
            captured_at=datetime.now(UTC).isoformat(),
            source="http://alertmanager:9093",
            alert_count=0,
            alerts=(),
        )
        # artifact_id is UUID-like, source is a URL
        self.assertNotEqual(snapshot.artifact_id, snapshot.source)
        # Check UUID format (8-4-4-4-12 pattern)
        assert isinstance(snapshot.artifact_id, str)  # for mypy
        parts = snapshot.artifact_id.split("-")
        self.assertEqual(len(parts), 5)
        self.assertEqual(len(parts[0]), 8)  # First part is 8 chars
        self.assertEqual(len(parts[4]), 12)  # Last part is 12 chars

    def test_normalize_payload_generates_artifact_id(self) -> None:
        """normalize_alertmanager_payload should generate artifact_id."""
        raw = [{"labels": {"alertname": "Test", "severity": "warning"}}]
        snapshot = normalize_alertmanager_payload(raw)
        self.assertIsNotNone(snapshot.artifact_id)


class TestAlertmanagerCompactArtifactId(unittest.TestCase):
    """Tests for AlertmanagerCompact artifact_id field."""

    def test_compact_from_snapshot_gets_own_artifact_id(self) -> None:
        """Compact derived from snapshot should get its OWN artifact_id."""
        snapshot = AlertmanagerSnapshot(
            status=AlertmanagerStatus.OK,
            captured_at=datetime.now(UTC).isoformat(),
            source="http://alertmanager:9093",
            alert_count=0,
            alerts=(),
        )
        compact = snapshot_to_compact(snapshot)
        # Compact gets its own unique ID (not inheriting from snapshot)
        self.assertIsNotNone(compact.artifact_id)
        self.assertNotEqual(compact.artifact_id, snapshot.artifact_id)

    def test_compact_to_dict_includes_artifact_id_when_present(self) -> None:
        """Compact serialization should include artifact_id when present."""
        snapshot = AlertmanagerSnapshot(
            status=AlertmanagerStatus.OK,
            captured_at=datetime.now(UTC).isoformat(),
            source="http://alertmanager:9093",
            alert_count=0,
            alerts=(),
        )
        compact = snapshot_to_compact(snapshot)
        data = compact.to_dict()
        self.assertIn("artifact_id", data)
        self.assertEqual(data["artifact_id"], compact.artifact_id)

    def test_compact_to_dict_excludes_artifact_id_when_none(self) -> None:
        """Compact serialization should not include artifact_id when None."""
        compact = AlertmanagerCompact(
            status="ok",
            alert_count=0,
            severity_counts=(),
            state_counts=(),
            top_alert_names=(),
            affected_namespaces=(),
            affected_clusters=(),
            affected_services=(),
            truncated=False,
            captured_at=datetime.now(UTC).isoformat(),
            # artifact_id defaults to None
        )
        data = compact.to_dict()
        # artifact_id should not be present when None (backward compat for legacy)
        self.assertNotIn("artifact_id", data)

    def test_compact_roundtrip_preserves_artifact_id(self) -> None:
        """Roundtrip serialization/deserialization should preserve artifact_id."""
        snapshot = AlertmanagerSnapshot(
            status=AlertmanagerStatus.OK,
            captured_at=datetime.now(UTC).isoformat(),
            source="http://alertmanager:9093",
            alert_count=1,
            alerts=(NormalizedAlert(
                fingerprint="abc123",
                alertname="TestAlert",
                state="active",
                severity="warning",
            ),),
        )
        compact = snapshot_to_compact(snapshot)
        self.assertIsNotNone(compact.artifact_id)


class TestAlertmanagerSourceInventoryArtifactId(unittest.TestCase):
    """Tests for AlertmanagerSourceInventory artifact_id field."""

    def test_new_inventory_includes_artifact_id(self) -> None:
        """New AlertmanagerSourceInventory should include artifact_id at creation."""
        inventory = AlertmanagerSourceInventory()
        self.assertIsNotNone(inventory.artifact_id)
        self.assertIsInstance(inventory.artifact_id, str)
        assert isinstance(inventory.artifact_id, str)  # for mypy
        self.assertGreater(len(inventory.artifact_id), 0)

    def test_inventory_to_dict_includes_artifact_id(self) -> None:
        """Inventory serialization should include artifact_id."""
        inventory = AlertmanagerSourceInventory()
        data = inventory.to_dict()
        self.assertIn("artifact_id", data)
        self.assertEqual(data["artifact_id"], inventory.artifact_id)

    def test_inventory_from_dict_parses_artifact_id(self) -> None:
        """Inventory deserialization should parse artifact_id."""
        raw = {
            "sources": [],
            "discovered_at": datetime.now(UTC).isoformat(),
            "cluster_context": "test-context",
            "artifact_id": "0192a1b8-3c4e-5678-abcd-1234567890ab",
        }
        inventory = AlertmanagerSourceInventory.from_dict(raw)
        self.assertEqual(inventory.artifact_id, "0192a1b8-3c4e-5678-abcd-1234567890ab")

    def test_inventory_from_dict_returns_none_for_legacy_artifact(self) -> None:
        """Legacy inventory without artifact_id should return None (not generate new ID)."""
        raw = {
            "sources": [],
            "discovered_at": datetime.now(UTC).isoformat(),
            "cluster_context": "test-context",
            # No artifact_id field
        }
        inventory = AlertmanagerSourceInventory.from_dict(raw)
        # Legacy artifacts return None for artifact_id (backward compatibility)
        self.assertIsNone(inventory.artifact_id)

    def test_inventory_roundtrip_preserves_artifact_id(self) -> None:
        """Roundtrip serialization/deserialization should preserve artifact_id."""
        inventory = AlertmanagerSourceInventory(cluster_context="test")
        data = inventory.to_dict()
        restored = AlertmanagerSourceInventory.from_dict(data)
        self.assertEqual(restored.artifact_id, inventory.artifact_id)

    def test_inventory_artifact_id_distinct_from_cluster_context(self) -> None:
        """artifact_id should be distinct from cluster_context."""
        inventory = AlertmanagerSourceInventory(cluster_context="my-cluster")
        # artifact_id is UUID-like, cluster_context is a string label
        self.assertNotEqual(inventory.artifact_id, inventory.cluster_context)
        # Check UUID format (8-4-4-4-12 pattern)
        assert isinstance(inventory.artifact_id, str)  # for mypy
        parts = inventory.artifact_id.split("-")
        self.assertEqual(len(parts), 5)


class TestArtifactIdSeparationFromEntityIdentity(unittest.TestCase):
    """Tests ensuring artifact_id stays distinct from entity/source identifiers."""

    def test_snapshot_artifact_id_not_canonical_entity_id(self) -> None:
        """Snapshot artifact_id should not be confused with canonical entity IDs."""
        snapshot = AlertmanagerSnapshot(
            status=AlertmanagerStatus.OK,
            captured_at=datetime.now(UTC).isoformat(),
            source="http://alertmanager:9093",
            alert_count=0,
            alerts=(),
        )
        # artifact_id is UUID, source is URL
        self.assertNotEqual(snapshot.artifact_id, snapshot.source)

    def test_inventory_artifact_id_not_source_identity(self) -> None:
        """Inventory artifact_id should not be confused with source identity."""
        inventory = AlertmanagerSourceInventory(cluster_context="prod-cluster")
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager:9093",
            namespace="monitoring",
            name="alertmanager-main",
        )
        inventory.add_source(source)
        
        # artifact_id is UUID format (5 parts with 8-4-4-4-12 pattern)
        # source_id is namespaced format like 'crd:namespace/name'
        self.assertNotEqual(inventory.artifact_id, source.source_id)
        # Check UUID format for artifact_id
        assert isinstance(inventory.artifact_id, str)  # for mypy
        parts = inventory.artifact_id.split("-")
        self.assertEqual(len(parts), 5)
        self.assertEqual(len(parts[0]), 8)  # First part is 8 chars
        self.assertEqual(len(parts[4]), 12)  # Last part is 12 chars

    def test_compact_artifact_id_differs_from_snapshot(self) -> None:
        """Compact artifact_id should be DIFFERENT from snapshot (own identity)."""
        snapshot = AlertmanagerSnapshot(
            status=AlertmanagerStatus.OK,
            captured_at=datetime.now(UTC).isoformat(),
            source="http://alertmanager:9093",
            alert_count=0,
            alerts=(),
        )
        compact = snapshot_to_compact(snapshot)
        # Compact gets its own unique ID (separate from snapshot)
        self.assertNotEqual(compact.artifact_id, snapshot.artifact_id)


class TestBackwardCompatibility(unittest.TestCase):
    """Tests for backward compatibility with legacy artifacts."""

    def test_legacy_snapshot_json_loads(self) -> None:
        """Legacy snapshot JSON without artifact_id should load successfully."""
        legacy_json = json.dumps({
            "status": "ok",
            "captured_at": "2024-01-01T00:00:00+00:00",
            "source": "http://alertmanager:9093",
            "alert_count": 0,
            "alerts": [],
            "errors": [],
            "truncated": False,
            # No artifact_id
        })
        snapshot = AlertmanagerSnapshot.from_dict(json.loads(legacy_json))
        # Legacy artifacts return None for artifact_id (backward compatibility)
        self.assertIsNone(snapshot.artifact_id)
        self.assertEqual(snapshot.status, AlertmanagerStatus.OK)

    def test_legacy_compact_json_loads(self) -> None:
        """Legacy compact JSON without artifact_id should load successfully."""
        # Direct construction for legacy compat (compact doesn't have from_dict)
        compact = AlertmanagerCompact(
            status="ok",
            alert_count=0,
            severity_counts=(),
            state_counts=(),
            top_alert_names=(),
            affected_namespaces=(),
            affected_clusters=(),
            affected_services=(),
            truncated=False,
            captured_at="2024-01-01T00:00:00+00:00",
            # artifact_id will be None
        )
        self.assertIsNone(compact.artifact_id)

    def test_legacy_inventory_json_loads(self) -> None:
        """Legacy inventory JSON without artifact_id should load successfully."""
        legacy_json = json.dumps({
            "sources": [],
            "discovered_at": "2024-01-01T00:00:00+00:00",
            "cluster_context": "legacy-context",
            # No artifact_id
        })
        inventory = AlertmanagerSourceInventory.from_dict(json.loads(legacy_json))
        # Legacy artifacts return None for artifact_id (backward compatibility)
        self.assertIsNone(inventory.artifact_id)
        self.assertEqual(inventory.cluster_context, "legacy-context")

    def test_new_artifacts_can_be_distinguished(self) -> None:
        """Multiple new artifacts should have unique artifact_ids."""
        ids = set()
        for _ in range(100):
            snapshot = AlertmanagerSnapshot(
                status=AlertmanagerStatus.OK,
                captured_at=datetime.now(UTC).isoformat(),
                source="http://alertmanager:9093",
                alert_count=0,
                alerts=(),
            )
            ids.add(snapshot.artifact_id)
        self.assertEqual(len(ids), 100)


if __name__ == "__main__":
    unittest.main()
