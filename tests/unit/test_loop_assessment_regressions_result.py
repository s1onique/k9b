"""Tests for RegressionAssessment class (result-type tests)."""

from __future__ import annotations

from k8s_diag_agent.health.loop_assessment_regressions import RegressionAssessment


class TestRegressionAssessment:
    """Tests for RegressionAssessment class."""

    def test_no_regression(self) -> None:
        """RegressionAssessment with no regression detected."""
        result = RegressionAssessment(has_regression=False)
        assert result.has_regression is False
        assert result.workload_regression is False
        assert result.node_regression is False
        assert result.references == []

    def test_workload_regression(self) -> None:
        """RegressionAssessment with workload regression."""
        result = RegressionAssessment(
            has_regression=True,
            workload_regression=True,
        )
        assert result.has_regression is True
        assert result.workload_regression is True
        assert result.node_regression is False

    def test_node_regression(self) -> None:
        """RegressionAssessment with node regression."""
        result = RegressionAssessment(
            has_regression=True,
            node_regression=True,
        )
        assert result.has_regression is True
        assert result.workload_regression is False
        assert result.node_regression is True

    def test_references_tracked(self) -> None:
        """RegressionAssessment tracks references."""
        result = RegressionAssessment(
            has_regression=True,
            references=["regression"],
        )
        assert result.references == ["regression"]
