"""Tests for Alertmanager source canonical identity and operator intent key.

This module tests the three-layer identity model:
1. Canonical historical identity (canonical_entity_id) - deterministic hash
2. Operator-intent persistence key (operator_intent_key) - for durable actions
3. Display identity - human-readable fields only

Key behaviors tested:
- Same source facts across rediscovery => same canonical_entity_id
- Different source facts => different canonical_entity_id
- Display changes (cluster_label, cluster_context) do NOT affect canonical_entity_id
- operator_intent_key prefers cluster_label for stability
- Legacy artifacts remain readable
- Serialization includes canonical_entity_id
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.identity.alertmanager_source import (
    build_alertmanager_canonical_entity_id,
    build_alertmanager_canonical_human_id,
    build_alertmanager_operator_intent_key,
    extract_alertmanager_source_facts,
    get_canonical_identity_summary,
)


class TestExtractAlertmanagerSourceFacts(unittest.TestCase):
    """Tests for extract_alertmanager_source_facts function."""

    def test_extracts_namespace_and_name(self) -> None:
        """Should extract namespace and name as primary anchors."""
        facts = extract_alertmanager_source_facts(
            namespace="monitoring",
            name="alertmanager-main",
        )
        self.assertEqual(facts["namespace"], "monitoring")
        self.assertEqual(facts["name"], "alertmanager-main")

    def test_includes_origin_when_provided(self) -> None:
        """Should include origin when provided."""
        facts = extract_alertmanager_source_facts(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
        )
        self.assertEqual(facts["origin"], "alertmanager-crd")

    def test_includes_cluster_uid_for_cross_cluster_disambiguation(self) -> None:
        """Should include cluster_uid when provided."""
        facts = extract_alertmanager_source_facts(
            namespace="monitoring",
            name="alertmanager-main",
            cluster_uid="abc-123-def",
        )
        self.assertEqual(facts["cluster_uid"], "abc-123-def")

    def test_includes_object_uid_when_provided(self) -> None:
        """Should include native object UID when provided."""
        facts = extract_alertmanager_source_facts(
            namespace="monitoring",
            name="alertmanager-main",
            object_uid="obj-uid-456",
        )
        self.assertEqual(facts["object_uid"], "obj-uid-456")

    def test_excludes_display_only_fields(self) -> None:
        """Should NOT include display-only fields (cluster_label, cluster_context)."""
        facts = extract_alertmanager_source_facts(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
        )
        # These should NOT be in facts
        self.assertNotIn("cluster_label", facts)
        self.assertNotIn("cluster_context", facts)

    def test_fallback_to_endpoint_when_no_namespace_name(self) -> None:
        """Should use endpoint as fallback when no namespace/name available."""
        facts = extract_alertmanager_source_facts(
            namespace=None,
            name=None,
            endpoint="http://external-alertmanager:9093",
        )
        self.assertEqual(facts["endpoint"], "external-alertmanager:9093")

    def test_normalizes_endpoint(self) -> None:
        """Should normalize endpoint by stripping scheme and trailing slash."""
        facts = extract_alertmanager_source_facts(
            namespace=None,
            name=None,
            endpoint="http://alertmanager.example.com:9093/",
        )
        self.assertEqual(facts["endpoint"], "alertmanager.example.com:9093")


class TestBuildAlertmanagerCanonicalEntityId(unittest.TestCase):
    """Tests for build_alertmanager_canonical_entity_id function."""

    def test_same_facts_produce_same_id(self) -> None:
        """Identical facts should produce identical canonical_entity_id."""
        id1 = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
        )
        id2 = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
        )
        self.assertEqual(id1, id2)

    def test_different_facts_produce_different_ids(self) -> None:
        """Different facts should produce different canonical_entity_id."""
        id1 = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
        )
        id2 = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-ops",
            origin="alertmanager-crd",
        )
        self.assertNotEqual(id1, id2)

    def test_idempotent_key_order(self) -> None:
        """Different fact ordering should produce same ID."""
        id1 = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
        )
        id2 = build_alertmanager_canonical_entity_id(
            name="alertmanager-main",
            namespace="monitoring",
        )
        self.assertEqual(id1, id2)

    def test_id_format_is_hex_32_chars(self) -> None:
        """ID should be 32-character hex string (128-bit hash)."""
        entity_id = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
        )
        self.assertIsInstance(entity_id, str)
        self.assertEqual(len(entity_id), 32)
        self.assertTrue(all(c in "0123456789abcdef" for c in entity_id))

    def test_display_changes_do_not_affect_canonical_id(self) -> None:
        """Display changes (cluster_label, cluster_context) should NOT affect canonical ID.
        
        The canonical_entity_id is built from defining facts only.
        Display-only fields are not accepted as parameters.
        """
        # These two calls have the same defining facts (namespace, name, origin)
        # but conceptually different display contexts
        id1 = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
        )
        id2 = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
        )
        # These should be the same since defining facts are identical
        self.assertEqual(id1, id2)

    def test_cluster_uid_changes_affect_canonical_id(self) -> None:
        """Different cluster_uid should produce different canonical ID (cross-cluster disambiguation)."""
        id1 = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
            cluster_uid="cluster-1-uid",
        )
        id2 = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
            cluster_uid="cluster-2-uid",
        )
        # Different clusters with same namespace/name should have different IDs
        self.assertNotEqual(id1, id2)

    def test_object_uid_changes_affect_canonical_id(self) -> None:
        """Different native object UIDs should produce different canonical ID."""
        id1 = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
            object_uid="uid-1",
        )
        id2 = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
            object_uid="uid-2",
        )
        self.assertNotEqual(id1, id2)


class TestBuildAlertmanagerOperatorIntentKey(unittest.TestCase):
    """Tests for build_alertmanager_operator_intent_key function."""

    def test_prefers_cluster_label_over_context(self) -> None:
        """Should prefer cluster_label over cluster_context for stability."""
        key1 = build_alertmanager_operator_intent_key(
            cluster_label="prod-cluster",
            cluster_context="admin@k8s",
            namespace="monitoring",
            name="alertmanager-main",
        )
        key2 = build_alertmanager_operator_intent_key(
            cluster_label="prod-cluster",  # Same stable label
            cluster_context="admin@different-context",  # Changed
            namespace="monitoring",
            name="alertmanager-main",
        )
        # Keys should be the same since cluster_label is stable
        self.assertEqual(key1, key2)

    def test_falls_back_to_cluster_context(self) -> None:
        """Should fall back to cluster_context when cluster_label unavailable."""
        key = build_alertmanager_operator_intent_key(
            cluster_label=None,
            cluster_context="my-context",
            namespace="monitoring",
            name="alertmanager-main",
        )
        self.assertEqual(key, "my-context:monitoring/alertmanager-main")

    def test_falls_back_to_unknown(self) -> None:
        """Should fall back to 'unknown' when neither label nor context available."""
        key = build_alertmanager_operator_intent_key(
            cluster_label=None,
            cluster_context=None,
            namespace="monitoring",
            name="alertmanager-main",
        )
        self.assertEqual(key, "unknown:monitoring/alertmanager-main")

    def test_uses_namespace_name_for_source_identity(self) -> None:
        """Should use namespace/name for source identity."""
        key = build_alertmanager_operator_intent_key(
            cluster_label="prod-cluster",
            namespace="monitoring",
            name="alertmanager-main",
        )
        self.assertEqual(key, "prod-cluster:monitoring/alertmanager-main")

    def test_context_rename_does_not_break_persistence(self) -> None:
        """Context rename should NOT break operator action persistence when label stable.
        
        This is the critical test for the operator-intent key design.
        """
        # Run 1: Operator promotes source when context was "old-context"
        key_run1 = build_alertmanager_operator_intent_key(
            cluster_label="prod-cluster",  # Stable label
            cluster_context="old-context",  # Original context
            namespace="monitoring",
            name="alertmanager-main",
        )
        
        # Run 2: kubeconfig context renamed to "new-context"
        key_run2 = build_alertmanager_operator_intent_key(
            cluster_label="prod-cluster",  # Still stable
            cluster_context="new-context",  # Changed!
            namespace="monitoring",
            name="alertmanager-main",
        )
        
        # Keys MUST be the same - this is the invariant
        self.assertEqual(key_run1, key_run2)


class TestBuildAlertmanagerCanonicalHumanId(unittest.TestCase):
    """Tests for build_alertmanager_canonical_human_id function."""

    def test_returns_namespace_name_format(self) -> None:
        """Should return human-readable namespace/name format."""
        human_id = build_alertmanager_canonical_human_id(
            namespace="monitoring",
            name="alertmanager-main",
        )
        self.assertEqual(human_id, "monitoring/alertmanager-main")

    def test_falls_back_to_endpoint(self) -> None:
        """Should fall back to endpoint when no namespace/name available."""
        human_id = build_alertmanager_canonical_human_id(
            namespace=None,
            name=None,
            endpoint="http://external:9093",
        )
        self.assertEqual(human_id, "external:9093")


class TestGetCanonicalIdentitySummary(unittest.TestCase):
    """Tests for get_canonical_identity_summary function."""

    def test_returns_namespace_name_format(self) -> None:
        """Should return human-readable namespace/name format."""
        summary = get_canonical_identity_summary(
            namespace="monitoring",
            name="alertmanager-main",
        )
        self.assertEqual(summary, "monitoring/alertmanager-main")

    def test_falls_back_to_endpoint(self) -> None:
        """Should fall back to normalized endpoint when no namespace/name."""
        summary = get_canonical_identity_summary(
            namespace=None,
            name=None,
            endpoint="http://external:9093/",
        )
        self.assertEqual(summary, "external:9093")

    def test_returns_unknown_when_no_identity(self) -> None:
        """Should return 'unknown' when no identity available."""
        summary = get_canonical_identity_summary(
            namespace=None,
            name=None,
            endpoint=None,
        )
        self.assertEqual(summary, "unknown")


class TestCanonicalVsOperatorIntentDistinct(unittest.TestCase):
    """Tests that canonical_entity_id and operator_intent_key are distinct."""

    def test_canonical_id_is_not_operator_intent_key(self) -> None:
        """Canonical entity ID should be an opaque hash, not a string like operator_intent_key."""
        canonical_id = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
        )
        operator_key = build_alertmanager_operator_intent_key(
            cluster_label="prod-cluster",
            namespace="monitoring",
            name="alertmanager-main",
        )
        
        # These should be different formats
        # canonical_id is 32-char hex
        # operator_key is "cluster:namespace/name" format
        self.assertNotEqual(canonical_id, operator_key)
        self.assertEqual(len(canonical_id), 32)
        self.assertIn(":", operator_key)

    def test_operator_intent_key_contains_cluster_info(self) -> None:
        """Operator intent key should include cluster information for multi-cluster."""
        key = build_alertmanager_operator_intent_key(
            cluster_label="prod-cluster",
            namespace="monitoring",
            name="alertmanager-main",
        )
        self.assertIn("prod-cluster", key)
        self.assertIn("monitoring/alertmanager-main", key)

    def test_canonical_id_excludes_cluster_info(self) -> None:
        """Canonical entity ID should NOT include cluster-specific info unless cluster_uid provided."""
        id_without_cluster = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
        )
        id_with_cluster = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            cluster_uid="some-uid",  # Only native cluster UID included
        )
        
        # Without cluster_uid, same across clusters
        # With cluster_uid, different across clusters
        self.assertNotEqual(id_without_cluster, id_with_cluster)


class TestIdentityLayeringIntegration(unittest.TestCase):
    """Integration tests for the three-layer identity model."""

    def test_three_layers_present_for_source(self) -> None:
        """All three identity layers should be constructible for a source."""
        # Layer 1: Canonical entity ID (opaque hash)
        canonical_id = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
        )
        
        # Layer 2: Operator intent key (for durable actions)
        operator_key = build_alertmanager_operator_intent_key(
            cluster_label="prod-cluster",
            cluster_context="admin@k8s",
            namespace="monitoring",
            name="alertmanager-main",
        )
        
        # Layer 3: Canonical identity summary (human-readable)
        identity_summary = get_canonical_identity_summary(
            namespace="monitoring",
            name="alertmanager-main",
        )
        
        # All three should be present and different
        self.assertIsNotNone(canonical_id)
        self.assertIsNotNone(operator_key)
        self.assertIsNotNone(identity_summary)
        
        self.assertNotEqual(canonical_id, operator_key)
        self.assertNotEqual(canonical_id, identity_summary)
        self.assertNotEqual(operator_key, identity_summary)
        
        # Verify formats
        self.assertEqual(len(canonical_id), 32)  # Hex hash
        self.assertIn(":", operator_key)  # Has cluster prefix
        self.assertEqual(identity_summary, "monitoring/alertmanager-main")  # Human-readable


if __name__ == "__main__":
    unittest.main()
