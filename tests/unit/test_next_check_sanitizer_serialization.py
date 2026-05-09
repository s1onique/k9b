"""Regression tests for kubectl context sanitization in next-check serialization.

These tests verify that internal context markers like "in-cluster"
do not leak into operator-facing display fields in:
- Next check plan candidates (description field)
- Next check queue items (description field)
- Orphaned approvals (candidateDescription field)
"""

import unittest

from k8s_diag_agent.ui.api_next_check_plan import (
    _serialize_next_check_candidate,
    _serialize_orphaned_approval,
)
from k8s_diag_agent.ui.api_next_check_queue import _serialize_next_check_queue
from k8s_diag_agent.ui.model_next_check_plan import (
    NextCheckCandidateView,
    NextCheckOrphanedApprovalView,
)
from k8s_diag_agent.ui.model_next_check_queue import NextCheckQueueItemView


class TestNextCheckCandidateSanitization(unittest.TestCase):
    """Regression tests for sanitization in _serialize_next_check_candidate."""

    def _make_candidate_view(
        self,
        description: str,
        target_cluster: str | None = None,
    ) -> NextCheckCandidateView:
        """Helper to create a NextCheckCandidateView with required defaults."""
        return NextCheckCandidateView(
            candidate_id="test-candidate",
            priority_label=None,
            candidate_index=0,
            description=description,
            target_cluster=target_cluster,
            source_reason="Test source",
            expected_signal="Test signal",
            suggested_command_family="kubectl-get",
            safe_to_automate=True,
            requires_operator_approval=False,
            risk_level="low",
            estimated_cost="low",
            confidence="high",
            gating_reason=None,
            duplicate_of_existing_evidence=False,
            duplicate_evidence_description=None,
            normalization_reason=None,
            safety_reason="Test safety",
            approval_reason=None,
            duplicate_reason=None,
            blocking_reason=None,
            approval_state=None,
            approval_status=None,
            approval_artifact_path=None,
            approval_timestamp=None,
            execution_state=None,
            outcome_status=None,
            latest_artifact_path=None,
            latest_timestamp=None,
            priority_rationale=None,
            ranking_reason=None,
            alertmanager_provenance=None,
            feedback_adaptation_provenance=None,
        )

    def test_candidate_description_sanitized_get_deployment(self) -> None:
        """kubectl get deployment with --context in-cluster must not leak to operator UI."""
        view = self._make_candidate_view(
            description="kubectl get deployment metrics-server -n kube-system --context in-cluster",
            target_cluster="cluster-a",
        )
        result = _serialize_next_check_candidate(view)
        # The sanitized description should NOT contain --context in-cluster
        self.assertNotIn("--context", result["description"])
        self.assertNotIn("in-cluster", result["description"])
        # But it SHOULD contain the actual command without context
        self.assertIn("kubectl get deployment metrics-server -n kube-system", result["description"])

    def test_candidate_description_sanitized_get_events(self) -> None:
        """kubectl get events with --context in-cluster must not leak to operator UI."""
        view = self._make_candidate_view(
            description="kubectl get events --all-namespaces --context in-cluster",
            target_cluster="cluster-b",
        )
        result = _serialize_next_check_candidate(view)
        self.assertNotIn("--context", result["description"])
        self.assertNotIn("in-cluster", result["description"])
        self.assertIn("kubectl get events --all-namespaces", result["description"])

    def test_candidate_description_sanitized_describe_pods(self) -> None:
        """kubectl describe pods with --context in-cluster must not leak to operator UI."""
        view = self._make_candidate_view(
            description="kubectl describe pods -n argocd --context in-cluster",
            target_cluster="cluster-c",
        )
        result = _serialize_next_check_candidate(view)
        self.assertNotIn("--context", result["description"])
        self.assertNotIn("in-cluster", result["description"])
        self.assertIn("kubectl describe pods -n argocd", result["description"])

    def test_candidate_description_sanitized_get_crd(self) -> None:
        """kubectl get crd with --context in-cluster must not leak to operator UI."""
        view = self._make_candidate_view(
            description="kubectl get crd --context in-cluster",
            target_cluster="cluster-d",
        )
        result = _serialize_next_check_candidate(view)
        self.assertNotIn("--context", result["description"])
        self.assertNotIn("in-cluster", result["description"])
        self.assertIn("kubectl get crd", result["description"])

    def test_candidate_description_preserves_real_context(self) -> None:
        """Real cluster contexts (not 'in-cluster') must be preserved in operator UI."""
        view = self._make_candidate_view(
            description="kubectl get pods --context prod-cluster",
            target_cluster="prod-cluster",
        )
        result = _serialize_next_check_candidate(view)
        # Real context SHOULD be preserved
        self.assertIn("--context prod-cluster", result["description"])
        self.assertIn("prod-cluster", result["description"])

    def test_candidate_description_removes_internal_namespace(self) -> None:
        """Internal namespace '-n in-cluster' must be removed from operator-facing display.

        In K9b-generated commands, 'in-cluster' as a namespace is an internal marker
        leak, not a real Kubernetes namespace. Both -n in-cluster and --context
        in-cluster must be removed.
        """
        view = self._make_candidate_view(
            description="kubectl get pods -n in-cluster --context in-cluster",
            target_cluster="cluster-a",
        )
        result = _serialize_next_check_candidate(view)
        # Both -n in-cluster and --context in-cluster should be removed
        self.assertNotIn("-n", result["description"])
        self.assertNotIn("in-cluster", result["description"])
        self.assertNotIn("--context", result["description"])
        self.assertEqual(result["description"], "kubectl get pods")


class TestNextCheckQueueSanitization(unittest.TestCase):
    """Regression tests for sanitization in _serialize_next_check_queue."""

    def _make_queue_item_view(
        self,
        description: str,
        candidate_id: str | None = "test-queue-item",
    ) -> NextCheckQueueItemView:
        """Helper to create a NextCheckQueueItemView with required defaults."""
        return NextCheckQueueItemView(
            candidate_id=candidate_id,
            candidate_index=0,
            description=description,
            target_cluster="cluster-a",
            priority_label="primary",
            suggested_command_family="kubectl-get",
            safe_to_automate=True,
            requires_operator_approval=False,
            approval_state=None,
            execution_state=None,
            outcome_status=None,
            latest_artifact_path=None,
            queue_status="pending",
            source_reason="Test source",
            source_type="planner",
            expected_signal="Test signal",
            normalization_reason=None,
            safety_reason="Test safety",
            approval_reason=None,
            duplicate_reason=None,
            blocking_reason=None,
            failure_class=None,
            failure_summary=None,
            suggested_next_operator_move=None,
            result_class=None,
            result_summary=None,
            target_context=None,
            command_preview=None,
            plan_artifact_path=None,
            workstream="incident",
            alertmanager_provenance=None,
            feedback_adaptation_provenance=None,
        )

    def test_queue_item_description_sanitized_get_deployment(self) -> None:
        """Queue item with --context in-cluster must not leak to operator UI."""
        view = self._make_queue_item_view(
            description="kubectl get deployment metrics-server -n kube-system --context in-cluster",
        )
        result = _serialize_next_check_queue((view,))
        self.assertEqual(len(result), 1)
        self.assertNotIn("--context", result[0]["description"])
        self.assertNotIn("in-cluster", result[0]["description"])
        self.assertIn("kubectl get deployment metrics-server -n kube-system", result[0]["description"])

    def test_queue_item_description_sanitized_get_events(self) -> None:
        """Queue item with --context in-cluster must not leak to operator UI."""
        view = self._make_queue_item_view(
            description="kubectl get events --all-namespaces --context in-cluster",
        )
        result = _serialize_next_check_queue((view,))
        self.assertEqual(len(result), 1)
        self.assertNotIn("--context", result[0]["description"])
        self.assertNotIn("in-cluster", result[0]["description"])
        self.assertIn("kubectl get events --all-namespaces", result[0]["description"])

    def test_queue_item_description_sanitized_describe_pods(self) -> None:
        """Queue item with --context in-cluster must not leak to operator UI."""
        view = self._make_queue_item_view(
            description="kubectl describe pods -n argocd --context in-cluster",
        )
        result = _serialize_next_check_queue((view,))
        self.assertEqual(len(result), 1)
        self.assertNotIn("--context", result[0]["description"])
        self.assertNotIn("in-cluster", result[0]["description"])
        self.assertIn("kubectl describe pods -n argocd", result[0]["description"])

    def test_queue_item_description_sanitized_get_crd(self) -> None:
        """Queue item with --context in-cluster must not leak to operator UI."""
        view = self._make_queue_item_view(
            description="kubectl get crd --context in-cluster",
        )
        result = _serialize_next_check_queue((view,))
        self.assertEqual(len(result), 1)
        self.assertNotIn("--context", result[0]["description"])
        self.assertNotIn("in-cluster", result[0]["description"])
        self.assertIn("kubectl get crd", result[0]["description"])

    def test_queue_item_description_preserves_real_context(self) -> None:
        """Real cluster contexts (not 'in-cluster') must be preserved in operator UI."""
        view = self._make_queue_item_view(
            description="kubectl get pods --context prod-cluster",
        )
        result = _serialize_next_check_queue((view,))
        self.assertEqual(len(result), 1)
        self.assertIn("--context prod-cluster", result[0]["description"])
        self.assertIn("prod-cluster", result[0]["description"])

    def test_queue_item_description_removes_internal_namespace(self) -> None:
        """Internal namespace '-n in-cluster' must be removed from queue item.

        In K9b-generated commands, 'in-cluster' as a namespace is an internal marker
        leak, not a real Kubernetes namespace. Both -n in-cluster and --context
        in-cluster must be removed.
        """
        view = self._make_queue_item_view(
            description="kubectl get pods -n in-cluster --context in-cluster",
        )
        result = _serialize_next_check_queue((view,))
        self.assertEqual(len(result), 1)
        self.assertNotIn("-n", result[0]["description"])
        self.assertNotIn("in-cluster", result[0]["description"])
        self.assertNotIn("--context", result[0]["description"])
        self.assertEqual(result[0]["description"], "kubectl get pods")


class TestOrphanedApprovalSanitization(unittest.TestCase):
    """Regression tests for sanitization in _serialize_orphaned_approval."""

    def _make_orphaned_view(
        self,
        candidate_description: str,
    ) -> NextCheckOrphanedApprovalView:
        """Helper to create a NextCheckOrphanedApprovalView with required defaults."""
        return NextCheckOrphanedApprovalView(
            approval_status="approval-orphaned",
            candidate_id="orphaned-candidate",
            candidate_index=5,
            candidate_description=candidate_description,
            target_cluster="cluster-a",
            plan_artifact_path="external-analysis/test-plan.json",
            approval_artifact_path="external-analysis/test-approval.json",
            approval_timestamp="2026-01-01T12:00:00Z",
        )

    def test_orphaned_approval_description_sanitized(self) -> None:
        """Orphaned approval candidateDescription with --context in-cluster must not leak."""
        view = self._make_orphaned_view(
            candidate_description="kubectl get deployment metrics-server -n kube-system --context in-cluster",
        )
        result = _serialize_orphaned_approval(view)

        candidate_description = result["candidateDescription"]
        self.assertIsNotNone(candidate_description)
        assert candidate_description is not None

        self.assertNotIn("--context", candidate_description)
        self.assertNotIn("in-cluster", candidate_description)
        self.assertIn("kubectl get deployment metrics-server -n kube-system", candidate_description)

    def test_orphaned_approval_description_preserves_real_context(self) -> None:
        """Real cluster contexts in orphaned approvals must be preserved."""
        view = self._make_orphaned_view(
            candidate_description="kubectl get pods --context prod-cluster",
        )
        result = _serialize_orphaned_approval(view)

        candidate_description = result["candidateDescription"]
        self.assertIsNotNone(candidate_description)
        assert candidate_description is not None

        self.assertIn("--context prod-cluster", candidate_description)


if __name__ == "__main__":
    unittest.main()