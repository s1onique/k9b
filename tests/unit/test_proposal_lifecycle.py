import unittest

from k8s_diag_agent.health.adaptation import (
    HealthProposal,
    ProposalLifecycleStatus,
    with_lifecycle_status,
)
from k8s_diag_agent.models import ConfidenceLevel


class ProposalLifecycleTests(unittest.TestCase):
    def _build_proposal(self) -> HealthProposal:
        return HealthProposal(
            proposal_id="p1",
            source_run_id="run-1",
            source_artifact_path="runs/health/review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Raise threshold",
            rationale="test",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="reduce noise",
            rollback_note="restore default",
        )

    def test_default_status_pending(self) -> None:
        proposal = self._build_proposal()
        latest = proposal.lifecycle_history[-1]
        self.assertEqual(latest.status, ProposalLifecycleStatus.PENDING)

    def test_with_lifecycle_status_adds_entry(self) -> None:
        proposal = self._build_proposal()
        updated = with_lifecycle_status(proposal, ProposalLifecycleStatus.CHECKED, note="evaluated")
        self.assertEqual(updated.lifecycle_history[-1].status, ProposalLifecycleStatus.CHECKED)
        self.assertEqual(updated.lifecycle_history[-1].note, "evaluated")
