"""Unit tests for manual source mode handling.

Tests cover:
- ManualSourceMode enum values
- Mode defaults for discovered sources
- Operator-configured sources
- Operator-promoted sources
- Serialization roundtrips with mode preservation
"""

from __future__ import annotations

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
    AlertmanagerSourceMode,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
    build_endpoint_for_manual,
)


class TestManualSourceModeDefaults:
    """Tests for default manual source mode."""

    def test_discovered_source_has_not_manual_mode(self) -> None:
        """Discovered sources should default to NOT_MANUAL mode."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager:9093",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
        )
        assert source.manual_source_mode == AlertmanagerSourceMode.NOT_MANUAL

    def test_operator_configured_source_has_operator_configured_mode(self) -> None:
        """Operator-configured sources (typed endpoint) should have OPERATOR_CONFIGURED mode."""
        source = build_endpoint_for_manual(
            endpoint="alertmanager.monitoring.svc.cluster.local:9093",
            namespace="monitoring",
            name="main",
        )
        assert source.manual_source_mode == AlertmanagerSourceMode.OPERATOR_CONFIGURED
        assert source.origin == AlertmanagerSourceOrigin.MANUAL
        assert source.state == AlertmanagerSourceState.MANUAL

    def test_operator_promoted_source_preserves_discovery_origin(self) -> None:
        """Operator-promoted sources should preserve their original discovery origin."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager:9093",
            namespace="monitoring",
            name="main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            manual_source_mode=AlertmanagerSourceMode.OPERATOR_PROMOTED,
        )
        assert source.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD  # Preserved!
        assert source.manual_source_mode == AlertmanagerSourceMode.OPERATOR_PROMOTED


class TestManualSourceModeSerialization:
    """Tests for manual source mode serialization."""

    def test_to_dict_includes_manual_source_mode_when_not_not_manual(self) -> None:
        """Serialization should include manual_source_mode only when not NOT_MANUAL."""
        # Operator-configured source - should include manual_source_mode
        configured = build_endpoint_for_manual(
            endpoint="alertmanager:9093",
        )
        configured_dict = configured.to_dict()
        assert "manual_source_mode" in configured_dict
        assert configured_dict["manual_source_mode"] == "operator-configured"

        # Operator-promoted source - should include manual_source_mode
        promoted = AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager:9093",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.MANUAL,
            manual_source_mode=AlertmanagerSourceMode.OPERATOR_PROMOTED,
        )
        promoted_dict = promoted.to_dict()
        assert "manual_source_mode" in promoted_dict
        assert promoted_dict["manual_source_mode"] == "operator-promoted"

        # Discovered source - should NOT include manual_source_mode (backward compat)
        discovered = AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager:9093",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )
        discovered_dict = discovered.to_dict()
        assert "manual_source_mode" not in discovered_dict

    def test_from_dict_parses_manual_source_mode(self) -> None:
        """Deserialization should correctly parse manual_source_mode."""
        # With manual_source_mode present
        data = {
            "source_id": "test:source",
            "endpoint": "http://alertmanager:9093",
            "origin": "manual",
            "state": "manual",
            "manual_source_mode": "operator-configured",
        }
        source = AlertmanagerSource.from_dict(data)
        assert source.manual_source_mode == AlertmanagerSourceMode.OPERATOR_CONFIGURED

        # With operator-promoted mode
        data_promoted = {
            "source_id": "test:source",
            "endpoint": "http://alertmanager:9093",
            "origin": "alertmanager-crd",  # Preserved origin!
            "state": "manual",
            "manual_source_mode": "operator-promoted",
        }
        source_promoted = AlertmanagerSource.from_dict(data_promoted)
        assert source_promoted.manual_source_mode == AlertmanagerSourceMode.OPERATOR_PROMOTED
        assert source_promoted.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD

        # Without manual_source_mode (backward compat - defaults to NOT_MANUAL)
        data_legacy = {
            "source_id": "test:source",
            "endpoint": "http://alertmanager:9093",
            "origin": "alertmanager-crd",
            "state": "auto-tracked",
        }
        source_legacy = AlertmanagerSource.from_dict(data_legacy)
        assert source_legacy.manual_source_mode == AlertmanagerSourceMode.NOT_MANUAL


class TestManualSourceModeRoundtrips:
    """Tests for roundtrip serialization with manual source mode."""

    def test_roundtrip_operator_configured_source(self) -> None:
        """Operator-configured source should survive serialization roundtrip."""
        original = build_endpoint_for_manual(
            endpoint="alertmanager.monitoring:9093",
            namespace="monitoring",
            name="main",
        )

        serialized = original.to_dict()
        restored = AlertmanagerSource.from_dict(serialized)

        assert restored.origin == AlertmanagerSourceOrigin.MANUAL
        assert restored.state == AlertmanagerSourceState.MANUAL
        assert restored.manual_source_mode == AlertmanagerSourceMode.OPERATOR_CONFIGURED

    def test_roundtrip_operator_promoted_source(self) -> None:
        """Operator-promoted source should survive serialization roundtrip preserving origin."""
        original = AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager:9093",
            namespace="monitoring",
            name="main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,  # Preserved origin!
            state=AlertmanagerSourceState.MANUAL,
            manual_source_mode=AlertmanagerSourceMode.OPERATOR_PROMOTED,
        )

        serialized = original.to_dict()
        restored = AlertmanagerSource.from_dict(serialized)

        assert restored.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD  # Origin preserved!
        assert restored.state == AlertmanagerSourceState.MANUAL
        assert restored.manual_source_mode == AlertmanagerSourceMode.OPERATOR_PROMOTED


class TestDisplayProvenance:
    """Tests for display provenance with merged origins."""

    def test_display_provenance_single_origin(self) -> None:
        """Test display_provenance for single-origin source."""
        source = AlertmanagerSource(
            source_id="crd:monitoring/alertmanager-main",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        )
        assert source.display_provenance == "Alertmanager CRD"

    def test_display_provenance_merged_origins(self) -> None:
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
