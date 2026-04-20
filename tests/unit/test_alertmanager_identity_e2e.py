"""End-to-end tests for Alertmanager identity threading.

This module tests the integration of identity helpers with registry/override/action paths,
ensuring:
1. operator_intent_key is used consistently for persistence
2. canonicalEntityId is available in serialized payloads
3. Legacy persisted keys remain readable
4. Mixed discovery shapes produce correct canonical IDs
5. Context rename stability for operator intent

Key behaviors tested:
- AlertmanagerSource.operator_intent_key uses cluster_label for stability
- AlertmanagerSource.canonicalEntityId is in to_dict() output
- Source roundtrip through to_dict()/from_dict() preserves identity
- Registry lookup matches operator_intent_key correctly
- Legacy registry entries remain readable
"""

from __future__ import annotations

from pathlib import Path

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
    AlertmanagerSourceInventory,
    AlertmanagerSourceMode,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
)
from k8s_diag_agent.external_analysis.alertmanager_source_registry import (
    AlertmanagerSourceRegistry,
    RegistryDesiredState,
    RegistryEntry,
    apply_registry_to_inventory,
    apply_registry_to_source,
    build_registry_key,
    lookup_registry_state,
    read_source_registry,
    write_source_registry,
)
from k8s_diag_agent.identity.alertmanager_source import (
    build_alertmanager_canonical_entity_id,
)


class TestCanonicalEntityIdSerialization:
    """Tests for canonicalEntityId serialization in AlertmanagerSource."""

    def test_canonical_entity_id_in_to_dict(self) -> None:
        """canonicalEntityId should be present in serialized source."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )

        serialized = source.to_dict()

        assert "canonicalEntityId" in serialized
        assert isinstance(serialized["canonicalEntityId"], str)
        assert len(serialized["canonicalEntityId"]) == 32  # 128-bit hex

    def test_canonical_entity_id_matches_property(self) -> None:
        """canonicalEntityId in dict should match canonical_entity_id property."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )

        serialized = source.to_dict()

        assert serialized["canonicalEntityId"] == source.canonical_entity_id

    def test_source_roundtrip_preserves_canonical_entity_id(self) -> None:
        """Roundtrip through to_dict/from_dict should preserve canonicalEntityId."""
        original = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_label="prod-cluster",
            cluster_context="admin@k8s",
        )

        serialized = original.to_dict()
        restored = AlertmanagerSource.from_dict(serialized)

        assert restored.canonical_entity_id == original.canonical_entity_id

    def test_canonical_entity_id_without_cluster_uid(self) -> None:
        """canonicalEntityId should be stable even without cluster_uid."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )

        # Should have a valid canonicalEntityId
        assert source.canonical_entity_id is not None
        assert len(source.canonical_entity_id) == 32

        serialized = source.to_dict()
        assert "canonicalEntityId" in serialized

    def test_canonical_entity_id_with_cluster_uid(self) -> None:
        """canonicalEntityId should include cluster_uid when available."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_uid="cluster-uid-123",
        )

        # cluster_uid should be serialized when present
        serialized = source.to_dict()
        assert "cluster_uid" in serialized
        assert serialized["cluster_uid"] == "cluster-uid-123"
        assert "canonicalEntityId" in serialized

    def test_cluster_uid_not_serialized_when_none(self) -> None:
        """cluster_uid should not appear in serialization when None."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )

        serialized = source.to_dict()
        assert "cluster_uid" not in serialized


class TestOperatorIntentKey:
    """Tests for operator_intent_key property on AlertmanagerSource."""

    def test_operator_intent_key_uses_cluster_label(self) -> None:
        """operator_intent_key should prefer cluster_label over cluster_context."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_label="prod-cluster",  # Should be used
            cluster_context="admin@k8s",  # Should be ignored
        )

        expected_key = "prod-cluster:monitoring/alertmanager-main"
        assert source.operator_intent_key == expected_key

    def test_operator_intent_key_falls_back_to_cluster_context(self) -> None:
        """operator_intent_key should fall back to cluster_context when no cluster_label."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_context="admin@k8s",
        )

        expected_key = "admin@k8s:monitoring/alertmanager-main"
        assert source.operator_intent_key == expected_key

    def test_operator_intent_key_falls_back_to_unknown(self) -> None:
        """operator_intent_key should use 'unknown' when no cluster identifiers."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )

        expected_key = "unknown:monitoring/alertmanager-main"
        assert source.operator_intent_key == expected_key

    def test_operator_intent_key_stable_across_context_rename(self) -> None:
        """operator_intent_key should remain stable when cluster_context changes."""
        source1 = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_label="prod-cluster",  # Stable
            cluster_context="old-context-name",  # Will change
        )

        source2 = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_label="prod-cluster",  # Same stable label
            cluster_context="new-context-name",  # Changed!
        )

        # Both should produce the same operator_intent_key
        assert source1.operator_intent_key == source2.operator_intent_key
        assert source1.operator_intent_key == "prod-cluster:monitoring/alertmanager-main"


class TestContextRenameStability:
    """Tests for context rename stability in registry persistence."""

    def test_registry_promotes_with_context_rename(self) -> None:
        """Registry should promote source even when cluster_context changed."""
        # Source discovered with stable cluster_label but different cluster_context
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_label="cluster1",  # Stable
            cluster_context="current-context",  # Current
        )

        # Registry entry was written with different context (or None)
        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="cluster1",  # Keyed by cluster_label
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        ))

        # Apply with the NEW context
        result = apply_registry_to_source(source, registry, "current-context")

        assert result is not None
        assert result.state == AlertmanagerSourceState.MANUAL
        assert result.manual_source_mode == AlertmanagerSourceMode.OPERATOR_PROMOTED

    def test_registry_disable_with_context_rename(self) -> None:
        """Registry should disable source even when cluster_context changed."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-ops",
            endpoint="http://alertmanager-ops.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-ops",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_label="cluster1",
            cluster_context="current-context",
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="cluster1",
            canonical_identity="monitoring/alertmanager-ops",
            desired_state=RegistryDesiredState.DISABLED,
        ))

        result = apply_registry_to_source(source, registry, "current-context")

        assert result is None  # Filtered out


class TestLegacyKeyCompatibility:
    """Tests for backward compatibility with legacy persisted keys."""

    def test_read_legacy_registry_entry(self) -> None:
        """Legacy registry entries keyed by cluster_context should remain readable."""
        # Simulate legacy format: keyed by cluster_context directly
        legacy_data = {
            "schema_version": "1",
            "entries": {
                "minikube:monitoring/alertmanager-main": {
                    "cluster_context": "minikube",
                    "canonical_identity": "monitoring/alertmanager-main",
                    "desired_state": "manual",
                    "reason": "Test",
                    "operator": None,
                    "updated_at": "2024-01-01T00:00:00+00:00",
                    "source_run_id": "run-123",
                    "endpoint": "http://alertmanager-main.monitoring:9093",
                    "namespace": "monitoring",
                    "name": "alertmanager-main",
                    "original_origin": "alertmanager-crd",
                    "original_state": "auto-tracked",
                }
            },
            "last_updated": "2024-01-01T00:00:00+00:00",
        }

        registry = AlertmanagerSourceRegistry.from_dict(legacy_data)

        assert len(registry.entries) == 1
        entry = registry.get_entry("minikube:monitoring/alertmanager-main")
        assert entry is not None
        assert entry.desired_state == RegistryDesiredState.MANUAL

    def test_legacy_key_lookup_falls_back(self) -> None:
        """lookup_registry_state should fall back to legacy key format."""
        # Source with cluster_label set
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_label="minikube",  # Will be used for canonical key
        )

        # Registry has legacy entry keyed by cluster_context
        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",  # Same value, but no cluster_label
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.DISABLED,
        ))

        # Lookup should find it via legacy key fallback
        state = lookup_registry_state(registry, "minikube", source)
        assert state == RegistryDesiredState.DISABLED

    def test_persistence_roundtrip_preserves_entries(self, tmp_path: Path) -> None:
        """Registry entries should survive write/read cycle."""
        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
            reason="Test promotion",
        ))
        registry.add_entry(RegistryEntry(
            cluster_context="prod",
            canonical_identity="monitoring/alertmanager-ops",
            desired_state=RegistryDesiredState.DISABLED,
            reason="Not needed",
        ))

        health_root = tmp_path / "health"
        health_root.mkdir(parents=True)

        write_source_registry(registry, health_root)
        restored = read_source_registry(health_root)

        assert restored is not None
        assert len(restored.entries) == 2

        # Check entries survived
        entry1 = restored.get_entry("minikube:monitoring/alertmanager-main")
        assert entry1 is not None
        assert entry1.desired_state == RegistryDesiredState.MANUAL

        entry2 = restored.get_entry("prod:monitoring/alertmanager-ops")
        assert entry2 is not None
        assert entry2.desired_state == RegistryDesiredState.DISABLED


class TestMixedDiscoveryCanonicalId:
    """Tests for canonical_entity_id with mixed discovery shapes."""

    def test_same_source_different_discovery_produces_same_canonical_id(self) -> None:
        """Same namespace/name/origin should produce same canonical_entity_id regardless of discovery."""
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
        assert id1 == id2

    def test_different_namespace_produces_different_canonical_id(self) -> None:
        """Different namespace should produce different canonical_entity_id."""
        id1 = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
        )
        id2 = build_alertmanager_canonical_entity_id(
            namespace="ops",
            name="alertmanager-main",
            origin="alertmanager-crd",
        )
        assert id1 != id2

    def test_cluster_uid_affects_canonical_id(self) -> None:
        """cluster_uid should affect canonical_entity_id when provided."""
        id_without = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
        )
        id_with = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
            cluster_uid="cluster-uid-123",
        )
        # Different canonical IDs because cluster_uid differs
        assert id_without != id_with

    def test_object_uid_affects_canonical_id(self) -> None:
        """object_uid should affect canonical_entity_id when provided."""
        id_without = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
        )
        id_with = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
            object_uid="object-uid-456",
        )
        # Different canonical IDs because object_uid differs
        assert id_without != id_with

    def test_mixed_discovery_same_endpoint_different_origins(self) -> None:
        """Sources with same endpoint but different origins should have different canonical_ids."""
        id_crd = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="alertmanager-crd",
        )
        id_heuristic = build_alertmanager_canonical_entity_id(
            namespace="monitoring",
            name="alertmanager-main",
            origin="service-heuristic",
        )
        # Different origins should produce different canonical IDs
        assert id_crd != id_heuristic


class TestBuildRegistryKeyUsesOperatorIntent:
    """Tests that build_registry_key delegates to operator_intent_key."""

    def test_build_registry_key_delegates_to_operator_intent_key(self) -> None:
        """build_registry_key should use source.operator_intent_key."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_label="prod-cluster",
        )

        key = build_registry_key("any-context", source)

        assert key == source.operator_intent_key
        assert key == "prod-cluster:monitoring/alertmanager-main"


class TestPromoteDisableInventory:
    """Tests for promote/disable through inventory pipeline."""

    def test_promote_and_disable_inventory(self) -> None:
        """Full inventory should handle both promotions and disables."""
        inventory = AlertmanagerSourceInventory(cluster_context="minikube")
        inventory.add_source(AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_label="minikube",
        ))
        inventory.add_source(AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-ops",
            endpoint="http://alertmanager-ops.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-ops",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_label="minikube",
        ))

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        ))
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-ops",
            desired_state=RegistryDesiredState.DISABLED,
        ))

        result = apply_registry_to_inventory(inventory, registry, "minikube")

        # alertmanager-main should be promoted
        main = result.sources.get("crd:monitoring/alertmanager-main")
        assert main is not None
        assert main.state == AlertmanagerSourceState.MANUAL
        assert main.manual_source_mode == AlertmanagerSourceMode.OPERATOR_PROMOTED

        # alertmanager-ops should be filtered out
        assert "crd:monitoring/alertmanager-ops" not in result.sources
