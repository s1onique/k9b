import json
import shutil
import tempfile
import unittest
from argparse import Namespace
from dataclasses import replace
from pathlib import Path

from k8s_diag_agent.cli_handlers import handle_promote_proposal
from k8s_diag_agent.health.adaptation import (
    HealthProposal,
    ProposalEvaluation,
    ProposalLifecycleStatus,
    with_lifecycle_status,
)
from k8s_diag_agent.models import ConfidenceLevel


class HealthPromotionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        self.health_config = self.root / "health-config.json"
        self.baseline = self.root / "health-baseline.json"
        shutil.copy(Path("runs/health-config.local.example.json"), self.health_config)
        shutil.copy(Path("runs/health-baseline.example.json"), self.baseline)
        self.promotions = self.root / "promotions"
        self.proposal_path = self.root / "proposal.json"

    def _write_proposal(self, proposal: HealthProposal) -> None:
        self.proposal_path.write_text(json.dumps(proposal.to_dict(), indent=2), encoding="utf-8")

    def _ready_proposal(self, proposal: HealthProposal) -> HealthProposal:
        evaluation = ProposalEvaluation(
            proposal_id=proposal.proposal_id,
            noise_reduction="Estimated noise reduction",
            signal_loss="Estimated signal loss",
            test_outcome="Fixture evaluation",
        )
        evaluated = replace(proposal, promotion_evaluation=evaluation)
        return with_lifecycle_status(
            evaluated,
            ProposalLifecycleStatus.REPLAYED,
            note="replayed for tests",
        )

    def _invoke(self, note: str | None = None) -> int:
        args = Namespace(
            proposal=self.proposal_path,
            health_config=self.health_config,
            baseline=self.baseline,
            output_dir=self.promotions,
            note=note,
        )
        return handle_promote_proposal(args)

    def test_supported_threshold_promotion_writes_patch(self) -> None:
        proposal = HealthProposal(
            proposal_id="threshold-test",
            source_run_id="run-1",
            source_artifact_path="runs/health/reviews/run-1-review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Raise threshold to cut noise.",
            rationale="Noisy warning events.",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="Reduce noise.",
            rollback_note="Revert if real issues arise.",
            promotion_payload={"threshold": 10},
        )
        self._write_proposal(self._ready_proposal(proposal))
        before = self.health_config.read_text(encoding="utf-8")
        exit_code = self._invoke()
        self.assertEqual(exit_code, 0)
        patch_file = self.promotions / "threshold-test.patch"
        self.assertTrue(patch_file.exists())
        patch_content = patch_file.read_text(encoding="utf-8")
        self.assertIn("-    \"warning_event_threshold\": 5", patch_content)
        self.assertIn("+    \"warning_event_threshold\": 10", patch_content)
        after = self.health_config.read_text(encoding="utf-8")
        self.assertEqual(before, after, "Health config should not be modified by promotion command")

    def test_supported_baseline_release_promotion_appends_version(self) -> None:
        proposal = HealthProposal(
            proposal_id="release-test",
            source_run_id="run-2",
            source_artifact_path="runs/health/reviews/run-2-review.json",
            target="health.baseline_policy.watched_releases",
            proposed_change="Allow new release version.",
            rationale="Release drift observed.",
            confidence=ConfidenceLevel.MEDIUM,
            expected_benefit="Prevent repeated drift alerts.",
            rollback_note="Revert to prior versions if instability occurs.",
            promotion_payload={"release_key": "stateful-stack/service", "versions": ["2.0.1"]},
        )
        self._write_proposal(self._ready_proposal(proposal))
        before = self.baseline.read_text(encoding="utf-8")
        exit_code = self._invoke()
        self.assertEqual(exit_code, 0)
        patch_file = self.promotions / "release-test.patch"
        self.assertTrue(patch_file.exists())
        patch_content = patch_file.read_text(encoding="utf-8")
        self.assertIn("-      \"allowed_versions\": [", patch_content)
        self.assertIn("+      \"allowed_versions\": [", patch_content)
        self.assertIn("+        \"2.0.1\"", patch_content)
        after = self.baseline.read_text(encoding="utf-8")
        self.assertEqual(before, after, "Baseline file should not be mutated by promotion command")

    def test_promotion_requires_replay_evaluation(self) -> None:
        proposal = HealthProposal(
            proposal_id="gate-test",
            source_run_id="run-gate",
            source_artifact_path="runs/health/reviews/run-gate-review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Adjust for gating.",
            rationale="Gate enforcement.",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="Safety.",
            rollback_note="Revert if needed.",
            promotion_payload={"threshold": 3},
        )
        self._write_proposal(proposal)
        exit_code = self._invoke()
        self.assertEqual(exit_code, 1)
        self.assertFalse(self.promotions.exists())

    def test_promotion_requires_replayed_status(self) -> None:
        evaluation = ProposalEvaluation(
            proposal_id="gate-test",
            noise_reduction="minimal",
            signal_loss="low",
            test_outcome="fixture brief",
        )
        proposal = HealthProposal(
            proposal_id="gate-test",
            source_run_id="run-gate",
            source_artifact_path="runs/health/reviews/run-gate-review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Adjust for gating.",
            rationale="Gate enforcement.",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="Safety.",
            rollback_note="Revert if needed.",
            promotion_payload={"threshold": 3},
            promotion_evaluation=evaluation,
        )
        self._write_proposal(proposal)
        exit_code = self._invoke()
        self.assertEqual(exit_code, 1)
        self.assertFalse(self.promotions.exists())

    def test_unsupported_target_is_rejected(self) -> None:
        proposal = HealthProposal(
            proposal_id="drilldown-test",
            source_run_id="run-3",
            source_artifact_path="runs/health/reviews/run-3-review.json",
            target="health.drilldown.review_order",
            proposed_change="Switch drilldown order.",
            rationale="Ranking complaint.",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="Better ordering.",
            rollback_note="Revert if noise increases.",
        )
        self._write_proposal(proposal)
        exit_code = self._invoke()
        self.assertEqual(exit_code, 1)
        self.assertFalse(self.promotions.exists() and any(self.promotions.iterdir()))
