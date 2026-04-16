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


if __name__ == "__main__":
    unittest.main()