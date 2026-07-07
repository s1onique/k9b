"""Tests for identity primitives (cluster_uid, artifact_id, entity IDs)."""

from __future__ import annotations

import unittest

import pytest

from k8s_diag_agent.identity.artifact import new_artifact_id
from k8s_diag_agent.identity.cluster import derive_cluster_uid, get_cluster_uid_from_snapshot
from k8s_diag_agent.identity.entity import build_deterministic_entity_id
from k8s_diag_agent.identity.k8s_object import build_k8s_object_ref, parse_k8s_object_ref
from tests.unit.k8s_fake_client import FakeKubernetesReadClient


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


class TestClusterUid:
    """Tests for cluster_uid derivation.

    Architecture note:
        After ACT-K9B-K8S-CLIENT-TEST-HARNESS-UPDATE01, these tests mock
        get_cached_kubernetes_client() instead of run_kubectl since production
        code now uses the Kubernetes Python client boundary.

    Note: These are pytest-style classes (not unittest.TestCase) to support
    the monkeypatch fixture for k8s client mocking.
    """

    def test_derive_cluster_uid_returns_none_or_uid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """derive_cluster_uid returns None when cluster unavailable or UID when available.

        IMPORTANT: canonical identity is ONLY the real kube-system namespace UID.
        No synthetic fallbacks are used.
        """
        # Mock k8s client to raise error (simulating cluster unavailable)
        fake_client = FakeKubernetesReadClient()
        # Default behavior already returns None for namespace uid

        monkeypatch.setattr(
            "k8s_diag_agent.identity.cluster.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        uid = derive_cluster_uid(kube_context=None, cluster_label="test-cluster")
        # Returns None when cluster unavailable OR a real UID when available
        # No synthetic fallbacks like "legacy:cluster_label" or "unknown"
        assert uid is None or (
            isinstance(uid, str) and len(uid) == 36 and uid.count("-") == 4
        )

    def test_derive_cluster_uid_returns_uid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """derive_cluster_uid returns str when cluster succeeds or None on failure."""
        # Mock k8s client to return a UID
        fake_client = FakeKubernetesReadClient.with_namespace_uid(
            namespace="kube-system",
            uid="550e8400-e29b-41d4-a716-446655440000",
        )

        monkeypatch.setattr(
            "k8s_diag_agent.identity.cluster.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        uid = derive_cluster_uid(kube_context=None)
        # Returns the real UID from kube-system namespace
        assert uid == "550e8400-e29b-41d4-a716-446655440000"

    def test_derive_cluster_uid_returns_none_when_client_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """derive_cluster_uid returns None when k8s client fails."""
        from k8s_diag_agent.security.kubernetes_client_errors import KubernetesClientUnavailableError

        class FailingFakeClient(FakeKubernetesReadClient):
            def read_namespace_uid(self, name: str) -> str | None:
                raise KubernetesClientUnavailableError("Cluster unavailable")

        fake_client = FailingFakeClient()

        monkeypatch.setattr(
            "k8s_diag_agent.identity.cluster.get_cached_kubernetes_client",
            lambda **kwargs: fake_client,
        )

        uid = derive_cluster_uid(kube_context=None)
        assert uid is None


class TestClusterUidFromSnapshot:
    """Tests for get_cluster_uid_from_snapshot (no mocking needed)."""

    def test_get_cluster_uid_from_snapshot_with_existing(self) -> None:
        """Should use existing cluster_uid in snapshot."""
        snapshot = {
            "cluster_uid": "existing-uid-123",
            "cluster_label": "test",
        }
        uid = get_cluster_uid_from_snapshot(snapshot)
        assert uid == "existing-uid-123"

    def test_get_cluster_uid_from_snapshot_with_metadata(self) -> None:
        """Should use cluster_uid from nested metadata structure."""
        snapshot = {
            "metadata": {
                "cluster_uid": "metadata-uid-456",
            },
        }
        uid = get_cluster_uid_from_snapshot(snapshot)
        assert uid == "metadata-uid-456"

    def test_get_cluster_uid_from_snapshot_without_uid(self) -> None:
        """Should return None when no cluster_uid in snapshot."""
        snapshot = {
            "cluster_label": "test",
        }
        uid = get_cluster_uid_from_snapshot(snapshot)
        assert uid is None

    def test_get_cluster_uid_from_empty_snapshot(self) -> None:
        """Should return None for empty snapshot."""
        uid = get_cluster_uid_from_snapshot({})
        assert uid is None

    def test_get_cluster_uid_from_snapshot_prefers_top_level(self) -> None:
        """Should prefer top-level cluster_uid over metadata cluster_uid."""
        snapshot = {
            "cluster_uid": "top-level-uid",
            "metadata": {
                "cluster_uid": "metadata-uid",
            },
        }
        uid = get_cluster_uid_from_snapshot(snapshot)
        assert uid == "top-level-uid"


class TestEntityId:
    """Tests for entity ID generation.

    Tests cover the identity contract invariants from entity.py:
    - Same entity rediscovered → same canonical_entity_id
    - Entity with different facts → different canonical_entity_id
    - Key order doesn't matter (sorted internally)
    - None values are skipped
    - Returns fixed-length (32 chars) hex string
    """

    def test_build_deterministic_entity_id_returns_string(self) -> None:
        """entity_id should be a non-empty string."""
        eid = build_deterministic_entity_id("test-entity", {"namespace": "test-ns", "name": "test-name"})
        assert isinstance(eid, str)
        assert len(eid) > 0

    def test_build_deterministic_entity_id_fixed_length(self) -> None:
        """entity_id should be exactly 32 characters (first 32 of SHA-256 hex)."""
        eid = build_deterministic_entity_id("test-entity", {"namespace": "ns", "name": "name"})
        assert len(eid) == 32, f"Expected 32 chars, got {len(eid)}"
        assert all(c in "0123456789abcdef" for c in eid), "Should be lowercase hex"

    def test_build_deterministic_entity_id_deterministic(self) -> None:
        """Same inputs should produce same entity_id (idempotence)."""
        eid1 = build_deterministic_entity_id("test-entity", {"namespace": "ns", "name": "name"})
        eid2 = build_deterministic_entity_id("test-entity", {"namespace": "ns", "name": "name"})
        assert eid1 == eid2

    def test_build_deterministic_entity_id_key_order_independent(self) -> None:
        """Key order should not affect the ID (keys are sorted internally)."""
        eid1 = build_deterministic_entity_id("test-entity", {"namespace": "ns", "name": "name"})
        eid2 = build_deterministic_entity_id("test-entity", {"name": "name", "namespace": "ns"})
        assert eid1 == eid2, "Same facts in different key order should produce same ID"

    def test_build_deterministic_entity_id_none_values_skipped(self) -> None:
        """None values should be skipped in ID generation."""
        eid1 = build_deterministic_entity_id("test-entity", {"namespace": "ns", "name": "name", "extra": None})
        eid2 = build_deterministic_entity_id("test-entity", {"namespace": "ns", "name": "name"})
        assert eid1 == eid2, "None values should not affect the ID"

    def test_build_deterministic_entity_id_different_inputs(self) -> None:
        """Different inputs should produce different entity_ids."""
        eid1 = build_deterministic_entity_id("test-entity", {"namespace": "ns1", "name": "name1"})
        eid2 = build_deterministic_entity_id("test-entity", {"namespace": "ns2", "name": "name2"})
        assert eid1 != eid2

    def test_build_deterministic_entity_id_alertmanager_same_source(self) -> None:
        """Same Alertmanager source should produce same entity_id."""
        source1 = build_deterministic_entity_id("alertmanager-source", {"namespace": "monitoring", "name": "alertmanager-main"})
        source2 = build_deterministic_entity_id("alertmanager-source", {"namespace": "monitoring", "name": "alertmanager-main"})
        assert source1 == source2, "Same Alertmanager source should have same ID"

    def test_build_deterministic_entity_id_alertmanager_different_sources(self) -> None:
        """Different Alertmanager sources should produce different entity_ids."""
        source1 = build_deterministic_entity_id("alertmanager-source", {"namespace": "monitoring", "name": "alertmanager-main"})
        source2 = build_deterministic_entity_id("alertmanager-source", {"namespace": "monitoring", "name": "alertmanager-upstream"})
        assert source1 != source2, "Different Alertmanager sources should have different IDs"


class TestK8sObjectRef:
    """Tests for Kubernetes object reference parsing."""

    def test_build_k8s_object_ref(self) -> None:
        """Should build a valid K8sObjectRef."""
        ref = build_k8s_object_ref(
            namespace="default",
            kind="Pod",
            name="test-pod",
            object_uid="abc-123",
        )
        assert ref.namespace == "default"
        assert ref.kind == "Pod"
        assert ref.name == "test-pod"
        assert ref.object_uid == "abc-123"
        # api_version is a computed property
        assert ref.api_version == "default/Pod/test-pod"

    def test_build_k8s_object_ref_cluster_scoped(self) -> None:
        """Should build a cluster-scoped K8sObjectRef (no namespace)."""
        ref = build_k8s_object_ref(
            namespace=None,
            kind="Namespace",
            name="default",
        )
        assert ref.namespace is None
        assert ref.kind == "Namespace"
        assert ref.name == "default"
        assert ref.api_version == "Namespace/default"

    def test_parse_k8s_object_ref_valid(self) -> None:
        """Should parse a valid object reference dict."""
        data = {
            "kind": "Pod",
            "namespace": "default",
            "name": "test-pod",
            "object_uid": "abc-123",
        }
        ref = parse_k8s_object_ref(data)
        assert ref is not None
        assert ref.kind == "Pod"
        assert ref.namespace == "default"
        assert ref.name == "test-pod"
        assert ref.object_uid == "abc-123"

    def test_parse_k8s_object_ref_cluster_scoped(self) -> None:
        """Should parse cluster-scoped object reference dict."""
        data = {
            "kind": "Namespace",
            "name": "default",
        }
        ref = parse_k8s_object_ref(data)
        assert ref is not None
        assert ref.kind == "Namespace"
        assert ref.namespace is None
        assert ref.name == "default"

    def test_parse_k8s_object_ref_invalid(self) -> None:
        """Should return None for missing required fields."""
        # Missing 'kind'
        data = {"name": "test"}
        ref = parse_k8s_object_ref(data)
        assert ref is None

        # Missing 'name'
        data = {"kind": "Pod"}
        ref = parse_k8s_object_ref(data)
        assert ref is None
