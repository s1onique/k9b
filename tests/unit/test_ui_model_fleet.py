"""Tests for model_fleet module import compatibility and behavior.

Verifies that fleet-status-summary symbols remain importable from both:
- k8s_diag_agent.ui.model (backward compatibility)
- k8s_diag_agent.ui.model_fleet (new modular location)
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.model import (
    FleetStatusSummary as Model_FleetStatusSummary,
)
from k8s_diag_agent.ui.model import (
    _build_fleet_status as Model__build_fleet_status,
)
from k8s_diag_agent.ui.model_fleet import (
    FleetStatusSummary,
    _build_fleet_status,
)


class TestImportCompatibility(unittest.TestCase):
    """Verify symbols are importable from both locations."""

    def test_fleet_status_summary_importable_from_model_fleet(self) -> None:
        """FleetStatusSummary should be importable from model_fleet."""
        assert FleetStatusSummary is not None

    def test_fleet_status_summary_importable_from_model(self) -> None:
        """FleetStatusSummary should be re-exported from model for backward compatibility."""
        assert Model_FleetStatusSummary is not None

    def test_build_fleet_status_importable_from_model_fleet(self) -> None:
        """_build_fleet_status should be importable from model_fleet."""
        assert callable(_build_fleet_status)

    def test_build_fleet_status_importable_from_model(self) -> None:
        """_build_fleet_status should be re-exported from model for backward compatibility."""
        assert callable(Model__build_fleet_status)


class TestFleetStatusSummaryBehavior(unittest.TestCase):
    """Verify FleetStatusSummary dataclass behavior is preserved."""

    def test_fleet_status_summary_creation(self) -> None:
        """FleetStatusSummary should be created with rating counts and degraded clusters."""
        view = FleetStatusSummary(
            rating_counts=(("healthy", 10), ("degraded", 2)),
            degraded_clusters=("cluster-1", "cluster-2"),
        )
        assert len(view.rating_counts) == 2
        assert len(view.degraded_clusters) == 2

    def test_fleet_status_summary_with_empty_values(self) -> None:
        """FleetStatusSummary should accept empty tuples."""
        view = FleetStatusSummary(
            rating_counts=(),
            degraded_clusters=(),
        )
        assert view.rating_counts == ()
        assert view.degraded_clusters == ()


class TestBuildFleetStatusBehavior(unittest.TestCase):
    """Verify _build_fleet_status behavior is preserved."""

    def test_build_fleet_status_from_valid_mapping(self) -> None:
        """_build_fleet_status should build FleetStatusSummary from raw mapping."""
        raw = {
            "rating_counts": [
                {"rating": "healthy", "count": 10},
                {"rating": "degraded", "count": 2},
            ],
            "degraded_clusters": ["cluster-1", "cluster-2"],
        }
        result = _build_fleet_status(raw)
        assert isinstance(result, FleetStatusSummary)
        assert len(result.rating_counts) == 2
        assert result.rating_counts[0] == ("healthy", 10)
        assert result.rating_counts[1] == ("degraded", 2)
        assert len(result.degraded_clusters) == 2

    def test_build_fleet_status_with_none_input(self) -> None:
        """_build_fleet_status should return empty summary for None input."""
        result = _build_fleet_status(None)
        assert isinstance(result, FleetStatusSummary)
        assert result.rating_counts == ()
        assert result.degraded_clusters == ()

    def test_build_fleet_status_with_non_mapping_input(self) -> None:
        """_build_fleet_status should return empty summary for non-Mapping input (list)."""
        result = _build_fleet_status(["not", "a", "mapping"])
        assert isinstance(result, FleetStatusSummary)
        assert result.rating_counts == ()
        assert result.degraded_clusters == ()

    def test_build_fleet_status_with_non_mapping_input_string(self) -> None:
        """_build_fleet_status should return empty summary for non-Mapping input (string)."""
        result = _build_fleet_status("not a mapping")
        assert isinstance(result, FleetStatusSummary)
        assert result.rating_counts == ()
        assert result.degraded_clusters == ()

    def test_build_fleet_status_with_missing_fields(self) -> None:
        """_build_fleet_status should handle missing fields gracefully."""
        raw = {}
        result = _build_fleet_status(raw)
        assert isinstance(result, FleetStatusSummary)
        assert result.rating_counts == ()
        assert result.degraded_clusters == ()

    def test_build_fleet_status_with_empty_rating_counts(self) -> None:
        """_build_fleet_status should handle empty rating_counts list."""
        raw = {
            "rating_counts": [],
            "degraded_clusters": ["cluster-1"],
        }
        result = _build_fleet_status(raw)
        assert isinstance(result, FleetStatusSummary)
        assert result.rating_counts == ()
        assert len(result.degraded_clusters) == 1

    def test_build_fleet_status_skips_non_mapping_entries(self) -> None:
        """_build_fleet_status should skip non-Mapping rating count entries."""
        raw = {
            "rating_counts": [
                "not a mapping",
                {"rating": "healthy", "count": 5},
                42,
            ],
            "degraded_clusters": [],
        }
        result = _build_fleet_status(raw)
        assert isinstance(result, FleetStatusSummary)
        assert len(result.rating_counts) == 1
        assert result.rating_counts[0] == ("healthy", 5)

    def test_build_fleet_status_coerces_values(self) -> None:
        """_build_fleet_status should coerce rating to str and count to int."""
        raw = {
            "rating_counts": [
                {"rating": 123, "count": "5"},
            ],
            "degraded_clusters": [1, 2, 3],
        }
        result = _build_fleet_status(raw)
        assert isinstance(result, FleetStatusSummary)
        assert result.rating_counts[0] == ("123", 5)
        assert result.degraded_clusters == ("1", "2", "3")


class TestEquivalenceAcrossModules(unittest.TestCase):
    """Verify that imported symbols from both modules are equivalent."""

    def test_fleet_status_summary_same_type(self) -> None:
        """FleetStatusSummary from model_fleet and model should be same type."""
        assert FleetStatusSummary is Model_FleetStatusSummary

    def test_build_fleet_status_same_function(self) -> None:
        """_build_fleet_status from both modules should be same function."""
        assert _build_fleet_status is Model__build_fleet_status


if __name__ == "__main__":
    unittest.main()
