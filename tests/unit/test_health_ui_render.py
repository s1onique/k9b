import html
import unittest

from k8s_diag_agent.ui.model import ProposalView
from k8s_diag_agent.ui.server import _render_proposal_row


class HealthUIRenderTests(unittest.TestCase):
    def test_proposal_row_shows_lifecycle_and_artifacts(self) -> None:
        proposal = ProposalView(
            proposal_id="p1",
            target="health.trigger_policy.warning_event_threshold",
            status="pending",
            confidence="low",
            rationale="test",
            expected_benefit="less noise",
            source_run_id="run-1",
            latest_note="note",
            artifact_path="proposals/p1.json",
            review_path="reviews/run-1-review.json",
            lifecycle_history=(
                ("pending", "2026-01-01T00:00:00Z", "checked"),
            ),
        )
        row = _render_proposal_row(proposal)
        self.assertIn("lifecycle-history", row)
        self.assertIn(html.escape("pending"), row)
        self.assertIn(html.escape("Proposal JSON"), row)
        self.assertIn(html.escape("Review JSON"), row)
