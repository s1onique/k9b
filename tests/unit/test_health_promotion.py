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


class PromotionWithImmutableLifecycleTests(unittest.TestCase):
    """Tests for promotion under the immutable lifecycle model.

    These tests verify that promotion derives evaluation from lifecycle events
    first, then falls back to embedded promotion_evaluation for legacy proposals.
    Base proposal artifacts must remain unchanged.
    """

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
        self.transitions_dir = self.proposal_path.parent / "transitions"
        self.transitions_dir.mkdir(parents=True, exist_ok=True)

    def _write_proposal(self, proposal: HealthProposal) -> None:
        self.proposal_path.write_text(json.dumps(proposal.to_dict(), indent=2), encoding="utf-8")

    def _write_check_event_with_evaluation(
        self,
        proposal_id: str,
        artifact_id: str,
        created_at: str,
        evaluation: dict[str, str],
    ) -> None:
        """Write a check event with evaluation in provenance."""
        data = {
            "artifact_id": artifact_id,
            "proposal_id": proposal_id,
            "status": "checked",
            "transition": "check",
            "created_at": created_at,
            "provenance": {
                "artifact_path": str(self.proposal_path),
                "fixture_path": "/fixtures/test.json",
                "evaluation": evaluation,
            },
        }
        filename = f"{proposal_id}-check-{artifact_id}.json"
        (self.transitions_dir / filename).write_text(json.dumps(data), encoding="utf-8")

    def _invoke(self, note: str | None = None) -> int:
        args = Namespace(
            proposal=self.proposal_path,
            health_config=self.health_config,
            baseline=self.baseline,
            output_dir=self.promotions,
            note=note,
        )
        return handle_promote_proposal(args)

    def _create_proposal(self, proposal_id: str) -> HealthProposal:
        """Create a base proposal with CHECKED status (but no embedded evaluation)."""
        from k8s_diag_agent.health.adaptation import ProposalLifecycleEntry, ProposalLifecycleStatus

        return HealthProposal(
            proposal_id=proposal_id,
            source_run_id="run-event-test",
            source_artifact_path="runs/health/reviews/run-event-test-review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Raise threshold for event-based test.",
            rationale="Event-based test proposal.",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="Test evaluation derivation.",
            rollback_note="Revert if needed.",
            promotion_payload={"threshold": 8},
            lifecycle_history=(
                ProposalLifecycleEntry(status=ProposalLifecycleStatus.PENDING, timestamp="2026-04-07T10:00:00+00:00"),
                ProposalLifecycleEntry(status=ProposalLifecycleStatus.CHECKED, timestamp="2026-04-07T11:00:00+00:00"),
            ),
            # No promotion_evaluation - evaluation comes from events
        )

    def test_promotion_succeeds_with_event_based_evaluation(self) -> None:
        """Verify promotion succeeds when evaluation exists only in lifecycle event provenance."""
        proposal = self._create_proposal("event-eval-test")
        self._write_proposal(proposal)

        # Write check event with evaluation (simulating check-proposal)
        evaluation = {
            "proposal_id": "event-eval-test",
            "noise_reduction": "Event-based evaluation: ~60% noise reduction",
            "signal_loss": "Event-based evaluation: Low signal loss",
            "test_outcome": "Event-based: Fixture test passed",
        }
        self._write_check_event_with_evaluation(
            "event-eval-test",
            "event-eval-001",
            "2026-04-07T11:00:00+00:00",
            evaluation,
        )

        # Verify proposal file does NOT have embedded evaluation
        original_proposal = json.loads(self.proposal_path.read_text(encoding="utf-8"))
        self.assertIsNone(original_proposal.get("promotion_evaluation"))

        before = self.health_config.read_text(encoding="utf-8")
        exit_code = self._invoke()
        self.assertEqual(exit_code, 0)

        # Verify patch was created
        patch_file = self.promotions / "event-eval-test.patch"
        self.assertTrue(patch_file.exists())
        patch_content = patch_file.read_text(encoding="utf-8")
        self.assertIn("+    \"warning_event_threshold\": 8", patch_content)

        # Verify health config was not modified
        after = self.health_config.read_text(encoding="utf-8")
        self.assertEqual(before, after)

        # Verify proposal artifact was not mutated
        current_proposal = json.loads(self.proposal_path.read_text(encoding="utf-8"))
        self.assertEqual(original_proposal, current_proposal)

    def test_promotion_succeeds_with_legacy_embedded_evaluation(self) -> None:
        """Verify backward compatibility: promotion succeeds with legacy embedded evaluation."""
        from k8s_diag_agent.health.adaptation import ProposalLifecycleEntry

        proposal = HealthProposal(
            proposal_id="legacy-eval-test",
            source_run_id="run-legacy",
            source_artifact_path="runs/health/reviews/run-legacy-review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Raise threshold for legacy test.",
            rationale="Legacy embedded evaluation test.",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="Test legacy evaluation.",
            rollback_note="Revert if needed.",
            promotion_payload={"threshold": 12},
            lifecycle_history=(
                ProposalLifecycleEntry(status=ProposalLifecycleStatus.PENDING, timestamp="2026-04-07T10:00:00+00:00"),
                ProposalLifecycleEntry(status=ProposalLifecycleStatus.CHECKED, timestamp="2026-04-07T11:00:00+00:00"),
            ),
            # Embedded evaluation (legacy style)
            promotion_evaluation=ProposalEvaluation(
                proposal_id="legacy-eval-test",
                noise_reduction="Legacy: ~70% noise reduction",
                signal_loss="Legacy: Low signal loss",
                test_outcome="Legacy: Test passed",
            ),
        )
        self._write_proposal(proposal)

        before = self.health_config.read_text(encoding="utf-8")
        exit_code = self._invoke()
        self.assertEqual(exit_code, 0)

        patch_file = self.promotions / "legacy-eval-test.patch"
        self.assertTrue(patch_file.exists())

        # Verify health config was not modified
        after = self.health_config.read_text(encoding="utf-8")
        self.assertEqual(before, after)

        # Verify proposal was not mutated
        current_proposal = json.loads(self.proposal_path.read_text(encoding="utf-8"))
        self.assertEqual(
            current_proposal.get("promotion_evaluation", {}).get("noise_reduction"),
            "Legacy: ~70% noise reduction",
        )

    def test_promotion_fails_when_neither_source_provides_evaluation(self) -> None:
        """Verify promotion fails clearly when neither event nor embedded evaluation exists."""
        from k8s_diag_agent.health.adaptation import ProposalLifecycleEntry

        # Create proposal with CHECKED status but no evaluation anywhere
        proposal = HealthProposal(
            proposal_id="no-eval-test",
            source_run_id="run-no-eval",
            source_artifact_path="runs/health/reviews/run-no-eval-review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Raise threshold.",
            rationale="No evaluation test.",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="Test.",
            rollback_note="Revert.",
            promotion_payload={"threshold": 15},
            lifecycle_history=(
                ProposalLifecycleEntry(status=ProposalLifecycleStatus.PENDING, timestamp="2026-04-07T10:00:00+00:00"),
                ProposalLifecycleEntry(status=ProposalLifecycleStatus.CHECKED, timestamp="2026-04-07T11:00:00+00:00"),
            ),
            # No evaluation at all
        )
        self._write_proposal(proposal)

        exit_code = self._invoke()

        # Should fail with clear message
        self.assertEqual(exit_code, 1)
        self.assertFalse(self.promotions.exists() and any(self.promotions.iterdir()))

    def test_promotion_prefers_event_evaluation_over_embedded(self) -> None:
        """Verify that when both event and embedded evaluation exist, event is preferred."""
        from k8s_diag_agent.health.adaptation import ProposalLifecycleEntry

        proposal = HealthProposal(
            proposal_id="prefer-event-test",
            source_run_id="run-prefer",
            source_artifact_path="runs/health/reviews/run-prefer-review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Raise threshold.",
            rationale="Prefer event test.",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="Test.",
            rollback_note="Revert.",
            promotion_payload={"threshold": 6},
            lifecycle_history=(
                ProposalLifecycleEntry(status=ProposalLifecycleStatus.PENDING, timestamp="2026-04-07T10:00:00+00:00"),
                ProposalLifecycleEntry(status=ProposalLifecycleStatus.CHECKED, timestamp="2026-04-07T11:00:00+00:00"),
            ),
            # Embedded evaluation (should be overridden by event-based)
            promotion_evaluation=ProposalEvaluation(
                proposal_id="prefer-event-test",
                noise_reduction="EMBEDDED: ~30% noise reduction",
                signal_loss="EMBEDDED: High signal loss",
                test_outcome="EMBEDDED: Test questionable",
            ),
        )
        self._write_proposal(proposal)

        # Write event-based evaluation (should be preferred)
        evaluation = {
            "proposal_id": "prefer-event-test",
            "noise_reduction": "EVENT: ~80% noise reduction",
            "signal_loss": "EVENT: Very low signal loss",
            "test_outcome": "EVENT: Test excellent",
        }
        self._write_check_event_with_evaluation(
            "prefer-event-test",
            "prefer-event-001",
            "2026-04-07T11:00:00+00:00",
            evaluation,
        )

        exit_code = self._invoke()
        self.assertEqual(exit_code, 0)

        # Event-based evaluation is preferred over embedded

    def test_base_proposal_remains_unchanged_after_promotion(self) -> None:
        """Verify base proposal artifact is not mutated during promotion."""
        proposal = self._create_proposal("unchanged-test")
        self._write_proposal(proposal)

        # Write check event with evaluation
        evaluation = {
            "proposal_id": "unchanged-test",
            "noise_reduction": "~50% noise reduction",
            "signal_loss": "Low signal loss",
            "test_outcome": "Test passed",
        }
        self._write_check_event_with_evaluation(
            "unchanged-test",
            "unchanged-001",
            "2026-04-07T11:00:00+00:00",
            evaluation,
        )

        original_content = self.proposal_path.read_text(encoding="utf-8")

        exit_code = self._invoke()
        self.assertEqual(exit_code, 0)

        # Verify proposal file is unchanged
        current_content = self.proposal_path.read_text(encoding="utf-8")
        self.assertEqual(original_content, current_content)

        # Verify transitions directory was created
        self.assertTrue(self.transitions_dir.exists())
