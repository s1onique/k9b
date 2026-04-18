"""Unit tests for Alertmanager auto-discovery module.

Tests cover:
- CRD discovery success
- Verification failure handling
- Duplicate merge with manual precedence
- Missing source grace behavior
- Inventory serialization
"""

from __future__ import annotations

import json
import urllib.error
from datetime import UTC, datetime
from typing import Any
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
    VerificationResult,
    build_endpoint_for_manual,
    discover_alertmanagers,
    verify_alertmanager_endpoint,
    verify_and_update_inventory,
)

# --- Model Tests ---

def test_source_identity_key() -> None:
    """Test that source_id is used as identity key."""
    source = AlertmanagerSource(
        source_id="crd:monitoring/main",
        endpoint="http://alertmanager:9093",
    )
    assert source.identity_key == "crd:monitoring/main"


def test_source_endpoint_normalization() -> None:
    """Test that endpoint trailing slashes are removed."""
    source = AlertmanagerSource(
        source_id="test",
        endpoint="http://alertmanager:9093/",
    )
    assert source.endpoint == "http://alertmanager:9093"


def test_source_to_dict_roundtrip() -> None:
    """Test source serialization and deserialization."""
    original = AlertmanagerSource(
        source_id="crd:monitoring/main",
        endpoint="http://alertmanager:9093",
        namespace="monitoring",
        name="main",
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        state=AlertmanagerSourceState.AUTO_TRACKED,
        verified_version="0.25.0",
        confidence_hints=("from-crd", "namespace=monitoring"),
    )
    
    serialized = original.to_dict()
    restored = AlertmanagerSource.from_dict(serialized)
    
    assert restored.source_id == original.source_id
    assert restored.endpoint == original.endpoint
    assert restored.namespace == original.namespace
    assert restored.name == original.name
    assert restored.origin == original.origin
    assert restored.state == original.state
    assert restored.verified_version == original.verified_version
    assert restored.confidence_hints == original.confidence_hints


def test_source_origin_enum_values() -> None:
    """Verify all expected origin values exist."""
    expected = {"manual", "alertmanager-crd", "prometheus-crd-config", "service-heuristic"}
    actual = {s.value for s in AlertmanagerSourceOrigin}
    assert actual == expected


def test_source_state_enum_values() -> None:
    """Verify all expected state values exist."""
    expected = {"discovered", "auto-tracked", "degraded", "missing", "manual"}
    actual = {s.value for s in AlertmanagerSourceState}
    assert actual == expected


# --- Inventory Tests ---

def test_inventory_add_source() -> None:
    """Test adding sources to inventory."""
    inventory = AlertmanagerSourceInventory()
    
    source = AlertmanagerSource(
        source_id="crd:monitoring/main",
        endpoint="http://alertmanager:9093",
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
    )
    
    inventory.add_source(source)
    
    assert len(inventory.sources) == 1
    assert "crd:monitoring/main" in inventory.sources


def test_inventory_manual_precedence() -> None:
    """Manual sources must not be overwritten by discovered sources."""
    inventory = AlertmanagerSourceInventory()
    
    # Add manual source first
    manual = AlertmanagerSource(
        source_id="manual:custom",
        endpoint="http://custom:9093",
        origin=AlertmanagerSourceOrigin.MANUAL,
        state=AlertmanagerSourceState.MANUAL,
    )
    inventory.add_source(manual)
    
    # Try to add a discovered source with the same identity
    discovered = AlertmanagerSource(
        source_id="manual:custom",
        endpoint="http://different:9093",
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
    )
    inventory.add_source(discovered)
    
    # Manual should still be there
    assert inventory.sources["manual:custom"].origin == AlertmanagerSourceOrigin.MANUAL
    assert inventory.sources["manual:custom"].endpoint == "http://custom:9093"


def test_inventory_manual_replaces_discovered() -> None:
    """Manual sources should replace discovered sources with same identity."""
    inventory = AlertmanagerSourceInventory()
    
    # Add discovered source first
    discovered = AlertmanagerSource(
        source_id="test:same",
        endpoint="http://discovered:9093",
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
    )
    inventory.add_source(discovered)
    
    # Add manual source with same ID
    manual = AlertmanagerSource(
        source_id="test:same",
        endpoint="http://manual:9093",
        origin=AlertmanagerSourceOrigin.MANUAL,
        state=AlertmanagerSourceState.MANUAL,
    )
    inventory.add_source(manual)
    
    # Manual should win
    assert inventory.sources["test:same"].origin == AlertmanagerSourceOrigin.MANUAL


def test_inventory_origin_priority() -> None:
    """Higher priority origin should replace lower priority."""
    inventory = AlertmanagerSourceInventory()
    
    # Add lower priority source (service heuristic)
    low_priority = AlertmanagerSource(
        source_id="test:priority",
        endpoint="http://low:9093",
        origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
    )
    inventory.add_source(low_priority)
    
    # Add higher priority source (CRD)
    high_priority = AlertmanagerSource(
        source_id="test:priority",
        endpoint="http://high:9093",
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
    )
    inventory.add_source(high_priority)
    
    # CRD should win
    assert inventory.sources["test:priority"].origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD


def test_inventory_get_by_origin() -> None:
    """Test filtering sources by origin."""
    inventory = AlertmanagerSourceInventory()
    
    sources = [
        AlertmanagerSource(
            source_id="crd:test",
            endpoint="http://crd:9093",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        ),
        AlertmanagerSource(
            source_id="manual:test",
            endpoint="http://manual:9093",
            origin=AlertmanagerSourceOrigin.MANUAL,
        ),
        AlertmanagerSource(
            source_id="service:test",
            endpoint="http://service:9093",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        ),
    ]
    
    for s in sources:
        inventory.add_source(s)
    
    crd_sources = inventory.get_by_origin(AlertmanagerSourceOrigin.ALERTMANAGER_CRD)
    assert len(crd_sources) == 1
    assert crd_sources[0].source_id == "crd:test"


def test_inventory_get_by_state() -> None:
    """Test filtering sources by state."""
    inventory = AlertmanagerSourceInventory()
    
    sources = [
        AlertmanagerSource(
            source_id="test:auto",
            endpoint="http://auto:9093",
            state=AlertmanagerSourceState.AUTO_TRACKED,
        ),
        AlertmanagerSource(
            source_id="test:manual",
            endpoint="http://manual:9093",
            state=AlertmanagerSourceState.MANUAL,
        ),
        AlertmanagerSource(
            source_id="test:degraded",
            endpoint="http://degraded:9093",
            state=AlertmanagerSourceState.DEGRADED,
        ),
    ]
    
    for s in sources:
        inventory.add_source(s)
    
    auto_sources = inventory.get_by_state(AlertmanagerSourceState.AUTO_TRACKED)
    assert len(auto_sources) == 1
    assert auto_sources[0].source_id == "test:auto"


def test_inventory_get_auto_tracked() -> None:
    """Test getting all tracked sources."""
    inventory = AlertmanagerSourceInventory()
    
    sources = [
        AlertmanagerSource(
            source_id="test:auto",
            endpoint="http://auto:9093",
            state=AlertmanagerSourceState.AUTO_TRACKED,
        ),
        AlertmanagerSource(
            source_id="test:manual",
            endpoint="http://manual:9093",
            state=AlertmanagerSourceState.MANUAL,
        ),
        AlertmanagerSource(
            source_id="test:degraded",
            endpoint="http://degraded:9093",
            state=AlertmanagerSourceState.DEGRADED,
        ),
    ]
    
    for s in sources:
        inventory.add_source(s)
    
    tracked = inventory.get_auto_tracked()
    assert len(tracked) == 2
    tracked_ids = {s.source_id for s in tracked}
    assert "test:auto" in tracked_ids
    assert "test:manual" in tracked_ids
    assert "test:degraded" not in tracked_ids


def test_inventory_to_dict_roundtrip() -> None:
    """Test inventory serialization and deserialization."""
    inventory = AlertmanagerSourceInventory(cluster_context="prod-cluster")
    
    source = AlertmanagerSource(
        source_id="crd:monitoring/main",
        endpoint="http://alertmanager:9093",
        namespace="monitoring",
        name="main",
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        state=AlertmanagerSourceState.AUTO_TRACKED,
    )
    inventory.add_source(source)
    
    serialized = inventory.to_dict()
    restored = AlertmanagerSourceInventory.from_dict(serialized)
    
    assert len(restored.sources) == 1
    assert restored.cluster_context == "prod-cluster"
    assert "crd:monitoring/main" in restored.sources


def test_inventory_empty_state() -> None:
    """Test that empty inventory has empty dicts."""
    inventory = AlertmanagerSourceInventory()
    
    assert len(inventory.sources) == 0
    assert inventory.get_by_origin(AlertmanagerSourceOrigin.MANUAL) == ()
    assert inventory.get_by_state(AlertmanagerSourceState.AUTO_TRACKED) == ()


# --- CRD Discovery Tests ---

def test_crd_discovery_success() -> None:
    """Test CRD discovery successfully finds Alertmanager CRDs."""
    strategy = CRDDiscoveryStrategy()
    
    # Mock kubectl output
    kubectl_output = {
        "apiVersion": "monitoring.coreos.com/v1",
        "kind": "AlertmanagerList",
        "items": [
            {
                "metadata": {
                    "name": "main",
                    "namespace": "monitoring",
                },
                "spec": {},
            },
            {
                "metadata": {
                    "name": "long-lasting",
                    "namespace": "observability",
                },
                "spec": {},
            },
        ],
    }
    
    with patch("subprocess.run") as mock_run:
        # Mock get alertmanagers
        mock_alertmanagers = MagicMock()
        mock_alertmanagers.returncode = 0
        mock_alertmanagers.stdout = json.dumps(kubectl_output)
        
        mock_run.return_value = mock_alertmanagers
        
        result = strategy.discover()
    
    assert result.strategy == "alertmanager-crd"
    assert len(result.sources) == 2
    
    source_ids = {s.source_id for s in result.sources}
    assert "crd:monitoring/main" in source_ids
    assert "crd:observability/long-lasting" in source_ids
    
    # All sources should have CRD origin
    for source in result.sources:
        assert source.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
        assert source.state == AlertmanagerSourceState.DISCOVERED


def test_crd_discovery_no_resources() -> None:
    """Test CRD discovery handles no resources gracefully."""
    strategy = CRDDiscoveryStrategy()
    
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "No resources found in alertmanager namespace"
        
        mock_run.return_value = mock_result
        
        result = strategy.discover()
    
    assert result.strategy == "alertmanager-crd"
    assert len(result.sources) == 0
    assert len(result.errors) == 0  # No error, just empty


def test_crd_discovery_crd_not_installed() -> None:
    """Test CRD discovery handles CRD not installed gracefully."""
    strategy = CRDDiscoveryStrategy()
    
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "the server doesn't have a resource type 'alertmanagers'"
        
        mock_run.return_value = mock_result
        
        result = strategy.discover()
    
    assert result.strategy == "alertmanager-crd"
    assert len(result.sources) == 0
    # CRD not installed generates an error message but still returns empty sources gracefully
    # This is acceptable behavior - the strategy tried but the CRD doesn't exist


def test_crd_discovery_kubectl_not_found() -> None:
    """Test CRD discovery handles kubectl not found."""
    strategy = CRDDiscoveryStrategy()
    
    with patch("subprocess.run", side_effect=FileNotFoundError("kubectl not found")):
        result = strategy.discover()
    
    assert result.strategy == "alertmanager-crd"
    assert len(result.sources) == 0
    assert "kubectl not found" in result.errors[0]


# --- Verification Tests ---

def test_verification_healthy_and_ready() -> None:
    """Test verification passes when both endpoints return success."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        # Mock responses for both endpoints and status
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({
            "status": "success",
            "data": {"versionInfo": {"version": "0.25.0"}}
        }).encode()
        
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        
        result = verify_alertmanager_endpoint("http://alertmanager:9093", timeout_seconds=5.0)
    
    assert result.healthy is True
    assert result.ready is True
    assert result.version == "0.25.0"
    assert result.error is None


def test_verification_failure_healthy() -> None:
    """Test verification fails when /-/healthy fails."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.status = 503
        mock_response.reason = "Service Unavailable"
        
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        
        result = verify_alertmanager_endpoint("http://alertmanager:9093", timeout_seconds=5.0)
    
    assert result.healthy is False
    assert result.ready is False
    assert result.error is not None


def test_verification_failure_ready() -> None:
    """Test verification fails when /-/ready fails but /-/healthy succeeds."""
    call_count = [0]
    
    def side_effect(url: Any, timeout: float | None = None) -> MagicMock:
        url_str = str(url)
        call_count[0] += 1
        
        if call_count[0] == 1:  # First call: /-/healthy
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response
        elif call_count[0] == 2:  # Second call: /-/ready - fail
            from http.client import HTTPMessage
            headers = HTTPMessage()
            raise urllib.error.HTTPError(
                url=url_str,
                code=500,
                msg="Internal Server Error",
                hdrs=headers,
                fp=None,
            )
        else:  # Third call: version info
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = json.dumps({
                "status": "success",
                "data": {"versionInfo": {"version": "0.25.0"}}
            }).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response
    
    with patch("urllib.request.urlopen", side_effect=side_effect):
        result = verify_alertmanager_endpoint("http://alertmanager:9093", timeout_seconds=5.0)
    
    assert result.healthy is True
    assert result.ready is False
    assert result.error is not None
    assert "500" in result.error


def test_verification_connection_error() -> None:
    """Test verification handles connection errors gracefully."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        
        result = verify_alertmanager_endpoint("http://alertmanager:9093", timeout_seconds=5.0)
    
    assert result.healthy is False
    assert result.ready is False
    assert result.error is not None
    assert "Connection failed" in result.error


def test_verification_timeout() -> None:
    """Test verification handles timeout gracefully."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = TimeoutError("timed out")
        
        result = verify_alertmanager_endpoint("http://alertmanager:9093", timeout_seconds=5.0)
    
    assert result.healthy is False
    assert result.ready is False
    assert result.error is not None
    assert "timed out" in result.error


# --- Orchestrated Discovery Tests ---

def test_discover_alertmanagers_with_manual_sources() -> None:
    """Test that manual sources are preserved during discovery."""
    manual = AlertmanagerSource(
        source_id="manual:custom",
        endpoint="http://custom:9093",
        origin=AlertmanagerSourceOrigin.MANUAL,
        state=AlertmanagerSourceState.MANUAL,
    )
    
    with patch.object(CRDDiscoveryStrategy, "discover") as mock_crd:
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
        
        result = discover_alertmanagers(manual_sources=(manual,))
    
    # Manual should be preserved
    assert "manual:custom" in result.sources
    assert result.sources["manual:custom"].origin == AlertmanagerSourceOrigin.MANUAL


def test_verify_and_update_inventory() -> None:
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


def test_verify_and_update_inventory_degraded() -> None:
    """Test that failing verification marks sources as degraded."""
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


# --- Utility Tests ---

def test_build_endpoint_for_manual() -> None:
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


def test_build_endpoint_for_manual_with_http_prefix() -> None:
    """Test that http:// prefix is handled correctly."""
    source = build_endpoint_for_manual(
        endpoint="http://alertmanager:9093",
    )
    
    assert source.endpoint == "http://alertmanager:9093"


# --- Duplicate Merge Tests ---

def test_duplicate_same_origin_same_id() -> None:
    """Test that same source from same origin updates state correctly."""
    inventory = AlertmanagerSourceInventory()
    
    # Add first source (discovered state)
    inventory.add_source(AlertmanagerSource(
        source_id="crd:monitoring/main",
        endpoint="http://alertmanager1:9093",
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        state=AlertmanagerSourceState.DISCOVERED,
    ))
    
    # Add same source (auto-tracked state should replace)
    inventory.add_source(AlertmanagerSource(
        source_id="crd:monitoring/main",
        endpoint="http://alertmanager2:9093",
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        state=AlertmanagerSourceState.AUTO_TRACKED,
    ))
    
    # Should prefer AUTO_TRACKED state from same origin
    assert inventory.sources["crd:monitoring/main"].state == AlertmanagerSourceState.AUTO_TRACKED


def test_duplicate_different_origins_manual_always_wins() -> None:
    """Test that manual always wins regardless of state."""
    inventory = AlertmanagerSourceInventory()
    
    # Add service heuristic first
    inventory.add_source(AlertmanagerSource(
        source_id="service:monitoring/alertmanager",
        endpoint="http://heuristic:9093",
        origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        state=AlertmanagerSourceState.AUTO_TRACKED,
    ))
    
    # Add manual source with similar identity
    inventory.add_source(AlertmanagerSource(
        source_id="service:monitoring/alertmanager",
        endpoint="http://manual:9093",
        origin=AlertmanagerSourceOrigin.MANUAL,
        state=AlertmanagerSourceState.MANUAL,
    ))
    
    # Manual should win
    assert inventory.sources["service:monitoring/alertmanager"].origin == AlertmanagerSourceOrigin.MANUAL


# --- Missing Source Grace Behavior Tests ---

def test_missing_source_returns_empty_tuple() -> None:
    """Test that querying for non-existent sources returns empty tuple."""
    inventory = AlertmanagerSourceInventory()
    
    crd_sources = inventory.get_by_origin(AlertmanagerSourceOrigin.ALERTMANAGER_CRD)
    assert crd_sources == ()
    
    state_sources = inventory.get_by_state(AlertmanagerSourceState.AUTO_TRACKED)
    assert state_sources == ()


def test_inventory_from_empty_dict() -> None:
    """Test that inventory from empty dict has empty sources."""
    inventory = AlertmanagerSourceInventory.from_dict({})
    
    assert len(inventory.sources) == 0
    assert inventory.cluster_context is None


def test_inventory_from_dict_missing_fields() -> None:
    """Test that inventory handles missing fields gracefully."""
    data = {
        "sources": [
            {
                "source_id": "test:source",
                "endpoint": "http://test:9093",
            }
        ]
    }
    
    inventory = AlertmanagerSourceInventory.from_dict(data)
    
    assert len(inventory.sources) == 1
    source = inventory.sources["test:source"]
    # Should have defaults for missing fields
    assert source.origin == AlertmanagerSourceOrigin.SERVICE_HEURISTIC
    assert source.state == AlertmanagerSourceState.DISCOVERED


# --- Prometheus Runtime Discovery Tests ---

def test_prometheus_crd_config_discovery_success() -> None:
    """Test Prometheus CRD config discovery finds configured Alertmanagers."""
    strategy = PrometheusCRDConfigDiscoveryStrategy()
    
    kubectl_output = {
        "apiVersion": "monitoring.coreos.com/v1",
        "kind": "PrometheusList",
        "items": [
            {
                "metadata": {
                    "name": "k8s",
                    "namespace": "monitoring",
                },
                "spec": {
                    "alerting": {
                        "alertmanagers": [
                            {
                                "name": "main",
                                "namespace": "monitoring",
                            }
                        ]
                    }
                },
            }
        ],
    }
    
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(kubectl_output)
        
        mock_run.return_value = mock_result
        
        result = strategy.discover()
    
    assert result.strategy == "prometheus-crd-config"
    assert len(result.sources) == 1
    assert result.sources[0].origin == AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG


def test_prometheus_crd_config_discovery_no_alertmanagers_configured() -> None:
    """Test Prometheus CRD config discovery handles no alerting config."""
    strategy = PrometheusCRDConfigDiscoveryStrategy()
    
    kubectl_output = {
        "apiVersion": "monitoring.coreos.com/v1",
        "kind": "PrometheusList",
        "items": [
            {
                "metadata": {
                    "name": "k8s",
                    "namespace": "monitoring",
                },
                "spec": {},
            }
        ],
    }
    
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(kubectl_output)
        
        mock_run.return_value = mock_result
        
        result = strategy.discover()
    
    assert result.strategy == "prometheus-crd-config"
    assert len(result.sources) == 0


# --- Service Heuristic Discovery Tests ---

def test_service_heuristic_discovery_success() -> None:
    """Test service heuristic discovery finds Alertmanager services."""
    strategy = ServiceHeuristicDiscoveryStrategy()
    
    kubectl_output = {
        "apiVersion": "v1",
        "kind": "ServiceList",
        "items": [
            {
                "metadata": {
                    "name": "alertmanager-main",
                    "namespace": "monitoring",
                },
                "spec": {
                    "ports": [
                        {"port": 9093, "targetPort": 9093}
                    ]
                }
            }
        ],
    }
    
    pod_output = {
        "apiVersion": "v1",
        "kind": "PodList",
        "items": []
    }
    
    with patch("subprocess.run") as mock_run:
        mock_svc = MagicMock()
        mock_svc.returncode = 0
        mock_svc.stdout = json.dumps(kubectl_output)
        
        mock_pod = MagicMock()
        mock_pod.returncode = 0
        mock_pod.stdout = json.dumps(pod_output)
        
        mock_run.side_effect = [mock_svc, mock_pod]
        
        result = strategy.discover()
    
    assert result.strategy == "service-heuristic"
    assert len(result.sources) == 1
    assert result.sources[0].origin == AlertmanagerSourceOrigin.SERVICE_HEURISTIC
    assert result.sources[0].name == "alertmanager-main"


def test_service_heuristic_skips_non_matching_services() -> None:
    """Test service heuristic skips services without 'alertmanager' in name."""
    strategy = ServiceHeuristicDiscoveryStrategy()
    
    kubectl_output = {
        "apiVersion": "v1",
        "kind": "ServiceList",
        "items": [
            {
                "metadata": {
                    "name": "nginx-service",
                    "namespace": "default",
                },
                "spec": {
                    "ports": [{"port": 80}]
                }
            },
            {
                "metadata": {
                    "name": "alertmanager-operated",
                    "namespace": "monitoring",
                },
                "spec": {
                    "ports": [{"port": 9093}]
                }
            }
        ],
    }
    
    pod_output = {"apiVersion": "v1", "kind": "PodList", "items": []}
    
    with patch("subprocess.run") as mock_run:
        mock_svc = MagicMock()
        mock_svc.returncode = 0
        mock_svc.stdout = json.dumps(kubectl_output)
        
        mock_pod = MagicMock()
        mock_pod.returncode = 0
        mock_pod.stdout = json.dumps(pod_output)
        
        mock_run.side_effect = [mock_svc, mock_pod]
        
        result = strategy.discover()
    
    assert len(result.sources) == 1
    assert result.sources[0].name == "alertmanager-operated"


# --- Discovery Result Tests ---

def test_discovery_result_creation() -> None:
    """Test DiscoveryResult creation with sources and errors."""
    result = DiscoveryResult(
        sources=(
            AlertmanagerSource(
                source_id="test:source",
                endpoint="http://test:9093",
            ),
        ),
        errors=("Error 1", "Error 2"),
        strategy="test-strategy",
    )
    
    assert len(result.sources) == 1
    assert len(result.errors) == 2
    assert result.strategy == "test-strategy"


# --- Verification Result Tests ---

def test_verification_result_all_fields() -> None:
    """Test VerificationResult with all fields populated."""
    result = VerificationResult(
        healthy=True,
        ready=True,
        version="0.25.0",
        error=None,
        checked_at=datetime.now(UTC),
    )
    
    assert result.healthy is True
    assert result.ready is True
    assert result.version == "0.25.0"
    assert result.error is None


def test_verification_result_with_error() -> None:
    """Test VerificationResult with error and no version."""
    result = VerificationResult(
        healthy=False,
        ready=False,
        version=None,
        error="Connection refused: Error 111",
    )
    
    assert result.healthy is False
    assert result.ready is False
    assert result.version is None
    assert result.error is not None
    assert "Connection refused" in result.error


# --- Edge Cases ---

def test_source_with_special_characters_in_id() -> None:
    """Test source handling special characters in source_id."""
    source = AlertmanagerSource(
        source_id="crd:my-namespace/my-alertmanager-instance",
        endpoint="http://alertmanager:9093",
        namespace="my-namespace",
        name="my-alertmanager-instance",
    )
    
    assert source.identity_key == "crd:my-namespace/my-alertmanager-instance"
    
    serialized = source.to_dict()
    restored = AlertmanagerSource.from_dict(serialized)
    
    assert restored.source_id == source.source_id


def test_inventory_large_source_count() -> None:
    """Test inventory with many sources (stress test)."""
    inventory = AlertmanagerSourceInventory()
    
    # Add 100 sources
    for i in range(100):
        source = AlertmanagerSource(
            source_id=f"crd:ns{i}/am{i}",
            endpoint=f"http://am{i}:9093",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        )
        inventory.add_source(source)
    
    assert len(inventory.sources) == 100
    
    # Verify filtering still works
    crd_sources = inventory.get_by_origin(AlertmanagerSourceOrigin.ALERTMANAGER_CRD)
    assert len(crd_sources) == 100
    
    manual_sources = inventory.get_by_origin(AlertmanagerSourceOrigin.MANUAL)
    assert len(manual_sources) == 0


def test_merge_deduplicate_inventory_different_origins_same_endpoint() -> None:
    """Test that merge_deduplicate_inventory merges CRD + Config sources with same namespace/name.
    
    Service heuristic stays separate when names differ (no aggressive merging per user requirement).
    """
    from k8s_diag_agent.external_analysis.alertmanager_discovery import merge_deduplicate_inventory
    
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


def test_merge_deduplicate_inventory_manual_preserved() -> None:
    """Test that merge_deduplicate_inventory preserves manual source (same source_id)."""
    from k8s_diag_agent.external_analysis.alertmanager_discovery import merge_deduplicate_inventory
    
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


def test_merge_deduplicate_inventory_different_endpoints_not_merged() -> None:
    """Test that sources with different endpoints are not merged."""
    from k8s_diag_agent.external_analysis.alertmanager_discovery import merge_deduplicate_inventory
    
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


def test_canonical_identity_tiered_approach() -> None:
    """Test that canonical_identity uses tiered approach: CRD/Config > Endpoint.
    
    CRD and Config tiers use namespace/name for merging (same canonical key).
    Service heuristic falls back to normalized endpoint.
    
    This verifies the Prometheus Operator duplicate case where:
    - alertmanager-operated (service) points to same pod as alertmanager-main (CRD)
    - CRD and Config sources with same namespace/name merge together
    - Service heuristic stays separate unless it matches endpoint of CRD source
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
    # This ensures different discovery methods can merge when they point to same AM
    service_source = AlertmanagerSource(
        source_id="service:monitoring/alertmanager-operated",
        endpoint="http://alertmanager-operated.monitoring:9093",
        namespace="monitoring",
        name="alertmanager-operated",
        origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
    )
    assert service_source.canonical_identity == "monitoring/alertmanager-operated"


def test_merge_deduplicate_inventory_prometheus_operator_case() -> None:
    """Test Prometheus Operator duplicate: CRD + Config sources merge when namespace/name matches.
    
    Real-world scenario (user requirement):
    - alertmanager-operated (service) points to same pod as alertmanager-main (CRD)
    - CRD + Config sources with same namespace/name merge together
    - Service heuristic with different name stays separate (no aggressive merging)
    
    This test uses same names for all 3 sources to verify proper merging.
    """
    from k8s_diag_agent.external_analysis.alertmanager_discovery import merge_deduplicate_inventory
    
    # Three sources with same namespace/name (for proper merging)
    crd_source = AlertmanagerSource(
        source_id="crd:monitoring/alertmanager-main",
        endpoint="http://alertmanager-operated.monitoring:9093",
        namespace="monitoring",
        name="alertmanager-main",
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        confidence_hints=("from-crd",),
    )
    
    config_source = AlertmanagerSource(
        source_id="prom-crd-config:monitoring/alertmanager-main",
        endpoint="http://alertmanager-operated.monitoring:9093",
        namespace="monitoring",
        name="alertmanager-main",
        origin=AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG,
        confidence_hints=("from-prometheus-crd-config",),
    )
    
    service_source = AlertmanagerSource(
        source_id="service:monitoring/alertmanager-main",
        endpoint="http://alertmanager-operated.monitoring:9093",
        namespace="monitoring",
        name="alertmanager-main",  # Same name for merging!
        origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        confidence_hints=("from-service",),
    )
    
    inventory = AlertmanagerSourceInventory()
    inventory.add_source(crd_source)
    inventory.add_source(config_source)
    inventory.add_source(service_source)
    
    # Before dedup: 3 sources
    assert len(inventory.sources) == 3
    
    # After dedup: 1 source (all have same namespace/name)
    result = merge_deduplicate_inventory(inventory)
    
    # The CRD source should win (highest priority)
    assert len(result.sources) == 1
    
    winner = list(result.sources.values())[0]
    assert winner.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
    assert winner.source_id == "crd:monitoring/alertmanager-main"
    
    # Provenances should be merged (all three origins)
    assert AlertmanagerSourceOrigin.ALERTMANAGER_CRD in winner.merged_provenances
    assert AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG in winner.merged_provenances
    assert AlertmanagerSourceOrigin.SERVICE_HEURISTIC in winner.merged_provenances


def test_display_provenance_single_origin() -> None:
    """Test display_provenance for single-origin source."""
    source = AlertmanagerSource(
        source_id="crd:monitoring/alertmanager-main",
        endpoint="http://alertmanager-operated.monitoring:9093",
        namespace="monitoring",
        name="alertmanager-main",
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
    )
    assert source.display_provenance == "Alertmanager CRD"


def test_display_provenance_merged_origins() -> None:
    """Test display_provenance shows all merged origins."""
    source = AlertmanagerSource(
        source_id="crd:monitoring/alertmanager-main",
        endpoint="http://alertmanager-operated.monitoring:9093",
        namespace="monitoring",
        name="alertmanager-main",
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        merged_provenances=(
            AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG,
            AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        ),
    )
    assert "Alertmanager CRD" in source.display_provenance
    assert "Prometheus Config" in source.display_provenance
    assert "Service Heuristic" in source.display_provenance


def test_prometheus_operator_alias_real_scenario() -> None:
    """Regression test: Real Prometheus Operator duplicate pattern.
    
    This is the exact scenario we observed in the UI:
    - CRD source: monitoring/kube-prometheus-stack-alertmanager (from kube-prometheus-stack)
    - Service source: monitoring/alertmanager-operated (Prometheus Operator conventional suffix)
    
    Both point to the same endpoint: alertmanager-operated.monitoring:9093
    Without alias resolution, they'd be 2 separate rows in the UI.
    With alias resolution, the service should be aliased to CRD name and merged.
    
    Expected UI row count: 1 (deduped)
    """
    from k8s_diag_agent.external_analysis.alertmanager_discovery import merge_deduplicate_inventory
    
    # CRD source - named after the Helm release (real scenario)
    crd_source = AlertmanagerSource(
        source_id="crd:monitoring/kube-prometheus-stack-alertmanager",
        endpoint="http://alertmanager-operated.monitoring:9093",
        namespace="monitoring",
        name="kube-prometheus-stack-alertmanager",
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
    )
    
    # Service source - the actual operated service (real scenario)
    service_source = AlertmanagerSource(
        source_id="service:monitoring/alertmanager-operated",
        endpoint="http://alertmanager-operated.monitoring:9093",
        namespace="monitoring",
        name="alertmanager-operated",  # Note: Different name than CRD
        origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
    )
    
    inventory = AlertmanagerSourceInventory()
    inventory.add_source(crd_source)
    inventory.add_source(service_source)
    
    # Before dedup: 2 sources
    assert len(inventory.sources) == 2
    
    # Dedup with alias resolution
    result = merge_deduplicate_inventory(inventory)
    
    # After dedup: 1 source (service aliased to CRD name)
    assert len(result.sources) == 1, f"Expected 1 source after dedup, got {len(result.sources)}"
    
    # The merged source should use CRD origin (highest priority)
    merged = next(iter(result.sources.values()))
    assert merged.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
    
    # The canonical identity should be the CRD name
    assert merged.canonical_identity == "monitoring/kube-prometheus-stack-alertmanager"
    
    # Both provenances should be merged
    assert AlertmanagerSourceOrigin.ALERTMANAGER_CRD in merged.merged_provenances
    assert AlertmanagerSourceOrigin.SERVICE_HEURISTIC in merged.merged_provenances
    
    # The display should show both origins
    assert "Alertmanager CRD" in merged.display_provenance
    assert "Service Heuristic" in merged.display_provenance


def test_prometheus_operator_alias_ambiguous_no_alias() -> None:
    """Test that alias is NOT applied when mapping is ambiguous (multiple CRDs in namespace).
    
    If there are 2 CRD Alertmanagers in the same namespace, we cannot determine
    which one the alertmanager-operated service belongs to, so no alias is applied.
    """
    from k8s_diag_agent.external_analysis.alertmanager_discovery import merge_deduplicate_inventory
    
    # Two CRD sources in same namespace
    crd1 = AlertmanagerSource(
        source_id="crd:monitoring/alertmanager-main",
        endpoint="http://alertmanager-operated.monitoring:9093",
        namespace="monitoring",
        name="alertmanager-main",
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
    )
    
    crd2 = AlertmanagerSource(
        source_id="crd:monitoring/alertmanager-secondary",
        endpoint="http://alertmanager-operated-secondary.monitoring:9093",
        namespace="monitoring",
        name="alertmanager-secondary",
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
    )
    
    # Service source - ambiguous which CRD it belongs to
    service_source = AlertmanagerSource(
        source_id="service:monitoring/alertmanager-operated",
        endpoint="http://alertmanager-operated.monitoring:9093",
        namespace="monitoring",
        name="alertmanager-operated",
        origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
    )
    
    inventory = AlertmanagerSourceInventory()
    inventory.add_source(crd1)
    inventory.add_source(crd2)
    inventory.add_source(service_source)
    
    result = merge_deduplicate_inventory(inventory)
    
    # Should have 3 sources - service NOT aliased because mapping is ambiguous
    assert len(result.sources) == 3
    
    # The service should still be separate (not aliased)
    service_key = "monitoring/alertmanager-operated"
    assert service_key in result.sources


def test_prometheus_operator_alias_single_crd_unambiguous() -> None:
    """Test that alias IS applied when there's exactly one CRD in namespace.
    
    This is the unambiguous case - single CRD Alertmanager, alias should apply.
    """
    from k8s_diag_agent.external_analysis.alertmanager_discovery import merge_deduplicate_inventory
    
    # Single CRD source
    crd_source = AlertmanagerSource(
        source_id="crd:monitoring/alertmanager-main",
        endpoint="http://alertmanager-operated.monitoring:9093",
        namespace="monitoring",
        name="alertmanager-main",
        origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
    )
    
    # Service source - should be aliased to CRD name
    service_source = AlertmanagerSource(
        source_id="service:monitoring/alertmanager-operated",
        endpoint="http://alertmanager-operated.monitoring:9093",
        namespace="monitoring",
        name="alertmanager-operated",
        origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
    )
    
    inventory = AlertmanagerSourceInventory()
    inventory.add_source(crd_source)
    inventory.add_source(service_source)
    
    result = merge_deduplicate_inventory(inventory)
    
    # Should have 1 source - service aliased to CRD
    assert len(result.sources) == 1
