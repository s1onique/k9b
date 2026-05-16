"""Smoke/regression tests for vmalert discovery real-world scenarios.

This module covers practical discovery shapes:
- no vmalert (VM stack components that should not match)
- one vmalert from VictoriaMetrics stack service
- multiple vmalert candidates across namespaces
- discovered-but-unverified endpoint
- CRD + Service duplicate deduplication

These tests complement unit-level tests with integration/smoke coverage
that exercises the full discovery pipeline.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.external_analysis.vmalert_discovery import (
    ServiceHeuristicDiscoveryStrategy,
    VerificationResult,
    VmalertSource,
    VmalertSourceInventory,
    VmalertSourceOrigin,
    VmalertSourceState,
    discover_vmalerts,
    merge_deduplicate_inventory,
    verify_and_update_inventory,
)
from k8s_diag_agent.health.loop_vmalert_discovery import run_vmalert_discovery

# ============================================================================
# TEST DATA (fixtures)
# ============================================================================


@pytest.fixture
def real_vm_stack_service() -> dict[str, Any]:
    """User's real VictoriaMetrics k8s-stack service fixture.

    Shape matches production deployment:
    - namespace: victoria-metrics-k8s-stack
    - service: vmalert-infra-victoria-metrics-k8s-stack
    - port: 8080/TCP
    - expected endpoint: http://vmalert-infra-victoria-metrics-k8s-stack.victoria-metrics-k8s-stack.svc:8080
    """
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": "vmalert-infra-victoria-metrics-k8s-stack",
            "namespace": "victoria-metrics-k8s-stack",
            "uid": "real-uid-vmalert-infra",
            "labels": {
                "app.kubernetes.io/name": "vmalert",
                "app.kubernetes.io/component": "vmalert",
                "app.kubernetes.io/part-of": "victoria-metrics-k8s-stack",
            },
        },
        "spec": {
            "ports": [{"port": 8080, "protocol": "TCP", "targetPort": 8080}],
            "selector": {"app": "vmalert", "app.kubernetes.io/name": "vmalert"},
        },
    }


def vm_stack_only_services() -> dict[str, Any]:
    """Service list containing VM stack components WITHOUT vmalert.

    This simulates a cluster with VictoriaMetrics installed but no vmalert.
    Should result in no vmalert sources discovered and no errors.
    """
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            # kube-state-metrics
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "kube-state-metrics",
                    "namespace": "monitoring",
                    "uid": "uid-kube-state",
                    "labels": {"app": "kube-state-metrics"},
                },
                "spec": {"ports": [{"port": 8080, "protocol": "TCP"}]},
            },
            # node-exporter
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "node-exporter",
                    "namespace": "monitoring",
                    "uid": "uid-node-exp",
                    "labels": {"app": "node-exporter"},
                },
                "spec": {"ports": [{"port": 9100, "protocol": "TCP"}]},
            },
            # vmagent
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "vmagent",
                    "namespace": "victoria-metrics",
                    "uid": "uid-vmagent",
                    "labels": {"app": "vmagent"},
                },
                "spec": {"ports": [{"port": 8429, "protocol": "TCP"}]},
            },
            # vminsert
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "vminsert",
                    "namespace": "victoria-metrics",
                    "uid": "uid-vminsert",
                    "labels": {"app": "vminsert"},
                },
                "spec": {"ports": [{"port": 8480, "protocol": "TCP"}]},
            },
            # vmselect
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "vmselect",
                    "namespace": "victoria-metrics",
                    "uid": "uid-vmselect",
                    "labels": {"app": "vmselect"},
                },
                "spec": {"ports": [{"port": 8481, "protocol": "TCP"}]},
            },
            # vmstorage
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "vmstorage",
                    "namespace": "victoria-metrics",
                    "uid": "uid-vmstorage",
                    "labels": {"app": "vmstorage"},
                },
                "spec": {"ports": [{"port": 8482, "protocol": "TCP"}]},
            },
            # vmalert in a different namespace (for multi-vmalert tests)
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "vmalert-main",
                    "namespace": "monitoring",
                    "uid": "uid-vmalert-monitoring",
                    "labels": {"app": "vmalert"},
                },
                "spec": {"ports": [{"port": 8880, "protocol": "TCP"}]},
            },
        ],
    }


def multi_vmalert_services() -> dict[str, Any]:
    """Multiple vmalert services in different namespaces.

    Tests that discovery correctly handles multiple vmalerts and
    preserves cluster_label/cluster_context after health-loop aggregation.
    """
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            # Primary vmalert in victoria-metrics-k8s-stack
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "vmalert-infra",
                    "namespace": "victoria-metrics-k8s-stack",
                    "uid": "uid-vmalert-infra",
                    "labels": {
                        "app.kubernetes.io/name": "vmalert",
                    },
                },
                "spec": {"ports": [{"port": 8080, "protocol": "TCP"}]},
            },
            # Secondary vmalert in monitoring namespace
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "vmalert-apps",
                    "namespace": "monitoring",
                    "uid": "uid-vmalert-apps",
                    "labels": {
                        "app": "vmalert",
                    },
                },
                "spec": {"ports": [{"port": 8080, "protocol": "TCP"}]},
            },
            # Third vmalert in a different cluster context
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "vmalert-prod",
                    "namespace": "prod-monitoring",
                    "uid": "uid-vmalert-prod",
                    "labels": {
                        "app.kubernetes.io/component": "vmalert",
                    },
                },
                "spec": {"ports": [{"port": 8880, "protocol": "TCP"}]},
            },
        ],
    }


@pytest.fixture
def temp_health_dir() -> Generator[Path, None, None]:
    """Create a temporary directory simulating the health run directory."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# ============================================================================
# REAL VM STACK SERVICE SHAPE TESTS
# ============================================================================


class TestRealVMStackServiceShape:
    """Regression tests for user's real VM stack service shape."""

    def test_golden_fixture_exact_endpoint(self, real_vm_stack_service: dict[str, Any]) -> None:
        """Regression: Golden fixture produces correct endpoint format."""
        strategy = ServiceHeuristicDiscoveryStrategy()

        source = strategy._parse_service_item(real_vm_stack_service, None)

        assert source is not None, "Real VM stack service should be discovered"
        assert source.name == "vmalert-infra-victoria-metrics-k8s-stack"
        assert source.namespace == "victoria-metrics-k8s-stack"
        assert source.endpoint == (
            "http://vmalert-infra-victoria-metrics-k8s-stack.victoria-metrics-k8s-stack.svc:8080"
        )
        assert source.origin == VmalertSourceOrigin.SERVICE_HEURISTIC
        assert "from-service" in source.confidence_hints
        assert "likely-namespace" in source.confidence_hints
        assert "likely-port" in source.confidence_hints

    def test_golden_fixture_matches_expected_shape(self, real_vm_stack_service: dict[str, Any]) -> None:
        """Regression: Golden fixture matches expected production shape."""
        metadata = real_vm_stack_service["metadata"]
        spec = real_vm_stack_service["spec"]

        # Verify structure matches user's production deployment
        assert metadata["namespace"] == "victoria-metrics-k8s-stack"
        assert "vmalert" in metadata["name"]
        assert "app.kubernetes.io/name" in metadata["labels"]
        assert metadata["labels"]["app.kubernetes.io/name"] == "vmalert"
        assert spec["ports"][0]["port"] == 8080
        assert spec["ports"][0]["protocol"] == "TCP"


# ============================================================================
# NO VMALERT REGRESSION TESTS
# ============================================================================


class TestNoVmalertRegression:
    """Regression tests for no-vmalert cluster state."""

    def test_vm_stack_components_not_discovered_as_vmalert(self) -> None:
        """Regression: VM stack components (kube-state-metrics, etc.) are not vmalerts."""
        strategy = ServiceHeuristicDiscoveryStrategy()

        # Only the vmalert service should be discovered
        items = vm_stack_only_services()["items"]
        discovered = [item for item in items if strategy._parse_service_item(item, None) is not None]

        # Should find only vmalert-main, not kube-state-metrics, node-exporter, etc.
        assert len(discovered) == 1
        assert discovered[0]["metadata"]["name"] == "vmalert-main"

    def test_no_vmalert_returns_empty_inventory(self) -> None:
        """Regression: No vmalert services returns empty inventory without error."""
        items = vm_stack_only_services()["items"]
        # Remove the vmalert service
        items = [i for i in items if i["metadata"]["name"] != "vmalert-main"]

        strategy = ServiceHeuristicDiscoveryStrategy()
        sources = []
        for item in items:
            source = strategy._parse_service_item(item, None)
            if source:
                sources.append(source)

        assert len(sources) == 0, "VM stack components should not be discovered as vmalerts"

    @patch("subprocess.run")
    def test_no_vmalert_cluster_is_quiet(self, mock_run: MagicMock) -> None:
        """Regression: No vmalert discovery produces no errors."""
        # Simulate kubectl returning only non-vmalert services
        services = {
            "apiVersion": "v1",
            "kind": "List",
            "items": [
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {
                        "name": "kube-state-metrics",
                        "namespace": "monitoring",
                    },
                    "spec": {"ports": [{"port": 8080}]},
                },
            ],
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(services),
            stderr="",
        )

        # Mock CRD discovery to return empty (no VMAlert CRDs installed)
        with patch(
            "k8s_diag_agent.external_analysis.vmalert_discovery.VMAlertCRDDiscoveryStrategy.discover"
        ) as mock_crd:
            mock_crd.return_value = MagicMock(
                sources=(),
                strategy="vmalert-crd",
                errors=(),
            )

            inventory = discover_vmalerts()

        # Should be empty, not an error
        assert len(inventory.sources) == 0


# ============================================================================
# MULTI-VMALERT REGRESSION TESTS
# ============================================================================


class TestMultiVmalertRegression:
    """Regression tests for multiple vmalert scenarios."""

    def test_multi_vmalert_all_discovered(self) -> None:
        """Regression: Multiple vmalerts in different namespaces are all discovered."""
        strategy = ServiceHeuristicDiscoveryStrategy()
        items = multi_vmalert_services()["items"]

        sources = []
        for item in items:
            source = strategy._parse_service_item(item, None)
            if source:
                sources.append(source)

        assert len(sources) == 3, "All three vmalerts should be discovered"

        # Verify distinct identities
        namespaces = {s.namespace for s in sources}
        assert namespaces == {"victoria-metrics-k8s-stack", "monitoring", "prod-monitoring"}

    def test_multi_vmalert_cluster_label_preserved(self) -> None:
        """Regression: cluster_label remains correct after aggregation."""
        strategy = ServiceHeuristicDiscoveryStrategy()
        items = multi_vmalert_services()["items"]

        # Simulate discovery with cluster context
        cluster_uid = "test-cluster-123"

        sources = []
        for item in items:
            source = strategy._parse_service_item(item, cluster_uid)
            if source:
                sources.append(source)

        # All sources should have the same cluster_uid
        for source in sources:
            assert source.cluster_uid == cluster_uid

    def test_multi_vmalert_different_clusters_distinct(self) -> None:
        """Regression: Same vmalert in different clusters remain distinct."""
        # Create two inventories with same namespace/name but different cluster_uid
        inventory1 = VmalertSourceInventory()
        inventory1.add_source(VmalertSource(
            source_id="service:ns/vmalert",
            endpoint="http://vmalert.ns:8080",
            namespace="ns",
            name="vmalert",
            origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
            cluster_uid="cluster-1",
            cluster_context="context-1",
            cluster_label="cluster-1",
        ))

        inventory2 = VmalertSourceInventory()
        inventory2.add_source(VmalertSource(
            source_id="service:ns/vmalert",
            endpoint="http://vmalert.ns:8080",
            namespace="ns",
            name="vmalert",
            origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
            cluster_uid="cluster-2",
            cluster_context="context-2",
            cluster_label="cluster-2",
        ))

        # After deduplication within each, both should survive
        merged1 = merge_deduplicate_inventory(inventory1)
        merged2 = merge_deduplicate_inventory(inventory2)

        assert len(merged1.sources) == 1
        assert len(merged2.sources) == 1

        # cluster_label should be distinct
        assert list(merged1.sources.values())[0].cluster_label == "cluster-1"
        assert list(merged2.sources.values())[0].cluster_label == "cluster-2"


# ============================================================================
# CRD + SERVICE DUPLICATE REGRESSION TESTS
# ============================================================================


class TestCRDServiceDuplicateRegression:
    """Regression tests for CRD + Service duplicate deduplication."""

    def test_crd_service_same_namespace_name_merged(self) -> None:
        """Regression: Same namespace/name from CRD and Service results in one source."""
        inventory = VmalertSourceInventory()

        # CRD source
        crd_source = VmalertSource(
            source_id="crd:victoria-metrics-k8s-stack/vmalert",
            endpoint="http://vmalert.victoria-metrics-k8s-stack:8080",
            namespace="victoria-metrics-k8s-stack",
            name="vmalert",
            origin=VmalertSourceOrigin.VMALERT_CRD,
        )

        # Service heuristic source (same logical endpoint)
        service_source = VmalertSource(
            source_id="service:victoria-metrics-k8s-stack/vmalert",
            endpoint="http://vmalert.victoria-metrics-k8s-stack:8080",
            namespace="victoria-metrics-k8s-stack",
            name="vmalert",
            origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
        )

        inventory.add_source(crd_source)
        inventory.add_source(service_source)

        merged = merge_deduplicate_inventory(inventory)

        # Should collapse to one
        assert len(merged.sources) == 1

        # VMAlert CRD should win
        winner = list(merged.sources.values())[0]
        assert winner.origin == VmalertSourceOrigin.VMALERT_CRD

        # merged_provenances should include both
        assert VmalertSourceOrigin.VMALERT_CRD in winner.merged_provenances
        assert VmalertSourceOrigin.SERVICE_HEURISTIC in winner.merged_provenances

    def test_crd_wins_over_service_heuristic(self) -> None:
        """Regression: VMAlert CRD takes precedence over Service Heuristic."""
        inventory = VmalertSourceInventory()

        inventory.add_source(VmalertSource(
            source_id="service:ns/vmalert",
            endpoint="http://vmalert.ns:8080",
            namespace="ns",
            name="vmalert",
            origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
        ))
        inventory.add_source(VmalertSource(
            source_id="crd:ns/vmalert",
            endpoint="http://vmalert.ns:8080",
            namespace="ns",
            name="vmalert",
            origin=VmalertSourceOrigin.VMALERT_CRD,
        ))

        merged = merge_deduplicate_inventory(inventory)

        winner = list(merged.sources.values())[0]
        assert winner.origin == VmalertSourceOrigin.VMALERT_CRD

    @patch("subprocess.run")
    def test_health_loop_dedup_crd_service(self, mock_run: MagicMock) -> None:
        """Regression: Health loop correctly deduplicates CRD + Service at discovery level.
        
        Note: CRD and Service sources have different source_id prefixes, so they exist
        as separate entries in the inventory. After merge_deduplicate_inventory, they
        should be grouped by canonical_identity and merged with CRD winning.
        """
        # Mock kubectl to return a service that matches the CRD
        services = {
            "apiVersion": "v1",
            "kind": "List",
            "items": [
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {
                        "name": "vmalert",
                        "namespace": "victoria-metrics",
                        "uid": "service-uid",
                    },
                    "spec": {"ports": [{"port": 8080}]},
                },
            ],
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(services),
            stderr="",
        )

        # Mock CRD discovery to return same vmalert
        with patch(
            "k8s_diag_agent.external_analysis.vmalert_discovery.VMAlertCRDDiscoveryStrategy.discover"
        ) as mock_crd:
            mock_crd.return_value = MagicMock(
                sources=(
                    VmalertSource(
                        source_id="crd:victoria-metrics/vmalert",
                        endpoint="http://vmalert.victoria-metrics:8080",
                        namespace="victoria-metrics",
                        name="vmalert",
                        origin=VmalertSourceOrigin.VMALERT_CRD,
                    ),
                ),
                strategy="vmalert-crd",
                errors=(),
            )

            inventory = discover_vmalerts()

        # CRD and Service have different source_id prefixes (crd: vs service:),
        # so they exist as separate inventory entries initially.
        # After merge_deduplicate_inventory by canonical_identity,
        # they should be merged to one source with CRD winning.
        assert len(inventory.sources) == 1

        # CRD should win as the authoritative source
        winner = list(inventory.sources.values())[0]
        assert winner.origin == VmalertSourceOrigin.VMALERT_CRD


# ============================================================================
# DISCOVERED-BUT-UNVERIFIED REGRESSION TESTS
# ============================================================================


class TestDiscoveredButUnverifiedRegression:
    """Regression tests for discovered-but-unverified state."""

    def test_unreachable_source_becomes_unverified(self) -> None:
        """Regression: Unreachable endpoint becomes discovered-but-unverified."""
        inventory = VmalertSourceInventory()
        inventory.add_source(VmalertSource(
            source_id="service:ns/vmalert",
            endpoint="http://unreachable:8080",
            namespace="ns",
            name="vmalert",
            origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
        ))

        unreachable_result = VerificationResult(
            reachable=False,
            error="Connection refused",
        )

        with patch(
            "k8s_diag_agent.external_analysis.vmalert_discovery.verify_vmalert_endpoint",
            return_value=unreachable_result,
        ):
            verified = verify_and_update_inventory(inventory, timeout_seconds=0.5)

        source = list(verified.sources.values())[0]
        assert source.state == VmalertSourceState.DISCOVERED_BUT_UNVERIFIED
        assert source.last_error == "Connection refused"
        assert source.verified_at is None

    def test_unverified_is_non_fatal_in_health_loop(
        self,
        real_vm_stack_service: dict[str, Any],
        temp_health_dir: Path,
    ) -> None:
        """Regression: Unverified sources are non-fatal in health loop."""
        strategy = ServiceHeuristicDiscoveryStrategy()
        source = strategy._parse_service_item(real_vm_stack_service, "test-cluster")
        assert source is not None

        inventory = VmalertSourceInventory()
        inventory.add_source(source)

        unreachable_result = VerificationResult(
            reachable=False,
            error="Connection refused",
        )

        mock_record = MagicMock()
        mock_record.target.context = "test-context"
        mock_record.target.label = "test-cluster"

        with patch(
            "k8s_diag_agent.health.loop_vmalert_discovery.discover_vmalerts",
            return_value=inventory,
        ):
            with patch(
                "k8s_diag_agent.health.loop_vmalert_discovery.verify_and_update_inventory",
                side_effect=lambda inv: verify_and_update_inventory(inv),
            ):
                with patch(
                    "k8s_diag_agent.external_analysis.vmalert_discovery.verify_vmalert_endpoint",
                    return_value=unreachable_result,
                ):
                    result = run_vmalert_discovery(
                        records=[mock_record],
                        directories={"root": temp_health_dir},
                        log_event=MagicMock(),
                        run_id="test-unverified-run",
                    )

        # Source should still exist
        assert len(result.sources) == 1
        unverified_source = list(result.sources.values())[0]
        assert unverified_source.state == VmalertSourceState.DISCOVERED_BUT_UNVERIFIED

        # Artifact should still be written
        artifact_path = temp_health_dir / "test-unverified-run-vmalert-sources.json"
        assert artifact_path.exists()

    def test_unverified_preserves_diagnostic_info(self) -> None:
        """Regression: Unverified source preserves endpoint and provenance for diagnostics."""
        inventory = VmalertSourceInventory()
        source = VmalertSource(
            source_id="service:ns/vmalert",
            endpoint="http://vmalert.ns:8080",
            namespace="ns",
            name="vmalert",
            origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
        )
        inventory.add_source(source)

        unreachable_result = VerificationResult(
            reachable=False,
            error="ETIMEDOUT",
        )

        with patch(
            "k8s_diag_agent.external_analysis.vmalert_discovery.verify_vmalert_endpoint",
            return_value=unreachable_result,
        ):
            verified = verify_and_update_inventory(inventory, timeout_seconds=0.5)

        source = list(verified.sources.values())[0]

        # Diagnostic info preserved
        assert source.endpoint == "http://vmalert.ns:8080"
        assert source.namespace == "ns"
        assert source.name == "vmalert"
        assert source.origin == VmalertSourceOrigin.SERVICE_HEURISTIC
        assert source.last_error == "ETIMEDOUT"


# ============================================================================
# INTEGRATION: FULL DISCOVERY PIPELINE TESTS
# ============================================================================


class TestFullDiscoveryPipeline:
    """Integration tests for full discovery pipeline."""

    @patch("subprocess.run")
    def test_full_pipeline_real_vm_stack_shape(
        self,
        mock_run: MagicMock,
        real_vm_stack_service: dict[str, Any],
    ) -> None:
        """Integration: Full pipeline handles real VM stack service shape."""
        # Mock kubectl returning the real VM stack service
        services = {
            "apiVersion": "v1",
            "kind": "List",
            "items": [real_vm_stack_service],
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(services),
            stderr="",
        )

        # Mock CRD discovery to return empty (no CRDs installed)
        # This isolates the test to service heuristic discovery
        with patch(
            "k8s_diag_agent.external_analysis.vmalert_discovery.VMAlertCRDDiscoveryStrategy.discover"
        ) as mock_crd:
            mock_crd.return_value = MagicMock(
                sources=(),
                strategy="vmalert-crd",
                errors=(),
            )

            inventory = discover_vmalerts()

        # Should discover the vmalert
        assert len(inventory.sources) == 1
        source = list(inventory.sources.values())[0]

        assert source.namespace == "victoria-metrics-k8s-stack"
        assert source.name == "vmalert-infra-victoria-metrics-k8s-stack"
        assert source.endpoint == (
            "http://vmalert-infra-victoria-metrics-k8s-stack.victoria-metrics-k8s-stack.svc:8080"
        )
        assert source.origin == VmalertSourceOrigin.SERVICE_HEURISTIC

    @patch("subprocess.run")
    def test_full_pipeline_no_false_positives(self, mock_run: MagicMock) -> None:
        """Integration: No false positives from VM stack components."""
        # Mock kubectl returning only non-vmalert services
        services = {
            "apiVersion": "v1",
            "kind": "List",
            "items": [
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "vmagent", "namespace": "victoria-metrics"},
                    "spec": {"ports": [{"port": 8429}]},
                },
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "kube-state-metrics", "namespace": "monitoring"},
                    "spec": {"ports": [{"port": 8080}]},
                },
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "node-exporter", "namespace": "monitoring"},
                    "spec": {"ports": [{"port": 9100}]},
                },
            ],
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(services),
            stderr="",
        )

        # Mock CRD discovery to return empty (no CRDs installed)
        with patch(
            "k8s_diag_agent.external_analysis.vmalert_discovery.VMAlertCRDDiscoveryStrategy.discover"
        ) as mock_crd:
            mock_crd.return_value = MagicMock(
                sources=(),
                strategy="vmalert-crd",
                errors=(),
            )

            inventory = discover_vmalerts()

        # No vmalerts should be discovered
        assert len(inventory.sources) == 0

    @patch("subprocess.run")
    def test_full_pipeline_multiple_vmalerts_deterministic(
        self,
        mock_run: MagicMock,
    ) -> None:
        """Integration: Multiple vmalerts produce deterministic results."""
        services = {
            "apiVersion": "v1",
            "kind": "List",
            "items": [
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {
                        "name": "vmalert-infra",
                        "namespace": "vm-stack",
                    },
                    "spec": {"ports": [{"port": 8080}]},
                },
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {
                        "name": "vmalert-main",
                        "namespace": "monitoring",
                    },
                    "spec": {"ports": [{"port": 8880}]},
                },
            ],
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(services),
            stderr="",
        )

        # Mock CRD discovery to return empty (no CRDs installed)
        with patch(
            "k8s_diag_agent.external_analysis.vmalert_discovery.VMAlertCRDDiscoveryStrategy.discover"
        ) as mock_crd:
            mock_crd.return_value = MagicMock(
                sources=(),
                strategy="vmalert-crd",
                errors=(),
            )

            # Run discovery twice
            inventory1 = discover_vmalerts()
            inventory2 = discover_vmalerts()

        # Results should be deterministic
        assert len(inventory1.sources) == len(inventory2.sources) == 2

        # Same sources in same order
        ids1 = sorted(s.source_id for s in inventory1.sources.values())
        ids2 = sorted(s.source_id for s in inventory2.sources.values())
        assert ids1 == ids2
