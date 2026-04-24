"""Import compatibility tests for model_next_check_plan modularization.

These tests verify that plan/candidate-related symbols remain importable
from k8s_diag_agent.ui.model after extraction to model_next_check_plan.py.
"""

import unittest
from collections.abc import Mapping


class TestPlanCandidateImportsFromModel(unittest.TestCase):
    """Verify plan/candidate symbols are importable from model.py (barrel re-export)."""

    def test_next_check_candidate_view_importable_from_model(self) -> None:
        """NextCheckCandidateView should be importable from model."""
        from k8s_diag_agent.ui.model import NextCheckCandidateView

        assert NextCheckCandidateView is not None

    def test_next_check_orphaned_approval_view_importable_from_model(self) -> None:
        """NextCheckOrphanedApprovalView should be importable from model."""
        from k8s_diag_agent.ui.model import NextCheckOrphanedApprovalView

        assert NextCheckOrphanedApprovalView is not None

    def test_next_check_outcome_count_view_importable_from_model(self) -> None:
        """NextCheckOutcomeCountView should be importable from model."""
        from k8s_diag_agent.ui.model import NextCheckOutcomeCountView

        assert NextCheckOutcomeCountView is not None

    def test_next_check_plan_view_importable_from_model(self) -> None:
        """NextCheckPlanView should be importable from model."""
        from k8s_diag_agent.ui.model import NextCheckPlanView

        assert NextCheckPlanView is not None

    def test_build_candidate_view_from_plan_importable_from_model(self) -> None:
        """_build_next_check_candidate_view_from_plan should be importable from model."""
        from k8s_diag_agent.ui.model import _build_next_check_candidate_view_from_plan

        assert _build_next_check_candidate_view_from_plan is not None

    def test_build_orphaned_approval_view_importable_from_model(self) -> None:
        """_build_orphaned_approval_view should be importable from model."""
        from k8s_diag_agent.ui.model import _build_orphaned_approval_view

        assert _build_orphaned_approval_view is not None

    def test_build_outcome_count_view_importable_from_model(self) -> None:
        """_build_outcome_count_view should be importable from model."""
        from k8s_diag_agent.ui.model import _build_outcome_count_view

        assert _build_outcome_count_view is not None


class TestPlanCandidateImportsDirectlyFromModule(unittest.TestCase):
    """Verify plan/candidate symbols are importable directly from model_next_check_plan.py."""

    def test_next_check_candidate_view_importable_from_module(self) -> None:
        """NextCheckCandidateView should be importable from model_next_check_plan."""
        from k8s_diag_agent.ui.model_next_check_plan import NextCheckCandidateView

        assert NextCheckCandidateView is not None

    def test_next_check_orphaned_approval_view_importable_from_module(self) -> None:
        """NextCheckOrphanedApprovalView should be importable from model_next_check_plan."""
        from k8s_diag_agent.ui.model_next_check_plan import NextCheckOrphanedApprovalView

        assert NextCheckOrphanedApprovalView is not None

    def test_next_check_outcome_count_view_importable_from_module(self) -> None:
        """NextCheckOutcomeCountView should be importable from model_next_check_plan."""
        from k8s_diag_agent.ui.model_next_check_plan import NextCheckOutcomeCountView

        assert NextCheckOutcomeCountView is not None

    def test_next_check_plan_view_importable_from_module(self) -> None:
        """NextCheckPlanView should be importable from model_next_check_plan."""
        from k8s_diag_agent.ui.model_next_check_plan import NextCheckPlanView

        assert NextCheckPlanView is not None

    def test_build_orphaned_approval_view_importable_from_module(self) -> None:
        """_build_orphaned_approval_view should be importable from model_next_check_plan."""
        from k8s_diag_agent.ui.model_next_check_plan import _build_orphaned_approval_view

        assert _build_orphaned_approval_view is not None

    def test_build_outcome_count_view_importable_from_module(self) -> None:
        """_build_outcome_count_view should be importable from model_next_check_plan."""
        from k8s_diag_agent.ui.model_next_check_plan import _build_outcome_count_view

        assert _build_outcome_count_view is not None

    def test_build_next_check_plan_view_importable_from_module(self) -> None:
        """_build_next_check_plan_view should be importable from model_next_check_plan."""
        from k8s_diag_agent.ui.model_next_check_plan import _build_next_check_plan_view

        assert _build_next_check_plan_view is not None

    def test_build_next_check_candidate_view_from_plan_importable_from_module(self) -> None:
        """_build_next_check_candidate_view_from_plan should be importable from model_next_check_plan."""
        from k8s_diag_agent.ui.model_next_check_plan import (
            _build_next_check_candidate_view_from_plan,
        )

        assert _build_next_check_candidate_view_from_plan is not None


class TestOrphanedApprovalBuilderBehavior(unittest.TestCase):
    """Builder behavior tests for orphaned approval views."""

    def test_build_orphaned_approval_view_returns_correct_view(self) -> None:
        """_build_orphaned_approval_view should build view correctly."""
        from k8s_diag_agent.ui.model_next_check_plan import (
            NextCheckOrphanedApprovalView,
            _build_orphaned_approval_view,
        )

        raw: Mapping[str, object] = {
            "approvalStatus": "approved",
            "candidateId": "test-candidate-1",
            "candidateIndex": 0,
            "candidateDescription": "Check pod status",
            "targetCluster": "prod-cluster",
            "planArtifactPath": "/path/to/plan.json",
            "approvalArtifactPath": "/path/to/approval.json",
            "approvalTimestamp": "2024-01-15T10:00:00Z",
        }
        result = _build_orphaned_approval_view(raw)

        assert isinstance(result, NextCheckOrphanedApprovalView)
        assert result.approval_status == "approved"
        assert result.candidate_id == "test-candidate-1"
        assert result.candidate_index == 0
        assert result.candidate_description == "Check pod status"
        assert result.target_cluster == "prod-cluster"
        assert result.plan_artifact_path == "/path/to/plan.json"
        assert result.approval_artifact_path == "/path/to/approval.json"
        assert result.approval_timestamp == "2024-01-15T10:00:00Z"

    def test_build_orphaned_approval_view_handles_none_values(self) -> None:
        """_build_orphaned_approval_view should handle None/missing values gracefully."""
        from k8s_diag_agent.ui.model_next_check_plan import (
            NextCheckOrphanedApprovalView,
            _build_orphaned_approval_view,
        )

        raw: Mapping[str, object] = {}
        result = _build_orphaned_approval_view(raw)

        assert isinstance(result, NextCheckOrphanedApprovalView)
        assert result.approval_status is None
        assert result.candidate_id is None
        assert result.candidate_index is None
        assert result.candidate_description is None


class TestOutcomeCountBuilderBehavior(unittest.TestCase):
    """Builder behavior tests for outcome count views."""

    def test_build_outcome_count_view_returns_correct_view(self) -> None:
        """_build_outcome_count_view should build view correctly."""
        from k8s_diag_agent.ui.model_next_check_plan import (
            NextCheckOutcomeCountView,
            _build_outcome_count_view,
        )

        raw: Mapping[str, object] = {"status": "approved-ready", "count": 5}
        result = _build_outcome_count_view(raw)

        assert isinstance(result, NextCheckOutcomeCountView)
        assert result.status == "approved-ready"
        assert result.count == 5

    def test_build_outcome_count_view_handles_non_mapping_input(self) -> None:
        """_build_outcome_count_view should return defaults for non-Mapping input."""
        from k8s_diag_agent.ui.model_next_check_plan import (
            NextCheckOutcomeCountView,
            _build_outcome_count_view,
        )

        result = _build_outcome_count_view({"status": None, "count": None})
        assert isinstance(result, NextCheckOutcomeCountView)


class TestCandidateBuilderBehavior(unittest.TestCase):
    """Builder behavior tests for candidate views."""

    def test_build_candidate_view_from_plan_includes_provenance(self) -> None:
        """_build_next_check_candidate_view_from_plan should include Alertmanager provenance."""
        from k8s_diag_agent.ui.model_next_check_plan import (
            NextCheckCandidateView,
            _build_next_check_candidate_view_from_plan,
        )

        raw: Mapping[str, object] = {
            "candidateId": "test-1",
            "description": "kubectl get pods",
            "targetCluster": "prod",
            "safeToAutomate": True,
            "requiresOperatorApproval": False,
            "riskLevel": "low",
            "estimatedCost": "cheap",
            "confidence": "high",
            "duplicateOfExistingEvidence": False,
            "alertmanagerProvenance": {
                "matchedDimensions": ["namespace", "severity"],
                "matchedValues": {"namespace": ("default",)},
                "appliedBonus": 2,
            },
        }
        result = _build_next_check_candidate_view_from_plan(raw)

        assert isinstance(result, NextCheckCandidateView)
        assert result.candidate_id == "test-1"
        assert result.description == "kubectl get pods"
        assert result.safe_to_automate is True
        assert result.alertmanager_provenance is not None
        assert result.alertmanager_provenance.applied_bonus == 2

    def test_build_candidate_view_from_plan_includes_feedback_provenance(self) -> None:
        """_build_next_check_candidate_view_from_plan should include feedback adaptation provenance."""
        from k8s_diag_agent.ui.model_next_check_plan import (
            NextCheckCandidateView,
            _build_next_check_candidate_view_from_plan,
        )

        raw: Mapping[str, object] = {
            "candidateId": "test-2",
            "description": "Check node conditions",
            "safeToAutomate": True,
            "requiresOperatorApproval": False,
            "riskLevel": "low",
            "estimatedCost": "cheap",
            "confidence": "high",
            "duplicateOfExistingEvidence": False,
            "feedbackAdaptationProvenance": {
                "feedbackAdaptation": True,
                "adaptationReason": "operator correction",
                "originalBonus": 3,
                "suppressedBonus": 1,
            },
        }
        result = _build_next_check_candidate_view_from_plan(raw)

        assert isinstance(result, NextCheckCandidateView)
        assert result.feedback_adaptation_provenance is not None
        assert result.feedback_adaptation_provenance.feedback_adaptation is True
        assert result.feedback_adaptation_provenance.adaptation_reason == "operator correction"

    def test_build_candidate_view_from_plan_handles_snake_case_keys(self) -> None:
        """_build_next_check_candidate_view_from_plan should handle snake_case provenance keys."""
        from k8s_diag_agent.ui.model_next_check_plan import (
            NextCheckCandidateView,
            _build_next_check_candidate_view_from_plan,
        )

        raw: Mapping[str, object] = {
            "candidateId": "test-3",
            "description": "Check events",
            "safeToAutomate": True,
            "requiresOperatorApproval": False,
            "riskLevel": "low",
            "estimatedCost": "cheap",
            "confidence": "high",
            "duplicateOfExistingEvidence": False,
            "alertmanager_provenance": {
                "matchedDimensions": ["cluster"],
                "appliedBonus": 1,
            },
            "feedback_adaptation_provenance": {
                "feedbackAdaptation": True,
            },
        }
        result = _build_next_check_candidate_view_from_plan(raw)

        assert isinstance(result, NextCheckCandidateView)
        assert result.alertmanager_provenance is not None
        assert result.alertmanager_provenance.applied_bonus == 1
        assert result.feedback_adaptation_provenance is not None
        assert result.feedback_adaptation_provenance.feedback_adaptation is True


class TestPlanBuilderBehavior(unittest.TestCase):
    """Builder behavior tests for plan views."""

    def test_build_next_check_plan_view_returns_none_for_non_mapping(self) -> None:
        """_build_next_check_plan_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model_next_check_plan import _build_next_check_plan_view

        assert _build_next_check_plan_view(None) is None
        assert _build_next_check_plan_view("not a mapping") is None
        assert _build_next_check_plan_view([1, 2, 3]) is None

    def test_build_next_check_plan_view_builds_complete_view(self) -> None:
        """_build_next_check_plan_view should build complete plan view."""
        from k8s_diag_agent.ui.model_next_check_plan import (
            NextCheckPlanView,
            _build_next_check_plan_view,
        )

        raw: Mapping[str, object] = {
            "status": "success",
            "summary": "Test plan",
            "artifactPath": "/path/to/plan.json",
            "reviewPath": "/path/to/review.json",
            "enrichmentArtifactPath": "/path/to/enrichment.json",
            "candidateCount": 2,
            "candidates": [
                {
                    "candidateId": "c1",
                    "description": "Check pods",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "riskLevel": "low",
                    "estimatedCost": "cheap",
                    "confidence": "high",
                    "duplicateOfExistingEvidence": False,
                },
                {
                    "candidateId": "c2",
                    "description": "Check nodes",
                    "safeToAutomate": False,
                    "requiresOperatorApproval": True,
                    "riskLevel": "medium",
                    "estimatedCost": "moderate",
                    "confidence": "medium",
                    "duplicateOfExistingEvidence": False,
                },
            ],
            "orphanedApprovals": [
                {
                    "approvalStatus": "orphaned",
                    "candidateId": "orphan-1",
                },
            ],
            "outcomeCounts": [
                {"status": "completed", "count": 1},
                {"status": "pending", "count": 1},
            ],
            "orphanedApprovalCount": 1,
        }
        result = _build_next_check_plan_view(raw)

        assert isinstance(result, NextCheckPlanView)
        assert result.status == "success"
        assert result.summary == "Test plan"
        assert result.candidate_count == 2
        assert len(result.candidates) == 2
        assert len(result.orphaned_approvals) == 1
        assert len(result.outcome_counts) == 2
        assert result.orphaned_approval_count == 1

    def test_build_next_check_plan_view_skips_non_mapping_entries(self) -> None:
        """_build_next_check_plan_view should skip non-Mapping entries in lists."""
        from k8s_diag_agent.ui.model_next_check_plan import (
            NextCheckPlanView,
            _build_next_check_plan_view,
        )

        raw: Mapping[str, object] = {
            "status": "success",
            "candidates": [
                {
                    "candidateId": "valid-candidate",
                    "description": "Valid check",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "riskLevel": "low",
                    "estimatedCost": "cheap",
                    "confidence": "high",
                    "duplicateOfExistingEvidence": False,
                },
                "not a mapping",
                None,
                123,
                {"candidateId": "another-valid", "description": "Another check", "safeToAutomate": True, "requiresOperatorApproval": False, "riskLevel": "low", "estimatedCost": "cheap", "confidence": "high", "duplicateOfExistingEvidence": False},
            ],
            "orphanedApprovals": ["invalid", None],
            "outcomeCounts": [None],
        }
        result = _build_next_check_plan_view(raw)

        assert isinstance(result, NextCheckPlanView)
        assert len(result.candidates) == 2
        assert len(result.orphaned_approvals) == 0
        assert len(result.outcome_counts) == 0


if __name__ == "__main__":
    unittest.main()
