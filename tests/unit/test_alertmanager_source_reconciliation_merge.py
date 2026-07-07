"""Unit tests for Alertmanager source reconciliation merge.

Tests for source collapsing and idempotency.
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
from k8s_diag_agent.external_analysis.alertmanager_source_reconciliation_merge import (
    reconcile_alertmanager_sources,
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


class TestReconciliationCollapse:
    """Tests for source collapsing during reconciliation."""

    def test_same_backing_pods_collapse(self) -> None:
        """Two sources with same backing pods collapse to 1 logical source."""
        mock_identity = BackingPodIdentity(
            kind="backing_pods",
            uid_set=frozenset({"pod-uid-0", "pod-uid-1"}),
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

        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_source_reconciliation_grouping.get_service_backing_identity',
            return_value=mock_identity,
        ):
            inventory = _make_inventory([operated, chart])
            reconciled = reconcile_alertmanager_sources(inventory)

        # Should collapse to 1 logical source
        assert len(reconciled.sources) == 1, (
            f"Expected 1 source after reconciliation, got {len(reconciled.sources)}"
        )

        # Canonical should be the chart service
        canonical = list(reconciled.sources.values())[0]
        assert canonical.name == "kube-prometheus-stack-alertmanager"

        # Should have aliases including the operated service
        alias_names = [a.alias_name for a in canonical.aliases]
        assert "alertmanager-operated" in alias_names

    def test_different_backing_pods_remain_separate(self) -> None:
        """Different backing pod UIDs remain as separate sources."""
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

        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_source_reconciliation_grouping.get_service_backing_identity',
            side_effect=mock_get_identity,
        ):
            inventory = _make_inventory([am1, am2])
            reconciled = reconcile_alertmanager_sources(inventory)

        # Should have 2 separate sources
        assert len(reconciled.sources) == 2


class TestIdempotency:
    """Tests for idempotency of reconciliation."""

    def test_idempotent_reconciliation(self) -> None:
        """Running reconciliation twice produces the same inventory."""
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

        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_source_reconciliation_grouping.get_service_backing_identity',
            return_value=mock_identity,
        ):
            inventory = _make_inventory([operated, chart])
            reconciled1 = reconcile_alertmanager_sources(inventory)
            reconciled2 = reconcile_alertmanager_sources(reconciled1)

        # Should produce identical inventories
        assert reconciled1.sources.keys() == reconciled2.sources.keys()
        for key in reconciled1.sources:
            s1 = reconciled1.sources[key]
            s2 = reconciled2.sources[key]
            assert s1.name == s2.name
            assert s1.endpoint == s2.endpoint
            assert len(s1.aliases) == len(s2.aliases)


class TestFallbackBehavior:
    """Tests for fallback behavior when backing pod info is unavailable."""

    def test_fallback_exact_endpoint_match(self) -> None:
        """Same endpoint collapses even without backing pod info."""
        source1 = _make_source(
            source_id="service:monitoring/alertmanager-a",
            endpoint="http://alertmanager.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-a",
        )
        source2 = _make_source(
            source_id="service:monitoring/alertmanager-b",
            endpoint="http://alertmanager.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-b",
        )

        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_source_reconciliation_grouping.get_service_backing_identity',
            return_value=None,
        ):
            inventory = _make_inventory([source1, source2])
            reconciled = reconcile_alertmanager_sources(inventory)

        # Should collapse because same endpoint
        assert len(reconciled.sources) == 1

    def test_different_endpoints_no_collapse(self) -> None:
        """Different endpoints do not collapse."""
        source1 = _make_source(
            source_id="service:monitoring/am1",
            endpoint="http://alertmanager-1.monitoring:9093",
            namespace="monitoring",
            name="am1",
        )
        source2 = _make_source(
            source_id="service:monitoring/am2",
            endpoint="http://alertmanager-2.monitoring:9093",
            namespace="monitoring",
            name="am2",
        )

        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_source_reconciliation_grouping.get_service_backing_identity',
            return_value=None,
        ):
            inventory = _make_inventory([source1, source2])
            reconciled = reconcile_alertmanager_sources(inventory)

        # Should NOT collapse
        assert len(reconciled.sources) == 2
