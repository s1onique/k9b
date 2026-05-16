"""Import compatibility tests for model_vmalert modularization.

These tests verify that vmalert-related symbols remain importable
from k8s_diag_agent.ui.model after extraction to model_vmalert.py.
"""

from __future__ import annotations

from k8s_diag_agent.ui.model import (
    VmalertSourcesView,
    VmalertSourceView,
    _build_vmalert_sources_view,
)


class TestVmalertImportsReExportedFromModel:
    """Verify all vmalert symbols are importable from model.py (re-export compatibility)."""

    def test_vmalert_source_view_importable(self) -> None:
        """VmalertSourceView should be importable from model."""
        assert VmalertSourceView is not None

    def test_vmalert_sources_view_importable(self) -> None:
        """VmalertSourcesView should be importable from model."""
        assert VmalertSourcesView is not None

    def test_build_vmalert_sources_view_importable(self) -> None:
        """_build_vmalert_sources_view should be importable from model."""
        assert _build_vmalert_sources_view is not None
        assert callable(_build_vmalert_sources_view)


class TestVmalertImportsDirectlyFromModule:
    """Verify vmalert symbols are importable directly from model_vmalert.py."""

    def test_vmalert_source_view_importable_from_module(self) -> None:
        """VmalertSourceView should be importable from model_vmalert."""
        from k8s_diag_agent.ui.model_vmalert import VmalertSourceView
        assert VmalertSourceView is not None

    def test_vmalert_sources_view_importable_from_module(self) -> None:
        """VmalertSourcesView should be importable from model_vmalert."""
        from k8s_diag_agent.ui.model_vmalert import VmalertSourcesView
        assert VmalertSourcesView is not None


class TestVmalertBuilders:
    """Verify vmalert builder functions work correctly."""

    def test_build_vmalert_sources_view_with_valid_data(self) -> None:
        """_build_vmalert_sources_view should build correct view from raw data."""
        raw = {
            "sources": [
                {
                    "source_id": "vmalert-src-1",
                    "matching_key": "http://vmalert:8880",
                    "canonical_identity": "http://vmalert:8880",
                    "endpoint": "http://vmalert:8880",
                    "namespace": "victoria-metrics",
                    "name": "vmalert-main",
                    "origin": "vmalert-crd",
                    "state": "auto-tracked",
                    "merged_provenances": ["vmalert-crd"],
                    "confidence_hints": ["crd_discovery"],
                },
            ],
            "discovery_timestamp": "2024-01-01T00:00:00Z",
            "cluster_context": "kind-prod",
        }
        result = _build_vmalert_sources_view(raw)
        assert result is not None
        assert result.total_count == 1
        assert result.auto_tracked_count == 1
        assert result.discovered_count == 0
        assert result.discovered_but_unverified_count == 0
        assert len(result.sources) == 1
        assert result.sources[0].source_id == "vmalert-src-1"
        assert result.sources[0].display_state == "Auto-tracked"

    def test_build_vmalert_sources_view_with_none(self) -> None:
        """_build_vmalert_sources_view should return None for non-Mapping input."""
        result = _build_vmalert_sources_view(None)
        assert result is None

    def test_build_vmalert_sources_view_with_empty_sources(self) -> None:
        """_build_vmalert_sources_view should handle empty sources list."""
        raw = {
            "sources": [],
            "discovery_timestamp": "2024-01-01T00:00:00Z",
            "cluster_context": "kind-prod",
        }
        result = _build_vmalert_sources_view(raw)
        assert result is not None
        assert result.total_count == 0
        assert result.source_count == 0
        assert result.discovered_count == 0
        assert result.discovered_but_unverified_count == 0
        assert result.auto_tracked_count == 0
        assert result.manual_count == 0
        assert len(result.sources) == 0

    def test_build_vmalert_sources_view_counts_discovered_but_unverified(self) -> None:
        """_build_vmalert_sources_view should count discovered-but-unverified correctly."""
        raw = {
            "sources": [
                {
                    "source_id": "vmalert-src-1",
                    "endpoint": "http://vmalert:8880",
                    "origin": "service-heuristic",
                    "state": "discovered-but-unverified",
                    "confidence_hints": [],
                },
                {
                    "source_id": "vmalert-src-2",
                    "endpoint": "http://vmalert2:8880",
                    "origin": "vmalert-crd",
                    "state": "discovered",
                    "confidence_hints": [],
                },
            ],
        }
        result = _build_vmalert_sources_view(raw)
        assert result is not None
        assert result.discovered_but_unverified_count == 1
        assert result.discovered_count == 1
        assert result.source_count == 2

    def test_build_vmalert_sources_view_applies_effective_state(self) -> None:
        """_build_vmalert_sources_view should apply effective_state override."""
        raw = {
            "sources": [
                {
                    "source_id": "vmalert-src-1",
                    "endpoint": "http://vmalert:8880",
                    "origin": "vmalert-crd",
                    "state": "auto-tracked",
                    "effective_state": "manual",
                    "manual_source_mode": "operator-promoted",
                    "confidence_hints": [],
                },
            ],
        }
        result = _build_vmalert_sources_view(raw)
        assert result is not None
        assert len(result.sources) == 1
        # Effective state override should change display
        assert result.sources[0].is_manual is True
        assert result.sources[0].manual_source_mode == "operator-promoted"

    def test_build_vmalert_sources_view_display_labels(self) -> None:
        """_build_vmalert_sources_view should use correct display labels."""
        raw = {
            "sources": [
                {
                    "source_id": "manual-src",
                    "endpoint": "http://vmalert:8880",
                    "origin": "manual",
                    "state": "manual",
                    "confidence_hints": [],
                },
                {
                    "source_id": "crd-src",
                    "endpoint": "http://vmalert2:8880",
                    "origin": "vmalert-crd",
                    "state": "auto-tracked",
                    "confidence_hints": [],
                },
                {
                    "source_id": "service-src",
                    "endpoint": "http://vmalert3:8880",
                    "origin": "service-heuristic",
                    "state": "discovered",
                    "confidence_hints": [],
                },
            ],
        }
        result = _build_vmalert_sources_view(raw)
        assert result is not None
        assert len(result.sources) == 3

        # Manual source
        manual_src = next(s for s in result.sources if s.source_id == "manual-src")
        assert manual_src.display_origin == "Manual"
        assert manual_src.display_state == "Manual"

        # CRD source
        crd_src = next(s for s in result.sources if s.source_id == "crd-src")
        assert crd_src.display_origin == "VMAlert CRD"
        assert crd_src.display_state == "Auto-tracked"

        # Service heuristic source
        service_src = next(s for s in result.sources if s.source_id == "service-src")
        assert service_src.display_origin == "Service Heuristic"
        assert service_src.display_state == "Discovered"
