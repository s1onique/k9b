"""Unit tests for cluster_label preservation.

Tests cover:
- cluster_label preservation during verification
- cluster_label preservation during merge/deduplication
- cluster_label preservation during alias resolution
- Multi-cluster scenarios
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
    AlertmanagerSourceInventory,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
    merge_deduplicate_inventory,
    verify_and_update_inventory,
)


class TestClusterLabelVerification:
    """Tests for cluster_label preservation during verification."""

    def test_verify_and_update_inventory_preserves_cluster_label(self) -> None:
        """Regression test: verify_and_update_inventory must preserve cluster_label."""
        inventory = AlertmanagerSourceInventory()

        # Add a source WITH cluster_label set
        source = AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager:9093",
            namespace="monitoring",
            name="main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
            cluster_label="prod-cluster-a",
            cluster_context="prod-context",
        )
        inventory.add_source(source)

        # Mock verification - source passes
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = json.dumps({
                "status": "success",
                "data": {"versionInfo": {"version": "0.25.0"}}
            }).encode()

            mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

            verified = verify_and_update_inventory(inventory)

        # cluster_label MUST be preserved after verification
        assert verified.sources["crd:monitoring/main"].cluster_label == "prod-cluster-a"
        assert verified.sources["crd:monitoring/main"].cluster_context == "prod-context"
        # Also verify merged_provenances is preserved
        assert AlertmanagerSourceOrigin.ALERTMANAGER_CRD in verified.sources["crd:monitoring/main"].merged_provenances

    def test_verify_and_update_inventory_preserves_cluster_label_degraded(self) -> None:
        """Regression test: verify_and_update_inventory preserves cluster_label on degraded sources."""
        import urllib.error

        inventory = AlertmanagerSourceInventory()

        source = AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager:9093",
            namespace="monitoring",
            name="main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
            cluster_label="staging-cluster-b",
            cluster_context="staging-context",
        )
        inventory.add_source(source)

        # Mock verification - source fails
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

            verified = verify_and_update_inventory(inventory)

        # cluster_label MUST be preserved even when degraded
        assert verified.sources["crd:monitoring/main"].cluster_label == "staging-cluster-b"
        assert verified.sources["crd:monitoring/main"].cluster_context == "staging-context"
        assert verified.sources["crd:monitoring/main"].state == AlertmanagerSourceState.DEGRADED


@pytest.mark.mock_kubectl
class TestClusterLabelMerge:
    """Tests for cluster_label preservation during merge."""

    def test_merge_deduplicate_inventory_preserves_cluster_label(self) -> None:
        """Regression test: merge_deduplicate_inventory must preserve cluster_label."""
        inventory = AlertmanagerSourceInventory()

        # CRD source with cluster_label
        crd_source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            cluster_label="prod-cluster-a",
            cluster_context="prod-context",
        )

        # Prometheus config source (same namespace/name) - should merge with CRD
        prom_source = AlertmanagerSource(
            source_id="prom-crd-config:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG,
            cluster_label="prod-cluster-a",  # Same cluster label
            cluster_context="prod-context",  # Same cluster context
        )

        inventory.add_source(crd_source)
        inventory.add_source(prom_source)

        # Dedup
        result = merge_deduplicate_inventory(inventory)

        # After dedup: 1 source
        assert len(result.sources) == 1

        # cluster_label MUST be preserved in merged source
        merged = next(iter(result.sources.values()))
        assert merged.cluster_label == "prod-cluster-a"
        assert merged.cluster_context == "prod-context"
        # Both provenances should be merged
        assert AlertmanagerSourceOrigin.ALERTMANAGER_CRD in merged.merged_provenances
        assert AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG in merged.merged_provenances

    def test_merge_deduplicate_inventory_preserves_cluster_label_manual_wins(self) -> None:
        """Regression test: merge_deduplicate_inventory preserves cluster_label when manual wins."""
        inventory = AlertmanagerSourceInventory()

        # Manual source with cluster_label
        manual_source = AlertmanagerSource(
            source_id="monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
            cluster_label="manual-cluster-x",
            cluster_context="manual-context-x",
        )

        # Discovered source without cluster_label (simulating legacy source)
        crd_source = AlertmanagerSource(
            source_id="monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            # Note: no cluster_label on this one
        )

        inventory.add_source(manual_source)
        inventory.add_source(crd_source)

        result = merge_deduplicate_inventory(inventory)

        # Manual should win
        assert len(result.sources) == 1
        merged = next(iter(result.sources.values()))
        assert merged.origin == AlertmanagerSourceOrigin.MANUAL
        # cluster_label from manual source must be preserved
        assert merged.cluster_label == "manual-cluster-x"
        assert merged.cluster_context == "manual-context-x"

    def test_merge_deduplicate_inventory_single_source_preserves_cluster_label(self) -> None:
        """Regression test: single source (no merge) preserves cluster_label."""
        inventory = AlertmanagerSourceInventory()

        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            cluster_label="test-cluster-1",
            cluster_context="test-context-1",
        )

        inventory.add_source(source)

        result = merge_deduplicate_inventory(inventory)

        # No merge needed, but cluster_label should still be preserved
        assert len(result.sources) == 1
        merged = next(iter(result.sources.values()))
        assert merged.cluster_label == "test-cluster-1"
        assert merged.cluster_context == "test-context-1"


@pytest.mark.mock_kubectl
class TestClusterLabelRoundtrip:
    """End-to-end tests for cluster_label through all transforms."""

    def test_cluster_label_roundtrip_through_all_transforms(self) -> None:
        """End-to-end regression test: cluster_label survives through all transforms."""
        # Step 1: Create inventory with source that has cluster_label
        inventory = AlertmanagerSourceInventory(cluster_context="test-context")

        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
            cluster_label="e2e-test-cluster",
            cluster_context="e2e-test-context",
        )
        inventory.add_source(source)

        # Verify cluster_label exists before transforms
        assert inventory.sources["crd:monitoring/alertmanager-main"].cluster_label == "e2e-test-cluster"

        # Step 2: Verify and update (simulate with identity_key preserved)
        verified = verify_and_update_inventory(inventory)

        # cluster_label must survive verification
        assert verified.sources["crd:monitoring/alertmanager-main"].cluster_label == "e2e-test-cluster"
        assert verified.sources["crd:monitoring/alertmanager-main"].cluster_context == "e2e-test-context"

        # Step 3: Merge/deduplicate
        result = merge_deduplicate_inventory(verified)

        # cluster_label must survive deduplication
        assert len(result.sources) == 1
        final_source = next(iter(result.sources.values()))
        assert final_source.cluster_label == "e2e-test-cluster"
        assert final_source.cluster_context == "e2e-test-context"

        # Step 4: Verify serialization preserves cluster_label
        serialized = final_source.to_dict()
        assert serialized.get("cluster_label") == "e2e-test-cluster"
        assert serialized.get("cluster_context") == "e2e-test-context"

        # Step 5: Verify deserialization restores cluster_label
        restored = AlertmanagerSource.from_dict(serialized)
        assert restored.cluster_label == "e2e-test-cluster"
        assert restored.cluster_context == "e2e-test-context"


class TestMultiClusterScenario:
    """Tests for multi-cluster scenarios."""

    def test_multi_cluster_sources_preserve_distinct_labels(self) -> None:
        """Regression test: sources from different clusters keep their distinct cluster_labels."""
        # Cluster A source
        cluster_a_source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-a.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            cluster_label="cluster-a",
            cluster_context="context-a",
        )

        # Cluster B source (same namespace/name, different endpoint)
        cluster_b_source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-b.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            cluster_label="cluster-b",
            cluster_context="context-b",
        )

        inventory_a = AlertmanagerSourceInventory()
        inventory_a.add_source(cluster_a_source)

        inventory_b = AlertmanagerSourceInventory()
        inventory_b.add_source(cluster_b_source)

        # Each inventory should keep its own cluster_label
        assert inventory_a.sources["crd:monitoring/alertmanager-main"].cluster_label == "cluster-a"
        assert inventory_b.sources["crd:monitoring/alertmanager-main"].cluster_label == "cluster-b"

        # After verification
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = json.dumps({
                "status": "success",
                "data": {"versionInfo": {"version": "0.25.0"}}
            }).encode()

            mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

            verified_a = verify_and_update_inventory(inventory_a)
            verified_b = verify_and_update_inventory(inventory_b)

        # cluster_labels must remain distinct
        assert verified_a.sources["crd:monitoring/alertmanager-main"].cluster_label == "cluster-a"
        assert verified_b.sources["crd:monitoring/alertmanager-main"].cluster_label == "cluster-b"
