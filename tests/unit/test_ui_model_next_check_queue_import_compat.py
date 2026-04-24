"""Import compatibility tests for model_next_check_queue modularization.

These tests verify that queue-related symbols remain importable
from k8s_diag_agent.ui.model after extraction to model_next_check_queue.py.

Scope: M-04b slice
- NextCheckQueueItemView
- NextCheckQueueCandidateAccountingView
- NextCheckQueueClusterStateView
- NextCheckQueueExplanationView
- _build_next_check_queue_view
- _build_queue_cluster_state_view
- _build_queue_candidate_accounting_view
- _build_queue_explanation_view
- _build_queue_item_view (internal helper)
"""

from __future__ import annotations

import unittest


class TestQueueViewsReExportedFromModel(unittest.TestCase):
    """Verify queue symbols are importable from model.py (re-export compatibility)."""

    def test_next_check_queue_item_view_importable(self) -> None:
        """NextCheckQueueItemView should be importable from model."""
        from k8s_diag_agent.ui.model import NextCheckQueueItemView
        assert NextCheckQueueItemView is not None

    def test_next_check_queue_candidate_accounting_view_importable(self) -> None:
        """NextCheckQueueCandidateAccountingView should be importable from model."""
        from k8s_diag_agent.ui.model import NextCheckQueueCandidateAccountingView
        assert NextCheckQueueCandidateAccountingView is not None

    def test_next_check_queue_cluster_state_view_importable(self) -> None:
        """NextCheckQueueClusterStateView should be importable from model."""
        from k8s_diag_agent.ui.model import NextCheckQueueClusterStateView
        assert NextCheckQueueClusterStateView is not None

    def test_next_check_queue_explanation_view_importable(self) -> None:
        """NextCheckQueueExplanationView should be importable from model."""
        from k8s_diag_agent.ui.model import NextCheckQueueExplanationView
        assert NextCheckQueueExplanationView is not None

    def test_build_next_check_queue_view_importable(self) -> None:
        """_build_next_check_queue_view should be importable from model."""
        from k8s_diag_agent.ui.model import _build_next_check_queue_view
        assert _build_next_check_queue_view is not None
        assert callable(_build_next_check_queue_view)

    def test_build_queue_cluster_state_view_importable(self) -> None:
        """_build_queue_cluster_state_view should be importable from model."""
        from k8s_diag_agent.ui.model import _build_queue_cluster_state_view
        assert _build_queue_cluster_state_view is not None
        assert callable(_build_queue_cluster_state_view)

    def test_build_queue_candidate_accounting_view_importable(self) -> None:
        """_build_queue_candidate_accounting_view should be importable from model."""
        from k8s_diag_agent.ui.model import _build_queue_candidate_accounting_view
        assert _build_queue_candidate_accounting_view is not None
        assert callable(_build_queue_candidate_accounting_view)

    def test_build_queue_explanation_view_importable(self) -> None:
        """_build_queue_explanation_view should be importable from model."""
        from k8s_diag_agent.ui.model import _build_queue_explanation_view
        assert _build_queue_explanation_view is not None
        assert callable(_build_queue_explanation_view)


class TestQueueViewsImportableFromModule(unittest.TestCase):
    """Verify queue symbols are importable directly from model_next_check_queue.py."""

    def test_next_check_queue_item_view_from_module(self) -> None:
        """NextCheckQueueItemView should be importable from model_next_check_queue."""
        from k8s_diag_agent.ui.model_next_check_queue import NextCheckQueueItemView
        assert NextCheckQueueItemView is not None

    def test_next_check_queue_candidate_accounting_view_from_module(self) -> None:
        """NextCheckQueueCandidateAccountingView should be importable from model_next_check_queue."""
        from k8s_diag_agent.ui.model_next_check_queue import NextCheckQueueCandidateAccountingView
        assert NextCheckQueueCandidateAccountingView is not None

    def test_next_check_queue_cluster_state_view_from_module(self) -> None:
        """NextCheckQueueClusterStateView should be importable from model_next_check_queue."""
        from k8s_diag_agent.ui.model_next_check_queue import NextCheckQueueClusterStateView
        assert NextCheckQueueClusterStateView is not None

    def test_next_check_queue_explanation_view_from_module(self) -> None:
        """NextCheckQueueExplanationView should be importable from model_next_check_queue."""
        from k8s_diag_agent.ui.model_next_check_queue import NextCheckQueueExplanationView
        assert NextCheckQueueExplanationView is not None

    def test_build_next_check_queue_view_from_module(self) -> None:
        """_build_next_check_queue_view should be importable from model_next_check_queue."""
        from k8s_diag_agent.ui.model_next_check_queue import _build_next_check_queue_view
        assert _build_next_check_queue_view is not None
        assert callable(_build_next_check_queue_view)

    def test_build_queue_item_view_from_module(self) -> None:
        """_build_queue_item_view should be importable from model_next_check_queue."""
        from k8s_diag_agent.ui.model_next_check_queue import _build_queue_item_view
        assert _build_queue_item_view is not None
        assert callable(_build_queue_item_view)


class TestQueueItemViewInstantiation(unittest.TestCase):
    """Verify NextCheckQueueItemView can be instantiated correctly."""

    def test_queue_item_view_minimal(self) -> None:
        """NextCheckQueueItemView should be instantiable with required fields."""
        from k8s_diag_agent.ui.model_next_check_queue import NextCheckQueueItemView

        view = NextCheckQueueItemView(
            candidate_id="cand-123",
            candidate_index=0,
            description="Check pod health",
            target_cluster="prod",
            priority_label="high",
            suggested_command_family="kubectl",
            safe_to_automate=True,
            requires_operator_approval=False,
            approval_state=None,
            execution_state="pending",
            outcome_status=None,
            latest_artifact_path=None,
            queue_status="queued",
            source_reason="alert",
            source_type="alertmanager",
            expected_signal="pod_unhealthy",
            normalization_reason=None,
            safety_reason=None,
            approval_reason=None,
            duplicate_reason=None,
            blocking_reason=None,
            target_context=None,
            command_preview="kubectl get pods",
            plan_artifact_path="/path/to/plan",
        )
        assert view.candidate_id == "cand-123"
        assert view.description == "Check pod health"
        assert view.safe_to_automate is True

    def test_queue_item_view_with_workstream(self) -> None:
        """NextCheckQueueItemView should preserve workstream field."""
        from k8s_diag_agent.ui.model_next_check_queue import NextCheckQueueItemView

        view = NextCheckQueueItemView(
            candidate_id="cand-456",
            candidate_index=1,
            description="Check node pressure",
            target_cluster="staging",
            priority_label="medium",
            suggested_command_family="kubectl",
            safe_to_automate=False,
            requires_operator_approval=True,
            approval_state="pending",
            execution_state=None,
            outcome_status=None,
            latest_artifact_path=None,
            queue_status="approval_needed",
            source_reason="symptom",
            source_type="drilldown",
            expected_signal="node_pressure",
            normalization_reason=None,
            safety_reason="high_risk_operation",
            approval_reason="requires_operator_review",
            duplicate_reason=None,
            blocking_reason=None,
            target_context=None,
            command_preview=None,
            plan_artifact_path=None,
            workstream="workload-availability",
        )
        assert view.workstream == "workload-availability"


class TestQueueBuilders(unittest.TestCase):
    """Verify queue builder functions work correctly."""

    def test_build_next_check_queue_view_null_input(self) -> None:
        """_build_next_check_queue_view should return empty tuple for non-Sequence input."""
        from k8s_diag_agent.ui.model_next_check_queue import _build_next_check_queue_view

        result = _build_next_check_queue_view(None)
        assert result == ()

        result = _build_next_check_queue_view("not a sequence")
        assert result == ()

        result = _build_next_check_queue_view(123)
        assert result == ()

    def test_build_next_check_queue_view_empty_sequence(self) -> None:
        """_build_next_check_queue_view should return empty tuple for empty sequence."""
        from k8s_diag_agent.ui.model_next_check_queue import _build_next_check_queue_view

        result = _build_next_check_queue_view([])
        assert result == ()

        result = _build_next_check_queue_view(())
        assert result == ()

    def test_build_next_check_queue_view_valid_input(self) -> None:
        """_build_next_check_queue_view should build queue items correctly."""
        from k8s_diag_agent.ui.model_next_check_queue import (
            NextCheckQueueItemView,
            _build_next_check_queue_view,
        )

        raw = [
            {
                "candidateId": "cand-001",
                "candidateIndex": 0,
                "description": "Check pod logs",
                "targetCluster": "prod-cluster",
                "priorityLabel": "high",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "approvalState": None,
                "executionState": "pending",
                "outcomeStatus": None,
                "latestArtifactPath": None,
                "queueStatus": "queued",
                "sourceReason": "alert",
                "sourceType": "alertmanager",
                "expectedSignal": "error_in_logs",
            },
        ]
        result = _build_next_check_queue_view(raw)
        assert len(result) == 1
        assert isinstance(result[0], NextCheckQueueItemView)
        assert result[0].candidate_id == "cand-001"
        assert result[0].target_cluster == "prod-cluster"
        assert result[0].queue_status == "queued"

    def test_build_next_check_queue_view_skips_non_mapping(self) -> None:
        """_build_next_check_queue_view should skip non-Mapping entries."""
        from k8s_diag_agent.ui.model_next_check_queue import _build_next_check_queue_view

        raw = [
            "not a mapping",
            123,
            None,
            {"candidateId": "cand-002", "candidateIndex": 1, "description": "Valid item",
             "targetCluster": "test", "priorityLabel": "low", "suggestedCommandFamily": "kubectl",
             "safeToAutomate": True, "requiresOperatorApproval": False, "approvalState": None,
             "executionState": "pending", "outcomeStatus": None, "latestArtifactPath": None,
             "queueStatus": "queued", "sourceReason": "manual", "sourceType": "operator",
             "expectedSignal": None},
        ]
        result = _build_next_check_queue_view(raw)
        assert len(result) == 1
        assert result[0].candidate_id == "cand-002"

    def test_build_queue_item_view_with_alertmanager_provenance(self) -> None:
        """_build_queue_item_view should preserve Alertmanager provenance."""
        from k8s_diag_agent.ui.model_next_check_queue import (
            _build_queue_item_view,
        )

        raw = {
            "candidateId": "cand-003",
            "candidateIndex": 2,
            "description": "Check deployment status",
            "targetCluster": "prod",
            "priorityLabel": "medium",
            "suggestedCommandFamily": "kubectl",
            "safeToAutomate": True,
            "requiresOperatorApproval": False,
            "approvalState": None,
            "executionState": "pending",
            "outcomeStatus": None,
            "latestArtifactPath": None,
            "queueStatus": "queued",
            "sourceReason": "alert",
            "sourceType": "alertmanager",
            "expectedSignal": "deployment_issue",
            "alertmanagerProvenance": {
                "matchedDimensions": ["namespace", "severity"],
                "matchedValues": {"namespace": ["monitoring"], "severity": ["critical"]},
                "appliedBonus": 10,
                "baseBonus": 5,
            },
        }
        result = _build_queue_item_view(raw)
        assert result.alertmanager_provenance is not None
        assert result.alertmanager_provenance.matched_dimensions == ("namespace", "severity")
        assert result.alertmanager_provenance.applied_bonus == 10

    def test_build_queue_item_view_with_feedback_adaptation_provenance(self) -> None:
        """_build_queue_item_view should preserve feedback adaptation provenance."""
        from k8s_diag_agent.ui.model_next_check_queue import (
            _build_queue_item_view,
        )

        raw = {
            "candidateId": "cand-004",
            "candidateIndex": 3,
            "description": "Check node resources",
            "targetCluster": "staging",
            "priorityLabel": "low",
            "suggestedCommandFamily": "kubectl",
            "safeToAutomate": False,
            "requiresOperatorApproval": True,
            "approvalState": "pending",
            "executionState": None,
            "outcomeStatus": None,
            "latestArtifactPath": None,
            "queueStatus": "approval_needed",
            "sourceReason": "operator_feedback",
            "sourceType": "feedback",
            "expectedSignal": None,
            "feedbackAdaptationProvenance": {
                "feedback_adaptation": True,
                "adaptation_reason": "Operator marked as noisy",
                "original_bonus": 10,
                "suppressed_bonus": 8,
                "penalty_applied": 2,
                "explanation": "Feedback suppressed bonus",
            },
        }
        result = _build_queue_item_view(raw)
        assert result.feedback_adaptation_provenance is not None
        assert result.feedback_adaptation_provenance.feedback_adaptation is True
        assert result.feedback_adaptation_provenance.adaptation_reason == "Operator marked as noisy"
        assert result.feedback_adaptation_provenance.original_bonus == 10

    def test_build_queue_item_view_snake_case_provenance(self) -> None:
        """_build_queue_item_view should handle snake_case provenance keys."""
        from k8s_diag_agent.ui.model_next_check_queue import (
            _build_queue_item_view,
        )

        raw = {
            "candidateId": "cand-005",
            "candidateIndex": 4,
            "description": "Check service endpoints",
            "targetCluster": "prod",
            "priorityLabel": "high",
            "suggestedCommandFamily": "kubectl",
            "safeToAutomate": True,
            "requiresOperatorApproval": False,
            "approvalState": None,
            "executionState": "pending",
            "outcomeStatus": None,
            "latestArtifactPath": None,
            "queueStatus": "queued",
            "sourceReason": "symptom",
            "sourceType": "drilldown",
            "expectedSignal": "endpoint_issue",
            # snake_case keys instead of camelCase
            "alertmanager_provenance": {
                "matched_dimensions": ["service"],
                "matched_values": {"service": ["api-gateway"]},
                "applied_bonus": 8,
            },
        }
        result = _build_queue_item_view(raw)
        assert result.alertmanager_provenance is not None
        assert result.alertmanager_provenance.matched_dimensions == ("service",)

    def test_build_queue_cluster_state_view_defaults(self) -> None:
        """_build_queue_cluster_state_view should return defaults for non-Mapping input."""
        from k8s_diag_agent.ui.model_next_check_queue import (
            NextCheckQueueClusterStateView,
            _build_queue_cluster_state_view,
        )

        result = _build_queue_cluster_state_view(None)
        assert isinstance(result, NextCheckQueueClusterStateView)
        assert result.degraded_cluster_count == 0
        assert result.degraded_cluster_labels == ()
        assert result.deterministic_next_check_count == 0

    def test_build_queue_cluster_state_view_valid_input(self) -> None:
        """_build_queue_cluster_state_view should build view correctly."""
        from k8s_diag_agent.ui.model_next_check_queue import (
            _build_queue_cluster_state_view,
        )

        raw = {
            "degradedClusterCount": 2,
            "degradedClusterLabels": ["cluster-a", "cluster-b"],
            "deterministicNextCheckCount": 5,
            "deterministicClusterCount": 3,
            "drilldownReadyCount": 4,
        }
        result = _build_queue_cluster_state_view(raw)
        assert result.degraded_cluster_count == 2
        assert result.degraded_cluster_labels == ("cluster-a", "cluster-b")
        assert result.deterministic_next_check_count == 5

    def test_build_queue_candidate_accounting_view_defaults(self) -> None:
        """_build_queue_candidate_accounting_view should return defaults for non-Mapping input."""
        from k8s_diag_agent.ui.model_next_check_queue import (
            NextCheckQueueCandidateAccountingView,
            _build_queue_candidate_accounting_view,
        )

        result = _build_queue_candidate_accounting_view(None)
        assert isinstance(result, NextCheckQueueCandidateAccountingView)
        assert result.generated == 0
        assert result.safe == 0
        assert result.orphaned_approvals == 0

    def test_build_queue_candidate_accounting_view_valid_input(self) -> None:
        """_build_queue_candidate_accounting_view should build view correctly."""
        from k8s_diag_agent.ui.model_next_check_queue import (
            _build_queue_candidate_accounting_view,
        )

        raw = {
            "generated": 10,
            "safe": 5,
            "approvalNeeded": 2,
            "duplicate": 1,
            "completed": 3,
            "staleOrphaned": 1,
            "orphanedApprovals": 2,
        }
        result = _build_queue_candidate_accounting_view(raw)
        assert result.generated == 10
        assert result.safe == 5
        assert result.approval_needed == 2
        assert result.orphaned_approvals == 2

    def test_build_queue_explanation_view_null_input(self) -> None:
        """_build_queue_explanation_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model_next_check_queue import _build_queue_explanation_view

        result = _build_queue_explanation_view(None)
        assert result is None

        result = _build_queue_explanation_view("not a mapping")
        assert result is None

    def test_build_queue_explanation_view_valid_input(self) -> None:
        """_build_queue_explanation_view should build view correctly."""
        from k8s_diag_agent.ui.model_next_check_queue import (
            NextCheckQueueExplanationView,
            _build_queue_explanation_view,
        )

        raw = {
            "status": "ready",
            "reason": "Queue populated",
            "hint": "Review high priority items",
            "plannerArtifactPath": "/path/to/planner",
            "clusterState": {
                "degradedClusterCount": 1,
                "degradedClusterLabels": ["cluster-x"],
                "deterministicNextCheckCount": 3,
                "deterministicClusterCount": 2,
                "drilldownReadyCount": 5,
            },
            "candidateAccounting": {
                "generated": 8,
                "safe": 4,
                "approvalNeeded": 1,
                "duplicate": 1,
                "completed": 2,
                "staleOrphaned": 0,
                "orphanedApprovals": 0,
            },
            "deterministicNextChecksAvailable": True,
            "recommendedNextActions": ["Action 1", "Action 2"],
        }
        result = _build_queue_explanation_view(raw)
        assert isinstance(result, NextCheckQueueExplanationView)
        assert result.status == "ready"
        assert result.reason == "Queue populated"
        assert result.deterministic_next_checks_available is True
        assert len(result.recommended_next_actions) == 2
        assert result.cluster_state.degraded_cluster_count == 1

    def test_build_queue_explanation_view_filters_empty_actions(self) -> None:
        """_build_queue_explanation_view should filter empty recommended actions."""
        from k8s_diag_agent.ui.model_next_check_queue import _build_queue_explanation_view

        raw = {
            "status": "ready",
            "recommendedNextActions": ["Action 1", "", "  ", "Action 2", None],
            "clusterState": {},
            "candidateAccounting": {},
        }
        result = _build_queue_explanation_view(raw)
        assert result is not None
        assert result.recommended_next_actions == ("Action 1", "Action 2")


class TestQueueBuilderPreservesProvenanceFields(unittest.TestCase):
    """Verify queue builders preserve provenance fields exactly."""

    def test_queue_item_preserves_alertmanager_provenance_fields(self) -> None:
        """NextCheckQueueItemView should preserve all Alertmanager provenance fields."""
        from k8s_diag_agent.ui.model_next_check_queue import _build_queue_item_view

        raw = {
            "candidateId": "cand-test",
            "candidateIndex": 0,
            "description": "Test",
            "targetCluster": "test",
            "priorityLabel": "test",
            "suggestedCommandFamily": "test",
            "safeToAutomate": True,
            "requiresOperatorApproval": False,
            "approvalState": None,
            "executionState": "pending",
            "outcomeStatus": None,
            "latestArtifactPath": None,
            "queueStatus": "queued",
            "sourceReason": "test",
            "sourceType": "test",
            "expectedSignal": None,
            "alertmanager_provenance": {
                "matched_dimensions": ["dim1", "dim2"],
                "matched_values": {"dim1": ["val1"], "dim2": ["val2", "val3"]},
                "applied_bonus": 15,
                "base_bonus": 10,
                "severity_summary": {"critical": 2, "warning": 5},
                "signal_status": "firing",
            },
        }
        result = _build_queue_item_view(raw)
        assert result.alertmanager_provenance is not None
        prov = result.alertmanager_provenance
        assert prov.matched_dimensions == ("dim1", "dim2")
        assert prov.matched_values == {"dim1": ("val1",), "dim2": ("val2", "val3")}
        assert prov.applied_bonus == 15
        assert prov.base_bonus == 10
        assert prov.severity_summary == {"critical": 2, "warning": 5}
        assert prov.signal_status == "firing"

    def test_queue_item_preserves_feedback_adaptation_provenance_fields(self) -> None:
        """NextCheckQueueItemView should preserve all feedback adaptation provenance fields."""
        from k8s_diag_agent.ui.model_next_check_queue import _build_queue_item_view

        raw = {
            "candidateId": "cand-test-2",
            "candidateIndex": 1,
            "description": "Test 2",
            "targetCluster": "test",
            "priorityLabel": "test",
            "suggestedCommandFamily": "test",
            "safeToAutomate": False,
            "requiresOperatorApproval": True,
            "approvalState": None,
            "executionState": "pending",
            "outcomeStatus": None,
            "latestArtifactPath": None,
            "queueStatus": "queued",
            "sourceReason": "test",
            "sourceType": "test",
            "expectedSignal": None,
            "feedback_adaptation_provenance": {
                "feedback_adaptation": True,
                "adaptation_reason": "Too noisy",
                "original_bonus": 15,
                "suppressed_bonus": 10,
                "penalty_applied": 5,
                "explanation": "Feedback-based penalty applied",
            },
        }
        result = _build_queue_item_view(raw)
        assert result.feedback_adaptation_provenance is not None
        prov = result.feedback_adaptation_provenance
        assert prov.feedback_adaptation is True
        assert prov.adaptation_reason == "Too noisy"
        assert prov.original_bonus == 15
        assert prov.suppressed_bonus == 10
        assert prov.penalty_applied == 5
        assert prov.explanation == "Feedback-based penalty applied"


if __name__ == "__main__":
    unittest.main()
