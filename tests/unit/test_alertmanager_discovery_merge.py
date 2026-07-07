"""Unit tests for merge/deduplication logic.

Tests cover:
- Source merging by same namespace/name
- Origin precedence during merge
- Different endpoints remain separate
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
    AlertmanagerSourceInventory,
    AlertmanagerSourceOrigin,
    merge_deduplicate_inventory,
)


@pytest.mark.mock_kubectl
class TestMergeDeduplicate:
    """Tests for merge_deduplicate_inventory function."""

    def test_merge_deduplicate_inventory_different_origins_same_endpoint(self) -> None:
        """Test that merge_deduplicate_inventory merges CRD + Config sources with same namespace/name.

        Service heuristic stays separate when names differ (no aggressive merging per user requirement).
        """
        inventory = AlertmanagerSourceInventory()

        # CRD source
        crd_source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        )

        # Prometheus config source (same namespace/name) - should merge with CRD
        prom_source = AlertmanagerSource(
            source_id="prom-crd-config:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG,
        )

        # Service heuristic source (same name) - should also merge
        service_source = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",  # Same name!
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )

        inventory.add_source(crd_source)
        inventory.add_source(prom_source)
        inventory.add_source(service_source)

        # Before dedup: 3 sources
        assert len(inventory.sources) == 3

        # Dedup
        result = merge_deduplicate_inventory(inventory)

        # After dedup: 1 source (all have same namespace/name, merge into one)
        assert len(result.sources) == 1

        # Get the merged source
        merged = next(iter(result.sources.values()))

        # CRD source should win (highest priority)
        assert merged.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD

        # Merged provenances should include all 3 origins
        assert len(merged.merged_provenances) == 3
        assert AlertmanagerSourceOrigin.ALERTMANAGER_CRD in merged.merged_provenances
        assert AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG in merged.merged_provenances
        assert AlertmanagerSourceOrigin.SERVICE_HEURISTIC in merged.merged_provenances

    def test_merge_deduplicate_inventory_manual_preserved(self) -> None:
        """Test that merge_deduplicate_inventory preserves manual source (same source_id)."""
        inventory = AlertmanagerSourceInventory()

        # Add manual source first (same source_id as would be discovered)
        manual_source = AlertmanagerSource(
            source_id="monitoring/alertmanager-main",  # Same ID as discovered
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.MANUAL,
        )

        # Add same endpoint discovered via CRD (same source_id)
        crd_source = AlertmanagerSource(
            source_id="monitoring/alertmanager-main",  # Same ID
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        )

        inventory.add_source(manual_source)
        inventory.add_source(crd_source)

        # Manual should win due to precedence (same source_id, manual takes priority)
        assert len(inventory.sources) == 1
        assert inventory.sources[list(inventory.sources.keys())[0]].origin == AlertmanagerSourceOrigin.MANUAL

        # After dedup: still 1 source with merged provenance
        result = merge_deduplicate_inventory(inventory)
        assert len(result.sources) == 1

        merged = next(iter(result.sources.values()))
        assert merged.origin == AlertmanagerSourceOrigin.MANUAL
        # Manual is in merged_provenances (via post_init)
        assert AlertmanagerSourceOrigin.MANUAL in merged.merged_provenances

    def test_merge_deduplicate_inventory_different_endpoints_not_merged(self) -> None:
        """Test that sources with different endpoints are not merged."""
        inventory = AlertmanagerSourceInventory()

        # Add two different endpoints (both via service heuristic)
        source1 = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-1",
            endpoint="http://alertmanager-1.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-1",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )

        source2 = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-2",
            endpoint="http://alertmanager-2.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-2",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )

        inventory.add_source(source1)
        inventory.add_source(source2)

        assert len(inventory.sources) == 2

        result = merge_deduplicate_inventory(inventory)

        # Still 2 sources (different endpoints)
        assert len(result.sources) == 2


@pytest.mark.mock_kubectl
class TestCanonicalIdentity:
    """Tests for canonical identity tiered approach."""

    def test_canonical_identity_tiered_approach(self) -> None:
        """Test that canonical_identity uses tiered approach: CRD/Config > Endpoint.

        CRD and Config tiers use namespace/name for merging (same canonical key).
        Service heuristic falls back to normalized endpoint.
        """
        # CRD and Config sources with same namespace/name share canonical identity
        crd_source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        )
        assert crd_source.canonical_identity == "monitoring/alertmanager-main"

        config_source = AlertmanagerSource(
            source_id="prom-crd-config:monitoring/alertmanager-main",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG,
        )
        # Config uses same canonical identity as CRD for proper merging
        assert config_source.canonical_identity == "monitoring/alertmanager-main"

        # Service heuristic with same namespace/name as CRD → same canonical identity
        service_source = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-operated",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-operated",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        assert service_source.canonical_identity == "monitoring/alertmanager-operated"


@pytest.mark.mock_kubectl
class TestMergeMixedInventory:
    """Tests for mixed inventory merge scenarios."""

    def test_merge_deduplicate_service_heuristics_different_endpoints_not_merged(self) -> None:
        """Test that SERVICE_HEURISTIC sources with different endpoints are NOT merged."""
        inventory = AlertmanagerSourceInventory()

        am1 = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-1",
            endpoint="http://alertmanager-1.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-1",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )

        am2 = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-2",
            endpoint="http://alertmanager-2.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-2",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )

        inventory.add_source(am1)
        inventory.add_source(am2)

        result = merge_deduplicate_inventory(inventory)

        # After dedup: 2 sources (different endpoints = different Alertmanagers)
        assert len(result.sources) == 2

    def test_merge_deduplicate_service_with_crd_prefers_crd(self) -> None:
        """Test that CRD source wins over SERVICE_HEURISTIC source when names match."""
        inventory = AlertmanagerSourceInventory()

        # CRD source
        crd_source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        )

        # Service heuristic with SAME name as CRD (shares canonical identity)
        service_source = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",  # Same name as CRD!
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )

        inventory.add_source(crd_source)
        inventory.add_source(service_source)

        result = merge_deduplicate_inventory(inventory)

        # CRD should win (higher priority origin)
        assert len(result.sources) == 1
        merged = next(iter(result.sources.values()))
        assert merged.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
        assert merged.name == "alertmanager-main"

    def test_merge_deduplicate_mixed_inventory_two_groups_two_sources(self) -> None:
        """Test mixed inventory: 2 SERVICE_HEURISTIC pairs = 2 separate logical Alertmanagers."""
        # Group A: AM-A (alertmanager-operated + kube-prometheus-stack-alertmanager)
        am_a_operated = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-operated",
            endpoint="http://alertmanager-main.monitoring:9093",  # AM-A endpoint
            namespace="monitoring",
            name="alertmanager-operated",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )

        am_a_chart = AlertmanagerSource(
            source_id="service:monitoring/kube-prometheus-stack-alertmanager",
            endpoint="http://alertmanager-main.monitoring:9093",  # AM-A endpoint (same!)
            namespace="monitoring",
            name="kube-prometheus-stack-alertmanager",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )

        # Group B: AM-B (standalone, different endpoint)
        am_b_standalone = AlertmanagerSource(
            source_id="service:monitoring/another-standalone-alertmanager",
            endpoint="http://alertmanager-backup.monitoring:9093",  # AM-B endpoint (different!)
            namespace="monitoring",
            name="another-standalone-alertmanager",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )

        inventory = AlertmanagerSourceInventory()
        inventory.add_source(am_a_operated)
        inventory.add_source(am_a_chart)
        inventory.add_source(am_b_standalone)

        assert len(inventory.sources) == 3

        result = merge_deduplicate_inventory(inventory)

        # After dedup: 2 sources
        assert len(result.sources) == 2
