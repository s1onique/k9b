"""Tests for Alertmanager source alias collapse projection in UI/API.

These tests verify that when Alertmanager sources are collapsed via alias matching,
the UI serialization produces the correct projection:
- 1 logical source row (canonical source)
- canonical endpoint visible
- alias endpoint visible in the aliases array
- endpoint count = canonical + aliases = 2
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from k8s_diag_agent.external_analysis.alertmanager_discovery_models import (
    AlertmanagerSource,
    AlertmanagerSourceAlias,
    AlertmanagerSourceInventory,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
)
from k8s_diag_agent.health.ui_diagnostic_pack import _serialize_alertmanager_sources


def _make_source(
    source_id: str,
    endpoint: str,
    namespace: str = "monitoring",
    name: str = "alertmanager",
    origin: AlertmanagerSourceOrigin = AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
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
    )


def _write_sources_artifact(output_dir: Path, run_id: str, sources: list[AlertmanagerSource]) -> None:
    """Write an alertmanager-sources artifact to the output directory."""
    from k8s_diag_agent.external_analysis.alertmanager_artifact import (
        write_alertmanager_sources,
    )
    inventory = AlertmanagerSourceInventory(
        sources={s.source_id: s for s in sources},
        cluster_context="test-context",
    )
    write_alertmanager_sources(output_dir, inventory, run_id)


class TestAlertmanagerSourceAliasProjection:
    """Tests for alertmanager source alias projection in UI serialization."""

    def test_collapsible_alias_sources_project_as_one_row(self, tmp_path: Path) -> None:
        """Collapsed chart + alertmanager-operated projects as 1 source row with alias.

        Scenario:
        - chart service (kube-prometheus-stack-alertmanager) is canonical
        - operated service (alertmanager-operated) is an alias
        - Expected: UI sees 1 source row with aliases array containing operated

        This verifies the projection contract:
        - sources length = 1 (canonical only)
        - aliases contains the operated service info
        - both endpoints are visible
        """
        run_id = "test-alias-projection"

        # Create canonical source (chart service) with operated as alias
        chart_source = _make_source(
            source_id="service:monitoring/kube-prometheus-stack-alertmanager",
            endpoint="http://kube-prometheus-stack-alertmanager.monitoring:9093",
            namespace="monitoring",
            name="kube-prometheus-stack-alertmanager",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        # Add alias for the operated service
        chart_with_alias = replace(
            chart_source,
            aliases=(
                AlertmanagerSourceAlias(
                    alias_name="alertmanager-operated",
                    alias_namespace="monitoring",
                    alias_endpoint="http://alertmanager-operated.monitoring:9093",
                    discovery_method=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
                    management_type="operator-managed",
                ),
            ),
        )

        # Write artifact with only the canonical source (operated is alias)
        _write_sources_artifact(tmp_path, run_id, [chart_with_alias])

        # Serialize for UI
        result = _serialize_alertmanager_sources(tmp_path, run_id)

        # Should return serialized data
        assert result is not None, "Expected non-null result from _serialize_alertmanager_sources"
        sources = cast(list[dict], result["sources"])

        # Should have exactly 1 source row (chart is canonical)
        assert len(sources) == 1, f"Expected 1 source row, got {len(sources)}"

        # Get the source data
        source_data = sources[0]
        assert source_data["name"] == "kube-prometheus-stack-alertmanager"
        assert source_data["endpoint"] == "http://kube-prometheus-stack-alertmanager.monitoring:9093"

        # Aliases should contain the operated service
        aliases = source_data.get("aliases", [])
        assert len(aliases) == 1, f"Expected 1 alias, got {len(aliases)}"

        alias_data = aliases[0]
        assert alias_data["alias_name"] == "alertmanager-operated"
        assert alias_data["alias_namespace"] == "monitoring"
        assert alias_data["alias_endpoint"] == "http://alertmanager-operated.monitoring:9093"

        # Verify endpoint visibility
        # Canonical endpoint
        assert "kube-prometheus-stack-alertmanager" in source_data["endpoint"]
        # Alias endpoint is in the aliases array
        alias_endpoints = [a.get("alias_endpoint") for a in aliases]
        assert "http://alertmanager-operated.monitoring:9093" in alias_endpoints

    def test_multiple_sources_with_aliases_project_correctly(self, tmp_path: Path) -> None:
        """Multiple sources with different aliases project correctly.

        Scenario:
        - Source A: has 1 alias
        - Source B: no aliases
        - Source C: has 2 aliases
        - Expected: correct source count and alias counts per row
        """
        run_id = "test-multi-alias-projection"

        # Source A with 1 alias
        source_a = _make_source(
            source_id="service:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
        )
        source_a_with_alias = replace(
            source_a,
            aliases=(
                AlertmanagerSourceAlias(
                    alias_name="alertmanager-main-operated",
                    alias_namespace="monitoring",
                    alias_endpoint="http://alertmanager-main-operated.monitoring:9093",
                    discovery_method=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
                    management_type="operator-managed",
                ),
            ),
        )

        # Source B with no aliases (CRD source)
        source_b = _make_source(
            source_id="crd:prod/alertmanager-prod",
            endpoint="http://alertmanager-prod.prod:9093",
            namespace="prod",
            name="alertmanager-prod",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        )

        # Source C with 2 aliases
        source_c = _make_source(
            source_id="service:monitoring/prometheus-alertmanager",
            endpoint="http://prometheus-alertmanager.monitoring:9093",
            namespace="monitoring",
            name="prometheus-alertmanager",
        )
        source_c_with_aliases = replace(
            source_c,
            aliases=(
                AlertmanagerSourceAlias(
                    alias_name="alertmanager-operated",
                    alias_namespace="monitoring",
                    alias_endpoint="http://alertmanager-operated.monitoring:9093",
                    discovery_method=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
                    management_type="operator-managed",
                ),
                AlertmanagerSourceAlias(
                    alias_name="kube-prometheus-stack-alertmanager",
                    alias_namespace="monitoring",
                    alias_endpoint="http://kube-prometheus-stack-alertmanager.monitoring:9093",
                    discovery_method=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
                    management_type="operator-managed",
                ),
            ),
        )

        # Write all sources
        _write_sources_artifact(tmp_path, run_id, [source_a_with_alias, source_b, source_c_with_aliases])

        # Serialize for UI
        result = _serialize_alertmanager_sources(tmp_path, run_id)

        # Should return serialized data
        assert result is not None
        sources = cast(list[dict], result["sources"])

        # Should have exactly 3 source rows
        assert len(sources) == 3, f"Expected 3 source rows, got {len(sources)}"

        # Build lookup by name for easier assertions
        sources_by_name = {s["name"]: s for s in sources}

        # Source A should have 1 alias
        assert len(sources_by_name["alertmanager-main"]["aliases"]) == 1

        # Source B should have 0 aliases
        assert len(sources_by_name["alertmanager-prod"]["aliases"]) == 0

        # Source C should have 2 aliases
        assert len(sources_by_name["prometheus-alertmanager"]["aliases"]) == 2

    def test_source_without_alias_projects_normally(self, tmp_path: Path) -> None:
        """Source without aliases projects with empty aliases array.

        Scenario:
        - CRD-based source has no aliases
        - Expected: empty aliases array in projection
        """
        run_id = "test-no-alias-projection"

        # Create a CRD source with no aliases
        crd_source = _make_source(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        )

        # Write artifact
        _write_sources_artifact(tmp_path, run_id, [crd_source])

        # Serialize for UI
        result = _serialize_alertmanager_sources(tmp_path, run_id)

        # Should return serialized data
        assert result is not None
        sources = cast(list[dict], result["sources"])

        # Should have exactly 1 source row
        assert len(sources) == 1

        # Source should have empty aliases array
        source_data = sources[0]
        assert source_data["name"] == "alertmanager-main"
        assert source_data.get("aliases", []) == []
