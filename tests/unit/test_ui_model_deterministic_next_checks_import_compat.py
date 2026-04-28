"""Import compatibility tests for model_deterministic_next_checks modularization.

These tests verify that deterministic-next-check-related symbols remain importable
from k8s_diag_agent.ui.model after extraction to model_deterministic_next_checks.py.
"""

import unittest
from collections.abc import Mapping


class TestDeterministicNextChecksImportsFromModel(unittest.TestCase):
    """Verify deterministic-next-check symbols are importable from model.py (barrel re-export)."""

    def test_deterministic_next_check_summary_view_importable_from_model(self) -> None:
        """DeterministicNextCheckSummaryView should be importable from model."""
        from k8s_diag_agent.ui.model import DeterministicNextCheckSummaryView

        assert DeterministicNextCheckSummaryView is not None

    def test_deterministic_next_check_cluster_view_importable_from_model(self) -> None:
        """DeterministicNextCheckClusterView should be importable from model."""
        from k8s_diag_agent.ui.model import DeterministicNextCheckClusterView

        assert DeterministicNextCheckClusterView is not None

    def test_deterministic_next_checks_view_importable_from_model(self) -> None:
        """DeterministicNextChecksView should be importable from model."""
        from k8s_diag_agent.ui.model import DeterministicNextChecksView

        assert DeterministicNextChecksView is not None

    def test_build_deterministic_next_checks_view_importable_from_model(self) -> None:
        """_build_deterministic_next_checks_view should be importable from model."""
        from k8s_diag_agent.ui.model import _build_deterministic_next_checks_view

        assert _build_deterministic_next_checks_view is not None

    def test_build_deterministic_next_check_cluster_view_importable_from_model(self) -> None:
        """_build_deterministic_next_check_cluster_view should be importable from model."""
        from k8s_diag_agent.ui.model import _build_deterministic_next_check_cluster_view

        assert _build_deterministic_next_check_cluster_view is not None

    def test_build_deterministic_next_check_summary_view_importable_from_model(self) -> None:
        """_build_deterministic_next_check_summary_view should be importable from model."""
        from k8s_diag_agent.ui.model import _build_deterministic_next_check_summary_view

        assert _build_deterministic_next_check_summary_view is not None


class TestDeterministicNextChecksImportsDirectlyFromModule(unittest.TestCase):
    """Verify deterministic-next-check symbols are importable directly from model_deterministic_next_checks.py."""

    def test_deterministic_next_check_summary_view_importable_from_module(self) -> None:
        """DeterministicNextCheckSummaryView should be importable from model_deterministic_next_checks."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import DeterministicNextCheckSummaryView

        assert DeterministicNextCheckSummaryView is not None

    def test_deterministic_next_check_cluster_view_importable_from_module(self) -> None:
        """DeterministicNextCheckClusterView should be importable from model_deterministic_next_checks."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import DeterministicNextCheckClusterView

        assert DeterministicNextCheckClusterView is not None

    def test_deterministic_next_checks_view_importable_from_module(self) -> None:
        """DeterministicNextChecksView should be importable from model_deterministic_next_checks."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import DeterministicNextChecksView

        assert DeterministicNextChecksView is not None

    def test_build_deterministic_next_checks_view_importable_from_module(self) -> None:
        """_build_deterministic_next_checks_view should be importable from model_deterministic_next_checks."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import _build_deterministic_next_checks_view

        assert _build_deterministic_next_checks_view is not None

    def test_build_deterministic_next_check_cluster_view_importable_from_module(self) -> None:
        """_build_deterministic_next_check_cluster_view should be importable from model_deterministic_next_checks."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import _build_deterministic_next_check_cluster_view

        assert _build_deterministic_next_check_cluster_view is not None

    def test_build_deterministic_next_check_summary_view_importable_from_module(self) -> None:
        """_build_deterministic_next_check_summary_view should be importable from model_deterministic_next_checks."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import _build_deterministic_next_check_summary_view

        assert _build_deterministic_next_check_summary_view is not None


class TestSummaryBuilderBehavior(unittest.TestCase):
    """Builder behavior tests for summary views."""

    def test_build_summary_view_returns_correct_view(self) -> None:
        """_build_deterministic_next_check_summary_view should build view correctly."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import (
            DeterministicNextCheckSummaryView,
            _build_deterministic_next_check_summary_view,
        )

        raw: Mapping[str, object] = {
            "description": "Check pod status",
            "owner": "platform-team",
            "method": "kubectl",
            "evidenceNeeded": ["pods", "events"],
            "workstream": "reliability",
            "urgency": "high",
            "isPrimaryTriage": True,
            "whyNow": "Recent alerts",
            "priorityScore": 85,
        }
        result = _build_deterministic_next_check_summary_view(raw)

        assert isinstance(result, DeterministicNextCheckSummaryView)
        assert result.description == "Check pod status"
        assert result.owner == "platform-team"
        assert result.method == "kubectl"
        assert result.evidence_needed == ("pods", "events")
        assert result.workstream == "reliability"
        assert result.urgency == "high"
        assert result.is_primary_triage is True
        assert result.why_now == "Recent alerts"
        assert result.priority_score == 85

    def test_build_summary_view_handles_none_values(self) -> None:
        """_build_deterministic_next_check_summary_view should handle None/missing values gracefully."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import (
            DeterministicNextCheckSummaryView,
            _build_deterministic_next_check_summary_view,
        )

        raw: Mapping[str, object] = {}
        result = _build_deterministic_next_check_summary_view(raw)

        assert isinstance(result, DeterministicNextCheckSummaryView)
        assert result.description == "-"
        assert result.owner == "-"
        assert result.method == "-"
        assert result.evidence_needed == ()
        assert result.workstream == "-"
        assert result.urgency == "-"
        assert result.is_primary_triage is False
        assert result.why_now == "-"
        assert result.priority_score is None

    def test_build_summary_view_handles_non_mapping_input(self) -> None:
        """_build_deterministic_next_check_summary_view should handle non-Mapping input."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import (
            _build_deterministic_next_check_summary_view,
        )

        # For non-Mapping input, the function will fail at attribute access
        # This is acceptable behavior - the contract expects Mapping input
        with self.assertRaises((TypeError, AttributeError)):
            _build_deterministic_next_check_summary_view(None)


class TestClusterBuilderBehavior(unittest.TestCase):
    """Builder behavior tests for cluster views."""

    def test_build_cluster_view_returns_correct_view(self) -> None:
        """_build_deterministic_next_check_cluster_view should build view correctly."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import (
            DeterministicNextCheckClusterView,
            _build_deterministic_next_check_cluster_view,
        )

        raw: Mapping[str, object] = {
            "label": "prod-cluster",
            "context": "kubernetes",
            "topProblem": "High memory usage",
            "deterministicNextCheckCount": 3,
            "deterministicNextCheckSummaries": [
                {
                    "description": "Check memory",
                    "owner": "platform",
                    "method": "kubectl",
                    "evidenceNeeded": ["nodes"],
                    "workstream": "reliability",
                    "urgency": "high",
                    "isPrimaryTriage": True,
                    "whyNow": "Memory pressure",
                },
            ],
            "drilldownAvailable": True,
            "assessmentArtifactPath": "/path/to/assessment.json",
            "drilldownArtifactPath": "/path/to/drilldown.json",
        }
        result = _build_deterministic_next_check_cluster_view(raw)

        assert isinstance(result, DeterministicNextCheckClusterView)
        assert result.label == "prod-cluster"
        assert result.context == "kubernetes"
        assert result.top_problem == "High memory usage"
        assert result.deterministic_next_check_count == 3
        assert len(result.deterministic_next_check_summaries) == 1
        assert result.drilldown_available is True
        assert result.assessment_artifact_path == "/path/to/assessment.json"
        assert result.drilldown_artifact_path == "/path/to/drilldown.json"

    def test_build_cluster_view_handles_empty_summaries(self) -> None:
        """_build_deterministic_next_check_cluster_view should handle empty summaries gracefully."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import (
            DeterministicNextCheckClusterView,
            _build_deterministic_next_check_cluster_view,
        )

        raw: Mapping[str, object] = {
            "label": "empty-cluster",
            "context": "kubernetes",
            "deterministicNextCheckCount": 0,
            "deterministicNextCheckSummaries": [],
            "drilldownAvailable": False,
        }
        result = _build_deterministic_next_check_cluster_view(raw)

        assert isinstance(result, DeterministicNextCheckClusterView)
        assert result.label == "empty-cluster"
        assert result.deterministic_next_check_count == 0
        assert result.deterministic_next_check_summaries == ()

    def test_build_cluster_view_skips_non_mapping_summaries(self) -> None:
        """_build_deterministic_next_check_cluster_view should skip non-Mapping entries."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import (
            DeterministicNextCheckClusterView,
            _build_deterministic_next_check_cluster_view,
        )

        raw: Mapping[str, object] = {
            "label": "test-cluster",
            "context": "kubernetes",
            "deterministicNextCheckCount": 1,
            "deterministicNextCheckSummaries": [
                "not a mapping",
                None,
                123,
                {
                    "description": "Valid check",
                    "owner": "team",
                    "method": "kubectl",
                    "evidenceNeeded": [],
                    "workstream": "ops",
                    "urgency": "medium",
                    "isPrimaryTriage": False,
                    "whyNow": "Routine check",
                },
            ],
            "drilldownAvailable": False,
        }
        result = _build_deterministic_next_check_cluster_view(raw)

        assert isinstance(result, DeterministicNextCheckClusterView)
        assert len(result.deterministic_next_check_summaries) == 1


class TestViewBuilderBehavior(unittest.TestCase):
    """Builder behavior tests for top-level view."""

    def test_build_view_returns_none_for_non_mapping(self) -> None:
        """_build_deterministic_next_checks_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import _build_deterministic_next_checks_view

        assert _build_deterministic_next_checks_view(None) is None
        assert _build_deterministic_next_checks_view("not a mapping") is None
        assert _build_deterministic_next_checks_view([1, 2, 3]) is None

    def test_build_view_builds_complete_view(self) -> None:
        """_build_deterministic_next_checks_view should build complete view."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import (
            DeterministicNextChecksView,
            _build_deterministic_next_checks_view,
        )

        raw: Mapping[str, object] = {
            "clusterCount": 2,
            "totalNextCheckCount": 5,
            "clusters": [
                {
                    "label": "cluster-1",
                    "context": "kubernetes",
                    "deterministicNextCheckCount": 2,
                    "deterministicNextCheckSummaries": [
                        {
                            "description": "Check 1",
                            "owner": "team",
                            "method": "kubectl",
                            "evidenceNeeded": [],
                            "workstream": "ops",
                            "urgency": "medium",
                            "isPrimaryTriage": False,
                            "whyNow": "Routine",
                        },
                    ],
                    "drilldownAvailable": True,
                },
                {
                    "label": "cluster-2",
                    "context": "kubernetes",
                    "deterministicNextCheckCount": 3,
                    "deterministicNextCheckSummaries": [],
                    "drilldownAvailable": False,
                },
            ],
        }
        result = _build_deterministic_next_checks_view(raw)

        assert isinstance(result, DeterministicNextChecksView)
        assert result.cluster_count == 2
        assert result.total_next_check_count == 5
        assert len(result.clusters) == 2

    def test_build_view_skips_non_mapping_clusters(self) -> None:
        """_build_deterministic_next_checks_view should skip non-Mapping entries in clusters."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import (
            DeterministicNextChecksView,
            _build_deterministic_next_checks_view,
        )

        raw: Mapping[str, object] = {
            "clusterCount": 1,
            "totalNextCheckCount": 2,
            "clusters": [
                "not a mapping",
                None,
                123,
                {
                    "label": "valid-cluster",
                    "context": "kubernetes",
                    "deterministicNextCheckCount": 2,
                    "deterministicNextCheckSummaries": [],
                    "drilldownAvailable": True,
                },
            ],
        }
        result = _build_deterministic_next_checks_view(raw)

        assert isinstance(result, DeterministicNextChecksView)
        assert len(result.clusters) == 1
        assert result.clusters[0].label == "valid-cluster"

    def test_build_view_handles_empty_clusters(self) -> None:
        """_build_deterministic_next_checks_view should handle empty clusters gracefully."""
        from k8s_diag_agent.ui.model_deterministic_next_checks import (
            DeterministicNextChecksView,
            _build_deterministic_next_checks_view,
        )

        raw: Mapping[str, object] = {
            "clusterCount": 0,
            "totalNextCheckCount": 0,
            "clusters": [],
        }
        result = _build_deterministic_next_checks_view(raw)

        assert isinstance(result, DeterministicNextChecksView)
        assert result.cluster_count == 0
        assert result.total_next_check_count == 0
        assert result.clusters == ()


if __name__ == "__main__":
    unittest.main()
