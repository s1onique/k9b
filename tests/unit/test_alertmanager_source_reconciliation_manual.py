"""Unit tests for Alertmanager manual source preservation policy.

Tests that manual sources follow the collapse policy:
- Manual sources are not collapsed away
- When manual and discovered share backing pods, manual wins canonical
- Discovered sources become aliases
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


class TestManualSourcePolicyA:
    """Policy A: Manual sources are not collapsed away.

    When a manual source and a discovered source share backing pods,
    the manual source wins canonical, and the discovered source
    becomes an alias.
    """

    def test_manual_source_becomes_canonical_when_same_backing_pods(self) -> None:
        """Manual source becomes canonical when it shares backing pods with discovered."""
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

        # Manual should be canonical
        canonical = list(reconciled.sources.values())[0]
        assert canonical.origin == AlertmanagerSourceOrigin.MANUAL
        assert canonical.name == "custom-alertmanager"

        # Total sources: 1 (manual is canonical, operated is alias)
        assert len(reconciled.sources) == 1

    def test_manual_source_not_collapsed_away(self) -> None:
        """Manual source is preserved even when discovered source has same backing."""
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

        # Manual source should still exist in inventory
        manual_keys = [
            k for k, v in reconciled.sources.items()
            if v.origin == AlertmanagerSourceOrigin.MANUAL
        ]
        assert len(manual_keys) == 1, (
            f"Manual source should be preserved, got {len(manual_keys)}"
        )


class TestNoDuplicatePromotion:
    """Collapsed alias does not appear as independently promotable."""

    def test_alias_not_independent_source(self) -> None:
        """Collapsed alias source_ids do not appear as separate sources."""
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

        # After reconciliation, should have only 1 source
        assert len(reconciled.sources) == 1

        # The source_id of the alias should not appear as a separate key
        source_ids = set(reconciled.sources.keys())
        # Either chart is canonical and operated is alias (key is chart identity)
        # or vice versa, but in either case only one key exists
        assert len(source_ids) == 1
