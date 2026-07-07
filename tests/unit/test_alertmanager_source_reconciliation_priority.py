"""Unit tests for Alertmanager source canonical priority.

Tests canonical source selection priority.
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
    AlertmanagerSourceMode,
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
    origin: AlertmanagerSourceOrigin = AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
    manual_mode: AlertmanagerSourceMode = AlertmanagerSourceMode.NOT_MANUAL,
) -> AlertmanagerSource:
    """Create a test AlertmanagerSource."""
    return AlertmanagerSource(
        source_id=source_id,
        endpoint=endpoint,
        namespace=namespace,
        name=name,
        origin=origin,
        state=AlertmanagerSourceState.DISCOVERED,
        discovered_at=datetime.now(UTC),
        cluster_context="test-context",
        cluster_label="test-cluster",
        manual_source_mode=manual_mode,
    )


def _make_inventory(sources: list[AlertmanagerSource]) -> AlertmanagerSourceInventory:
    """Create a test AlertmanagerSourceInventory."""
    return AlertmanagerSourceInventory(
        sources={s.source_id: s for s in sources},
        cluster_context="test-context",
    )


class TestCanonicalSourcePriority:
    """Tests for canonical source selection priority via behavior."""

    def test_chart_service_becomes_canonical(self) -> None:
        """When operated and chart have same backing pods, chart becomes canonical."""
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
            reconciled = reconcile_alertmanager_sources(inventory)

        # Chart should become canonical (preferred over operated)
        canonical = list(reconciled.sources.values())[0]
        assert canonical.name == "kube-prometheus-stack-alertmanager", (
            f"Chart service should be canonical, got {canonical.name}"
        )

    def test_promoted_source_becomes_canonical(self) -> None:
        """When promoted source and chart have same backing pods, promoted becomes canonical."""
        mock_identity = BackingPodIdentity(
            kind="backing_pods",
            uid_set=frozenset({"pod-uid-0"}),
            name_set=frozenset(),
            service_names=("alertmanager-operated",),
        )

        chart = _make_source(
            source_id="service:monitoring/kube-prometheus-stack-alertmanager",
            endpoint="http://kube-prometheus-stack-alertmanager.monitoring:9093",
            namespace="monitoring",
            name="kube-prometheus-stack-alertmanager",
        )
        promoted = _make_source(
            source_id="service:monitoring/alertmanager-operated",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-operated",
            manual_mode=AlertmanagerSourceMode.OPERATOR_PROMOTED,
        )

        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_source_reconciliation_grouping.get_service_backing_identity',
            return_value=mock_identity,
        ):
            inventory = _make_inventory([chart, promoted])
            reconciled = reconcile_alertmanager_sources(inventory)

        # Promoted source should become canonical
        canonical = list(reconciled.sources.values())[0]
        assert canonical.name == "alertmanager-operated", (
            f"Promoted source should be canonical, got {canonical.name}"
        )

    def test_manual_source_becomes_canonical(self) -> None:
        """When manual and operated have same backing pods, manual becomes canonical."""
        mock_identity = BackingPodIdentity(
            kind="backing_pods",
            uid_set=frozenset({"pod-uid-0"}),
            name_set=frozenset(),
            service_names=("alertmanager-operated",),
        )

        manual = _make_source(
            source_id="manual:http://custom.am.example.com:9093",
            endpoint="http://custom.am.example.com:9093",
            origin=AlertmanagerSourceOrigin.MANUAL,
            name="custom-alertmanager",
        )
        operated = _make_source(
            source_id="service:monitoring/alertmanager-operated",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-operated",
        )

        with patch(
            'k8s_diag_agent.external_analysis.alertmanager_source_reconciliation_grouping.get_service_backing_identity',
            return_value=mock_identity,
        ):
            inventory = _make_inventory([manual, operated])
            reconciled = reconcile_alertmanager_sources(inventory)

        # Manual source should become canonical
        canonical = list(reconciled.sources.values())[0]
        assert canonical.origin == AlertmanagerSourceOrigin.MANUAL, (
            f"Manual source should be canonical, got {canonical.origin}"
        )
