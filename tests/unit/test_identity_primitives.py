"""Tests for identity primitives (cluster_uid, artifact_id, entity IDs)."""

from __future__ import annotations

import unittest

from k8s_diag_agent.identity.artifact import new_artifact_id
from k8s_diag_agent.identity.cluster import derive_cluster_uid, get_cluster_uid_from_snapshot
from k8s_diag_agent.identity.entity import build_deterministic_entity_id
from k8s_diag_agent.identity.k8s_object import K8sObjectRef, build_k8s_object_ref, parse_k8s_object_ref


class TestArtifactId(unittest.TestCase):
    """Tests for artifact_id generation (UUIDv7)."""

    def test_new_artifact_id_returns_string(self) -> None:
        """artifact_id should be a non-empty string."""
        aid = new_artifact_id()
        self.assertIsInstance(aid, str)
        self.assertGreater(len(aid), 0)

    def test_new_artifact_id_unique(self) -> None:
        """Multiple artifact_ids should be unique."""
        ids = {new_artifact_id() for _ in range(100)}
        self.assertEqual(len(ids), 100)

    def test_new_artifact_id_format(self) -> None:
        """artifact_id should be UUID-like format."""
        aid = new_artifact_id()
        # UUID format: 8-4-4-4-12 hex chars
        parts = aid.split("-")
        self.assertEqual(len(parts), 5)
        self.assertEqual(len(parts[0]), 8)
        self.assertEqual(len(parts[1]), 4)
        self.assertEqual(len(parts[2]), 4)
        self.assertEqual(len(parts[3]), 4)
        self.assertEqual(len(parts[4]), 12)


class TestClusterUid(unittest.TestCase):
    """Tests for cluster_uid derivation."""

    def test_derive_cluster_uid_returns_none_or_uid(self) -> None:
        """derive_cluster_uid returns None when kubectl unavailable or UID when available.
        
        IMPORTANT: canonical identity is ONLY the real kube-system namespace UID.
        No synthetic fallbacks are used.
        """
        uid = derive_cluster_uid(kube_context=None, cluster_label="test-cluster")
        # Returns None when kubectl unavailable OR a real UID when available
        # No synthetic fallbacks like "legacy:cluster_label" or "unknown"
        self.assertTrue(
            uid is None or 
            (isinstance(uid, str) and len(uid) == 36 and uid.count("-") == 4)
        )

    def test_derive_cluster_uid_returns_uid(self) -> None:
        """derive_cluster_uid returns str when kubectl succeeds or None on failure."""
        uid = derive_cluster_uid(kube_context=None)
        # Either returns a real UID or None
        self.assertTrue(uid is None or isinstance(uid, str))

    def test_get_cluster_uid_from_snapshot_with_existing(self) -> None:
        """Should use existing cluster_uid in snapshot."""
        snapshot = {
            "cluster_uid": "existing-uid-123",
            "cluster_label": "test",
        }
        uid = get_cluster_uid_from_snapshot(snapshot)
        self.assertEqual(uid, "existing-uid-123")

    def test_get_cluster_uid_from_snapshot_derives_when_missing(self) -> None:
        """Should return None when cluster_uid is not in snapshot.
        
        IMPORTANT: cluster_uid is ONLY the kube-system namespace UID.
        Do NOT fall back to cluster_id (a display field) for canonical identity.
        """
        snapshot = {
            "cluster_label": "test-cluster",
        }
        uid = get_cluster_uid_from_snapshot(snapshot)
        # cluster_uid returns None when not available - no synthetic fallbacks
        self.assertIsNone(uid)


class TestDeterministicEntityId(unittest.TestCase):
    """Tests for deterministic entity ID generation."""

    def test_same_facts_produce_same_id(self) -> None:
        """Identical facts should produce identical IDs."""
        facts = {"namespace": "monitoring", "name": "alertmanager-main"}
        id1 = build_deterministic_entity_id("alertmanager-source", facts)
        id2 = build_deterministic_entity_id("alertmanager-source", facts)
        self.assertEqual(id1, id2)

    def test_different_facts_produce_different_ids(self) -> None:
        """Different facts should produce different IDs."""
        facts1 = {"namespace": "monitoring", "name": "alertmanager-main"}
        facts2 = {"namespace": "monitoring", "name": "alertmanager-alt"}
        id1 = build_deterministic_entity_id("alertmanager-source", facts1)
        id2 = build_deterministic_entity_id("alertmanager-source", facts2)
        self.assertNotEqual(id1, id2)

    def test_different_entity_types_produce_different_ids(self) -> None:
        """Different entity types should produce different IDs even with same facts."""
        facts = {"namespace": "monitoring", "name": "alertmanager-main"}
        id1 = build_deterministic_entity_id("alertmanager-source", facts)
        id2 = build_deterministic_entity_id("prometheus-source", facts)
        self.assertNotEqual(id1, id2)

    def test_deterministic_id_format(self) -> None:
        """Deterministic ID should be hex string of fixed length."""
        facts = {"namespace": "monitoring", "name": "alertmanager-main"}
        entity_id = build_deterministic_entity_id("alertmanager-source", facts)
        self.assertIsInstance(entity_id, str)
        self.assertEqual(len(entity_id), 32)  # 32 hex chars = 128 bits

    def test_idempotent_key_order(self) -> None:
        """Different key order should produce same ID."""
        facts1 = {"namespace": "monitoring", "name": "alertmanager-main"}
        facts2 = {"name": "alertmanager-main", "namespace": "monitoring"}
        id1 = build_deterministic_entity_id("alertmanager-source", facts1)
        id2 = build_deterministic_entity_id("alertmanager-source", facts2)
        self.assertEqual(id1, id2)

    def test_none_values_ignored(self) -> None:
        """None values should not affect ID generation."""
        facts1 = {"namespace": "monitoring", "name": "alertmanager-main", "extra": None}
        facts2 = {"namespace": "monitoring", "name": "alertmanager-main"}
        id1 = build_deterministic_entity_id("alertmanager-source", facts1)
        id2 = build_deterministic_entity_id("alertmanager-source", facts2)
        self.assertEqual(id1, id2)


class TestK8sObjectRef(unittest.TestCase):
    """Tests for Kubernetes object references."""

    def test_build_k8s_object_ref_basic(self) -> None:
        """Should create valid K8sObjectRef."""
        ref = build_k8s_object_ref(
            namespace="default",
            kind="Pod",
            name="my-pod",
        )
        self.assertIsInstance(ref, K8sObjectRef)
        self.assertEqual(ref.namespace, "default")
        self.assertEqual(ref.kind, "Pod")
        self.assertEqual(ref.name, "my-pod")
        self.assertIsNone(ref.object_uid)

    def test_build_k8s_object_ref_with_uid(self) -> None:
        """Should include object_uid when provided."""
        ref = build_k8s_object_ref(
            namespace="default",
            kind="Pod",
            name="my-pod",
            object_uid="abc-123-def",
        )
        self.assertEqual(ref.object_uid, "abc-123-def")

    def test_build_k8s_object_ref_cluster_scoped(self) -> None:
        """Should handle cluster-scoped resources (no namespace)."""
        ref = build_k8s_object_ref(
            namespace=None,
            kind="Node",
            name="node-1",
        )
        self.assertIsNone(ref.namespace)
        self.assertEqual(ref.kind, "Node")

    def test_api_version_property(self) -> None:
        """Should produce correct API version string."""
        ref = build_k8s_object_ref(
            namespace="default",
            kind="Pod",
            name="my-pod",
        )
        self.assertEqual(ref.api_version, "default/Pod/my-pod")

    def test_api_version_cluster_scoped(self) -> None:
        """Should produce correct API version for cluster-scoped resources."""
        ref = build_k8s_object_ref(
            namespace=None,
            kind="Node",
            name="node-1",
        )
        self.assertEqual(ref.api_version, "Node/node-1")

    def test_to_dict_roundtrip(self) -> None:
        """Should serialize and deserialize correctly."""
        ref = build_k8s_object_ref(
            namespace="default",
            kind="Pod",
            name="my-pod",
            object_uid="abc-123",
        )
        data = ref.to_dict()
        self.assertEqual(data["namespace"], "default")
        self.assertEqual(data["kind"], "Pod")
        self.assertEqual(data["name"], "my-pod")
        self.assertEqual(data["object_uid"], "abc-123")

    def test_parse_k8s_object_ref(self) -> None:
        """Should parse from dict."""
        data = {
            "namespace": "default",
            "kind": "Pod",
            "name": "my-pod",
            "object_uid": "abc-123",
        }
        ref = parse_k8s_object_ref(data)
        self.assertIsNotNone(ref)
        assert ref is not None
        self.assertEqual(ref.namespace, "default")
        self.assertEqual(ref.object_uid, "abc-123")

    def test_parse_k8s_object_ref_missing_kind(self) -> None:
        """Should return None when kind is missing."""
        data = {"namespace": "default", "name": "my-pod"}
        ref = parse_k8s_object_ref(data)
        self.assertIsNone(ref)

    def test_parse_k8s_object_ref_missing_name(self) -> None:
        """Should return None when name is missing."""
        data = {"namespace": "default", "kind": "Pod"}
        ref = parse_k8s_object_ref(data)
        self.assertIsNone(ref)


class TestAlertmanagerSourceCanonicalId(unittest.TestCase):
    """Tests for Alertmanager source canonical identity invariants."""

    def test_alertmanager_same_source_different_discoveries(self) -> None:
        """Same Alertmanager source discovered multiple times should have same canonical ID."""
        # Facts that define an Alertmanager source
        facts1 = {"namespace": "monitoring", "name": "alertmanager-main"}
        facts2 = {"namespace": "monitoring", "name": "alertmanager-main"}

        id1 = build_deterministic_entity_id("alertmanager-source", facts1)
        id2 = build_deterministic_entity_id("alertmanager-source", facts2)

        self.assertEqual(id1, id2, "Same Alertmanager source should have same canonical ID")

    def test_alertmanager_different_sources(self) -> None:
        """Different Alertmanager sources should have different canonical IDs."""
        facts1 = {"namespace": "monitoring", "name": "alertmanager-main"}
        facts2 = {"namespace": "monitoring", "name": "alertmanager-alt"}

        id1 = build_deterministic_entity_id("alertmanager-source", facts1)
        id2 = build_deterministic_entity_id("alertmanager-source", facts2)

        self.assertNotEqual(id1, id2, "Different sources should have different IDs")


if __name__ == "__main__":
    unittest.main()
