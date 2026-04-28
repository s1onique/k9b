"""Tests for model_cluster module import compatibility and behavior.

Verifies that cluster-related symbols remain importable from both:
- k8s_diag_agent.ui.model (backward compatibility)
- k8s_diag_agent.ui.model_cluster (new modular location)
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.model import (
    ClusterView as Model_ClusterView,
)
from k8s_diag_agent.ui.model import (
    _build_cluster_view as Model__build_cluster_view,
)
from k8s_diag_agent.ui.model_cluster import (
    ClusterView,
    _build_cluster_view,
)


class TestImportCompatibility(unittest.TestCase):
    """Verify symbols are importable from both locations."""

    def test_cluster_view_importable_from_model_cluster(self) -> None:
        """ClusterView should be importable from model_cluster."""
        assert ClusterView is not None

    def test_cluster_view_importable_from_model(self) -> None:
        """ClusterView should be re-exported from model for backward compatibility."""
        assert Model_ClusterView is not None

    def test_build_cluster_view_importable_from_model_cluster(self) -> None:
        """_build_cluster_view should be importable from model_cluster."""
        assert callable(_build_cluster_view)

    def test_build_cluster_view_importable_from_model(self) -> None:
        """_build_cluster_view should be re-exported from model for backward compatibility."""
        assert callable(Model__build_cluster_view)


class TestClusterViewDataclassBehavior(unittest.TestCase):
    """Verify ClusterView dataclass behavior is preserved."""

    def test_cluster_view_creation(self) -> None:
        """ClusterView should be created with all required fields."""
        view = ClusterView(
            label="production",
            context="gke_us_central1",
            cluster_class="gke",
            cluster_role="production",
            baseline_cohort="prod-us",
            node_count=5,
            control_plane_version="1.28",
            health_rating="healthy",
            warnings=2,
            non_running_pods=1,
            baseline_policy_path="/path/to/policy",
            missing_evidence=("evidence1", "evidence2"),
            latest_run_timestamp="2024-01-01T00:00:00Z",
            top_trigger_reason="Node pressure",
            drilldown_available=True,
            drilldown_timestamp="2024-01-01T12:00:00Z",
            snapshot_path="/path/to/snapshot",
            assessment_path="/path/to/assessment",
            drilldown_path="/path/to/drilldown",
        )
        assert view.label == "production"
        assert view.context == "gke_us_central1"
        assert view.node_count == 5
        assert view.health_rating == "healthy"
        assert view.drilldown_available is True
        assert view.snapshot_path == "/path/to/snapshot"
        assert view.missing_evidence == ("evidence1", "evidence2")

    def test_cluster_view_frozen(self) -> None:
        """ClusterView should be frozen."""
        view = ClusterView(
            label="test",
            context="minikube",
            cluster_class="minikube",
            cluster_role="dev",
            baseline_cohort="dev",
            node_count=1,
            control_plane_version="1.27",
            health_rating="unknown",
            warnings=0,
            non_running_pods=0,
            baseline_policy_path="",
            missing_evidence=(),
            latest_run_timestamp="",
            top_trigger_reason=None,
            drilldown_available=False,
            drilldown_timestamp=None,
            snapshot_path=None,
            assessment_path=None,
            drilldown_path=None,
        )
        with self.assertRaises(Exception):  # dataclasses.FrozenInstanceError
            view.label = "modified"  # type: ignore[misc]

    def test_cluster_view_with_optional_fields_none(self) -> None:
        """ClusterView should accept None values for optional fields."""
        view = ClusterView(
            label="test",
            context="context",
            cluster_class="class",
            cluster_role="role",
            baseline_cohort="cohort",
            node_count=1,
            control_plane_version="1.0",
            health_rating="ok",
            warnings=0,
            non_running_pods=0,
            baseline_policy_path="/path",
            missing_evidence=(),
            latest_run_timestamp="2024-01-01",
            top_trigger_reason=None,
            drilldown_available=False,
            drilldown_timestamp=None,
            snapshot_path=None,
            assessment_path=None,
            drilldown_path=None,
        )
        assert view.top_trigger_reason is None
        assert view.drilldown_timestamp is None
        assert view.snapshot_path is None


class TestBuildClusterViewBehavior(unittest.TestCase):
    """Verify _build_cluster_view behavior is preserved."""

    def test_build_cluster_view_from_valid_mapping(self) -> None:
        """_build_cluster_view should build ClusterView from raw mapping."""
        raw = {
            "label": "production",
            "context": "gke_us_central1",
            "cluster_class": "gke",
            "cluster_role": "production",
            "baseline_cohort": "prod-us",
            "node_count": 5,
            "control_plane_version": "1.28",
            "health_rating": "healthy",
            "warnings": 2,
            "non_running_pods": 1,
            "baseline_policy_path": "/path/to/policy",
            "missing_evidence": ["evidence1", "evidence2"],
            "latest_run_timestamp": "2024-01-01T00:00:00Z",
            "top_trigger_reason": "Node pressure",
            "drilldown_available": True,
            "drilldown_timestamp": "2024-01-01T12:00:00Z",
            "artifact_paths": {
                "snapshot": "/path/to/snapshot",
                "assessment": "/path/to/assessment",
                "drilldown": "/path/to/drilldown",
            },
        }
        result = _build_cluster_view(raw)
        assert isinstance(result, ClusterView)
        assert result.label == "production"
        assert result.context == "gke_us_central1"
        assert result.node_count == 5
        assert result.health_rating == "healthy"
        assert result.drilldown_available is True
        assert result.snapshot_path == "/path/to/snapshot"
        assert result.assessment_path == "/path/to/assessment"
        assert result.drilldown_path == "/path/to/drilldown"
        assert result.missing_evidence == ("evidence1", "evidence2")

    def test_build_cluster_view_with_missing_fields(self) -> None:
        """_build_cluster_view should handle missing fields with defaults."""
        raw: dict = {}
        result = _build_cluster_view(raw)
        assert isinstance(result, ClusterView)
        assert result.label == "-"
        assert result.context == "-"
        assert result.node_count == 0
        assert result.health_rating == "-"
        assert result.warnings == 0
        assert result.non_running_pods == 0
        assert result.missing_evidence == ()
        assert result.latest_run_timestamp == "-"
        assert result.top_trigger_reason is None
        assert result.drilldown_available is False
        assert result.drilldown_timestamp is None
        assert result.snapshot_path is None
        assert result.assessment_path is None
        assert result.drilldown_path is None

    def test_build_cluster_view_with_optional_drilldown_fields(self) -> None:
        """_build_cluster_view should handle optional drilldown fields correctly."""
        raw = {
            "label": "test",
            "context": "context",
            "cluster_class": "class",
            "cluster_role": "role",
            "baseline_cohort": "cohort",
            "node_count": 1,
            "control_plane_version": "1.0",
            "health_rating": "ok",
            "warnings": 0,
            "non_running_pods": 0,
            "baseline_policy_path": "/path",
            "missing_evidence": [],
            "latest_run_timestamp": "2024-01-01",
            "drilldown_available": True,
            "drilldown_timestamp": "2024-01-02T00:00:00Z",
            "artifact_paths": {
                "snapshot": None,
                "assessment": None,
                "drilldown": None,
            },
        }
        result = _build_cluster_view(raw)
        assert result.drilldown_available is True
        assert result.drilldown_timestamp == "2024-01-02T00:00:00Z"
        assert result.snapshot_path is None
        assert result.assessment_path is None
        assert result.drilldown_path is None

    def test_build_cluster_view_with_non_string_non_int_values(self) -> None:
        """_build_cluster_view should coerce non-string/non-int values correctly."""
        raw = {
            "label": 123,
            "context": ["invalid"],
            "cluster_class": {"invalid": "type"},
            "cluster_role": "role",
            "baseline_cohort": "cohort",
            "node_count": "not_an_int",
            "control_plane_version": 1.5,
            "health_rating": "ok",
            "warnings": "two",
            "non_running_pods": [],
            "baseline_policy_path": "/path",
            "missing_evidence": [],
            "latest_run_timestamp": "2024-01-01",
            "drilldown_available": "yes",
            "drilldown_timestamp": None,
        }
        result = _build_cluster_view(raw)
        # String coercion: numeric types become strings
        assert result.label == "123"
        assert result.context == "['invalid']"
        assert result.cluster_class == "{'invalid': 'type'}"
        # Int coercion: non-int types become 0
        assert result.node_count == 0
        assert result.warnings == 0
        assert result.non_running_pods == 0
        # String coercion: float becomes string
        assert result.control_plane_version == "1.5"
        # Bool coercion from string "yes"
        assert result.drilldown_available is True


class TestEquivalenceAcrossModules(unittest.TestCase):
    """Verify that imported symbols from both modules are equivalent."""

    def test_cluster_view_same_type(self) -> None:
        """ClusterView from both modules should be same type."""
        assert ClusterView is Model_ClusterView

    def test_build_cluster_view_same_function(self) -> None:
        """_build_cluster_view from both modules should be same function."""
        assert _build_cluster_view is Model__build_cluster_view


if __name__ == "__main__":
    unittest.main()
