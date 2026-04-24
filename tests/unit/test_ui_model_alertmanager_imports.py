"""Import compatibility tests for model_alertmanager modularization.

These tests verify that Alertmanager-related symbols remain importable
from k8s_diag_agent.ui.model after extraction to model_alertmanager.py.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.ui.model import (
    AlertmanagerCompactView,
    AlertmanagerEvidenceReferenceView,
    AlertmanagerProvenanceView,
    AlertmanagerSourceView,
    AlertmanagerSourcesView,
    ClusterAlertSummaryView,
    _build_alertmanager_compact_view,
    _build_alertmanager_evidence_reference_view,
    _build_alertmanager_provenance_view,
    _build_alertmanager_sources_view,
)


class TestAlertmanagerImportsReExportedFromModel:
    """Verify all Alertmanager symbols are importable from model.py (re-export compatibility)."""

    def test_alertmanager_compact_view_importable(self) -> None:
        """AlertmanagerCompactView should be importable from model."""
        from k8s_diag_agent.ui.model import AlertmanagerCompactView
        assert AlertmanagerCompactView is not None

    def test_alertmanager_evidence_reference_view_importable(self) -> None:
        """AlertmanagerEvidenceReferenceView should be importable from model."""
        from k8s_diag_agent.ui.model import AlertmanagerEvidenceReferenceView
        assert AlertmanagerEvidenceReferenceView is not None

    def test_alertmanager_provenance_view_importable(self) -> None:
        """AlertmanagerProvenanceView should be importable from model."""
        from k8s_diag_agent.ui.model import AlertmanagerProvenanceView
        assert AlertmanagerProvenanceView is not None

    def test_alertmanager_source_view_importable(self) -> None:
        """AlertmanagerSourceView should be importable from model."""
        from k8s_diag_agent.ui.model import AlertmanagerSourceView
        assert AlertmanagerSourceView is not None

    def test_alertmanager_sources_view_importable(self) -> None:
        """AlertmanagerSourcesView should be importable from model."""
        from k8s_diag_agent.ui.model import AlertmanagerSourcesView
        assert AlertmanagerSourcesView is not None

    def test_cluster_alert_summary_view_importable(self) -> None:
        """ClusterAlertSummaryView should be importable from model."""
        from k8s_diag_agent.ui.model import ClusterAlertSummaryView
        assert ClusterAlertSummaryView is not None

    def test_build_alertmanager_compact_view_importable(self) -> None:
        """_build_alertmanager_compact_view should be importable from model."""
        from k8s_diag_agent.ui.model import _build_alertmanager_compact_view
        assert _build_alertmanager_compact_view is not None
        assert callable(_build_alertmanager_compact_view)

    def test_build_alertmanager_evidence_reference_view_importable(self) -> None:
        """_build_alertmanager_evidence_reference_view should be importable from model."""
        from k8s_diag_agent.ui.model import _build_alertmanager_evidence_reference_view
        assert _build_alertmanager_evidence_reference_view is not None
        assert callable(_build_alertmanager_evidence_reference_view)

    def test_build_alertmanager_provenance_view_importable(self) -> None:
        """_build_alertmanager_provenance_view should be importable from model."""
        from k8s_diag_agent.ui.model import _build_alertmanager_provenance_view
        assert _build_alertmanager_provenance_view is not None
        assert callable(_build_alertmanager_provenance_view)

    def test_build_alertmanager_sources_view_importable(self) -> None:
        """_build_alertmanager_sources_view should be importable from model."""
        from k8s_diag_agent.ui.model import _build_alertmanager_sources_view
        assert _build_alertmanager_sources_view is not None
        assert callable(_build_alertmanager_sources_view)


class TestAlertmanagerImportsDirectlyFromModule:
    """Verify Alertmanager symbols are importable directly from model_alertmanager.py."""

    def test_alertmanager_compact_view_importable_from_module(self) -> None:
        """AlertmanagerCompactView should be importable from model_alertmanager."""
        from k8s_diag_agent.ui.model_alertmanager import AlertmanagerCompactView
        assert AlertmanagerCompactView is not None

    def test_alertmanager_provenance_view_importable_from_module(self) -> None:
        """AlertmanagerProvenanceView should be importable from model_alertmanager."""
        from k8s_diag_agent.ui.model_alertmanager import AlertmanagerProvenanceView
        assert AlertmanagerProvenanceView is not None


class TestAlertmanagerBuilders:
    """Verify Alertmanager builder functions work correctly."""

    def test_build_alertmanager_provenance_view_with_valid_data(self) -> None:
        """_build_alertmanager_provenance_view should build correct view from raw data."""
        raw = {
            "matched_dimensions": ["namespace", "severity"],
            "matched_values": {"namespace": ["monitoring"], "severity": ["critical", "warning"]},
            "applied_bonus": 15,
            "base_bonus": 5,
            "severity_summary": {"critical": 3, "warning": 5},
            "signal_status": "active",
        }
        result = _build_alertmanager_provenance_view(raw)
        assert result is not None
        assert result.matched_dimensions == ("namespace", "severity")
        assert result.matched_values == {"namespace": ("monitoring",), "severity": ("critical", "warning")}
        assert result.applied_bonus == 15
        assert result.base_bonus == 5
        assert result.severity_summary == {"critical": 3, "warning": 5}
        assert result.signal_status == "active"

    def test_build_alertmanager_provenance_view_with_none(self) -> None:
        """_build_alertmanager_provenance_view should return None for non-Mapping input."""
        result = _build_alertmanager_provenance_view(None)
        assert result is None

    def test_build_alertmanager_evidence_reference_view(self) -> None:
        """_build_alertmanager_evidence_reference_view should build correct view."""
        raw = {
            "cluster": "prod-cluster",
            "matchedDimensions": ["namespace", "service"],
            "reason": "Alert matches candidate target",
            "usedFor": "ranking",
        }
        result = _build_alertmanager_evidence_reference_view(raw)
        assert result.cluster == "prod-cluster"
        assert result.matched_dimensions == ("namespace", "service")
        assert result.reason == "Alert matches candidate target"
        assert result.used_for == "ranking"

    def test_build_alertmanager_sources_view_with_valid_data(self) -> None:
        """_build_alertmanager_sources_view should build correct view from raw data."""
        raw = {
            "sources": [
                {
                    "source_id": "src-1",
                    "matching_key": "http://am:9093",
                    "canonical_identity": "http://am:9093",
                    "endpoint": "http://am:9093",
                    "origin": "manual",
                    "state": "manual",
                    "merged_provenances": ["manual"],
                    "confidence_hints": [],
                },
            ],
            "discovery_timestamp": "2024-01-01T00:00:00Z",
            "cluster_context": "kind-prod",
        }
        result = _build_alertmanager_sources_view(raw)
        assert result is not None
        assert result.total_count == 1
        assert result.manual_count == 1
        assert result.tracked_count == 1
        assert len(result.sources) == 1
        assert result.sources[0].source_id == "src-1"

    def test_build_alertmanager_sources_view_with_none(self) -> None:
        """_build_alertmanager_sources_view should return None for non-Mapping input."""
        result = _build_alertmanager_sources_view(None)
        assert result is None