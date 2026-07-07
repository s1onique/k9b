"""Unit tests for Alertmanager registry reconciliation.

Tests for persisted registry duplicate detection and migration.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from k8s_diag_agent.external_analysis.alertmanager_discovery_backing_identity import (
    BackingPodIdentity,
)
from k8s_diag_agent.external_analysis.alertmanager_discovery_models import (
    AlertmanagerSource,
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
    detect_duplicate_registry_entries,
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


class TestRegistryDuplicateDetection:
    """Tests for detecting duplicate entries in persisted registry."""

    def test_detects_duplicates_with_same_backing_pods(self) -> None:
        """Detects duplicate registry entries that share backing pods."""
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

        # Create registry with both entries
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
            duplicates = detect_duplicate_registry_entries(registry, inventory, "test-context")

        # Should detect 1 duplicate pair (chart is duplicate of operated)
        assert len(duplicates) == 1, f"Expected 1 duplicate, got {len(duplicates)}"
        canonical_key, duplicate_key = duplicates[0]
        assert canonical_key == "test-context:monitoring/alertmanager-operated"
        assert duplicate_key == "test-context:monitoring/kube-prometheus-stack-alertmanager"

    def test_no_duplicates_with_different_backing_pods(self) -> None:
        """No duplicates detected when backing pods differ."""
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
            service_names=("alertmanager-alt",),
        )

        def mock_get_identity(ns: str, name: str, context: str | None = None) -> BackingPodIdentity | None:
            if "alertmanager-main" in name:
                return mock_identity_am1
            elif "alertmanager-alt" in name:
                return mock_identity_am2
            return None

        am1 = _make_source(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
        )
        am2 = _make_source(
            source_id="crd:monitoring/alertmanager-alt",
            endpoint="http://alertmanager-alt.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-alt",
        )

        # Create registry with both entries
        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        ))
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="monitoring/alertmanager-alt",
            desired_state=RegistryDesiredState.DISABLED,
        ))

        inventory = _make_inventory([am1, am2])

        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_source_reconciliation_grouping.get_service_backing_identity',
            side_effect=mock_get_identity,
        ):
            duplicates = detect_duplicate_registry_entries(registry, inventory, "test-context")

        # No duplicates (different backing pods)
        assert len(duplicates) == 0, f"Expected 0 duplicates, got {len(duplicates)}"

    def test_empty_registry_returns_empty(self) -> None:
        """Empty registry returns empty duplicate list."""
        operated = _make_source(
            source_id="service:monitoring/alertmanager-operated",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-operated",
        )

        registry = AlertmanagerSourceRegistry()
        inventory = _make_inventory([operated])

        duplicates = detect_duplicate_registry_entries(registry, inventory, "test-context")
        assert duplicates == []

    def test_none_registry_returns_empty(self) -> None:
        """None registry returns empty duplicate list."""
        operated = _make_source(
            source_id="service:monitoring/alertmanager-operated",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-operated",
        )

        inventory = _make_inventory([operated])

        duplicates = detect_duplicate_registry_entries(None, inventory, "test-context")
        assert duplicates == []


class TestRegistryIdempotency:
    """Tests for idempotent registry reconciliation."""

    def test_idempotent_duplicate_detection(self) -> None:
        """Duplicate detection produces consistent results."""
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
            duplicates1 = detect_duplicate_registry_entries(registry, inventory, "test-context")
            duplicates2 = detect_duplicate_registry_entries(registry, inventory, "test-context")

        # Results should be identical
        assert duplicates1 == duplicates2


class TestRegistryCollapse:
    """Tests for collapsing duplicate registry entries."""

    def test_collapse_duplicate_entries_keeps_highest_priority(self) -> None:
        """Collapses duplicates keeping the highest priority entry."""
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
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
        )

        # Create registry with both entries - operated has MANUAL (highest priority)
        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="monitoring/alertmanager-operated",
            desired_state=RegistryDesiredState.MANUAL,
        ))
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.DISABLED,
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
        # Should have 1 entry remaining (the manual one)
        assert len(cleaned_registry.entries) == 1, f"Expected 1 entry, got {len(cleaned_registry.entries)}"
        # The manual entry should be kept
        assert "test-context:monitoring/alertmanager-operated" in cleaned_registry.entries

    def test_collapse_empty_registry(self) -> None:
        """Empty registry returns unchanged with 0 collapsed."""
        operated = _make_source(
            source_id="service:monitoring/alertmanager-operated",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-operated",
        )

        registry = AlertmanagerSourceRegistry()
        inventory = _make_inventory([operated])

        cleaned_registry, count = collapse_duplicate_registry_entries(
            registry, inventory, "test-context"
        )

        assert count == 0
        assert len(cleaned_registry.entries) == 0

    def test_collapse_no_duplicates(self) -> None:
        """No collapse when entries are for different backing pods."""
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
            service_names=("alertmanager-alt",),
        )

        def mock_get_identity(ns: str, name: str, context: str | None = None) -> BackingPodIdentity | None:
            if "alertmanager-main" in name:
                return mock_identity_am1
            elif "alertmanager-alt" in name:
                return mock_identity_am2
            return None

        am1 = _make_source(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
        )
        am2 = _make_source(
            source_id="crd:monitoring/alertmanager-alt",
            endpoint="http://alertmanager-alt.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-alt",
        )

        registry = AlertmanagerSourceRegistry()
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="monitoring/alertmanager-main",
            desired_state=RegistryDesiredState.MANUAL,
        ))
        registry.add_entry(RegistryEntry(
            cluster_context="test-context",
            canonical_identity="monitoring/alertmanager-alt",
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

        # No collapse (different backing pods)
        assert count == 0
        assert len(cleaned_registry.entries) == 2

    def test_collapse_idempotent(self) -> None:
        """Running collapse twice produces same result."""
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
            # Run again on the already-cleaned registry
            cleaned2, count2 = collapse_duplicate_registry_entries(
                cleaned1, inventory, "test-context"
            )

        # First run should collapse 1
        assert count1 == 1
        # Second run should collapse 0
        assert count2 == 0
        # Both should have same entry count
        assert len(cleaned1.entries) == len(cleaned2.entries) == 1
