"""Tests for model_drilldown module import compatibility and behavior.

Verifies that findings/drilldown-related symbols remain importable from both:
- k8s_diag_agent.ui.model (backward compatibility)
- k8s_diag_agent.ui.model_drilldown (new modular location)
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.model import (
    DrilldownAvailabilityView as Model_DrilldownAvailabilityView,
)
from k8s_diag_agent.ui.model import (
    DrilldownCoverageEntry as Model_DrilldownCoverageEntry,
)
from k8s_diag_agent.ui.model import (
    FindingsView as Model_FindingsView,
)
from k8s_diag_agent.ui.model import (
    _build_drilldown_availability as Model__build_drilldown_availability,
)
from k8s_diag_agent.ui.model import (
    _build_drilldown_coverage as Model__build_drilldown_coverage,
)
from k8s_diag_agent.ui.model import (
    _build_findings as Model__build_findings,
)
from k8s_diag_agent.ui.model_drilldown import (
    DrilldownAvailabilityView,
    DrilldownCoverageEntry,
    FindingsView,
    _build_drilldown_availability,
    _build_drilldown_coverage,
    _build_findings,
)


class TestImportCompatibility(unittest.TestCase):
    """Verify symbols are importable from both locations."""

    def test_findings_view_importable_from_model_drilldown(self) -> None:
        """FindingsView should be importable from model_drilldown."""
        assert FindingsView is not None

    def test_findings_view_importable_from_model(self) -> None:
        """FindingsView should be re-exported from model for backward compatibility."""
        assert Model_FindingsView is not None

    def test_drilldown_coverage_entry_importable_from_model_drilldown(self) -> None:
        """DrilldownCoverageEntry should be importable from model_drilldown."""
        assert DrilldownCoverageEntry is not None

    def test_drilldown_coverage_entry_importable_from_model(self) -> None:
        """DrilldownCoverageEntry should be re-exported from model for backward compatibility."""
        assert Model_DrilldownCoverageEntry is not None

    def test_drilldown_availability_view_importable_from_model_drilldown(self) -> None:
        """DrilldownAvailabilityView should be importable from model_drilldown."""
        assert DrilldownAvailabilityView is not None

    def test_drilldown_availability_view_importable_from_model(self) -> None:
        """DrilldownAvailabilityView should be re-exported from model for backward compatibility."""
        assert Model_DrilldownAvailabilityView is not None

    def test_build_findings_importable_from_model_drilldown(self) -> None:
        """_build_findings should be importable from model_drilldown."""
        assert callable(_build_findings)

    def test_build_findings_importable_from_model(self) -> None:
        """_build_findings should be re-exported from model for backward compatibility."""
        assert callable(Model__build_findings)

    def test_build_drilldown_coverage_importable_from_model_drilldown(self) -> None:
        """_build_drilldown_coverage should be importable from model_drilldown."""
        assert callable(_build_drilldown_coverage)

    def test_build_drilldown_coverage_importable_from_model(self) -> None:
        """_build_drilldown_coverage should be re-exported from model for backward compatibility."""
        assert callable(Model__build_drilldown_coverage)

    def test_build_drilldown_availability_importable_from_model_drilldown(self) -> None:
        """_build_drilldown_availability should be importable from model_drilldown."""
        assert callable(_build_drilldown_availability)

    def test_build_drilldown_availability_importable_from_model(self) -> None:
        """_build_drilldown_availability should be re-exported from model for backward compatibility."""
        assert callable(Model__build_drilldown_availability)


class TestFindingsViewBehavior(unittest.TestCase):
    """Verify FindingsView dataclass behavior is preserved."""

    def test_findings_view_creation(self) -> None:
        """FindingsView should be created with all required fields."""
        view = FindingsView(
            label="test-cluster",
            context="prod",
            trigger_reasons=("high_memory",),
            warning_events=5,
            non_running_pods=2,
            summary=(("key1", "value1"),),
            rollout_status=(" rollout-1",),
            pattern_details=(("pattern1", "detail1"),),
            artifact_path="/path/to/findings.json",
        )
        assert view.label == "test-cluster"
        assert view.context == "prod"
        assert view.warning_events == 5

    def test_findings_view_with_none_optional_fields(self) -> None:
        """FindingsView should accept None for optional fields."""
        view = FindingsView(
            label=None,
            context=None,
            trigger_reasons=(),
            warning_events=0,
            non_running_pods=0,
            summary=(),
            rollout_status=(),
            pattern_details=(),
            artifact_path=None,
        )
        assert view.label is None
        assert view.artifact_path is None


class TestBuildFindingsBehavior(unittest.TestCase):
    """Verify _build_findings behavior is preserved."""

    def test_build_findings_from_mapping(self) -> None:
        """_build_findings should build FindingsView from raw mapping."""
        raw = {
            "label": "test-cluster",
            "context": "prod",
            "trigger_reasons": ["high_memory", "high_cpu"],
            "warning_events": 5,
            "non_running_pods": 2,
            "summary": {"key1": "value1", "key2": "value2"},
            "rollout_status": ["rollout-1", "rollout-2"],
            "pattern_details": {"pattern1": "detail1"},
            "artifact_path": "/path/to/findings.json",
        }
        result = _build_findings(raw)
        assert isinstance(result, FindingsView)
        assert result.label == "test-cluster"
        assert result.context == "prod"
        assert result.warning_events == 5
        assert result.non_running_pods == 2
        assert len(result.trigger_reasons) == 2
        assert len(result.summary) == 2

    def test_build_findings_with_none_input(self) -> None:
        """_build_findings should return None for non-Mapping input."""
        result = _build_findings(None)
        assert result is None

    def test_build_findings_with_non_mapping_input(self) -> None:
        """_build_findings should return None for non-Mapping input (list)."""
        result = _build_findings(["not", "a", "mapping"])
        assert result is None

    def test_build_findings_with_non_mapping_input_string(self) -> None:
        """_build_findings should return None for non-Mapping input (string)."""
        result = _build_findings("not a mapping")
        assert result is None

    def test_build_findings_with_missing_fields(self) -> None:
        """_build_findings should handle missing fields gracefully."""
        raw = {}
        result = _build_findings(raw)
        assert isinstance(result, FindingsView)
        assert result.label is None
        assert result.context is None
        assert result.warning_events == 0
        assert result.non_running_pods == 0
        assert result.summary == ()


class TestDrilldownCoverageEntryBehavior(unittest.TestCase):
    """Verify DrilldownCoverageEntry dataclass behavior is preserved."""

    def test_drilldown_coverage_entry_creation(self) -> None:
        """DrilldownCoverageEntry should be created with all fields."""
        entry = DrilldownCoverageEntry(
            label="cluster-1",
            context="prod",
            available=True,
            timestamp="2026-04-24T10:00:00Z",
            artifact_path="/path/to/drilldown.json",
        )
        assert entry.label == "cluster-1"
        assert entry.context == "prod"
        assert entry.available is True
        assert entry.timestamp == "2026-04-24T10:00:00Z"


class TestBuildDrilldownCoverageBehavior(unittest.TestCase):
    """Verify _build_drilldown_coverage behavior is preserved."""

    def test_build_drilldown_coverage_from_mapping(self) -> None:
        """_build_drilldown_coverage should build DrilldownCoverageEntry from raw mapping."""
        raw = {
            "label": "cluster-1",
            "context": "prod",
            "available": True,
            "timestamp": "2026-04-24T10:00:00Z",
            "artifact_path": "/path/to/drilldown.json",
        }
        result = _build_drilldown_coverage(raw)
        assert isinstance(result, DrilldownCoverageEntry)
        assert result.label == "cluster-1"
        assert result.context == "prod"
        assert result.available is True
        assert result.timestamp == "2026-04-24T10:00:00Z"

    def test_build_drilldown_coverage_with_unavailable(self) -> None:
        """_build_drilldown_coverage should handle unavailable drilldown."""
        raw = {
            "label": "cluster-2",
            "context": "dev",
            "available": False,
            "timestamp": None,
            "artifact_path": None,
        }
        result = _build_drilldown_coverage(raw)
        assert result.available is False
        assert result.timestamp is None


class TestDrilldownAvailabilityViewBehavior(unittest.TestCase):
    """Verify DrilldownAvailabilityView dataclass behavior is preserved."""

    def test_drilldown_availability_view_creation(self) -> None:
        """DrilldownAvailabilityView should be created with all fields."""
        entry = DrilldownCoverageEntry(
            label="cluster-1",
            context="prod",
            available=True,
            timestamp="2026-04-24T10:00:00Z",
            artifact_path="/path/to/drilldown.json",
        )
        view = DrilldownAvailabilityView(
            total_clusters=5,
            available=3,
            missing=2,
            missing_clusters=("cluster-4", "cluster-5"),
            coverage=(entry,),
        )
        assert view.total_clusters == 5
        assert view.available == 3
        assert view.missing == 2
        assert len(view.missing_clusters) == 2
        assert len(view.coverage) == 1


class TestBuildDrilldownAvailabilityBehavior(unittest.TestCase):
    """Verify _build_drilldown_availability behavior is preserved."""

    def test_build_from_valid_mapping(self) -> None:
        """_build_drilldown_availability should build DrilldownAvailabilityView from raw mapping."""
        raw = {
            "total_clusters": 5,
            "available": 3,
            "missing": 2,
            "missing_clusters": ["cluster-4", "cluster-5"],
            "coverage": [
                {
                    "label": "cluster-1",
                    "context": "prod",
                    "available": True,
                    "timestamp": "2026-04-24T10:00:00Z",
                    "artifact_path": "/path/to/drilldown1.json",
                },
                {
                    "label": "cluster-2",
                    "context": "dev",
                    "available": False,
                    "timestamp": None,
                    "artifact_path": None,
                },
            ],
        }
        result = _build_drilldown_availability(raw)
        assert isinstance(result, DrilldownAvailabilityView)
        assert result.total_clusters == 5
        assert result.available == 3
        assert result.missing == 2
        assert len(result.missing_clusters) == 2
        assert len(result.coverage) == 2
        assert result.coverage[0].available is True
        assert result.coverage[1].available is False

    def test_build_from_none_input(self) -> None:
        """_build_drilldown_availability should return empty view for non-Mapping input."""
        result = _build_drilldown_availability(None)
        assert isinstance(result, DrilldownAvailabilityView)
        assert result.total_clusters == 0
        assert result.available == 0
        assert result.missing == 0
        assert result.missing_clusters == ()
        assert result.coverage == ()

    def test_build_from_non_mapping_input(self) -> None:
        """_build_drilldown_availability should return empty view for non-Mapping input."""
        result = _build_drilldown_availability("not a mapping")
        assert isinstance(result, DrilldownAvailabilityView)
        assert result.total_clusters == 0
        assert result.coverage == ()

    def test_build_with_empty_coverage(self) -> None:
        """_build_drilldown_availability should handle empty coverage list."""
        raw = {
            "total_clusters": 0,
            "available": 0,
            "missing": 0,
            "missing_clusters": [],
            "coverage": [],
        }
        result = _build_drilldown_availability(raw)
        assert isinstance(result, DrilldownAvailabilityView)
        assert result.coverage == ()

    def test_build_skips_non_mapping_coverage_entries(self) -> None:
        """_build_drilldown_availability should skip non-Mapping coverage entries."""
        raw = {
            "total_clusters": 2,
            "available": 1,
            "missing": 1,
            "missing_clusters": [],
            "coverage": [
                "not a mapping",
                {
                    "label": "cluster-1",
                    "context": "prod",
                    "available": True,
                    "timestamp": "2026-04-24T10:00:00Z",
                    "artifact_path": None,
                },
            ],
        }
        result = _build_drilldown_availability(raw)
        assert len(result.coverage) == 1
        assert result.coverage[0].label == "cluster-1"


class TestEquivalenceAcrossModules(unittest.TestCase):
    """Verify that imported symbols from both modules are equivalent."""

    def test_findings_view_same_type(self) -> None:
        """FindingsView from model_drilldown and model should be same type."""
        assert FindingsView is Model_FindingsView

    def test_drilldown_coverage_entry_same_type(self) -> None:
        """DrilldownCoverageEntry from model_drilldown and model should be same type."""
        assert DrilldownCoverageEntry is Model_DrilldownCoverageEntry

    def test_drilldown_availability_view_same_type(self) -> None:
        """DrilldownAvailabilityView from model_drilldown and model should be same type."""
        assert DrilldownAvailabilityView is Model_DrilldownAvailabilityView

    def test_build_findings_same_function(self) -> None:
        """_build_findings from both modules should be same function."""
        assert _build_findings is Model__build_findings

    def test_build_drilldown_coverage_same_function(self) -> None:
        """_build_drilldown_coverage from both modules should be same function."""
        assert _build_drilldown_coverage is Model__build_drilldown_coverage

    def test_build_drilldown_availability_same_function(self) -> None:
        """_build_drilldown_availability from both modules should be same function."""
        assert _build_drilldown_availability is Model__build_drilldown_availability


if __name__ == "__main__":
    unittest.main()
