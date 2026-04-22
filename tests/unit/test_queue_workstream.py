"""Tests for queue workstream field serialization and frontend filtering."""

import unittest

from k8s_diag_agent.ui.api import (
    _serialize_next_check_queue,
    build_run_payload,
)
from k8s_diag_agent.ui.model import build_ui_context
from tests.fixtures.ui_index_sample import sample_ui_index


class QueueWorkstreamBackendTests(unittest.TestCase):
    """Tests for workstream field in queue serialization."""

    def setUp(self) -> None:
        self.context = build_ui_context(sample_ui_index())

    def test_run_payload_queue_items_include_workstream_field(self) -> None:
        """Test that queue items in the run payload include workstream field."""
        payload = build_run_payload(self.context)
        queue = payload.get("nextCheckQueue")
        self.assertIsNotNone(queue)
        assert isinstance(queue, list)
        self.assertGreater(len(queue), 0)
        # Verify workstream field is present in queue items
        for entry in queue:
            self.assertIn("workstream", entry)

    def test_serialize_queue_includes_workstream_from_promotions(self) -> None:
        """Test that serialized queue includes workstream from promoted entries."""
        promotions = [
            {
                "candidateId": "promo-workstream-test",
                "description": "Test promotion with workstream",
                "queueStatus": "approval-needed",
                "planArtifactPath": "external-analysis/promo.json",
                "sourceType": "deterministic",
                "workstream": "incident",
            }
        ]
        serialized = _serialize_next_check_queue(self.context.run.next_check_queue, promotions)
        promoted_entry = serialized[-1]
        self.assertEqual(promoted_entry["candidateId"], "promo-workstream-test")
        self.assertEqual(promoted_entry.get("workstream"), "incident")

    def test_serialize_queue_preserves_workstream_values(self) -> None:
        """Test that workstream values ('incident', 'evidence', 'drift') are preserved."""
        promotions = [
            {
                "candidateId": "incident-check",
                "description": "Firefight check",
                "queueStatus": "approval-needed",
                "workstream": "incident",
            },
            {
                "candidateId": "evidence-check",
                "description": "Evidence gathering",
                "queueStatus": "safe-ready",
                "workstream": "evidence",
            },
            {
                "candidateId": "drift-check",
                "description": "Drift follow-up",
                "queueStatus": "duplicate-or-stale",
                "workstream": "drift",
            },
        ]
        serialized = _serialize_next_check_queue(self.context.run.next_check_queue, promotions)
        
        # Check that promoted entries have correct workstream values
        self.assertEqual(serialized[-3]["workstream"], "incident")
        self.assertEqual(serialized[-2]["workstream"], "evidence")
        self.assertEqual(serialized[-1]["workstream"], "drift")


class CRDWorkstreamRoutingTests(unittest.TestCase):
    """Tests for CRD demotion and drift workstream routing in queue building."""

    def test_demoted_crd_gets_drift_workstream(self) -> None:
        """Demoted CRD candidates (rankingPolicyReason contains crd-demoted) should get drift workstream."""
        # Simulate a plan_entry with a demoted CRD candidate
        plan_entry = {
            "artifactPath": "external-analysis/plan.json",
            "candidates": [
                {
                    "candidateId": "crd-demoted-1",
                    "description": "kubectl get crd",
                    "suggestedCommandFamily": "kubectl-get-crd",
                    "rankingPolicyReason": "crd-demoted-early-incident-triage:incident:initial_triage",
                    "priorityLabel": "secondary",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                },
                {
                    "candidateId": "describe-1",
                    "description": "kubectl describe pod",
                    "suggestedCommandFamily": "kubectl-describe",
                    "priorityLabel": "primary",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                },
            ],
        }
        from k8s_diag_agent.health.ui_planner_queue import _build_next_check_queue
        queue = _build_next_check_queue(plan_entry, {})
        
        # Find the CRD demoted entry
        crd_entry = next((e for e in queue if e.get("candidateId") == "crd-demoted-1"), None)
        self.assertIsNotNone(crd_entry)
        assert crd_entry is not None  # for mypy
        # CRD demoted entry should have workstream = "drift"
        self.assertEqual(crd_entry.get("workstream"), "drift")
        
        # Describe entry should NOT have workstream (not demoted)
        describe_entry = next((e for e in queue if e.get("candidateId") == "describe-1"), None)
        self.assertIsNotNone(describe_entry)
        # Cast to dict to help mypy understand the type
        describe_dict: dict[str, object] = describe_entry  # type: ignore[assignment]
        self.assertNotIn("workstream", describe_dict)

    def test_non_demoted_crd_keeps_original_workstream(self) -> None:
        """Non-demoted CRD candidates should not have workstream assigned by queue builder."""
        plan_entry = {
            "artifactPath": "external-analysis/plan.json",
            "candidates": [
                {
                    "candidateId": "crd-normal",
                    "description": "kubectl get crd",
                    "suggestedCommandFamily": "kubectl-get-crd",
                    "priorityLabel": "secondary",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                },
            ],
        }
        from k8s_diag_agent.health.ui_planner_queue import _build_next_check_queue
        queue = _build_next_check_queue(plan_entry, {})
        
        crd_entry = queue[0]
        # No rankingPolicyReason, so no workstream assignment
        self.assertNotIn("workstream", crd_entry)


if __name__ == "__main__":
    unittest.main()
