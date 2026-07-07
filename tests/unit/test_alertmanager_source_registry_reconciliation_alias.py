"""Unit tests for Alertmanager registry reconciliation with aliases.

Tests for registry collapse when inventory is already reconciled with aliases.
These tests verify that registry migration works even when the inventory has
already been collapsed into canonical sources with aliases.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import patch

from k8s_diag_agent.external_analysis.alertmanager_discovery_backing_identity import (
    BackingPodIdentity,
)
from k8s_diag_agent.external_analysis.alertmanager_discovery_models import (
    AlertmanagerSource,
    AlertmanagerSourceAlias,
    AlertmanagerSourceInventory,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
)
from k8s_diag_agent.external_analysis.alertmanager_source_models import (
    AlertmanagerSourceRegistry,
    RegistryDesiredState,
    RegistryEntry,
)
from k8s_diag_agent.external_analysis.alertmanager_source_registry_reconciliation import (
    collapse_duplicate_registry_entries,
)


def _make_source(
    source_id: str,
    endpoint: str,
    namespace: str = "monitoring",
    name: str = "alertmanager",
) -> AlertmanagerSource:
    """Create a test AlertmanagerSource."""
    return AlertmanagerSource(
        source_id=source_id,
        endpoint=endpoint,
        namespace=namespace,
        name=name,
        origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        state=AlertmanagerSourceState.DISCOVERED,
        discovered_at=datetime.now(UTC),
        cluster_context="test-context",
        cluster_label="test-cluster",
    )


def _make_inventory(sources: list[AlertmanagerSource]) -> AlertmanagerSourceInventory:
    """Create a test AlertmanagerSourceInventory."""
    return AlertmanagerSourceInventory(
        sources={s.source_id: s for s in sources},
        cluster_context="test-context",
    )


class TestRegistryCollapseWithAliases:
    """Tests for registry collapse when inventory is already reconciled with aliases."""

    def test_already_reconciled_inventory_collapses_via_alias(self) -> None:
        """Registry collapses entries when inventory has canonical source with alias.

        Scenario:
        - Inventory already reconciled: 1 canonical source with alias
        - Registry has entries for both canonical and alias identities
        - Expected: registry collapses to 1 entry
        """
        mock_identity = BackingPodIdentity(
            kind="backing_pods",
            uid_set=frozenset({"pod-uid-0"}),
            name_set=frozenset(),
            service_names=("alertmanager-operated", "kube-prometheus-stack-alertmanager"),
        )

        # Create canonical source (chart service) with operated as alias
        chart_source = _make_source(
            source_id="service:monitoring/kube-prometheus-stack-alertmanager",
            endpoint="http://kube-prometheus-stack-alertmanager.monitoring:9093",
            namespace="monitoring",
            name="kube-prometheus-stack-alertmanager",
        )
        # Add alias for the operated service
        chart_with_alias = replace(
            chart_source,
            aliases=(
                AlertmanagerSourceAlias(
                    alias_name="alertmanager-operated",
                    alias_namespace="monitoring",
                    alias_endpoint="http://alertmanager-operated.monitoring:9093",
                    discovery_method=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
                    management_type="operator-managed",
                ),
            ),
        )

        # Inventory has only the canonical source (operated already merged as alias)
        inventory = _make_inventory([chart_with_alias])

        # Registry has both entries (old persisted state)
        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="monitoring/kube-prometheus-stack-alertmanager",
            desired_state=RegistryDesiredState.DISABLED,
            name="kube-prometheus-stack-alertmanager",
        ))
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="monitoring/alertmanager-operated",
            desired_state=RegistryDesiredState.MANUAL,
            name="alertmanager-operated",
        ))

        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_source_reconciliation_grouping.get_service_backing_identity',
            return_value=mock_identity,
        ):
            cleaned_registry, count = collapse_duplicate_registry_entries(
                registry, inventory, "test-context"
            )

        # Should collapse 1 duplicate
        assert count == 1, f"Expected 1 collapsed, got {count}"
        # Should have 1 entry remaining
        assert len(cleaned_registry.entries) == 1, f"Expected 1 entry, got {len(cleaned_registry.entries)}"
        # Manual entry should be kept (operated has higher priority)
        assert "test-context:monitoring/alertmanager-operated" in cleaned_registry.entries

    def test_chart_beats_headless_when_neither_manual(self) -> None:
        """Chart service wins over headless -operated when neither is manual/tracked.

        Scenario:
        - Same backing pods
        - Neither entry is MANUAL or DISABLED (both use DISCOVERED/neutral state)
        - Expected: chart-facing service becomes canonical (priority 25 > 10)
        """
        mock_identity = BackingPodIdentity(
            kind="backing_pods",
            uid_set=frozenset({"pod-uid-0"}),
            name_set=frozenset(),
            service_names=("alertmanager-operated", "kube-prometheus-stack-alertmanager"),
        )

        operated = _make_source(
            source_id="service:monitoring/alertmanager-operated",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-operated",
        )
        chart = _make_source(
            source_id="service:monitoring/kube-prometheus-stack-alertmanager",
            endpoint="http://kube-prometheus-stack-alertmanager.monitoring:9093",
            namespace="monitoring",
            name="kube-prometheus-stack-alertmanager",
        )

        # Both entries use DISCOVERED state (neutral/default)
        # Priority will be determined by service-name classification
        # Chart (25) > headless (10)
        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="monitoring/alertmanager-operated",
            desired_state=RegistryDesiredState.DISCOVERED,
            name="alertmanager-operated",
        ))
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="monitoring/kube-prometheus-stack-alertmanager",
            desired_state=RegistryDesiredState.DISCOVERED,
            name="kube-prometheus-stack-alertmanager",
        ))

        inventory = _make_inventory([operated, chart])

        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_source_reconciliation_grouping.get_service_backing_identity',
            return_value=mock_identity,
        ):
            cleaned_registry, count = collapse_duplicate_registry_entries(
                registry, inventory, "test-context"
            )

        # Should collapse 1 duplicate
        assert count == 1, f"Expected 1 collapsed, got {count}"
        # Should have 1 entry
        assert len(cleaned_registry.entries) == 1, f"Expected 1 entry, got {len(cleaned_registry.entries)}"
        # Chart should win (priority 25 > 10)
        assert list(cleaned_registry.entries) == [
            "test-context:monitoring/kube-prometheus-stack-alertmanager"
        ]

    def test_manual_tracked_state_wins_over_chart(self) -> None:
        """Manual/tracked desired state survives collapse over chart.

        Scenario:
        - operated is MANUAL (operator-promoted)
        - chart is DISCOVERED (neutral/default)
        - Expected: operated key survives, desired_state preserved as MANUAL
        """
        mock_identity = BackingPodIdentity(
            kind="backing_pods",
            uid_set=frozenset({"pod-uid-0"}),
            name_set=frozenset(),
            service_names=("alertmanager-operated", "kube-prometheus-stack-alertmanager"),
        )

        operated = _make_source(
            source_id="service:monitoring/alertmanager-operated",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-operated",
        )
        chart = _make_source(
            source_id="service:monitoring/kube-prometheus-stack-alertmanager",
            endpoint="http://kube-prometheus-stack-alertmanager.monitoring:9093",
            namespace="monitoring",
            name="kube-prometheus-stack-alertmanager",
        )

        # operated is MANUAL (priority 40), chart is DISCOVERED (neutral)
        # Manual wins over chart even though chart would normally win on priority
        # ( MANUAL=40 > chart=25 )
        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="monitoring/alertmanager-operated",
            desired_state=RegistryDesiredState.MANUAL,
            name="alertmanager-operated",
        ))
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="monitoring/kube-prometheus-stack-alertmanager",
            desired_state=RegistryDesiredState.DISCOVERED,
            name="kube-prometheus-stack-alertmanager",
        ))

        inventory = _make_inventory([operated, chart])

        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_source_reconciliation_grouping.get_service_backing_identity',
            return_value=mock_identity,
        ):
            cleaned_registry, count = collapse_duplicate_registry_entries(
                registry, inventory, "test-context"
            )

        # Should collapse 1 duplicate
        assert count == 1, f"Expected 1 collapsed, got {count}"
        # Should have 1 entry
        assert len(cleaned_registry.entries) == 1, f"Expected 1 entry, got {len(cleaned_registry.entries)}"
        # Manual entry should be kept
        assert "test-context:monitoring/alertmanager-operated" in cleaned_registry.entries
        # Desired state should be preserved as MANUAL
        entry = cleaned_registry.entries["test-context:monitoring/alertmanager-operated"]
        assert entry.desired_state == RegistryDesiredState.MANUAL

    def test_different_backing_pods_remain_separate(self) -> None:
        """Entries with different backing pod UIDs remain separate.

        Scenario:
        - Two Alertmanagers with different pod UIDs
        - Expected: both entries remain, no collapse
        """
        mock_identity_am1 = BackingPodIdentity(
            kind="backing_pods",
            uid_set=frozenset({"pod-uid-am1-0"}),
            name_set=frozenset(),
            service_names=("alertmanager-main",),
        )
        mock_identity_am2 = BackingPodIdentity(
            kind="backing_pods",
            uid_set=frozenset({"pod-uid-am2-0"}),
            name_set=frozenset(),
            service_names=("alertmanager-main",),
        )

        def mock_get_identity(ns: str, name: str, context: str | None = None) -> BackingPodIdentity | None:
            if "monitoring" in ns:
                return mock_identity_am1
            elif "prod" in ns:
                return mock_identity_am2
            return None

        am1 = _make_source(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
        )
        am2 = _make_source(
            source_id="crd:prod/alertmanager-main",
            endpoint="http://alertmanager-main.prod:9093",
            namespace="prod",
            name="alertmanager-main",
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        ))
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="prod/alertmanager-main",
            desired_state=RegistryDesiredState.DISABLED,
        ))

        inventory = _make_inventory([am1, am2])

        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_source_reconciliation_grouping.get_service_backing_identity',
            side_effect=mock_get_identity,
        ):
            cleaned_registry, count = collapse_duplicate_registry_entries(
                registry, inventory, "test-context"
            )

        # Different backing pods = no collapse
        assert count == 0, f"Expected 0 collapsed, got {count}"
        assert len(cleaned_registry.entries) == 2, f"Expected 2 entries, got {len(cleaned_registry.entries)}"

    def test_second_collapse_returns_zero(self) -> None:
        """Second collapse on already-cleaned registry returns count 0.

        Scenario:
        - Run collapse once
        - Run collapse again on cleaned registry
        - Expected: second run returns count 0, entries unchanged
        """
        mock_identity = BackingPodIdentity(
            kind="backing_pods",
            uid_set=frozenset({"pod-uid-0"}),
            name_set=frozenset(),
            service_names=("alertmanager-operated",),
        )

        operated = _make_source(
            source_id="service:monitoring/alertmanager-operated",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-operated",
        )
        chart = _make_source(
            source_id="service:monitoring/kube-prometheus-stack-alertmanager",
            endpoint="http://kube-prometheus-stack-alertmanager.monitoring:9093",
            namespace="monitoring",
            name="kube-prometheus-stack-alertmanager",
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="monitoring/alertmanager-operated",
            desired_state=RegistryDesiredState.MANUAL,
        ))
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="monitoring/kube-prometheus-stack-alertmanager",
            desired_state=RegistryDesiredState.DISABLED,
        ))

        inventory = _make_inventory([operated, chart])

        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_source_reconciliation_grouping.get_service_backing_identity',
            return_value=mock_identity,
        ):
            cleaned1, count1 = collapse_duplicate_registry_entries(
                registry, inventory, "test-context"
            )
            cleaned2, count2 = collapse_duplicate_registry_entries(
                cleaned1, inventory, "test-context"
            )

        # First run collapses 1
        assert count1 == 1
        # Second run collapses 0
        assert count2 == 0
        # Both have same entry count
        assert len(cleaned1.entries) == len(cleaned2.entries) == 1
