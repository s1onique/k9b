"""Tests for Alertmanager source registry cross-run persistence.

This module tests the durable cross-run registry that ensures operator
promote/disable actions persist across health loop runs.

Key behaviors tested:
- Registry entries are keyed by cluster_context + canonical_identity
- Disabled sources are filtered out from inventory (return None from apply_registry_to_source)
- Manual sources are promoted to MANUAL state
- Registry persists to disk as runs/health/alertmanager-source-registry.json
- Cross-run persistence: registry survives across separate read/write cycles
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


class TestRegistryEntry:
    """Tests for RegistryEntry dataclass."""

    def test_registry_key_format(self) -> None:
        """Registry key should be formatted as cluster_context:canonical_identity."""
        entry = RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        )
        assert entry.registry_key == "minikube:monitoring/alertmanager-main"

    def test_registry_key_with_special_characters(self) -> None:
        """Registry key should handle special characters in namespace/name."""
        entry = RegistryEntry(
            cluster_context="prod-cluster",
            canonical_identity="monitoring/alertmanager-main-0",
            desired_state=RegistryDesiredState.DISABLED,
        )
        assert entry.registry_key == "prod-cluster:monitoring/alertmanager-main-0"

    def test_to_dict_roundtrip(self) -> None:
        """RegistryEntry should serialize and deserialize correctly."""
        original = RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
            reason="Operator decision",
            operator="admin@example.com",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            original_origin="alertmanager-crd",
            original_state="auto-tracked",
        )

        data = original.to_dict()
        restored = RegistryEntry.from_dict(data)

        assert restored.cluster_context == original.cluster_context
        assert restored.canonical_identity == original.canonical_identity
        assert restored.desired_state == original.desired_state
        assert restored.reason == original.reason
        assert restored.operator == original.operator
        assert restored.endpoint == original.endpoint
        assert restored.namespace == original.namespace
        assert restored.name == original.name
        assert restored.original_origin == original.original_origin
        assert restored.original_state == original.original_state


class TestAlertmanagerSourceRegistry:
    """Tests for AlertmanagerSourceRegistry dataclass."""

    def test_add_and_get_entry(self) -> None:
        """Registry should store and retrieve entries by key."""
        registry = AlertmanagerSourceRegistry()
        entry = RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        )

        registry.add_entry(entry)
        retrieved = registry.get_entry(entry.registry_key)

        assert retrieved is not None
        assert retrieved.desired_state == RegistryDesiredState.MANUAL

    def test_get_desired_state(self) -> None:
        """Registry should return desired state for valid cluster_context + identity."""
        registry = AlertmanagerSourceRegistry()
        entry = RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.DISABLED,
        )
        registry.add_entry(entry)

        state = registry.get_desired_state("minikube", "monitoring/alertmanager-main")
        assert state == RegistryDesiredState.DISABLED

    def test_get_desired_state_not_found(self) -> None:
        """Registry should return None for non-existent entry."""
        registry = AlertmanagerSourceRegistry()
        state = registry.get_desired_state("minikube", "monitoring/alertmanager-main")
        assert state is None

    def test_get_desired_state_wrong_context(self) -> None:
        """Registry should return None for wrong cluster_context."""
        registry = AlertmanagerSourceRegistry()
        entry = RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        )
        registry.add_entry(entry)

        # Different cluster context
        state = registry.get_desired_state("prod-cluster", "monitoring/alertmanager-main")
        assert state is None

    def test_get_disabled_sources(self) -> None:
        """Registry should return all disabled source entries."""
        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.DISABLED,
        ))
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-ops",
            desired_state=RegistryDesiredState.MANUAL,
        ))
        registry.add_entry(RegistryEntry(
            cluster_context="prod-cluster",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.DISABLED,
        ))

        disabled = registry.get_disabled_sources()
        assert len(disabled) == 2
        assert all(e.desired_state == RegistryDesiredState.DISABLED for e in disabled)

    def test_get_manual_sources(self) -> None:
        """Registry should return all manual source entries."""
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

        manual = registry.get_manual_sources()
        assert len(manual) == 1
        assert manual[0].desired_state == RegistryDesiredState.MANUAL

    def test_to_dict_roundtrip(self) -> None:
        """Registry should serialize and deserialize correctly."""
        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
            reason="Operator decision",
        ))

        data = registry.to_dict()
        restored = AlertmanagerSourceRegistry.from_dict(data)

        assert len(restored.entries) == 1
        entry = list(restored.entries.values())[0]
        assert entry.cluster_context == "minikube"
        assert entry.canonical_identity == "monitoring/alertmanager-main"
        assert entry.desired_state == RegistryDesiredState.MANUAL


class TestRegistryPersistence:
    """Tests for registry persistence to disk."""

    def test_write_and_read_registry(self, tmp_path: Path) -> None:
        """Registry should persist to disk and be readable."""
        health_root = tmp_path / "health"
        health_root.mkdir(parents=True)

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
            reason="Test reason",
        ))

        # Write to disk
        write_source_registry(registry, health_root)

        # Verify file exists
        registry_path = health_root / "alertmanager-source-registry.json"
        assert registry_path.exists()

        # Read back
        restored = read_source_registry(health_root)
        assert restored is not None
        assert len(restored.entries) == 1

        entry = list(restored.entries.values())[0]
        assert entry.cluster_context == "minikube"
        assert entry.canonical_identity == "monitoring/alertmanager-main"
        assert entry.desired_state == RegistryDesiredState.MANUAL
        assert entry.reason == "Test reason"

    def test_read_nonexistent_registry(self, tmp_path: Path) -> None:
        """Reading non-existent registry should return None."""
        health_root = tmp_path / "health"
        health_root.mkdir(parents=True)

        registry = read_source_registry(health_root)
        assert registry is None

    def test_cross_run_persistence(self, tmp_path: Path) -> None:
        """Registry should survive across separate read/write cycles (simulating runs)."""
        health_root = tmp_path / "health"
        health_root.mkdir(parents=True)

        # Simulate Run 1: Operator disables a source
        registry1 = AlertmanagerSourceRegistry()
        registry1.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-ops",
            desired_state=RegistryDesiredState.DISABLED,
            reason="No longer needed",
        ))
        write_source_registry(registry1, health_root)

        # Simulate end of Run 1, start of Run 2
        # Read existing registry
        registry2 = read_source_registry(health_root)
        assert registry2 is not None

        # Add another source in Run 2
        registry2.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
            reason="Promoted by operator",
        ))
        write_source_registry(registry2, health_root)

        # Simulate end of Run 2, start of Run 3
        # Verify both entries persist
        registry3 = read_source_registry(health_root)
        assert registry3 is not None
        assert len(registry3.entries) == 2

        # Verify disabled source is still disabled
        disabled_state = registry3.get_desired_state("minikube", "monitoring/alertmanager-ops")
        assert disabled_state == RegistryDesiredState.DISABLED

        # Verify manual source is still manual
        manual_state = registry3.get_desired_state("minikube", "monitoring/alertmanager-main")
        assert manual_state == RegistryDesiredState.MANUAL


class TestApplyRegistryToSource:
    """Tests for applying registry state to individual sources."""

    def test_no_registry_returns_source_unchanged(self) -> None:
        """With no registry, source should be returned unchanged."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )

        result = apply_registry_to_source(source, None, "minikube")
        assert result is not None
        assert result.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
        assert result.state == AlertmanagerSourceState.AUTO_TRACKED

    def test_no_matching_entry_returns_source_unchanged(self) -> None:
        """When registry has no matching entry, source should be returned unchanged."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="prod-cluster",  # Different context
            canonical_identity="monitoring/alertmanager-other",
            desired_state=RegistryDesiredState.MANUAL,
        ))

        result = apply_registry_to_source(source, registry, "minikube")
        assert result is not None
        assert result.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
        assert result.state == AlertmanagerSourceState.AUTO_TRACKED

    def test_manual_state_promotes_source(self) -> None:
        """Registry MANUAL state should promote source to manual state while preserving origin.
        
        REGRESSION FIX: Origin is now PRESERVED (not overwritten to MANUAL).
        The distinction is preserved via manual_source_mode field.
        """
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        ))

        result = apply_registry_to_source(source, registry, "minikube")
        assert result is not None
        # Origin is PRESERVED (not overwritten to MANUAL) - this is the fix
        assert result.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
        # State is set to MANUAL
        assert result.state == AlertmanagerSourceState.MANUAL
        # manual_source_mode indicates it was promoted (not operator-configured)
        assert result.manual_source_mode == AlertmanagerSourceMode.OPERATOR_PROMOTED

    def test_disabled_state_returns_none(self) -> None:
        """Registry DISABLED state should return None to filter out the source."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-ops",
            endpoint="http://alertmanager-ops.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-ops",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-ops",
            desired_state=RegistryDesiredState.DISABLED,
        ))

        result = apply_registry_to_source(source, registry, "minikube")
        assert result is None

    def test_different_context_no_match(self) -> None:
        """Registry should not match sources from different cluster contexts."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="prod-cluster",  # Different context
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.DISABLED,
        ))

        # Apply with different context - should NOT filter out
        result = apply_registry_to_source(source, registry, "minikube")
        assert result is not None
        # Source remains in original state since registry entry is for different context
        assert result.state == AlertmanagerSourceState.AUTO_TRACKED

    def test_manual_state_preserves_cluster_label(self) -> None:
        """Regression test: Registry MANUAL promotion must preserve cluster_label.
        
        This test verifies that when a source is promoted via registry,
        its cluster_label is preserved for per-cluster UI filtering.
        
        CRITICAL: Origin is PRESERVED (not overwritten to MANUAL) - this is the fix.
        The distinction is preserved via manual_source_mode field.
        """
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_label="prod-cluster-a",
            cluster_context="prod-context",
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="prod-context",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        ))

        result = apply_registry_to_source(source, registry, "prod-context")
        assert result is not None
        # Origin is PRESERVED (not overwritten to MANUAL) - this is the fix
        assert result.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
        assert result.state == AlertmanagerSourceState.MANUAL
        # manual_source_mode indicates it was promoted
        assert result.manual_source_mode == AlertmanagerSourceMode.OPERATOR_PROMOTED
        # cluster_label MUST be preserved
        assert result.cluster_label == "prod-cluster-a"
        # cluster_context from registry lookup is set on the source
        assert result.cluster_context == "prod-context"

    def test_manual_state_sets_cluster_context_when_source_has_none(self) -> None:
        """Regression test: Registry promotion must set cluster_context from registry lookup.

        When a discovered source has cluster_context=None (common for CRD discovery),
        but the registry was written with cluster_context=cluster1, the apply_registry_to_source
        must set cluster_context=cluster1 on the promoted source so that the serializer
        can match it back to the registry entry.

        This is the key fix for the UI bug where promoted sources showed "Managed manually"
        instead of "Promoted" - the serializer couldn't match the source to the registry
        because cluster_context was null.
        """
        # Source has cluster_context=None (common for CRD discovery before apply_registry)
        source = AlertmanagerSource(
            source_id="crd:monitoring/kube-prometheus-stack-alertmanager",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="kube-prometheus-stack-alertmanager",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
            cluster_label="cluster1",
            cluster_context=None,  # This is the common case for CRD discovery
        )

        registry = AlertmanagerSourceRegistry()
        # Registry was written with cluster_context=cluster1 (from the UI server)
        registry.add_entry(RegistryEntry(
            cluster_context="cluster1",
            canonical_identity="monitoring/kube-prometheus-stack-alertmanager",
            desired_state=RegistryDesiredState.MANUAL,
        ))

        # Apply registry with cluster_context=cluster1 (from health loop)
        result = apply_registry_to_source(source, registry, "cluster1")
        assert result is not None
        
        # Source is promoted
        assert result.state == AlertmanagerSourceState.MANUAL
        assert result.manual_source_mode == AlertmanagerSourceMode.OPERATOR_PROMOTED
        
        # cluster_context is set from the registry lookup, not from the source
        # This is critical for the serializer to match the source to the registry
        assert result.cluster_context == "cluster1"
        
        # Origin is preserved
        assert result.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD


class TestApplyRegistryToInventory:
    """Tests for applying registry state to entire source inventory."""

    def test_disabled_sources_filtered_out(self) -> None:
        """Disabled sources should be removed from the inventory."""
        inventory = AlertmanagerSourceInventory(cluster_context="minikube")
        inventory.add_source(AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        ))
        inventory.add_source(AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-ops",
            endpoint="http://alertmanager-ops.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-ops",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        ))

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-ops",
            desired_state=RegistryDesiredState.DISABLED,
        ))

        result = apply_registry_to_inventory(inventory, registry, "minikube")

        # Only alertmanager-main should remain
        assert len(result.sources) == 1
        assert "crd:monitoring/alertmanager-main" in result.sources
        assert "crd:monitoring/alertmanager-ops" not in result.sources

    def test_manual_sources_promoted(self) -> None:
        """Manual registry entries should promote sources in the inventory.
        
        REGRESSION FIX: Origin is PRESERVED (not overwritten to MANUAL).
        The distinction is preserved via manual_source_mode field.
        """
        inventory = AlertmanagerSourceInventory(cluster_context="minikube")
        inventory.add_source(AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        ))

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        ))

        result = apply_registry_to_inventory(inventory, registry, "minikube")

        # Source should be promoted to manual
        # Origin is PRESERVED (not overwritten to MANUAL) - this is the fix
        promoted = result.sources["crd:monitoring/alertmanager-main"]
        assert promoted.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
        assert promoted.state == AlertmanagerSourceState.MANUAL
        assert promoted.manual_source_mode == AlertmanagerSourceMode.OPERATOR_PROMOTED

    def test_no_registry_returns_original_inventory(self) -> None:
        """With no registry, inventory should be returned unchanged."""
        inventory = AlertmanagerSourceInventory(cluster_context="minikube")
        inventory.add_source(AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        ))

        result = apply_registry_to_inventory(inventory, None, "minikube")

        assert len(result.sources) == 1
        assert result.sources["crd:monitoring/alertmanager-main"].state == AlertmanagerSourceState.AUTO_TRACKED

    def test_mixed_promote_and_disable(self) -> None:
        """Inventory should handle both promotions and disables correctly."""
        inventory = AlertmanagerSourceInventory(cluster_context="minikube")
        inventory.add_source(AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        ))
        inventory.add_source(AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-ops",
            endpoint="http://alertmanager-ops.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-ops",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        ))
        inventory.add_source(AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-dev",
            endpoint="http://alertmanager-dev.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-dev",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        ))

        registry = AlertmanagerSourceRegistry()
        # Promote alertmanager-main
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        ))
        # Disable alertmanager-ops
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-ops",
            desired_state=RegistryDesiredState.DISABLED,
        ))

        result = apply_registry_to_inventory(inventory, registry, "minikube")

        # alertmanager-main should be promoted
        # Origin is PRESERVED (not overwritten to MANUAL) - this is the fix
        assert "crd:monitoring/alertmanager-main" in result.sources
        assert result.sources["crd:monitoring/alertmanager-main"].origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
        assert result.sources["crd:monitoring/alertmanager-main"].manual_source_mode == AlertmanagerSourceMode.OPERATOR_PROMOTED

        # alertmanager-ops should be removed
        assert "crd:monitoring/alertmanager-ops" not in result.sources

        # alertmanager-dev should remain unchanged
        assert "crd:monitoring/alertmanager-dev" in result.sources
        assert result.sources["crd:monitoring/alertmanager-dev"].origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD


class TestBuildRegistryKey:
    """Tests for build_registry_key function."""

    def test_key_format(self) -> None:
        """Registry key should be cluster_context:canonical_identity."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
        )

        key = build_registry_key("minikube", source)
        assert key == "minikube:monitoring/alertmanager-main"

    def test_none_context_defaults_to_unknown(self) -> None:
        """None cluster_context should default to 'unknown'."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
        )

        key = build_registry_key(None, source)
        assert key == "unknown:monitoring/alertmanager-main"


class TestLookupRegistryState:
    """Tests for lookup_registry_state function."""

    def test_returns_none_for_no_registry(self) -> None:
        """Should return None when registry is None."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
        )

        state = lookup_registry_state(None, "minikube", source)
        assert state is None

    def test_returns_state_for_matching_entry(self) -> None:
        """Should return desired state for matching cluster_context + identity."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.DISABLED,
        ))

        state = lookup_registry_state(registry, "minikube", source)
        assert state == RegistryDesiredState.DISABLED

    def test_none_context_uses_unknown(self) -> None:
        """Should use 'unknown' when cluster_context is None."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="unknown",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        ))

        state = lookup_registry_state(registry, None, source)
        assert state == RegistryDesiredState.MANUAL


# --- ManualSourceMode Origin Preservation Tests ---


class TestManualSourceModeOriginPreservation:
    """Tests for origin preservation when sources are promoted via registry.
    
    This is the critical regression test for the provenance collapse issue:
    - Operator-promoted sources should PRESERVE their original discovery origin
    - Only operator-configured sources (typed endpoint) should have origin=MANUAL
    """

    def test_registry_promotion_preserves_alertmanager_crd_origin(self) -> None:
        """Registry MANUAL promotion must PRESERVE the original alertmanager-crd origin.
        
        This is the core fix for the provenance collapse issue.
        Before: origin was overwritten to "manual"
        After: origin stays as "alertmanager-crd", mode indicates it was promoted
        """
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        ))

        result = apply_registry_to_source(source, registry, "minikube")
        assert result is not None
        
        # CRITICAL: Origin should be PRESERVED (not overwritten to MANUAL)
        assert result.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD, (
            f"Origin was overwritten! Expected 'alertmanager-crd', got '{result.origin.value}'"
        )
        
        # State should be MANUAL
        assert result.state == AlertmanagerSourceState.MANUAL
        
        # Mode should indicate this was promoted from discovery
        assert result.manual_source_mode == AlertmanagerSourceMode.OPERATOR_PROMOTED

    def test_registry_promotion_preserves_service_heuristic_origin(self) -> None:
        """Registry MANUAL promotion should preserve service-heuristic origin."""
        source = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-operated",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-operated",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-operated",
            desired_state=RegistryDesiredState.MANUAL,
        ))

        result = apply_registry_to_source(source, registry, "minikube")
        assert result is not None
        
        # Origin should be PRESERVED
        assert result.origin == AlertmanagerSourceOrigin.SERVICE_HEURISTIC, (
            f"Origin was overwritten! Expected 'service-heuristic', got '{result.origin.value}'"
        )
        
        # Mode should indicate this was promoted
        assert result.manual_source_mode == AlertmanagerSourceMode.OPERATOR_PROMOTED

    def test_registry_promotion_preserves_prometheus_crd_config_origin(self) -> None:
        """Registry MANUAL promotion should preserve prometheus-crd-config origin."""
        source = AlertmanagerSource(
            source_id="prom-crd-config:monitoring/alertmanager-main",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        ))

        result = apply_registry_to_source(source, registry, "minikube")
        assert result is not None
        
        # Origin should be PRESERVED
        assert result.origin == AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG, (
            f"Origin was overwritten! Expected 'prometheus-crd-config', got '{result.origin.value}'"
        )
        
        # Mode should indicate this was promoted
        assert result.manual_source_mode == AlertmanagerSourceMode.OPERATOR_PROMOTED

    def test_registry_promoted_source_serializes_manual_source_mode(self) -> None:
        """Promoted source should serialize manual_source_mode for UI consumption."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        ))

        result = apply_registry_to_source(source, registry, "minikube")
        assert result is not None
        
        # Serialize
        serialized = result.to_dict()
        
        # manual_source_mode should be present
        assert "manual_source_mode" in serialized
        assert serialized["manual_source_mode"] == "operator-promoted"
        
        # Origin should be preserved in serialization
        assert serialized["origin"] == "alertmanager-crd"

    def test_disabled_source_returns_none(self) -> None:
        """Registry DISABLED state should return None regardless of origin."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-ops",
            endpoint="http://alertmanager-ops.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-ops",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-ops",
            desired_state=RegistryDesiredState.DISABLED,
        ))

        result = apply_registry_to_source(source, registry, "minikube")
        assert result is None

    def test_promoted_source_roundtrip_through_inventory(self) -> None:
        """Promoted source should survive full inventory processing pipeline."""
        inventory = AlertmanagerSourceInventory(cluster_context="minikube")
        
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )
        inventory.add_source(source)

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="minikube",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        ))

        # Apply registry to inventory
        result = apply_registry_to_inventory(inventory, registry, "minikube")
        
        # Verify the promoted source has correct fields
        promoted = result.sources["crd:monitoring/alertmanager-main"]
        assert promoted.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
        assert promoted.state == AlertmanagerSourceState.MANUAL
        assert promoted.manual_source_mode == AlertmanagerSourceMode.OPERATOR_PROMOTED

    def test_distinguish_promoted_vs_configured_sources(self) -> None:
        """Test that promoted and configured sources are distinguishable.
        
        This verifies the UI can show different provenance info:
        - Promoted: "Alertmanager CRD (promoted to manual)"
        - Configured: "Manual (operator configured)"
        """
        # Source 1: Operator-promoted (from CRD)
        promoted_source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.MANUAL,
            manual_source_mode=AlertmanagerSourceMode.OPERATOR_PROMOTED,
        )
        
        # Source 2: Operator-configured (typed endpoint)
        configured_source = AlertmanagerSource(
            source_id="manual:alertmanager-external:9093",
            endpoint="http://alertmanager-external:9093",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
            manual_source_mode=AlertmanagerSourceMode.OPERATOR_CONFIGURED,
        )
        
        # They should be distinguishable
        assert promoted_source.manual_source_mode == AlertmanagerSourceMode.OPERATOR_PROMOTED
        assert configured_source.manual_source_mode == AlertmanagerSourceMode.OPERATOR_CONFIGURED
        
        # Origin differs
        assert promoted_source.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
        assert configured_source.origin == AlertmanagerSourceOrigin.MANUAL
        
        # Display provenance differs
        assert "Alertmanager CRD" in promoted_source.display_provenance
        assert configured_source.display_provenance == "Manual"
