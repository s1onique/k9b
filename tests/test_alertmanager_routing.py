"""Tests for Alertmanager routing logic.

ACT-K9B-HULK-PROMOTION-LIVE-WIRE-AND-PROJECTION-TRUTH01-CORRECTION11

Verifies:
- In-cluster mode always uses direct routing (no port-forward)
- Out-of-cluster mode preserves port-forward behavior for cluster-internal FQDNs
- All hostname formats handled correctly
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.health.loop_alertmanager_snapshot_collection import (
    determine_port_forward_need,
)


class MockAlertmanagerSource:
    """Minimal mock for AlertmanagerSource."""

    def __init__(
        self,
        endpoint: str,
        name: str = "alertmanager",
    ) -> None:
        self.endpoint = endpoint
        self.name = name


class TestInClusterRouting:
    """Tests for in-cluster routing authority."""

    @pytest.mark.parametrize(
        "endpoint",
        [
            "http://alertmanager-operated/api/v2",
            "http://alertmanager-operated.monitoring/api/v2",
            "http://alertmanager-operated.monitoring.svc.cluster.local/api/v2",
            "http://custom-alertmanager.monitoring.svc.cluster.local:9093/api/v2",
        ],
    )
    def test_in_cluster_skips_port_forward(self, endpoint: str) -> None:
        """In-cluster mode always uses direct routing regardless of hostname format."""
        source = MockAlertmanagerSource(endpoint=endpoint)
        needs_pf, service_name = determine_port_forward_need(
            endpoint=endpoint,
            selected_source=source,
            cluster_context="in-cluster",
        )
        assert needs_pf is False
        assert service_name is None

    def test_in_cluster_single_label(self) -> None:
        """In-cluster single-label Service names use direct routing."""
        source = MockAlertmanagerSource(endpoint="http://alertmanager-operated/api/v2")
        needs_pf, _ = determine_port_forward_need(
            endpoint="http://alertmanager-operated/api/v2",
            selected_source=source,
            cluster_context="in-cluster",
        )
        assert needs_pf is False


class TestOutOfClusterRouting:
    """Tests for out-of-cluster routing behavior."""

    def test_out_of_cluster_localhost_skips_pf(self) -> None:
        """Out-of-cluster localhost does not use port-forward."""
        source = MockAlertmanagerSource(endpoint="http://localhost:9093/api/v2")
        needs_pf, _ = determine_port_forward_need(
            endpoint="http://localhost:9093/api/v2",
            selected_source=source,
            cluster_context="out-of-cluster",
        )
        assert needs_pf is False

    def test_out_of_cluster_127_skips_pf(self) -> None:
        """Out-of-cluster 127.0.0.1 does not use port-forward."""
        source = MockAlertmanagerSource(endpoint="http://127.0.0.1:9093/api/v2")
        needs_pf, _ = determine_port_forward_need(
            endpoint="http://127.0.0.1:9093/api/v2",
            selected_source=source,
            cluster_context="out-of-cluster",
        )
        assert needs_pf is False

    def test_out_of_cluster_service_fqdn_uses_pf(self) -> None:
        """Out-of-cluster cluster-internal FQDN uses port-forward."""
        source = MockAlertmanagerSource(
            endpoint="http://alertmanager-operated.monitoring.svc.cluster.local:9093/api/v2"
        )
        needs_pf, service_name = determine_port_forward_need(
            endpoint="http://alertmanager-operated.monitoring.svc.cluster.local:9093/api/v2",
            selected_source=source,
            cluster_context="out-of-cluster",
        )
        assert needs_pf is True
        assert service_name == "alertmanager-operated"

    def test_out_of_cluster_extracts_service_name(self) -> None:
        """Out-of-cluster extracts service name from FQDN first component."""
        source = MockAlertmanagerSource(
            endpoint="http://my-custom-alertmanager.monitoring:9093/api/v2"
        )
        needs_pf, service_name = determine_port_forward_need(
            endpoint="http://my-custom-alertmanager.monitoring:9093/api/v2",
            selected_source=source,
            cluster_context="out-of-cluster",
        )
        assert needs_pf is True
        assert service_name == "my-custom-alertmanager"


class TestRoutingEdgeCases:
    """Tests for edge cases in routing logic."""

    def test_none_cluster_context_defaults_to_out_of_cluster(self) -> None:
        """None cluster_context defaults to out-of-cluster behavior."""
        source = MockAlertmanagerSource(
            endpoint="http://alertmanager-operated.monitoring:9093/api/v2"
        )
        needs_pf, _ = determine_port_forward_need(
            endpoint="http://alertmanager-operated.monitoring:9093/api/v2",
            selected_source=source,
            cluster_context=None,
        )
        assert needs_pf is True

    def test_empty_endpoint_skips_pf(self) -> None:
        """Empty endpoint does not use port-forward."""
        source = MockAlertmanagerSource(endpoint="")
        needs_pf, _ = determine_port_forward_need(
            endpoint="",
            selected_source=source,
            cluster_context="out-of-cluster",
        )
        assert needs_pf is False

    def test_no_scheme_skips_pf(self) -> None:
        """Endpoint without scheme does not use port-forward."""
        source = MockAlertmanagerSource(endpoint="alertmanager-operated.monitoring:9093")
        needs_pf, _ = determine_port_forward_need(
            endpoint="alertmanager-operated.monitoring:9093",
            selected_source=source,
            cluster_context="out-of-cluster",
        )
        assert needs_pf is False
