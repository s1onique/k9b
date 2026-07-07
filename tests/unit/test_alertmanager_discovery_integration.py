"""Unit tests for orchestrated Alertmanager discovery.

Tests cover:
- Integration with discover_alertmanagers
- Verification and inventory update
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
    AlertmanagerSourceInventory,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
    CRDDiscoveryStrategy,
    DiscoveryResult,
    PrometheusCRDConfigDiscoveryStrategy,
    ServiceHeuristicDiscoveryStrategy,
    build_endpoint_for_manual,
    discover_alertmanagers,
    verify_and_update_inventory,
)


class TestDiscoverAlertmanagers:
    """Tests for orchestrated discovery."""

    def test_discover_alertmanagers_with_manual_sources(self) -> None:
        """Test that manual sources are preserved during discovery.

        FIX: Mock all three strategies to avoid real subprocess calls.
        Previously only CRDStrategy was mocked, causing Prometheus and Service
        strategies to run real kubectl calls (~60s per test).
        Now all strategies are mocked for deterministic sub-second execution.
        """
        manual = AlertmanagerSource(
            source_id="manual:custom",
            endpoint="http://custom:9093",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
        )

        with (
            patch.object(CRDDiscoveryStrategy, "discover") as mock_crd,
            patch.object(PrometheusCRDConfigDiscoveryStrategy, "discover") as mock_prom,
            patch.object(ServiceHeuristicDiscoveryStrategy, "discover") as mock_service,
        ):
            # CRD returns a conflicting source that manual should override
            mock_crd.return_value = DiscoveryResult(
                sources=(
                    AlertmanagerSource(
                        source_id="manual:custom",
                        endpoint="http://discovered:9093",
                        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
                    ),
                ),
                errors=(),
                strategy="alertmanager-crd",
            )

            # Prometheus returns empty (simulates no Prometheus CRDs)
            mock_prom.return_value = DiscoveryResult(
                sources=(),
                errors=(),
                strategy="prometheus-crd-config",
            )

            # Service returns empty (simulates no service matches)
            mock_service.return_value = DiscoveryResult(
                sources=(),
                errors=(),
                strategy="service-heuristic",
            )

            result = discover_alertmanagers(manual_sources=(manual,))

        # Manual should be preserved
        assert "manual:custom" in result.sources
        assert result.sources["manual:custom"].origin == AlertmanagerSourceOrigin.MANUAL


class TestVerifyAndUpdateInventory:
    """Tests for inventory verification and update."""

    def test_verify_and_update_inventory(self) -> None:
        """Test that verification updates inventory states correctly."""
        inventory = AlertmanagerSourceInventory()

        # Add a CRD source
        inventory.add_source(AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager:9093",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
        ))

        # Add a manual source (should not be verified)
        inventory.add_source(AlertmanagerSource(
            source_id="manual:custom",
            endpoint="http://custom:9093",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
        ))

        # Mock verification - CRD source passes
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

        # CRD source should be auto-tracked
        assert verified.sources["crd:monitoring/main"].state == AlertmanagerSourceState.AUTO_TRACKED
        assert verified.sources["crd:monitoring/main"].verified_version == "0.25.0"

        # Manual source should remain manual
        assert verified.sources["manual:custom"].state == AlertmanagerSourceState.MANUAL

    def test_verify_and_update_inventory_degraded(self) -> None:
        """Test that failing verification marks sources as degraded."""
        import urllib.error

        inventory = AlertmanagerSourceInventory()

        # Add a CRD source
        inventory.add_source(AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager:9093",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
        ))

        # Mock verification - source fails
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

            verified = verify_and_update_inventory(inventory)

        # Source should be degraded
        assert verified.sources["crd:monitoring/main"].state == AlertmanagerSourceState.DEGRADED
        assert verified.sources["crd:monitoring/main"].last_error is not None


class TestBuildEndpointForManual:
    """Tests for manual endpoint building utility."""

    def test_build_endpoint_for_manual(self) -> None:
        """Test building a manual source from endpoint."""
        source = build_endpoint_for_manual(
            endpoint="alertmanager.monitoring.svc.cluster.local:9093",
            namespace="monitoring",
            name="main",
        )

        assert source.origin == AlertmanagerSourceOrigin.MANUAL
        assert source.state == AlertmanagerSourceState.MANUAL
        assert source.endpoint == "http://alertmanager.monitoring.svc.cluster.local:9093"
        assert source.namespace == "monitoring"
        assert source.name == "main"
        assert "manual:" in source.source_id

    def test_build_endpoint_for_manual_with_http_prefix(self) -> None:
        """Test that http:// prefix is handled correctly."""
        source = build_endpoint_for_manual(
            endpoint="http://alertmanager:9093",
        )

        assert source.endpoint == "http://alertmanager:9093"
