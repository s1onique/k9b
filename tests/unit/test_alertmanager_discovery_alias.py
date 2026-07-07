"""Unit tests for Prometheus operator alias resolution.

Tests cover:
- Alias resolution for alertmanager-operated services
- Ambiguous alias scenarios (multiple CRDs)
- Unambiguous alias scenarios (single CRD)
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
    AlertmanagerSourceOrigin,
    _resolve_prometheus_operator_alias,
    merge_deduplicate_inventory,
)
from k8s_diag_agent.external_analysis.alertmanager_discovery_models import (
    AlertmanagerSourceInventory,
)


class TestAliasResolution:
    """Tests for _resolve_prometheus_operator_alias function."""

    def test_prometheus_operator_alias_preserves_cluster_label(self) -> None:
        """Regression test: _resolve_prometheus_operator_alias must preserve cluster_label."""
        # Service source with cluster_label
        service_source = AlertmanagerSource(
            source_id="service:monitoring/alertmanager-operated",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-operated",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            cluster_label="alias-test-cluster",
            cluster_context="alias-test-context",
        )

        # CRD source (for alias resolution to apply)
        crd_source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        )

        all_sources = {"crd:monitoring/alertmanager-main": crd_source}

        # Apply alias resolution
        aliased = _resolve_prometheus_operator_alias(service_source, all_sources)

        # cluster_label MUST be preserved in aliased source
        assert aliased.cluster_label == "alias-test-cluster"
        assert aliased.cluster_context == "alias-test-context"
        # Also verify other fields are correctly set
        assert aliased.name == "alertmanager-main"  # CRD name used
        assert aliased.source_id == "service:monitoring/alertmanager-main"  # Aliased source_id

    def test_prometheus_operator_alias_no_alias_preserves_cluster_label(self) -> None:
        """Regression test: _resolve_prometheus_operator_alias preserves cluster_label when alias not applied."""
        # Non-service-heuristic source with cluster_label
        crd_source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            cluster_label="crd-cluster-preserved",
            cluster_context="crd-context-preserved",
        )

        all_sources: dict[str, AlertmanagerSource] = {}

        # Alias resolution should return source unchanged
        result = _resolve_prometheus_operator_alias(crd_source, all_sources)

        # cluster_label must be preserved
        assert result.cluster_label == "crd-cluster-preserved"
        assert result.cluster_context == "crd-context-preserved"
        assert result.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD


@pytest.mark.mock_kubectl
class TestPrometheusOperatorAliasMerge:
    """Tests for Prometheus operator alias during merge."""

    def test_prometheus_operator_alias_real_scenario(self) -> None:
        """Regression test: Real Prometheus Operator duplicate pattern.

        This is the exact scenario we observed in the UI:
        - CRD source: monitoring/kube-prometheus-stack-alertmanager (from kube-prometheus-stack)
        - Service source: monitoring/alertmanager-operated (Prometheus Operator conventional suffix)
        """
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

        assert len(inventory.sources) == 2

        # Dedup with alias resolution
        result = merge_deduplicate_inventory(inventory)

        # After dedup: 1 source (service aliased to CRD name)
        assert len(result.sources) == 1

        # The merged source should use CRD origin (highest priority)
        merged = next(iter(result.sources.values()))
        assert merged.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD

        # The canonical identity should be the CRD name
        assert merged.canonical_identity == "monitoring/kube-prometheus-stack-alertmanager"

        # Both provenances should be merged
        assert AlertmanagerSourceOrigin.ALERTMANAGER_CRD in merged.merged_provenances
        assert AlertmanagerSourceOrigin.SERVICE_HEURISTIC in merged.merged_provenances

    def test_prometheus_operator_alias_ambiguous_no_alias(self) -> None:
        """Test that alias is NOT applied when mapping is ambiguous (multiple CRDs in namespace)."""
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

    def test_prometheus_operator_alias_single_crd_unambiguous(self) -> None:
        """Test that alias IS applied when there's exactly one CRD in namespace."""
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


class TestPrometheusOperatorAliasHelpers:
    """Tests for alias helper functions."""

    def test_is_headless_operated_service(self) -> None:
        """Test the _is_headless_operated_service helper."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery import _is_headless_operated_service

        # Should return True
        assert _is_headless_operated_service("alertmanager-operated") is True
        assert _is_headless_operated_service("prometheus-operated") is True
        assert _is_headless_operated_service("custom-alertmanager-operated") is True
        assert _is_headless_operated_service("ALERTMANAGER-OPERATED") is True  # case insensitive

        # Should return False
        assert _is_headless_operated_service("kube-prometheus-stack-alertmanager") is False
        assert _is_headless_operated_service("alertmanager-main") is False
        assert _is_headless_operated_service("alertmanager") is False
        assert _is_headless_operated_service("") is False
        assert _is_headless_operated_service(None) is False

    def test_is_chart_alertmanager_service(self) -> None:
        """Test the _is_chart_alertmanager_service helper."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery import _is_chart_alertmanager_service

        # Should return True
        assert _is_chart_alertmanager_service("alertmanager") is True
        assert _is_chart_alertmanager_service("kube-prometheus-stack-alertmanager") is True
        assert _is_chart_alertmanager_service("prometheus-operator-alertmanager") is True
        assert _is_chart_alertmanager_service("grafana-alertmanager") is True
        assert _is_chart_alertmanager_service("ALERTMANAGER") is True  # case insensitive

        # Should return False (ends with -operated)
        assert _is_chart_alertmanager_service("alertmanager-operated") is False
        assert _is_chart_alertmanager_service("prometheus-operated") is False

        # Should return False (no alertmanager in name)
        assert _is_chart_alertmanager_service("nginx") is False
        assert _is_chart_alertmanager_service("") is False
        assert _is_chart_alertmanager_service(None) is False


class TestAliasSerialization:
    """Tests for alias serialization."""

    def test_source_alias_creation(self) -> None:
        """Test AlertmanagerSourceAlias creation and serialization."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_models import (
            AlertmanagerSourceAlias,
        )

        alias = AlertmanagerSourceAlias(
            alias_name="alertmanager-operated",
            alias_namespace="monitoring",
            alias_endpoint="http://alertmanager-operated.monitoring.svc:9093",
            discovery_method=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            management_type="operator-managed",
        )

        assert alias.alias_name == "alertmanager-operated"
        assert alias.alias_namespace == "monitoring"
        assert alias.alias_endpoint == "http://alertmanager-operated.monitoring.svc:9093"
        assert alias.discovery_method == AlertmanagerSourceOrigin.SERVICE_HEURISTIC
        assert alias.management_type == "operator-managed"

    def test_source_alias_to_dict_roundtrip(self) -> None:
        """Test AlertmanagerSourceAlias serialization roundtrip."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_models import (
            AlertmanagerSourceAlias,
        )

        original = AlertmanagerSourceAlias(
            alias_name="alertmanager-main",
            alias_namespace="monitoring",
            alias_endpoint="http://alertmanager-main.monitoring.svc:9093",
            discovery_method=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            management_type="chart-managed",
        )

        serialized = original.to_dict()
        restored = AlertmanagerSourceAlias.from_dict(serialized)

        assert restored.alias_name == original.alias_name
        assert restored.alias_namespace == original.alias_namespace
        assert restored.alias_endpoint == original.alias_endpoint
        assert restored.discovery_method == original.discovery_method
        assert restored.management_type == original.management_type

    def test_source_with_aliases(self) -> None:
        """Test AlertmanagerSource with aliases field."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_models import (
            AlertmanagerSourceAlias,
        )

        alias1 = AlertmanagerSourceAlias(
            alias_name="alertmanager-operated",
            alias_namespace="monitoring",
            alias_endpoint="http://alertmanager-operated.monitoring.svc:9093",
            discovery_method=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            management_type="operator-managed",
        )
        alias2 = AlertmanagerSourceAlias(
            alias_name="alertmanager-main",
            alias_namespace="monitoring",
            alias_endpoint="http://alertmanager-main.monitoring.svc:9093",
            discovery_method=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            management_type="chart-managed",
        )

        source = AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager-main.monitoring.svc:9093",
            namespace="monitoring",
            name="main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            aliases=(alias1, alias2),
        )

        assert len(source.aliases) == 2
        assert source.aliases[0].alias_name == "alertmanager-operated"
        assert source.aliases[1].alias_name == "alertmanager-main"

    def test_source_aliases_to_dict_roundtrip(self) -> None:
        """Test that AlertmanagerSource aliases survive serialization roundtrip."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_models import (
            AlertmanagerSourceAlias,
        )

        alias = AlertmanagerSourceAlias(
            alias_name="alertmanager-operated",
            alias_namespace="monitoring",
            alias_endpoint="http://alertmanager-operated.monitoring.svc:9093",
            discovery_method=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            management_type="operator-managed",
        )

        original = AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager-main.monitoring.svc:9093",
            namespace="monitoring",
            name="main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            aliases=(alias,),
        )

        serialized = original.to_dict()
        assert "aliases" in serialized
        assert len(serialized["aliases"]) == 1

        restored = AlertmanagerSource.from_dict(serialized)
        assert len(restored.aliases) == 1
        assert restored.aliases[0].alias_name == "alertmanager-operated"


class TestManagementTypeInference:
    """Tests for management type inference."""

    def test_infer_management_type_operator_managed(self) -> None:
        """Test _infer_management_type returns operator-managed for -operated services."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_sources import (
            _infer_management_type,
        )

        assert _infer_management_type("alertmanager-operated", "http://test:9093") == "operator-managed"
        assert _infer_management_type("prometheus-operated", "http://test:9093") == "operator-managed"

    def test_infer_management_type_chart_managed(self) -> None:
        """Test _infer_management_type returns chart-managed for known chart patterns."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_sources import (
            _infer_management_type,
        )

        assert _infer_management_type("alertmanager", "http://test:9093") == "chart-managed"
        assert _infer_management_type("kube-prometheus-stack-alertmanager", "http://test:9093") == "chart-managed"
        assert _infer_management_type("prometheus-operator-alertmanager", "http://test:9093") == "chart-managed"

    def test_infer_management_type_unknown(self) -> None:
        """Test _infer_management_type returns unknown for unrecognized patterns."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_sources import (
            _infer_management_type,
        )

        assert _infer_management_type("my-custom-service", "http://test:9093") == "unknown"

    def test_prometheus_operator_alias_with_chart_service(self) -> None:
        """Test that chart services matching CRD name are detected as aliases."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_sources import (
            _resolve_prometheus_operator_alias,
        )

        # CRD source
        crd_source = AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager-main.monitoring.svc:9093",
            namespace="monitoring",
            name="main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        )

        # Chart service with same name as CRD
        chart_service = AlertmanagerSource(
            source_id="service:monitoring/main",
            endpoint="http://alertmanager-main.monitoring.svc:9093",
            namespace="monitoring",
            name="main",  # Same as CRD name
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )

        all_sources = {crd_source.source_id: crd_source, chart_service.source_id: chart_service}

        # The alias resolution should identify this as an alias candidate
        resolved = _resolve_prometheus_operator_alias(chart_service, all_sources)

        # Should be resolved to CRD name
        assert resolved.name == "main"
