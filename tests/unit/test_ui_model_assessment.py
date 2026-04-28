"""Tests for model_assessment module import compatibility and behavior.

Verifies that assessment-related symbols remain importable from both:
- k8s_diag_agent.ui.model (backward compatibility)
- k8s_diag_agent.ui.model_assessment (new modular location)
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.model import (
    AssessmentFindingView as Model_AssessmentFindingView,
)
from k8s_diag_agent.ui.model import (
    AssessmentHypothesisView as Model_AssessmentHypothesisView,
)
from k8s_diag_agent.ui.model import (
    AssessmentNextCheckView as Model_AssessmentNextCheckView,
)
from k8s_diag_agent.ui.model import (
    AssessmentView as Model_AssessmentView,
)
from k8s_diag_agent.ui.model import (
    RecommendedActionView as Model_RecommendedActionView,
)
from k8s_diag_agent.ui.model import (
    _build_assessment_findings as Model__build_assessment_findings,
)
from k8s_diag_agent.ui.model import (
    _build_assessment_hypotheses as Model__build_assessment_hypotheses,
)
from k8s_diag_agent.ui.model import (
    _build_assessment_next_checks as Model__build_assessment_next_checks,
)
from k8s_diag_agent.ui.model import (
    _build_assessment_view as Model__build_assessment_view,
)
from k8s_diag_agent.ui.model import (
    _build_recommended_action as Model__build_recommended_action,
)
from k8s_diag_agent.ui.model_assessment import (
    AssessmentFindingView,
    AssessmentHypothesisView,
    AssessmentNextCheckView,
    AssessmentView,
    RecommendedActionView,
    _build_assessment_findings,
    _build_assessment_hypotheses,
    _build_assessment_next_checks,
    _build_assessment_view,
    _build_recommended_action,
)


class TestImportCompatibility(unittest.TestCase):
    """Verify symbols are importable from both locations."""

    def test_assessment_finding_view_importable_from_model_assessment(self) -> None:
        """AssessmentFindingView should be importable from model_assessment."""
        assert AssessmentFindingView is not None

    def test_assessment_finding_view_importable_from_model(self) -> None:
        """AssessmentFindingView should be re-exported from model for backward compatibility."""
        assert Model_AssessmentFindingView is not None

    def test_assessment_hypothesis_view_importable_from_model_assessment(self) -> None:
        """AssessmentHypothesisView should be importable from model_assessment."""
        assert AssessmentHypothesisView is not None

    def test_assessment_hypothesis_view_importable_from_model(self) -> None:
        """AssessmentHypothesisView should be re-exported from model for backward compatibility."""
        assert Model_AssessmentHypothesisView is not None

    def test_assessment_next_check_view_importable_from_model_assessment(self) -> None:
        """AssessmentNextCheckView should be importable from model_assessment."""
        assert AssessmentNextCheckView is not None

    def test_assessment_next_check_view_importable_from_model(self) -> None:
        """AssessmentNextCheckView should be re-exported from model for backward compatibility."""
        assert Model_AssessmentNextCheckView is not None

    def test_recommended_action_view_importable_from_model_assessment(self) -> None:
        """RecommendedActionView should be importable from model_assessment."""
        assert RecommendedActionView is not None

    def test_recommended_action_view_importable_from_model(self) -> None:
        """RecommendedActionView should be re-exported from model for backward compatibility."""
        assert Model_RecommendedActionView is not None

    def test_assessment_view_importable_from_model_assessment(self) -> None:
        """AssessmentView should be importable from model_assessment."""
        assert AssessmentView is not None

    def test_assessment_view_importable_from_model(self) -> None:
        """AssessmentView should be re-exported from model for backward compatibility."""
        assert Model_AssessmentView is not None

    def test_build_assessment_view_importable_from_model_assessment(self) -> None:
        """_build_assessment_view should be importable from model_assessment."""
        assert callable(_build_assessment_view)

    def test_build_assessment_view_importable_from_model(self) -> None:
        """_build_assessment_view should be re-exported from model for backward compatibility."""
        assert callable(Model__build_assessment_view)

    def test_build_assessment_findings_importable_from_model_assessment(self) -> None:
        """_build_assessment_findings should be importable from model_assessment."""
        assert callable(_build_assessment_findings)

    def test_build_assessment_findings_importable_from_model(self) -> None:
        """_build_assessment_findings should be re-exported from model for backward compatibility."""
        assert callable(Model__build_assessment_findings)

    def test_build_assessment_hypotheses_importable_from_model_assessment(self) -> None:
        """_build_assessment_hypotheses should be importable from model_assessment."""
        assert callable(_build_assessment_hypotheses)

    def test_build_assessment_hypotheses_importable_from_model(self) -> None:
        """_build_assessment_hypotheses should be re-exported from model for backward compatibility."""
        assert callable(Model__build_assessment_hypotheses)

    def test_build_assessment_next_checks_importable_from_model_assessment(self) -> None:
        """_build_assessment_next_checks should be importable from model_assessment."""
        assert callable(_build_assessment_next_checks)

    def test_build_assessment_next_checks_importable_from_model(self) -> None:
        """_build_assessment_next_checks should be re-exported from model for backward compatibility."""
        assert callable(Model__build_assessment_next_checks)

    def test_build_recommended_action_importable_from_model_assessment(self) -> None:
        """_build_recommended_action should be importable from model_assessment."""
        assert callable(_build_recommended_action)

    def test_build_recommended_action_importable_from_model(self) -> None:
        """_build_recommended_action should be re-exported from model for backward compatibility."""
        assert callable(Model__build_recommended_action)


class TestAssessmentViewDataclassBehavior(unittest.TestCase):
    """Verify AssessmentView dataclass behavior is preserved."""

    def test_assessment_view_creation(self) -> None:
        """AssessmentView should be created with all required fields."""
        view = AssessmentView(
            cluster_label="test-cluster",
            context="test-context",
            timestamp="2024-01-01T00:00:00Z",
            health_rating="degraded",
            missing_evidence=("evidence1", "evidence2"),
            findings=(),
            hypotheses=(),
            next_checks=(),
            recommended_action=None,
            probable_layer="node",
            overall_confidence="medium",
            artifact_path="/path/to/assessment",
            snapshot_path="/path/to/snapshot",
        )
        assert view.cluster_label == "test-cluster"
        assert view.health_rating == "degraded"
        assert view.findings == ()
        assert view.hypotheses == ()
        assert view.next_checks == ()
        assert view.recommended_action is None

    def test_assessment_view_with_recommended_action(self) -> None:
        """AssessmentView should include recommended action when provided."""
        action = RecommendedActionView(
            action_type="observe",
            description="Check pod logs",
            references=("kubectl logs",),
            safety_level="low-risk",
        )
        view = AssessmentView(
            cluster_label="cluster",
            context="ctx",
            timestamp="ts",
            health_rating="healthy",
            missing_evidence=(),
            findings=(),
            hypotheses=(),
            next_checks=(),
            recommended_action=action,
            probable_layer=None,
            overall_confidence=None,
            artifact_path=None,
            snapshot_path=None,
        )
        assert view.recommended_action is not None
        assert view.recommended_action.action_type == "observe"


class TestAssessmentFindingViewDataclassBehavior(unittest.TestCase):
    """Verify AssessmentFindingView dataclass behavior is preserved."""

    def test_assessment_finding_view_creation(self) -> None:
        """AssessmentFindingView should be created with all fields."""
        view = AssessmentFindingView(
            description="High CPU usage detected",
            layer="workload",
            supporting_signals=("cpu_utilization > 80%",),
        )
        assert view.description == "High CPU usage detected"
        assert view.layer == "workload"
        assert len(view.supporting_signals) == 1

    def test_assessment_finding_view_frozen(self) -> None:
        """AssessmentFindingView should be frozen."""
        with self.assertRaises(Exception):  # dataclasses.FrozenInstanceError
            self.finding.description = "modified"  # type: ignore[misc]

    finding = AssessmentFindingView(
        description="test",
        layer="node",
        supporting_signals=(),
    )


class TestAssessmentHypothesisViewDataclassBehavior(unittest.TestCase):
    """Verify AssessmentHypothesisView dataclass behavior is preserved."""

    def test_assessment_hypothesis_view_creation(self) -> None:
        """AssessmentHypothesisView should be created with all fields."""
        view = AssessmentHypothesisView(
            description="Memory pressure causing OOMKills",
            confidence="medium",
            probable_layer="node",
            what_would_falsify="Node memory within limits",
        )
        assert view.confidence == "medium"
        assert view.probable_layer == "node"


class TestAssessmentNextCheckViewDataclassBehavior(unittest.TestCase):
    """Verify AssessmentNextCheckView dataclass behavior is preserved."""

    def test_assessment_next_check_view_creation(self) -> None:
        """AssessmentNextCheckView should be created with all fields."""
        view = AssessmentNextCheckView(
            description="Check node memory pressure",
            owner="platform-team",
            method="kubectl top nodes",
            evidence_needed=("memory_usage", "memory_limit"),
        )
        assert view.description == "Check node memory pressure"
        assert view.owner == "platform-team"
        assert len(view.evidence_needed) == 2


class TestRecommendedActionViewDataclassBehavior(unittest.TestCase):
    """Verify RecommendedActionView dataclass behavior is preserved."""

    def test_recommended_action_view_creation(self) -> None:
        """RecommendedActionView should be created with all fields."""
        view = RecommendedActionView(
            action_type="change",
            description="Scale deployment",
            references=("kubectl scale",),
            safety_level="change-with-caution",
        )
        assert view.action_type == "change"
        assert view.safety_level == "change-with-caution"


class TestBuildAssessmentViewBehavior(unittest.TestCase):
    """Verify _build_assessment_view behavior is preserved."""

    def test_build_assessment_view_from_valid_mapping(self) -> None:
        """_build_assessment_view should build AssessmentView from raw mapping."""
        raw = {
            "cluster_label": "test-cluster",
            "context": "test-context",
            "timestamp": "2024-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": ["evidence1"],
            "findings": [
                {
                    "description": "High CPU",
                    "layer": "workload",
                    "supporting_signals": ["cpu > 90%"],
                },
            ],
            "hypotheses": [
                {
                    "description": "Resource contention",
                    "confidence": "medium",
                    "probable_layer": "node",
                    "what_would_falsify": "Node resources available",
                },
            ],
            "next_evidence_to_collect": [
                {
                    "description": "Check node metrics",
                    "owner": "platform-team",
                    "method": "kubectl top nodes",
                    "evidence_needed": ["memory", "cpu"],
                },
            ],
            "recommended_action": {
                "type": "observe",
                "description": "Monitor deployment",
                "references": ["kubectl logs"],
                "safety_level": "low-risk",
            },
            "probable_layer_of_origin": "workload",
            "overall_confidence": "high",
            "artifact_path": "/path/to/assessment",
            "snapshot_path": "/path/to/snapshot",
        }
        result = _build_assessment_view(raw)
        assert isinstance(result, AssessmentView)
        assert result.cluster_label == "test-cluster"
        assert result.health_rating == "degraded"
        assert len(result.findings) == 1
        assert len(result.hypotheses) == 1
        assert len(result.next_checks) == 1
        assert result.recommended_action is not None
        assert result.probable_layer == "workload"

    def test_build_assessment_view_with_none_input(self) -> None:
        """_build_assessment_view should return None for None input."""
        result = _build_assessment_view(None)
        assert result is None

    def test_build_assessment_view_with_non_mapping_input(self) -> None:
        """_build_assessment_view should return None for non-Mapping input."""
        result = _build_assessment_view("not a mapping")
        assert result is None

    def test_build_assessment_view_with_non_mapping_input_list(self) -> None:
        """_build_assessment_view should return None for list input."""
        result = _build_assessment_view(["item1", "item2"])
        assert result is None

    def test_build_assessment_view_with_missing_fields(self) -> None:
        """_build_assessment_view should handle missing fields with defaults."""
        raw: dict = {}
        result = _build_assessment_view(raw)
        assert isinstance(result, AssessmentView)
        assert result.cluster_label == "-"
        assert result.context == "-"
        assert result.missing_evidence == ()
        assert result.findings == ()
        assert result.hypotheses == ()
        assert result.next_checks == ()


class TestBuildAssessmentFindingsBehavior(unittest.TestCase):
    """Verify _build_assessment_findings behavior is preserved."""

    def test_build_assessment_findings_from_valid_sequence(self) -> None:
        """_build_assessment_findings should build findings from raw sequence."""
        raw = [
            {
                "description": "Finding 1",
                "layer": "workload",
                "supporting_signals": ["signal1"],
            },
            {
                "description": "Finding 2",
                "layer": "node",
                "supporting_signals": ["signal2", "signal3"],
            },
        ]
        result = _build_assessment_findings(raw)
        assert len(result) == 2
        assert result[0].description == "Finding 1"
        assert result[1].layer == "node"

    def test_build_assessment_findings_with_none_input(self) -> None:
        """_build_assessment_findings should return empty tuple for None."""
        result = _build_assessment_findings(None)
        assert result == ()

    def test_build_assessment_findings_with_non_sequence_input(self) -> None:
        """_build_assessment_findings should return empty tuple for non-Sequence."""
        result = _build_assessment_findings("not a sequence")
        assert result == ()

    def test_build_assessment_findings_skips_non_mapping_entries(self) -> None:
        """_build_assessment_findings should skip non-Mapping entries."""
        raw = [
            "not a mapping",
            {"description": "Valid finding", "layer": "workload", "supporting_signals": []},
            42,
        ]
        result = _build_assessment_findings(raw)
        assert len(result) == 1
        assert result[0].description == "Valid finding"

    def test_build_assessment_findings_coerces_values(self) -> None:
        """_build_assessment_findings should coerce non-string values to strings."""
        raw = [
            {
                "description": 123,
                "layer": "workload",
                "supporting_signals": [1, 2, 3],
            },
        ]
        result = _build_assessment_findings(raw)
        assert len(result) == 1
        assert result[0].description == "123"
        assert result[0].supporting_signals == ("1", "2", "3")


class TestBuildAssessmentHypothesesBehavior(unittest.TestCase):
    """Verify _build_assessment_hypotheses behavior is preserved."""

    def test_build_assessment_hypotheses_from_valid_sequence(self) -> None:
        """_build_assessment_hypotheses should build hypotheses from raw sequence."""
        raw = [
            {
                "description": "Hypothesis 1",
                "confidence": "high",
                "probable_layer": "workload",
                "what_would_falsify": "Low CPU usage",
            },
        ]
        result = _build_assessment_hypotheses(raw)
        assert len(result) == 1
        assert result[0].confidence == "high"

    def test_build_assessment_hypotheses_with_none_input(self) -> None:
        """_build_assessment_hypotheses should return empty tuple for None."""
        result = _build_assessment_hypotheses(None)
        assert result == ()

    def test_build_assessment_hypotheses_with_non_sequence_input(self) -> None:
        """_build_assessment_hypotheses should return empty tuple for non-Sequence."""
        result = _build_assessment_hypotheses(42)
        assert result == ()

    def test_build_assessment_hypotheses_skips_non_mapping_entries(self) -> None:
        """_build_assessment_hypotheses should skip non-Mapping entries."""
        raw = [
            None,
            {"description": "Valid hypothesis", "confidence": "medium", "probable_layer": "node", "what_would_falsify": "N/A"},
        ]
        result = _build_assessment_hypotheses(raw)
        assert len(result) == 1


class TestBuildAssessmentNextChecksBehavior(unittest.TestCase):
    """Verify _build_assessment_next_checks behavior is preserved."""

    def test_build_assessment_next_checks_from_valid_sequence(self) -> None:
        """_build_assessment_next_checks should build next checks from raw sequence."""
        raw = [
            {
                "description": "Check memory",
                "owner": "platform-team",
                "method": "kubectl top nodes",
                "evidence_needed": ["memory_usage", "memory_requests"],
            },
        ]
        result = _build_assessment_next_checks(raw)
        assert len(result) == 1
        assert result[0].owner == "platform-team"

    def test_build_assessment_next_checks_with_none_input(self) -> None:
        """_build_assessment_next_checks should return empty tuple for None."""
        result = _build_assessment_next_checks(None)
        assert result == ()

    def test_build_assessment_next_checks_with_non_sequence_input(self) -> None:
        """_build_assessment_next_checks should return empty tuple for non-Sequence."""
        result = _build_assessment_next_checks({"not": "a sequence"})
        assert result == ()

    def test_build_assessment_next_checks_skips_non_mapping_entries(self) -> None:
        """_build_assessment_next_checks should skip non-Mapping entries."""
        raw = [
            "string entry",
            {
                "description": "Valid check",
                "owner": "ops-team",
                "method": "kubectl get pods",
                "evidence_needed": [],
            },
        ]
        result = _build_assessment_next_checks(raw)
        assert len(result) == 1


class TestBuildRecommendedActionBehavior(unittest.TestCase):
    """Verify _build_recommended_action behavior is preserved."""

    def test_build_recommended_action_from_valid_mapping(self) -> None:
        """_build_recommended_action should build RecommendedActionView from raw mapping."""
        raw = {
            "type": "observe",
            "description": "Monitor deployment health",
            "references": ["kubectl describe deployment"],
            "safety_level": "observe-only",
        }
        result = _build_recommended_action(raw)
        assert isinstance(result, RecommendedActionView)
        assert result.action_type == "observe"
        assert result.safety_level == "observe-only"

    def test_build_recommended_action_with_none_input(self) -> None:
        """_build_recommended_action should return None for None input."""
        result = _build_recommended_action(None)
        assert result is None

    def test_build_recommended_action_with_non_mapping_input(self) -> None:
        """_build_recommended_action should return None for non-Mapping input."""
        result = _build_recommended_action("not a mapping")
        assert result is None

    def test_build_recommended_action_with_non_mapping_input_list(self) -> None:
        """_build_recommended_action should return None for list input."""
        result = _build_recommended_action(["item"])
        assert result is None

    def test_build_recommended_action_coerces_values(self) -> None:
        """_build_recommended_action should coerce non-string values to strings."""
        raw = {
            "type": 123,
            "description": "Test",
            "references": [1, 2, 3],
            "safety_level": "low-risk",
        }
        result = _build_recommended_action(raw)
        assert result is not None
        assert result.action_type == "123"
        assert result.references == ("1", "2", "3")


class TestEquivalenceAcrossModules(unittest.TestCase):
    """Verify that imported symbols from both modules are equivalent."""

    def test_assessment_finding_view_same_type(self) -> None:
        """AssessmentFindingView from both modules should be same type."""
        assert AssessmentFindingView is Model_AssessmentFindingView

    def test_assessment_hypothesis_view_same_type(self) -> None:
        """AssessmentHypothesisView from both modules should be same type."""
        assert AssessmentHypothesisView is Model_AssessmentHypothesisView

    def test_assessment_next_check_view_same_type(self) -> None:
        """AssessmentNextCheckView from both modules should be same type."""
        assert AssessmentNextCheckView is Model_AssessmentNextCheckView

    def test_recommended_action_view_same_type(self) -> None:
        """RecommendedActionView from both modules should be same type."""
        assert RecommendedActionView is Model_RecommendedActionView

    def test_assessment_view_same_type(self) -> None:
        """AssessmentView from both modules should be same type."""
        assert AssessmentView is Model_AssessmentView

    def test_build_assessment_view_same_function(self) -> None:
        """_build_assessment_view from both modules should be same function."""
        assert _build_assessment_view is Model__build_assessment_view

    def test_build_assessment_findings_same_function(self) -> None:
        """_build_assessment_findings from both modules should be same function."""
        assert _build_assessment_findings is Model__build_assessment_findings

    def test_build_assessment_hypotheses_same_function(self) -> None:
        """_build_assessment_hypotheses from both modules should be same function."""
        assert _build_assessment_hypotheses is Model__build_assessment_hypotheses

    def test_build_assessment_next_checks_same_function(self) -> None:
        """_build_assessment_next_checks from both modules should be same function."""
        assert _build_assessment_next_checks is Model__build_assessment_next_checks

    def test_build_recommended_action_same_function(self) -> None:
        """_build_recommended_action from both modules should be same function."""
        assert _build_recommended_action is Model__build_recommended_action


if __name__ == "__main__":
    unittest.main()
