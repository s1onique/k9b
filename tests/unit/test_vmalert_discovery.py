"""Unit tests for vmalert discovery module.

Tests cover:
- Source and inventory data structures
- Discovery strategies (CRD, service heuristic)
- Verification
- Deduplication
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.external_analysis.vmalert_discovery import (
    DiscoveryResult,
    ServiceHeuristicDiscoveryStrategy,
    VerificationResult,
    VMAlertCRDDiscoveryStrategy,
    VmalertSource,
    VmalertSourceInventory,
    VmalertSourceMode,
    VmalertSourceOrigin,
    VmalertSourceState,
    _kubectl_context_args,
    _should_add_context_flag,
    build_endpoint_for_manual,
    discover_vmalerts,
    merge_deduplicate_inventory,
    verify_and_update_inventory,
)

# --- Test Fixtures ---


@pytest.fixture
def golden_fixture_service() -> dict[str, Any]:
    """Golden fixture for VM stack vmalert service discovery.
    
    This matches the user's target cluster:
    - namespace = victoria-metrics-k8s-stack
    - service   = vmalert-infra-victoria-metrics-k8s-stack
    - ports     = [{"port": 8080, "protocol": "TCP"}]
    """
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": "vmalert-infra-victoria-metrics-k8s-stack",
            "namespace": "victoria-metrics-k8s-stack",
            "uid": "test-uid-vmalert",
            "labels": {
                "app.kubernetes.io/name": "vmalert",
                "app.kubernetes.io/component": "vmalert",
            },
        },
        "spec": {
            "ports": [{"port": 8080, "protocol": "TCP", "targetPort": 8080}],
            "selector": {"app": "vmalert"},
        },
    }


@pytest.fixture
def multi_namespace_services() -> dict[str, Any]:
    """Multiple services across namespaces for testing scoring."""
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            # Primary target - exact match
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "vmalert-infra-victoria-metrics-k8s-stack",
                    "namespace": "victoria-metrics-k8s-stack",
                    "uid": "uid-vm-primary",
                    "labels": {
                        "app.kubernetes.io/name": "vmalert",
                    },
                },
                "spec": {
                    "ports": [{"port": 8080, "protocol": "TCP"}],
                },
            },
            # Another vmalert in same namespace
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "vmalert-apps-victoria-metrics-k8s-stack",
                    "namespace": "victoria-metrics-k8s-stack",
                    "uid": "uid-vm-apps",
                    "labels": {},
                },
                "spec": {
                    "ports": [{"port": 8080, "protocol": "TCP"}],
                },
            },
            # vmalert in monitoring namespace
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "vmalert-main",
                    "namespace": "monitoring",
                    "uid": "uid-monitoring",
                    "labels": {
                        "app": "vmalert",
                    },
                },
                "spec": {
                    "ports": [{"port": 8080, "protocol": "TCP"}],
                },
            },
            # Non-vmalert service that should be filtered
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "alertmanager-main",
                    "namespace": "monitoring",
                    "uid": "uid-am",
                    "labels": {},
                },
                "spec": {
                    "ports": [{"port": 9093, "protocol": "TCP"}],
                },
            },
        ],
    }


# --- VmalertSource Tests ---


def test_source_identity_key() -> None:
    """Test that source_id is used as identity key."""
    source = VmalertSource(
        source_id="service:victoria-metrics-k8s-stack/vmalert-infra",
        endpoint="http://vmalert-infra.victoria-metrics-k8s-stack:8080",
        namespace="victoria-metrics-k8s-stack",
        name="vmalert-infra",
    )
    assert source.identity_key == "service:victoria-metrics-k8s-stack/vmalert-infra"


def test_source_endpoint_normalization() -> None:
    """Test that endpoint trailing slashes are removed."""
    source = VmalertSource(
        source_id="test",
        endpoint="http://vmalert.test:8080/",
    )
    assert source.endpoint == "http://vmalert.test:8080"


def test_source_to_dict_roundtrip() -> None:
    """Test source serialization and deserialization."""
    source = VmalertSource(
        source_id="service:victoria-metrics-k8s-stack/vmalert-infra",
        endpoint="http://vmalert-infra.victoria-metrics-k8s-stack:8080",
        namespace="victoria-metrics-k8s-stack",
        name="vmalert-infra",
        origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
        state=VmalertSourceState.DISCOVERED,
        confidence_hints=("from-service", "likely-port"),
    )

    data = source.to_dict()
    restored = VmalertSource.from_dict(data)

    assert restored.source_id == source.source_id
    assert restored.endpoint == source.endpoint
    assert restored.namespace == source.namespace
    assert restored.name == source.name
    assert restored.origin == source.origin
    assert restored.state == source.state


def test_source_origin_enum_values() -> None:
    """Verify all expected origin values exist."""
    assert VmalertSourceOrigin.MANUAL.value == "manual"
    assert VmalertSourceOrigin.VMALERT_CRD.value == "vmalert-crd"
    assert VmalertSourceOrigin.SERVICE_HEURISTIC.value == "service-heuristic"


def test_source_state_enum_values() -> None:
    """Verify all expected state values exist."""
    assert VmalertSourceState.DISCOVERED.value == "discovered"
    assert VmalertSourceState.DISCOVERED_BUT_UNVERIFIED.value == "discovered-but-unverified"
    assert VmalertSourceState.AUTO_TRACKED.value == "auto-tracked"
    assert VmalertSourceState.MANUAL.value == "manual"


def test_manual_source_mode_enum_values() -> None:
    """Verify all expected manual_source_mode values exist."""
    assert VmalertSourceMode.NOT_MANUAL.value == "not-manual"
    assert VmalertSourceMode.OPERATOR_CONFIGURED.value == "operator-configured"
    assert VmalertSourceMode.OPERATOR_PROMOTED.value == "operator-promoted"


def test_discovered_source_has_not_manual_mode() -> None:
    """Discovered sources should default to NOT_MANUAL mode."""
    source = VmalertSource(
        source_id="test",
        endpoint="http://test:8080",
    )
    assert source.manual_source_mode == VmalertSourceMode.NOT_MANUAL


def test_operator_configured_source_has_operator_configured_mode() -> None:
    """Operator-configured sources should have OPERATOR_CONFIGURED mode."""
    source = build_endpoint_for_manual(
        endpoint="http://vmalert.test:8080",
        namespace="test",
        name="vmalert-test",
    )
    assert source.manual_source_mode == VmalertSourceMode.OPERATOR_CONFIGURED


# --- Inventory Tests ---


def test_inventory_add_source() -> None:
    """Test adding sources to inventory."""
    inventory = VmalertSourceInventory()
    source = VmalertSource(
        source_id="service:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
    )
    inventory.add_source(source)
    assert len(inventory.sources) == 1


def test_inventory_manual_precedence() -> None:
    """Manual sources must not be overwritten by discovered sources."""
    inventory = VmalertSourceInventory()

    discovered = VmalertSource(
        source_id="service:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
    )
    manual = VmalertSource(
        source_id="service:ns/vmalert",
        endpoint="http://vmalert.ns:9090",  # Different port
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.MANUAL,
        state=VmalertSourceState.MANUAL,
        manual_source_mode=VmalertSourceMode.OPERATOR_CONFIGURED,
    )

    inventory.add_source(discovered)
    inventory.add_source(manual)

    assert inventory.sources["service:ns/vmalert"].origin == VmalertSourceOrigin.MANUAL


def test_inventory_get_by_origin() -> None:
    """Test filtering sources by origin."""
    inventory = VmalertSourceInventory()
    inventory.add_source(VmalertSource(
        source_id="s1",
        endpoint="http://s1:8080",
        origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
    ))
    inventory.add_source(VmalertSource(
        source_id="s2",
        endpoint="http://s2:8080",
        origin=VmalertSourceOrigin.VMALERT_CRD,
    ))

    service_sources = inventory.get_by_origin(VmalertSourceOrigin.SERVICE_HEURISTIC)
    assert len(service_sources) == 1
    assert service_sources[0].source_id == "s1"


def test_inventory_get_by_state() -> None:
    """Test filtering sources by state."""
    inventory = VmalertSourceInventory()
    inventory.add_source(VmalertSource(
        source_id="s1",
        endpoint="http://s1:8080",
        state=VmalertSourceState.DISCOVERED,
    ))
    inventory.add_source(VmalertSource(
        source_id="s2",
        endpoint="http://s2:8080",
        state=VmalertSourceState.DISCOVERED_BUT_UNVERIFIED,
    ))

    discovered = inventory.get_by_state(VmalertSourceState.DISCOVERED)
    assert len(discovered) == 1


def test_inventory_to_dict_roundtrip() -> None:
    """Test inventory serialization and deserialization."""
    inventory = VmalertSourceInventory()
    inventory.add_source(VmalertSource(
        source_id="service:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
    ))

    data = inventory.to_dict()
    restored = VmalertSourceInventory.from_dict(data)

    assert len(restored.sources) == 1


# --- Discovery Strategy Tests ---


class TestServiceHeuristicDiscovery:
    """Tests for ServiceHeuristicDiscoveryStrategy."""

    def test_golden_fixture_discovers_vmalert(self, golden_fixture_service: dict[str, Any]) -> None:
        """Regression: Golden VM stack fixture discovers vmalert on port 8080."""
        strategy = ServiceHeuristicDiscoveryStrategy()
        
        source = strategy._parse_service_item(golden_fixture_service, None)
        
        assert source is not None
        assert source.name == "vmalert-infra-victoria-metrics-k8s-stack"
        assert source.namespace == "victoria-metrics-k8s-stack"
        assert source.endpoint == "http://vmalert-infra-victoria-metrics-k8s-stack.victoria-metrics-k8s-stack.svc:8080"
        assert source.origin == VmalertSourceOrigin.SERVICE_HEURISTIC

    def test_matches_vmalert_name_exact_prefix(self) -> None:
        """Test that service name starting with 'vmalert-' is matched."""
        strategy = ServiceHeuristicDiscoveryStrategy()
        assert strategy._matches_vmalert_name("vmalert-infra") is True
        assert strategy._matches_vmalert_name("vmalert-main") is True

    def test_matches_vmalert_name_contains(self) -> None:
        """Test that service name containing 'vmalert' is matched."""
        strategy = ServiceHeuristicDiscoveryStrategy()
        assert strategy._matches_vmalert_name("my-vmalert-service") is True
        assert strategy._matches_vmalert_name("vmalert") is True

    def test_matches_vmalert_name_rejects_non_match(self) -> None:
        """Test that non-vmalert names are rejected."""
        strategy = ServiceHeuristicDiscoveryStrategy()
        assert strategy._matches_vmalert_name("alertmanager-main") is False
        assert strategy._matches_vmalert_name("prometheus-server") is False

    def test_matches_vmalert_labels_app_kubernetes_io(self) -> None:
        """Test that app.kubernetes.io labels are checked."""
        strategy = ServiceHeuristicDiscoveryStrategy()
        
        # Match on app.kubernetes.io/name
        assert strategy._matches_vmalert_labels({
            "app.kubernetes.io/name": "vmalert",
        }) is True
        
        # Match on app.kubernetes.io/component
        assert strategy._matches_vmalert_labels({
            "app.kubernetes.io/component": "vmalert",
        }) is True

    def test_matches_vmalert_labels_vm_operator(self) -> None:
        """Test that VM operator labels are checked."""
        strategy = ServiceHeuristicDiscoveryStrategy()
        
        assert strategy._matches_vmalert_labels({
            "operator.victoriametrics.com/name": "my-vmalert",
        }) is True
        
        assert strategy._matches_vmalert_labels({
            "app": "vmalert",
        }) is True

    def test_extracts_port_by_name(self) -> None:
        """Test port extraction by likely port names."""
        strategy = ServiceHeuristicDiscoveryStrategy()
        
        ports = [
            {"name": "http", "port": 8080, "protocol": "TCP"},
            {"name": "metrics", "port": 9090, "protocol": "TCP"},
        ]
        assert strategy._extract_vmalert_port(ports) == 8080

    def test_extracts_port_by_number(self) -> None:
        """Test port extraction by likely port numbers."""
        strategy = ServiceHeuristicDiscoveryStrategy()
        
        ports = [
            {"port": 9093, "protocol": "TCP"},  # Alertmanager port
            {"port": 8080, "protocol": "TCP"},  # vmalert port
        ]
        assert strategy._extract_vmalert_port(ports) == 8080

    def test_extracts_first_tcp_port_fallback(self) -> None:
        """Test fallback to first TCP port."""
        strategy = ServiceHeuristicDiscoveryStrategy()
        
        ports = [
            {"port": 9093, "protocol": "TCP"},
        ]
        assert strategy._extract_vmalert_port(ports) == 9093

    def test_returns_none_for_no_ports(self) -> None:
        """Test that None is returned when no suitable port."""
        strategy = ServiceHeuristicDiscoveryStrategy()
        assert strategy._extract_vmalert_port([]) is None

    def test_likely_namespace_detection(self) -> None:
        """Test likely namespace detection."""
        strategy = ServiceHeuristicDiscoveryStrategy()
        
        assert strategy._matches_likely_namespace("victoria-metrics-k8s-stack") is True
        assert strategy._matches_likely_namespace("monitoring") is True
        assert strategy._matches_likely_namespace("victoria-metrics") is True
        assert strategy._matches_likely_namespace("default") is False


class TestContextFlagHandling:
    """Tests for context flag handling (mirrors Alertmanager tests)."""

    def test_returns_false_for_none_context(self) -> None:
        """When context is None, should not add --context flag."""
        assert _should_add_context_flag(None) is False

    def test_returns_false_for_in_cluster_context(self) -> None:
        """When context is 'in-cluster', should NOT add --context flag."""
        assert _should_add_context_flag("in-cluster") is False

    def test_returns_true_for_named_context(self) -> None:
        """When context is a named kubeconfig context, should add --context flag."""
        assert _should_add_context_flag("minikube") is True

    def test_kubectl_context_args_none(self) -> None:
        """When context is None, should return empty list."""
        assert _kubectl_context_args(None) == []

    def test_kubectl_context_args_in_cluster(self) -> None:
        """When context is 'in-cluster', should return empty list."""
        assert _kubectl_context_args("in-cluster") == []

    def test_kubectl_context_args_named(self) -> None:
        """When context is a named context, should return --context args."""
        assert _kubectl_context_args("minikube") == ["--context", "minikube"]


class TestVMAlertCRDDiscovery:
    """Tests for VMAlert CRD discovery strategy."""

    def test_crd_discovery_parsing(self) -> None:
        """Test CRD item parsing."""
        strategy = VMAlertCRDDiscoveryStrategy()
        
        crd_item = {
            "metadata": {
                "name": "vmalert-main",
                "namespace": "victoria-metrics-k8s-stack",
                "uid": "test-crd-uid",
            },
            "spec": {
                "port": 8080,
            },
        }
        
        source = strategy._parse_crd_item(crd_item, None, None)
        
        assert source is not None
        assert source.name == "vmalert-main"
        assert source.namespace == "victoria-metrics-k8s-stack"
        assert source.endpoint == "http://vmalert-main.victoria-metrics-k8s-stack.svc:8080"
        assert source.origin == VmalertSourceOrigin.VMALERT_CRD
        assert source.object_uid == "test-crd-uid"


# --- Verification Tests ---


class TestVerification:
    """Tests for vmalert endpoint verification."""

    def test_verification_result_all_fields(self) -> None:
        """Test VerificationResult with all fields populated."""
        result = VerificationResult(
            reachable=True,
            version="1.0.0",
            error=None,
        )
        assert result.reachable is True
        assert result.version == "1.0.0"

    def test_verification_result_with_error(self) -> None:
        """Test VerificationResult with error and no version."""
        result = VerificationResult(
            reachable=False,
            error="Connection refused",
        )
        assert result.reachable is False
        assert result.error == "Connection refused"
        assert result.version is None


# --- Deduplication Tests ---


def test_merge_deduplicate_inventory_single_source() -> None:
    """Test that single source passes through unchanged."""
    inventory = VmalertSourceInventory()
    inventory.add_source(VmalertSource(
        source_id="service:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
    ))

    merged = merge_deduplicate_inventory(inventory)
    assert len(merged.sources) == 1


def test_merge_deduplicate_inventory_same_identity() -> None:
    """Test that sources with same canonical identity are merged."""
    inventory = VmalertSourceInventory()
    # Same namespace/name but different source_id prefix
    inventory.add_source(VmalertSource(
        source_id="crd:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.VMALERT_CRD,
    ))
    inventory.add_source(VmalertSource(
        source_id="service:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
    ))

    merged = merge_deduplicate_inventory(inventory)
    assert len(merged.sources) == 1
    # CRD should win (higher priority)
    assert list(merged.sources.values())[0].origin == VmalertSourceOrigin.VMALERT_CRD


def test_merge_deduplicate_inventory_manual_preserved() -> None:
    """Test that manual source is preserved during merge."""
    inventory = VmalertSourceInventory()
    inventory.add_source(VmalertSource(
        source_id="service:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
    ))
    inventory.add_source(VmalertSource(
        source_id="service:ns/vmalert",
        endpoint="http://vmalert.ns:9090",
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.MANUAL,
        state=VmalertSourceState.MANUAL,
        manual_source_mode=VmalertSourceMode.OPERATOR_CONFIGURED,
    ))

    merged = merge_deduplicate_inventory(inventory)
    assert len(merged.sources) == 1
    assert list(merged.sources.values())[0].origin == VmalertSourceOrigin.MANUAL


# --- Discovery Result Tests ---


def test_discovery_result_creation() -> None:
    """Test DiscoveryResult creation with sources and errors."""
    result = DiscoveryResult(
        sources=(VmalertSource(source_id="test", endpoint="http://test:8080"),),
        strategy="service-heuristic",
        errors=("error1",),
    )
    assert len(result.sources) == 1
    assert len(result.errors) == 1
    assert result.strategy == "service-heuristic"


# --- Endpoint Building Tests ---


def test_build_endpoint_for_manual() -> None:
    """Test building a manual source from endpoint."""
    source = build_endpoint_for_manual(
        endpoint="http://vmalert.test:8080",
        namespace="test",
        name="vmalert-test",
    )
    assert source.endpoint == "http://vmalert.test:8080"
    assert source.namespace == "test"
    assert source.name == "vmalert-test"
    assert source.origin == VmalertSourceOrigin.MANUAL


def test_build_endpoint_for_manual_with_http_prefix() -> None:
    """Test that http:// prefix is handled correctly."""
    source = build_endpoint_for_manual(
        endpoint="vmalert.test:8080",  # No scheme
        namespace="test",
        name="vmalert-test",
    )
    assert source.endpoint == "http://vmalert.test:8080"


# --- Discovery Orchestration Tests ---


@patch("subprocess.run")
def test_discover_vmalerts_no_cluster(mock_run: MagicMock) -> None:
    """Test that discovery handles no cluster gracefully."""
    # Simulate kubectl not finding any services
    mock_run.return_value = MagicMock(
        returncode=1,
        stderr="no resources found",
    )
    
    inventory = discover_vmalerts()
    assert len(inventory.sources) == 0


def test_verify_and_update_inventory_unreachable_becomes_discovered_but_unverified() -> None:
    """Test that unreachable verification result becomes DISCOVERED_BUT_UNVERIFIED."""
    inventory = VmalertSourceInventory()
    original_artifact_id = inventory.artifact_id
    inventory.add_source(VmalertSource(
        source_id="service:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
    ))

    # Mock verification to return unreachable
    unreachable_result = VerificationResult(
        reachable=False,
        error="Connection refused",
    )

    with patch("k8s_diag_agent.external_analysis.vmalert_discovery.verify_vmalert_endpoint", return_value=unreachable_result):
        verified = verify_and_update_inventory(inventory, timeout_seconds=0.5)

    source = list(verified.sources.values())[0]
    assert source.state == VmalertSourceState.DISCOVERED_BUT_UNVERIFIED
    assert source.last_error == "Connection refused"
    assert source.verified_at is None
    # Verify artifact_id is preserved
    assert verified.artifact_id == original_artifact_id


def test_verify_and_update_inventory_reachable_remains_discovered() -> None:
    """Test that reachable verification result keeps DISCOVERED state."""
    inventory = VmalertSourceInventory()
    inventory.add_source(VmalertSource(
        source_id="service:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
    ))

    # Mock verification to return reachable
    reachable_result = VerificationResult(
        reachable=True,
        version="1.0.0",
    )

    with patch("k8s_diag_agent.external_analysis.vmalert_discovery.verify_vmalert_endpoint", return_value=reachable_result):
        verified = verify_and_update_inventory(inventory, timeout_seconds=0.5)

    source = list(verified.sources.values())[0]
    assert source.state == VmalertSourceState.DISCOVERED
    assert source.verified_at is not None
    assert source.last_check is not None
    assert source.verified_version == "1.0.0"


def test_verify_and_update_inventory_manual_source_not_verified() -> None:
    """Test that manual sources skip verification."""
    inventory = VmalertSourceInventory()
    inventory.add_source(VmalertSource(
        source_id="manual:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.MANUAL,
        state=VmalertSourceState.MANUAL,
        manual_source_mode=VmalertSourceMode.OPERATOR_CONFIGURED,
    ))

    with patch("k8s_diag_agent.external_analysis.vmalert_discovery.verify_vmalert_endpoint") as mock_verify:
        verified = verify_and_update_inventory(inventory, timeout_seconds=0.5)

    # verify_vmalert_endpoint should NOT have been called
    mock_verify.assert_not_called()
    source = list(verified.sources.values())[0]
    assert source.state == VmalertSourceState.MANUAL


# --- Roundtrip Tests ---


def test_roundtrip_operator_configured_source() -> None:
    """Operator-configured source should survive serialization roundtrip."""
    source = build_endpoint_for_manual(
        endpoint="http://vmalert.test:8080",
        namespace="test",
        name="vmalert-test",
    )

    data = source.to_dict()
    restored = VmalertSource.from_dict(data)

    assert restored.manual_source_mode == VmalertSourceMode.OPERATOR_CONFIGURED
    assert restored.origin == VmalertSourceOrigin.MANUAL


def test_canonical_identity_tiered_approach() -> None:
    """Test that canonical_identity uses namespace/name when available."""
    source = VmalertSource(
        source_id="service:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
    )
    assert source.canonical_identity == "ns/vmalert"


def test_canonical_identity_fallback_to_endpoint() -> None:
    """Test fallback to endpoint when no namespace/name."""
    source = VmalertSource(
        source_id="manual:http://external:8080",
        endpoint="http://external:8080",
    )
    # Without namespace/name, should normalize endpoint
    assert "external" in source.canonical_identity


def test_display_provenance_single_origin() -> None:
    """Test display_provenance for single-origin source."""
    source = VmalertSource(
        source_id="test",
        endpoint="http://test:8080",
        origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
    )
    assert "Service Heuristic" in source.display_provenance


def test_display_provenance_merged_origins() -> None:
    """Test display_provenance shows all merged origins."""
    source = VmalertSource(
        source_id="test",
        endpoint="http://test:8080",
        origin=VmalertSourceOrigin.VMALERT_CRD,
        merged_provenances=(
            VmalertSourceOrigin.VMALERT_CRD,
            VmalertSourceOrigin.SERVICE_HEURISTIC,
        ),
    )
    provenance = source.display_provenance
    assert "VMAlert CRD" in provenance
    assert "Service Heuristic" in provenance


# --- Deduplication artifact_id Preservation Tests ---


def test_merge_deduplicate_inventory_preserves_artifact_id() -> None:
    """Regression: merge_deduplicate_inventory must preserve artifact_id."""
    inventory = VmalertSourceInventory()
    original_artifact_id = inventory.artifact_id

    # Add duplicate CRD + Service sources with same namespace/name
    inventory.add_source(VmalertSource(
        source_id="crd:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.VMALERT_CRD,
    ))
    inventory.add_source(VmalertSource(
        source_id="service:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
    ))

    merged = merge_deduplicate_inventory(inventory)

    # artifact_id must be preserved through deduplication
    assert merged.artifact_id == original_artifact_id


def test_discover_vmalerts_default_dedup_collapses_to_one() -> None:
    """Test that discover_vmalerts() default dedup behavior collapses CRD + Service duplicates."""
    # Mock both CRD and Service to return the same logical vmalert
    crd_source = VmalertSource(
        source_id="crd:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.VMALERT_CRD,
    )
    service_source = VmalertSource(
        source_id="service:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
    )

    with patch.object(VMAlertCRDDiscoveryStrategy, "discover", return_value=DiscoveryResult(
        sources=(crd_source,),
        strategy="vmalert-crd",
    )), patch.object(ServiceHeuristicDiscoveryStrategy, "discover", return_value=DiscoveryResult(
        sources=(service_source,),
        strategy="service-heuristic",
    )):
        inventory = discover_vmalerts()

    # Only one source should remain
    assert len(inventory.sources) == 1

    # VMAlert CRD should win (higher priority)
    winner = list(inventory.sources.values())[0]
    assert winner.origin == VmalertSourceOrigin.VMALERT_CRD

    # merged_provenances should include both origins
    assert VmalertSourceOrigin.VMALERT_CRD in winner.merged_provenances
    assert VmalertSourceOrigin.SERVICE_HEURISTIC in winner.merged_provenances


# --- Service Heuristic Label/Name Behavior Tests ---


def test_vmalert_prefix_name_without_labels_accepted() -> None:
    """Test that vmalert-prefix name without labels is accepted (prefix is strong signal)."""
    strategy = ServiceHeuristicDiscoveryStrategy()

    service = {
        "metadata": {
            "name": "vmalert-main",
            "namespace": "monitoring",
            "uid": "uid-vmalert-main",
            "labels": {},  # No labels
        },
        "spec": {
            "ports": [{"port": 8080, "protocol": "TCP"}],
        },
    }

    source = strategy._parse_service_item(service, None)

    # vmalert-prefix should be accepted even without labels
    assert source is not None
    assert source.name == "vmalert-main"


def test_contains_vmalert_without_labels_rejected() -> None:
    """Test that 'contains vmalert' without vmalert- prefix and without labels is rejected."""
    strategy = ServiceHeuristicDiscoveryStrategy()

    service = {
        "metadata": {
            "name": "my-vmalert-service",
            "namespace": "monitoring",
            "uid": "uid-mixed",
            "labels": {},  # No labels
        },
        "spec": {
            "ports": [{"port": 8080, "protocol": "TCP"}],
        },
    }

    source = strategy._parse_service_item(service, None)

    # Contains match without prefix and without labels should be rejected
    # (stricter behavior to reduce false positives)
    assert source is None


def test_non_vmalert_service_with_operator_label_rejected() -> None:
    """Test that non-vmalert service with only generic operator.victoriametrics.com/name is rejected."""
    strategy = ServiceHeuristicDiscoveryStrategy()

    service = {
        "metadata": {
            "name": "prometheus-server",
            "namespace": "monitoring",
            "uid": "uid-prom",
            "labels": {
                "operator.victoriametrics.com/name": "some-resource",
            },
        },
        "spec": {
            "ports": [{"port": 9090, "protocol": "TCP"}],
        },
    }

    source = strategy._parse_service_item(service, None)

    # Non-vmalert name should be rejected even with operator label
    assert source is None


def test_vmalert_service_with_operator_label_accepted() -> None:
    """Test that vmalert service with operator.victoriametrics.com/name label is accepted."""
    strategy = ServiceHeuristicDiscoveryStrategy()

    service = {
        "metadata": {
            "name": "my-vmalert-service",
            "namespace": "monitoring",
            "uid": "uid-vm",
            "labels": {
                "operator.victoriametrics.com/name": "my-vmalert",
            },
        },
        "spec": {
            "ports": [{"port": 8080, "protocol": "TCP"}],
        },
    }

    source = strategy._parse_service_item(service, None)

    # Contains match with VM operator label should be accepted
    assert source is not None
    assert source.name == "my-vmalert-service"
